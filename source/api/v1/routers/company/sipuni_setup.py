"""
Sipuni one-click setup endpoints

Automated setup: login to Sipuni dashboard, extract credentials, enable services, add webhook.
Manual fallback: admin provides cabinet_id + security_key directly.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import AppConfig
from db import get_session
from db.models.user import User
from db.models.company import Company
from db.models.sipuni_setup_config import SipuniSetupConfig
from db.models.enums import ProviderEnum
from utils.permissions import require_permissions, Permissions
from api.v1.schemas.sipuni_setup import (
    SipuniSetupRequest,
    SipuniManualSetupRequest,
    SipuniSetupStatusResponse,
    SipuniConfigResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sipuni", tags=["Sipuni Setup"])


def _get_webhook_url(company: Company) -> str:
    """Build the Sipuni webhook URL for a company."""
    base = AppConfig.BASE_URL.rstrip("/")
    return f"{base}/api/v1/company/webhooks/{company.webhook_token}"


def _mask_key(key: str) -> str:
    """Mask a security key for display (show first 4 chars)."""
    if not key or len(key) <= 4:
        return "***"
    return key[:4] + "***"


def _build_status_response(
    config: SipuniSetupConfig | None,
    company: Company,
) -> SipuniSetupStatusResponse:
    """Build a status response from config + company."""
    provider_config = company.provider_config or {}
    cabinet_id = provider_config.get("cabinet_id")
    is_connected = bool(cabinet_id and provider_config.get("security_key"))

    return SipuniSetupStatusResponse(
        setup_status=config.setup_status if config else "not_started",
        setup_error=config.setup_error if config else None,
        setup_method=config.setup_method if config else None,
        is_connected=is_connected,
        cabinet_id=cabinet_id,
        webhook_url=_get_webhook_url(company) if is_connected else None,
    )


async def _require_sipuni_company(
    user: User, session: AsyncSession
) -> Company:
    """Load the user's company and verify it's a Sipuni provider."""
    company = await Company.get(session=session, id=user.company_id)
    if not company:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Company not found")
    if company.provider_type != ProviderEnum.SIPUNI:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Company does not use Sipuni provider",
        )
    return company


# ── Endpoints ────────────────────────────────────────────────────

@router.post("/setup", response_model=SipuniSetupStatusResponse)
@require_permissions(Permissions.SETTINGS_MANAGE)
async def setup_sipuni(
    data: SipuniSetupRequest,
    background_tasks: BackgroundTasks,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session),
):
    """Start automated Sipuni setup.

    Logs into Sipuni dashboard, extracts credentials, enables services,
    adds webhook. Runs in background — poll GET /setup/status for progress.
    """
    company = await _require_sipuni_company(user, session)

    # Get or create config
    config = await SipuniSetupConfig.get(
        session=session, company_id=company.id
    )
    if not config:
        config = await SipuniSetupConfig.create(
            session=session, company_id=company.id
        )

    if config.setup_status == "setting_up":
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="Setup already in progress"
        )

    # Mark as setting_up
    config.setup_status = "setting_up"
    config.setup_error = None
    await config.update(session=session)

    webhook_url = _get_webhook_url(company)

    # Launch background task — password passed in-memory, never stored
    background_tasks.add_task(
        _run_sipuni_setup,
        company_id=company.id,
        email=data.email,
        password=data.password,
        webhook_url=webhook_url,
    )

    return _build_status_response(config, company)


@router.get("/setup/status", response_model=SipuniSetupStatusResponse)
@require_permissions(Permissions.SETTINGS_READ)
async def get_setup_status(
    user: User = User.current(),
    session: AsyncSession = Depends(get_session),
):
    """Poll for Sipuni setup progress."""
    company = await _require_sipuni_company(user, session)
    config = await SipuniSetupConfig.get(
        session=session, company_id=company.id
    )
    return _build_status_response(config, company)


@router.post("/setup/manual", response_model=SipuniSetupStatusResponse)
@require_permissions(Permissions.SETTINGS_MANAGE)
async def manual_setup(
    data: SipuniManualSetupRequest,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session),
):
    """Manual setup — admin provides cabinet_id and security_key directly."""
    company = await _require_sipuni_company(user, session)

    # Update provider_config
    company.provider_config = {
        "cabinet_id": data.cabinet_id,
        "security_key": data.security_key,
    }
    await company.update(session=session)

    # Get or create config
    config = await SipuniSetupConfig.get(
        session=session, company_id=company.id
    )
    if not config:
        config = await SipuniSetupConfig.create(
            session=session,
            company_id=company.id,
            setup_status="ready",
            setup_method="manual",
        )
    else:
        config.setup_status = "ready"
        config.setup_method = "manual"
        config.setup_error = None
        await config.update(session=session)

    return _build_status_response(config, company)


@router.get("/config", response_model=SipuniConfigResponse)
@require_permissions(Permissions.SETTINGS_READ)
async def get_sipuni_config(
    user: User = User.current(),
    session: AsyncSession = Depends(get_session),
):
    """Get current Sipuni connection configuration."""
    company = await _require_sipuni_company(user, session)
    config = await SipuniSetupConfig.get(
        session=session, company_id=company.id
    )

    provider_config = company.provider_config or {}
    cabinet_id = provider_config.get("cabinet_id")
    security_key = provider_config.get("security_key", "")
    is_connected = bool(cabinet_id and security_key)

    return SipuniConfigResponse(
        is_connected=is_connected,
        cabinet_id=cabinet_id,
        security_key_masked=_mask_key(security_key) if security_key else None,
        webhook_url=_get_webhook_url(company) if is_connected else None,
        setup_status=config.setup_status if config else "not_started",
        setup_method=config.setup_method if config else None,
        services_enabled=config.services_enabled if config else None,
    )


@router.post("/disconnect", response_model=SipuniSetupStatusResponse)
@require_permissions(Permissions.SETTINGS_MANAGE)
async def disconnect_sipuni(
    user: User = User.current(),
    session: AsyncSession = Depends(get_session),
):
    """Disconnect Sipuni. Clears provider_config, resets setup status.

    Does NOT remove webhook from Sipuni (would need password again).
    """
    company = await _require_sipuni_company(user, session)

    # Clear provider_config
    company.provider_config = {}
    await company.update(session=session)

    # Reset setup config
    config = await SipuniSetupConfig.get(
        session=session, company_id=company.id
    )
    if config:
        config.setup_status = "not_started"
        config.setup_error = None
        config.setup_method = None
        config.services_enabled = None
        await config.update(session=session)

    return _build_status_response(config, company)


# ── Background Task ──────────────────────────────────────────────

async def _run_sipuni_setup(
    company_id, email: str, password: str, webhook_url: str
):
    """Background task: login to Sipuni, extract creds, enable services, add webhook."""
    from utils.services.sipuni_client import (
        SipuniAsyncClient,
        SipuniSetupError,
    )
    from db import async_session_factory

    async with async_session_factory() as session:
        client = SipuniAsyncClient()
        try:
            creds = await client.full_setup(email, password, webhook_url)

            # Update company.provider_config
            company = await Company.get(session=session, id=company_id)
            if not company:
                return

            company.provider_config = {
                "cabinet_id": creds["user_id"],
                "security_key": creds["secret_key"],
            }
            await company.update(session=session)

            # Update setup config
            config = await SipuniSetupConfig.get(
                session=session, company_id=company_id
            )
            if config:
                config.setup_status = "ready"
                config.setup_method = "auto"
                config.setup_error = None
                config.services_enabled = {"stream": True, "callback": True}
                await config.update(session=session)

            logger.info("Sipuni setup complete for company %s", company_id)

        except SipuniSetupError as e:
            logger.warning(
                "Sipuni setup failed for company %s: %s", company_id, e
            )
            try:
                config = await SipuniSetupConfig.get(
                    session=session, company_id=company_id
                )
                if config:
                    config.setup_status = "failed"
                    config.setup_error = str(e)[:500]
                    await config.update(session=session)
            except Exception:
                logger.exception("Failed to update setup_error")

        except Exception as e:
            logger.exception(
                "Sipuni setup failed unexpectedly for company %s", company_id
            )
            try:
                config = await SipuniSetupConfig.get(
                    session=session, company_id=company_id
                )
                if config:
                    config.setup_status = "failed"
                    config.setup_error = str(e)[:500]
                    await config.update(session=session)
            except Exception:
                logger.exception("Failed to update setup_error")

        finally:
            await client.close()
