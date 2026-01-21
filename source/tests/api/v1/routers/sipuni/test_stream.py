import uuid
import time
from unittest.mock import patch

import pytest
from httpx import AsyncClient


class TestStream:
    """Tests for the /api/v1/sipuni/stream/{id} endpoint."""

    @patch.dict("os.environ", {"ALLOWED_IPS": "testclient;127.0.0.1"})
    async def test_stream_hangup_event_success(
        self, client: AsyncClient, test_sipuni, test_session
    ):
        """Test successful hangup event processing."""
        current_timestamp = int(time.time())
        call_start_timestamp = current_timestamp - 300  # 5 minutes ago

        # Build query params for hangup event
        params = {
            "event": "2",  # Hangup event
            "call_id": f"test-call-{uuid.uuid4()}",
            "call_record_link": "https://example.com/record.mp3",
            "status": "ANSWER",
            "short_dst_num": "100",
            "short_src_num": "200",
            "dst_type": "1",
            "src_num": "998901234567",
            "src_type": "1",
            "last_called": "operator1",
            "call_start_timestamp": str(call_start_timestamp),
            "timestamp": str(current_timestamp),
        }

        response = await client.get(
            f"/api/v1/sipuni/stream/{test_sipuni.id}/",
            params=params,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    @patch.dict("os.environ", {"ALLOWED_IPS": "testclient;127.0.0.1"})
    async def test_stream_non_hangup_event(
        self, client: AsyncClient, test_sipuni
    ):
        """Test non-hangup event (event != 2) is handled gracefully."""
        params = {
            "event": "1",  # Not a hangup event
            "call_id": f"test-call-{uuid.uuid4()}",
        }

        response = await client.get(
            f"/api/v1/sipuni/stream/{test_sipuni.id}/",
            params=params,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    @patch.dict("os.environ", {"ALLOWED_IPS": "testclient;127.0.0.1"})
    async def test_stream_invalid_sipuni_id(self, client: AsyncClient):
        """Test stream with invalid Sipuni ID fails."""
        random_id = uuid.uuid4()

        response = await client.get(
            f"/api/v1/sipuni/stream/{random_id}/",
            params={"event": "1"},
        )
        assert response.status_code == 404

    @patch.dict("os.environ", {"ALLOWED_IPS": "192.168.1.1"})
    async def test_stream_forbidden_ip(self, client: AsyncClient, test_sipuni):
        """Test stream from non-allowed IP is forbidden."""
        response = await client.get(
            f"/api/v1/sipuni/stream/{test_sipuni.id}/",
            params={"event": "1"},
        )
        assert response.status_code == 403
        assert "Forbidden IP" in response.json()["detail"]

    @patch.dict("os.environ", {"ALLOWED_IPS": "testclient;127.0.0.1"})
    async def test_stream_hangup_with_noanswer_status(
        self, client: AsyncClient, test_sipuni
    ):
        """Test hangup event with NOANSWER status."""
        current_timestamp = int(time.time())
        call_start_timestamp = current_timestamp - 30

        params = {
            "event": "2",
            "call_id": f"test-call-{uuid.uuid4()}",
            "call_record_link": "",
            "status": "NOANSWER",
            "short_dst_num": "100",
            "short_src_num": "200",
            "dst_type": "1",
            "src_num": "998901234567",
            "src_type": "2",  # Internal call
            "last_called": "operator2",
            "call_start_timestamp": str(call_start_timestamp),
            "timestamp": str(current_timestamp),
        }

        response = await client.get(
            f"/api/v1/sipuni/stream/{test_sipuni.id}/",
            params=params,
        )
        assert response.status_code == 200

    @patch.dict("os.environ", {"ALLOWED_IPS": "testclient;127.0.0.1"})
    async def test_stream_hangup_with_optional_fields(
        self, client: AsyncClient, test_sipuni
    ):
        """Test hangup event with optional fields."""
        current_timestamp = int(time.time())
        call_start_timestamp = current_timestamp - 120

        params = {
            "event": "2",
            "call_id": f"test-call-{uuid.uuid4()}",
            "call_record_link": "https://example.com/record.mp3",
            "status": "ANSWER",
            "pbxdstnum": "12345",
            "short_dst_num": "100",
            "short_src_num": "200",
            "dst_num": "998901111111",
            "dst_type": "1",
            "src_num": "998902222222",
            "src_type": "1",
            "last_called": "operator3",
            "transfer_from": "operator1",
            "treeName": "main_tree",
            "treeNumber": "5",
            "user_id": "user123",
            "call_start_timestamp": str(call_start_timestamp),
            "timestamp": str(current_timestamp),
        }

        response = await client.get(
            f"/api/v1/sipuni/stream/{test_sipuni.id}/",
            params=params,
        )
        assert response.status_code == 200

    @patch.dict("os.environ", {"ALLOWED_IPS": "testclient;127.0.0.1"})
    async def test_stream_no_event_parameter(
        self, client: AsyncClient, test_sipuni
    ):
        """Test stream without event parameter."""
        response = await client.get(
            f"/api/v1/sipuni/stream/{test_sipuni.id}/",
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    @patch.dict("os.environ", {"ALLOWED_IPS": "testclient;127.0.0.1"})
    async def test_stream_invalid_uuid_format(self, client: AsyncClient):
        """Test stream with invalid UUID format."""
        response = await client.get(
            "/api/v1/sipuni/stream/invalid-uuid/",
            params={"event": "1"},
        )
        assert response.status_code == 422
