import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from httpx import AsyncClient


class TestInternalCall:
    """Tests for the /api/v1/sipuni/internal_call endpoint."""

    @patch("api.v1.routers.sipuni.call.SipuniApiSimulator.call_number")
    async def test_internal_call_success(
        self, mock_call_number, client: AsyncClient, test_sipuni
    ):
        """Test successful internal call."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"success": True, "call_id": "test-call-123"}
        mock_call_number.return_value = mock_response

        response = await client.post(
            "/api/v1/sipuni/internal_call",
            json={
                "token": test_sipuni.token,
                "phone": "998901234567",
                "sip_number": "100",
                "reverse": False,
                "antiaon": False,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["call_id"] == "test-call-123"

        mock_call_number.assert_called_once()

    async def test_internal_call_invalid_token(self, client: AsyncClient):
        """Test internal call with invalid token fails."""
        invalid_token = "x" * 64

        response = await client.post(
            "/api/v1/sipuni/internal_call",
            json={
                "token": invalid_token,
                "phone": "998901234567",
                "sip_number": "100",
                "reverse": False,
                "antiaon": False,
            },
        )
        assert response.status_code == 404

    async def test_internal_call_invalid_phone(self, client: AsyncClient, test_sipuni):
        """Test internal call with invalid phone number fails."""
        response = await client.post(
            "/api/v1/sipuni/internal_call",
            json={
                "token": test_sipuni.token,
                "phone": "invalid-phone",
                "sip_number": "100",
                "reverse": False,
                "antiaon": False,
            },
        )
        assert response.status_code == 422

    async def test_internal_call_short_token(self, client: AsyncClient):
        """Test internal call with short token fails validation."""
        response = await client.post(
            "/api/v1/sipuni/internal_call",
            json={
                "token": "short",
                "phone": "998901234567",
                "sip_number": "100",
                "reverse": False,
                "antiaon": False,
            },
        )
        assert response.status_code == 422

    async def test_internal_call_missing_fields(self, client: AsyncClient, test_sipuni):
        """Test internal call with missing required fields fails."""
        response = await client.post(
            "/api/v1/sipuni/internal_call",
            json={
                "token": test_sipuni.token,
                "phone": "998901234567",
            },
        )
        assert response.status_code == 422


class TestExternalCall:
    """Tests for the /api/v1/sipuni/external_call endpoint."""

    @patch("api.v1.routers.sipuni.call.SipuniApiSimulator.external_call")
    async def test_external_call_success(
        self, mock_external_call, client: AsyncClient, test_sipuni
    ):
        """Test successful external call."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "success": True,
            "call_id": "ext-call-456",
        }
        mock_external_call.return_value = mock_response

        response = await client.post(
            "/api/v1/sipuni/external_call",
            json={
                "token": test_sipuni.token,
                "phone1": "998901234567",
                "phone2": "998937654321",
                "bridge_start": "201",
                "bridge_end": "202",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["call_id"] == "ext-call-456"

        mock_external_call.assert_called_once()

    @patch("api.v1.routers.sipuni.call.SipuniApiSimulator.external_call")
    async def test_external_call_default_bridges(
        self, mock_external_call, client: AsyncClient, test_sipuni
    ):
        """Test external call with default bridge values."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"success": True}
        mock_external_call.return_value = mock_response

        response = await client.post(
            "/api/v1/sipuni/external_call",
            json={
                "token": test_sipuni.token,
                "phone1": "998901234567",
                "phone2": "998937654321",
            },
        )
        assert response.status_code == 200

    async def test_external_call_invalid_token(self, client: AsyncClient):
        """Test external call with invalid token fails."""
        invalid_token = "y" * 64

        response = await client.post(
            "/api/v1/sipuni/external_call",
            json={
                "token": invalid_token,
                "phone1": "998901234567",
                "phone2": "998937654321",
            },
        )
        assert response.status_code == 404

    async def test_external_call_invalid_phone1(self, client: AsyncClient, test_sipuni):
        """Test external call with invalid phone1 fails."""
        response = await client.post(
            "/api/v1/sipuni/external_call",
            json={
                "token": test_sipuni.token,
                "phone1": "invalid",
                "phone2": "998937654321",
            },
        )
        assert response.status_code == 422

    async def test_external_call_invalid_phone2(self, client: AsyncClient, test_sipuni):
        """Test external call with invalid phone2 fails."""
        response = await client.post(
            "/api/v1/sipuni/external_call",
            json={
                "token": test_sipuni.token,
                "phone1": "998901234567",
                "phone2": "invalid",
            },
        )
        assert response.status_code == 422


class TestCallTree:
    """Tests for the /api/v1/sipuni/call_tree endpoint."""

    @patch("api.v1.routers.sipuni.call.SipuniApiSimulator.call_tree")
    async def test_call_tree_success(
        self, mock_call_tree, client: AsyncClient, test_sipuni
    ):
        """Test successful call tree."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "success": True,
            "call_id": "tree-call-789",
        }
        mock_call_tree.return_value = mock_response

        response = await client.post(
            "/api/v1/sipuni/call_tree",
            json={
                "token": test_sipuni.token,
                "phone": "998901234567",
                "sip_number": "100",
                "tree": "main_tree",
                "reverse": False,
                "attempt_duration": 60,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["call_id"] == "tree-call-789"

        mock_call_tree.assert_called_once()

    @patch("api.v1.routers.sipuni.call.SipuniApiSimulator.call_tree")
    async def test_call_tree_default_duration(
        self, mock_call_tree, client: AsyncClient, test_sipuni
    ):
        """Test call tree with default attempt duration."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"success": True}
        mock_call_tree.return_value = mock_response

        response = await client.post(
            "/api/v1/sipuni/call_tree",
            json={
                "token": test_sipuni.token,
                "phone": "998901234567",
                "sip_number": "100",
                "tree": "main_tree",
                "reverse": False,
            },
        )
        assert response.status_code == 200

    async def test_call_tree_invalid_token(self, client: AsyncClient):
        """Test call tree with invalid token fails."""
        invalid_token = "z" * 64

        response = await client.post(
            "/api/v1/sipuni/call_tree",
            json={
                "token": invalid_token,
                "phone": "998901234567",
                "sip_number": "100",
                "tree": "main_tree",
                "reverse": False,
            },
        )
        assert response.status_code == 404

    async def test_call_tree_invalid_phone(self, client: AsyncClient, test_sipuni):
        """Test call tree with invalid phone number fails."""
        response = await client.post(
            "/api/v1/sipuni/call_tree",
            json={
                "token": test_sipuni.token,
                "phone": "invalid-phone",
                "sip_number": "100",
                "tree": "main_tree",
                "reverse": False,
            },
        )
        assert response.status_code == 422

    async def test_call_tree_short_duration(self, client: AsyncClient, test_sipuni):
        """Test call tree with too short attempt duration fails."""
        response = await client.post(
            "/api/v1/sipuni/call_tree",
            json={
                "token": test_sipuni.token,
                "phone": "998901234567",
                "sip_number": "100",
                "tree": "main_tree",
                "reverse": False,
                "attempt_duration": 10,  # Less than minimum 30
            },
        )
        assert response.status_code == 422

    async def test_call_tree_missing_fields(self, client: AsyncClient, test_sipuni):
        """Test call tree with missing required fields fails."""
        response = await client.post(
            "/api/v1/sipuni/call_tree",
            json={
                "token": test_sipuni.token,
                "phone": "998901234567",
            },
        )
        assert response.status_code == 422
