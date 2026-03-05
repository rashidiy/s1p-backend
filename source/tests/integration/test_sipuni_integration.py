"""
Integration tests for Sipuni telephony provider.

These tests call the real Sipuni API and require the following env variables:
  SIPUNI_CABINET_ID   — Sipuni account (cabinet) number
  SIPUNI_SECURITY_KEY — API secret key
  SIPUNI_SIPNUMBER    — Internal SIP extension to use (e.g. "100001")
  SIPUNI_TEST_PHONE   — External phone number for test calls

Tests are automatically skipped when the env variables are not set.
"""

import os
import hashlib
import asyncio

import pytest

from utils.services.telephony.sipuni_provider import SipuniProvider
from utils.services.telephony.base import CallRequest, ProviderException


CABINET_ID = os.environ.get("SIPUNI_CABINET_ID")
SECURITY_KEY = os.environ.get("SIPUNI_SECURITY_KEY")
SIPNUMBER = os.environ.get("SIPUNI_SIPNUMBER")
TEST_PHONE = os.environ.get("SIPUNI_TEST_PHONE")

requires_sipuni = pytest.mark.skipif(
    not all([CABINET_ID, SECURITY_KEY, SIPNUMBER, TEST_PHONE]),
    reason="SIPUNI_CABINET_ID, SIPUNI_SECURITY_KEY, SIPUNI_SIPNUMBER, and SIPUNI_TEST_PHONE env vars required",
)


def _make_provider() -> SipuniProvider:
    return SipuniProvider(
        config={
            "cabinet_id": CABINET_ID,
            "security_key": SECURITY_KEY,
        }
    )


class TestHashGeneration:
    """Verify MD5 hash computation matches expected values."""

    def test_hash_simple(self):
        provider = SipuniProvider(
            config={"cabinet_id": "12345", "security_key": "mysecret"}
        )
        result = provider._generate_hash("a", "b", "c")
        expected = hashlib.md5("a+b+c+mysecret".encode()).hexdigest()
        assert result == expected

    def test_hash_single_param(self):
        provider = SipuniProvider(
            config={"cabinet_id": "12345", "security_key": "key123"}
        )
        result = provider._generate_hash("only")
        expected = hashlib.md5("only+key123".encode()).hexdigest()
        assert result == expected

    def test_hash_call_external_order(self):
        """Hash params for call_external: phoneFrom + phoneTo + sipnumber + sipnumber2 + user + secret."""
        provider = SipuniProvider(
            config={"cabinet_id": "99999", "security_key": "sec"}
        )
        result = provider._generate_hash(
            "79001234567", "79007654321", "100", "100", "99999"
        )
        raw = "79001234567+79007654321+100+100+99999+sec"
        expected = hashlib.md5(raw.encode()).hexdigest()
        assert result == expected

    def test_hash_cancel_order(self):
        """Hash params for cancel: callbackId + user + secret."""
        provider = SipuniProvider(
            config={"cabinet_id": "99999", "security_key": "sec"}
        )
        result = provider._generate_hash("cb-123", "99999")
        raw = "cb-123+99999+sec"
        expected = hashlib.md5(raw.encode()).hexdigest()
        assert result == expected


@requires_sipuni
class TestMakeCall:
    """Test call initiation against the real Sipuni API."""

    @pytest.mark.asyncio
    async def test_make_call(self):
        provider = _make_provider()
        request = CallRequest(
            phone_1=TEST_PHONE,
            phone_2=TEST_PHONE,
            operator_id=SIPNUMBER,
        )
        response = await provider.make_call(request)
        assert response.success is True
        assert response.call_id, "Expected a callID in the response"

    @pytest.mark.asyncio
    async def test_make_call_requires_operator_id(self):
        provider = _make_provider()
        request = CallRequest(
            phone_1=TEST_PHONE,
            phone_2=TEST_PHONE,
        )
        with pytest.raises(ProviderException, match="operator_id"):
            await provider.make_call(request)


@requires_sipuni
class TestCancelCall:
    """Test call cancellation against the real Sipuni API."""

    @pytest.mark.asyncio
    async def test_cancel_call(self):
        provider = _make_provider()

        # First, initiate a call
        request = CallRequest(
            phone_1=TEST_PHONE,
            phone_2=TEST_PHONE,
            operator_id=SIPNUMBER,
        )
        make_response = await provider.make_call(request)
        assert make_response.success is True
        assert make_response.call_id

        # Brief delay to let the call register
        await asyncio.sleep(1)

        # Cancel it
        cancel_response = await provider.cancel_call(make_response.call_id)
        assert cancel_response.call_id == make_response.call_id


@requires_sipuni
class TestCallNumber:
    """Test call_number API against the real Sipuni API."""

    @pytest.mark.asyncio
    async def test_call_number(self):
        provider = _make_provider()
        response = await provider.call_number(
            phone=TEST_PHONE,
            sipnumber=SIPNUMBER,
        )
        assert response.success is True
        assert response.call_id, "Expected a callID in the response"
