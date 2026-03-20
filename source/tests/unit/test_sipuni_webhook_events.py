"""
Unit tests for Sipuni webhook event handling (events 1-4).

Tests the SipuniProvider.handle_webhook() method for all 4 event types
and the terminal state protection logic in the webhook handler.
"""

import pytest
from utils.services.telephony.sipuni_provider import SipuniProvider


def _make_provider() -> SipuniProvider:
    return SipuniProvider(config={
        "cabinet_id": "018315",
        "security_key": "testsecret",
    })


class TestEvent1CallStart:
    """Event 1: Call initiated — RINGING state."""

    @pytest.mark.asyncio
    async def test_returns_ringing_state(self):
        provider = _make_provider()
        result = await provider.handle_webhook({
            "event": "1",
            "call_id": "abc123",
            "src_num": "79991234567",
            "dst_num": "018315201",
            "src_type": "1",
            "dst_type": "2",
            "timestamp": "1710000000",
            "treeName": "Входящая",
            "treeNumber": "000-913898",
        }, {})

        assert result is not None
        assert result["_event_type"] == "call_started"
        assert result["state"] == "RINGING"
        assert result["provider_call_id"] == "sipuni_abc123"
        assert result["direction"] == "inbound"
        assert result["call_start_timestamp"] == 1710000000
        assert result["scheme_name"] == "Входящая"
        assert result["scheme_number"] == "000-913898"

    @pytest.mark.asyncio
    async def test_strips_cabinet_prefix_from_src(self):
        provider = _make_provider()
        result = await provider.handle_webhook({
            "event": "1",
            "call_id": "abc123",
            "src_num": "018315201",
            "dst_num": "79991234567",
            "src_type": "2",
            "dst_type": "1",
            "timestamp": "1710000000",
        }, {})

        assert result["phone_1"] == "201"
        assert result["direction"] == "outbound"


class TestEvent2Hangup:
    """Event 2: Call ended — final state with recording."""

    @pytest.mark.asyncio
    async def test_returns_final_state(self):
        provider = _make_provider()
        result = await provider.handle_webhook({
            "event": "2",
            "call_id": "abc123",
            "src_num": "79991234567",
            "dst_num": "018315201",
            "src_type": "1",
            "dst_type": "2",
            "status": "ANSWER",
            "call_start_timestamp": "1710000000",
            "timestamp": "1710000120",
            "call_answer_timestamp": "1710000005",
            "call_record_link": "https://rec.sipuni.com/abc.mp3",
            "treeName": "Входящая",
            "transfer_from": "",
            "last_called": "201",
        }, {})

        assert result["_event_type"] == "call_ended"
        assert result["state"] == "ANSWER"
        assert result["call_start_timestamp"] == 1710000000
        assert result["call_end_timestamp"] == 1710000120
        assert result["call_answer_timestamp"] == 1710000005
        assert result["record_url"] == "https://rec.sipuni.com/abc.mp3"
        assert result["last_called"] == "201"
        assert result["transfer_from"] is None  # empty string → None

    @pytest.mark.asyncio
    async def test_zero_answer_timestamp_becomes_none(self):
        provider = _make_provider()
        result = await provider.handle_webhook({
            "event": "2",
            "call_id": "abc123",
            "src_num": "79991234567",
            "dst_num": "201",
            "status": "NOANSWER",
            "call_start_timestamp": "1710000000",
            "timestamp": "1710000030",
            "call_answer_timestamp": "0",
        }, {})

        assert result["call_answer_timestamp"] is None
        assert result["state"] == "NOANSWER"

    @pytest.mark.asyncio
    async def test_uses_callback_id_over_call_id(self):
        provider = _make_provider()
        result = await provider.handle_webhook({
            "event": "2",
            "call_id": "abc123",
            "callbackId": "cb_456",
            "src_num": "201",
            "dst_num": "79991234567",
            "status": "ANSWER",
            "timestamp": "1710000120",
        }, {})

        assert result["provider_call_id"] == "sipuni_cb_456"


class TestEvent3Answer:
    """Event 3: Call answered — answer timestamp only."""

    @pytest.mark.asyncio
    async def test_returns_answer_timestamp(self):
        provider = _make_provider()
        result = await provider.handle_webhook({
            "event": "3",
            "call_id": "abc123",
            "src_num": "79991234567",
            "dst_num": "018315201",
            "src_type": "1",
            "dst_type": "2",
            "timestamp": "1710000005",
        }, {})

        assert result["_event_type"] == "call_answered"
        assert result["call_answer_timestamp"] == 1710000005
        assert "state" not in result  # Should not set state

    @pytest.mark.asyncio
    async def test_no_state_field(self):
        """Event 3 must not include 'state' to avoid overwriting RINGING."""
        provider = _make_provider()
        result = await provider.handle_webhook({
            "event": "3",
            "call_id": "abc123",
            "src_num": "79991234567",
            "dst_num": "201",
            "timestamp": "1710000005",
        }, {})

        assert "state" not in result


class TestEvent4TransferHangup:
    """Event 4: Transfer hang-up — marks transfer."""

    @pytest.mark.asyncio
    async def test_returns_transfer_info(self):
        provider = _make_provider()
        result = await provider.handle_webhook({
            "event": "4",
            "call_id": "abc123",
            "src_num": "79991234567",
            "dst_num": "018315202",
            "src_type": "1",
            "dst_type": "2",
            "status": "ANSWER",
            "call_start_timestamp": "1710000000",
            "timestamp": "1710000060",
            "call_answer_timestamp": "1710000005",
            "call_record_link": "https://rec.sipuni.com/abc.mp3",
            "transfer_from": "201",
            "last_called": "202",
        }, {})

        assert result["_event_type"] == "call_transferred"
        assert result["is_transfer"] is True
        assert result["transfer_from"] == "201"
        assert result["last_called"] == "202"
        assert result["state"] == "ANSWER"


class TestUnknownEvent:
    """Unknown event types return None."""

    @pytest.mark.asyncio
    async def test_unknown_event_returns_none(self):
        provider = _make_provider()
        result = await provider.handle_webhook({
            "event": "5",
            "call_id": "abc123",
        }, {})
        assert result is None

    @pytest.mark.asyncio
    async def test_missing_event_returns_none(self):
        provider = _make_provider()
        result = await provider.handle_webhook({
            "call_id": "abc123",
        }, {})
        assert result is None


class TestDirectionDetection:
    """Direction detection from src_type/dst_type."""

    @pytest.mark.asyncio
    async def test_inbound(self):
        provider = _make_provider()
        result = await provider.handle_webhook({
            "event": "1", "call_id": "x",
            "src_num": "7999", "dst_num": "201",
            "src_type": "1", "dst_type": "2",
            "timestamp": "1",
        }, {})
        assert result["direction"] == "inbound"

    @pytest.mark.asyncio
    async def test_outbound(self):
        provider = _make_provider()
        result = await provider.handle_webhook({
            "event": "1", "call_id": "x",
            "src_num": "201", "dst_num": "7999",
            "src_type": "2", "dst_type": "1",
            "timestamp": "1",
        }, {})
        assert result["direction"] == "outbound"

    @pytest.mark.asyncio
    async def test_internal(self):
        provider = _make_provider()
        result = await provider.handle_webhook({
            "event": "1", "call_id": "x",
            "src_num": "201", "dst_num": "202",
            "src_type": "2", "dst_type": "2",
            "timestamp": "1",
        }, {})
        assert result["direction"] == "internal"
