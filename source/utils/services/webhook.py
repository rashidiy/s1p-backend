"""
Outbound webhook delivery service

Handles event dispatching, HMAC signing, delivery with retry.
"""

import asyncio
import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any
from uuid import UUID

import aiohttp
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from db.base import AsyncDatabaseSession
from db.models.webhook import WebhookEndpoint, WebhookDelivery

logger = logging.getLogger(__name__)

# Retry delays in seconds: 10s, 60s, 300s
RETRY_DELAYS = [10, 60, 300]
MAX_ATTEMPTS = 3
DELIVERY_TIMEOUT = 10  # seconds


def sign_payload(payload_bytes: bytes, secret: str) -> str:
    """Generate HMAC-SHA256 signature for webhook payload."""
    return hmac.new(
        secret.encode("utf-8"),
        payload_bytes,
        hashlib.sha256
    ).hexdigest()


def _json_serializer(obj: Any) -> Any:
    """JSON serializer for objects not serializable by default."""
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


async def _deliver(endpoint: WebhookEndpoint, delivery_id: UUID, payload_bytes: bytes, signature: str) -> tuple[int | None, str | None]:
    """
    Make HTTP POST to the webhook URL.

    Returns (status_code, response_body) or (None, error_message) on failure.
    """
    try:
        timeout = aiohttp.ClientTimeout(total=DELIVERY_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                endpoint.url,
                data=payload_bytes,
                headers={
                    "Content-Type": "application/json",
                    "X-Webhook-Signature": signature,
                    "User-Agent": "S1P-Webhooks/1.0",
                },
            ) as response:
                body = await response.text()
                # Truncate response body to 1KB for storage
                return response.status, body[:1024]
    except asyncio.TimeoutError:
        return None, "Request timed out"
    except aiohttp.ClientError as e:
        return None, str(e)[:1024]
    except Exception as e:
        logger.error(f"Webhook delivery error for endpoint {endpoint.id}: {e}")
        return None, str(e)[:1024]


async def _process_delivery(delivery_id: UUID, endpoint_url: str, endpoint_secret: str, endpoint_id: UUID):
    """
    Process a single delivery attempt with retries.

    Runs as a background task — creates its own DB session.
    """
    session_factory = AsyncDatabaseSession()

    for attempt in range(MAX_ATTEMPTS):
        # Wait for retry delay (skip on first attempt)
        if attempt > 0:
            delay = RETRY_DELAYS[attempt - 1] if attempt - 1 < len(RETRY_DELAYS) else RETRY_DELAYS[-1]
            await asyncio.sleep(delay)

        async for session in session_factory():
            try:
                # Re-fetch delivery to get current state
                delivery = await session.get(WebhookDelivery, delivery_id)
                if not delivery:
                    return

                # Re-fetch endpoint to check if still active
                endpoint = await session.get(WebhookEndpoint, endpoint_id)
                if not endpoint or not endpoint.is_active:
                    delivery.status = "failed"
                    delivery.response_body = "Endpoint deactivated or deleted"
                    await session.commit()
                    return

                # Build payload bytes and signature
                payload_bytes = json.dumps(delivery.payload, default=_json_serializer).encode("utf-8")
                signature = sign_payload(payload_bytes, endpoint.secret)

                # Attempt delivery
                status_code, response_body = await _deliver(endpoint, delivery_id, payload_bytes, signature)

                # Update delivery record
                delivery.attempts = attempt + 1
                delivery.last_attempt_at = datetime.now(timezone.utc)
                delivery.response_code = status_code
                delivery.response_body = response_body

                if status_code and 200 <= status_code < 300:
                    delivery.status = "success"
                    delivery.next_retry_at = None
                    await session.commit()
                    return
                elif attempt < MAX_ATTEMPTS - 1:
                    # Schedule next retry
                    delay = RETRY_DELAYS[attempt] if attempt < len(RETRY_DELAYS) else RETRY_DELAYS[-1]
                    delivery.next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
                    delivery.status = "pending"
                    await session.commit()
                else:
                    # Final attempt failed
                    delivery.status = "failed"
                    delivery.next_retry_at = None
                    await session.commit()
                    return

            except Exception as e:
                logger.error(f"Webhook delivery processing error: {e}", exc_info=True)
                await session.rollback()
                return


async def fire_webhook_event(
    company_id: UUID,
    event_type: str,
    data: dict,
    session: AsyncSession,
):
    """
    Fire a webhook event for a company.

    Finds all active endpoints subscribed to this event type,
    creates delivery records, and dispatches delivery tasks.

    Args:
        company_id: Company that triggered the event
        event_type: Event type string (e.g., "lead.created")
        data: Event payload data
        session: Current database session
    """
    # Find all active endpoints for this company that subscribe to this event
    query = select(WebhookEndpoint).where(
        and_(
            WebhookEndpoint.company_id == company_id,
            WebhookEndpoint.is_active.is_(True),
        )
    )
    result = await session.execute(query)
    endpoints = result.scalars().all()

    if not endpoints:
        return

    # Filter endpoints that subscribe to this event type
    matching_endpoints = [
        ep for ep in endpoints
        if event_type in (ep.events or [])
    ]

    if not matching_endpoints:
        return

    # Build the full payload
    now = datetime.now(timezone.utc)
    payload = {
        "event": event_type,
        "timestamp": now.isoformat(),
        "data": data,
    }

    # Create delivery records and dispatch
    for endpoint in matching_endpoints:
        delivery = WebhookDelivery(
            endpoint_id=endpoint.id,
            event_type=event_type,
            payload=payload,
            status="pending",
            attempts=0,
        )
        session.add(delivery)
        await session.flush()

        # Dispatch delivery in background (non-blocking)
        asyncio.create_task(
            _process_delivery(
                delivery_id=delivery.id,
                endpoint_url=endpoint.url,
                endpoint_secret=endpoint.secret,
                endpoint_id=endpoint.id,
            )
        )
