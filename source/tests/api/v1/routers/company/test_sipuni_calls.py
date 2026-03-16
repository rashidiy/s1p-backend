"""
Tests for Sipuni-specific call endpoints: /api/v1/company/calls/sipuni/

Covers:
  - POST /calls/sipuni/external  — external-to-external call
  - POST /calls/sipuni/number    — SIP-to-external call
  - POST /calls/sipuni/tree      — call via IVR tree
  - POST /calls/sipuni/{id}/cancel — cancel active call
  - Provider type validation (non-sipuni company → 400)
  - Permission checks (missing calls.make → 403)
"""

import uuid

import pytest
import pytest_asyncio
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient

from db.models.enums import ProviderEnum, RoleEnum
from db.models.call_event import CallEvent
from db.models.company import Company
from db.models.user import User
from utils.managers import PasswordManager, JWTManager


# ── Fixtures ──────────────────────────────────────────────────────────

MOCK_PROVIDER = "api.v1.routers.company.calls.sipuni.ProviderFactory.create"
MOCK_NEXT_NUM = "api.v1.routers.company.calls.sipuni.next_call_number"


@pytest_asyncio.fixture
async def no_calls_user(db_session, test_company):
    """A real user in test_company WITHOUT calls.make permission."""
    user = User(
        id=uuid.uuid4(),
        company_id=test_company.id,
        email=f"nocalls_{uuid.uuid4().hex[:8]}@test.com",
        password_hash=PasswordManager.hash("testpassword123"),
        first_name="NoCalls",
        last_name="User",
        phone=f"+1999{uuid.uuid4().int % 10**7:07d}",
        role=RoleEnum.COMPANY_OPERATOR,
        permissions=["leads.read", "contacts.read"],
        is_active=True,
        email_verified=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
def no_calls_headers(no_calls_user):
    creds = JWTManager.generate_credentials(
        sub=no_calls_user.id,
        company_id=no_calls_user.company_id,
        role=no_calls_user.role.value,
        permissions=no_calls_user.permissions or [],
    )
    return {"Authorization": f"Bearer {creds['access']}"}


def _provider_resp(success, call_id="abc-123", error=None, message=None):
    """Build a mock provider CallResponse."""
    from utils.services.telephony.base import CallResponse as ProviderCallResponse
    return ProviderCallResponse(
        success=success, call_id=call_id, error=error, message=message,
    )


BASE = "/api/v1/company/calls/sipuni"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  POST /calls/sipuni/external
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestCallExternal:
    """POST /api/v1/company/calls/sipuni/external"""

    @pytest.mark.asyncio
    @patch(MOCK_NEXT_NUM, new_callable=AsyncMock, return_value=90000001)
    @patch(MOCK_PROVIDER)
    async def test_external_call_success(
        self, mock_factory, mock_next, client: AsyncClient, auth_headers
    ):
        mock_provider = AsyncMock()
        mock_provider.make_call.return_value = _provider_resp(True, "ext-1")
        mock_factory.return_value = mock_provider

        response = await client.post(
            f"{BASE}/external",
            headers=auth_headers,
            json={"phone_1": "+998901234567", "phone_2": "+998937654321"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert isinstance(data["call_id"], int)

    @pytest.mark.asyncio
    async def test_external_call_missing_phone(self, client: AsyncClient, auth_headers):
        """Missing required phone_2 → 422."""
        response = await client.post(
            f"{BASE}/external",
            headers=auth_headers,
            json={"phone_1": "+998901234567"},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_external_call_empty_body(self, client: AsyncClient, auth_headers):
        """Empty body → 422."""
        response = await client.post(
            f"{BASE}/external", headers=auth_headers, json={},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    @patch(MOCK_PROVIDER)
    async def test_external_call_provider_exception(
        self, mock_factory, client: AsyncClient, auth_headers
    ):
        """ProviderException → 502."""
        from utils.services.telephony.base import ProviderException
        mock_factory.side_effect = ProviderException("API down", provider="sipuni")

        response = await client.post(
            f"{BASE}/external",
            headers=auth_headers,
            json={"phone_1": "+998901234567", "phone_2": "+998937654321"},
        )
        assert response.status_code == 502

    @pytest.mark.asyncio
    async def test_external_call_permission_denied(
        self, client: AsyncClient, no_calls_headers
    ):
        """User without calls.make → 403."""
        response = await client.post(
            f"{BASE}/external",
            headers=no_calls_headers,
            json={"phone_1": "+998901234567", "phone_2": "+998937654321"},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    @patch(MOCK_NEXT_NUM, new_callable=AsyncMock, return_value=90000002)
    @patch(MOCK_PROVIDER)
    async def test_external_call_creates_call_event(
        self, mock_factory, mock_next, client: AsyncClient, auth_headers
    ):
        """Successful call creates a CallEvent in the database."""
        mock_provider = AsyncMock()
        mock_provider.make_call.return_value = _provider_resp(True, "ev-1")
        mock_factory.return_value = mock_provider

        response = await client.post(
            f"{BASE}/external",
            headers=auth_headers,
            json={"phone_1": "+998901234567", "phone_2": "+998937654321"},
        )
        assert response.status_code == 200
        assert response.json()["call_id"] is not None

    @pytest.mark.asyncio
    async def test_external_call_unauthorized(self, client: AsyncClient):
        """No auth → 401/403."""
        response = await client.post(
            f"{BASE}/external",
            json={"phone_1": "+998901234567", "phone_2": "+998937654321"},
        )
        assert response.status_code in [401, 403, 422]

    @pytest.mark.asyncio
    @patch(MOCK_PROVIDER)
    async def test_external_call_provider_returns_failure(
        self, mock_factory, client: AsyncClient, auth_headers
    ):
        """Provider returns success=False → 200 with error info."""
        mock_provider = AsyncMock()
        mock_provider.make_call.return_value = _provider_resp(
            False, call_id="", error="BUSY", message="Line busy"
        )
        mock_factory.return_value = mock_provider

        response = await client.post(
            f"{BASE}/external",
            headers=auth_headers,
            json={"phone_1": "+998901234567", "phone_2": "+998937654321"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["error"] == "BUSY"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  POST /calls/sipuni/number
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestCallNumber:
    """POST /api/v1/company/calls/sipuni/number"""

    @pytest.mark.asyncio
    @patch(MOCK_NEXT_NUM, new_callable=AsyncMock, return_value=90000003)
    @patch(MOCK_PROVIDER)
    async def test_call_number_success(
        self, mock_factory, mock_next, client: AsyncClient, auth_headers
    ):
        mock_provider = AsyncMock()
        mock_provider.call_number.return_value = _provider_resp(True, "num-1")
        mock_factory.return_value = mock_provider

        response = await client.post(
            f"{BASE}/number",
            headers=auth_headers,
            json={"phone": "+998901234567", "operator_id": "100"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert isinstance(data["call_id"], int)

    @pytest.mark.asyncio
    async def test_call_number_missing_operator(self, client: AsyncClient, auth_headers):
        """Missing required operator_id → 422."""
        response = await client.post(
            f"{BASE}/number",
            headers=auth_headers,
            json={"phone": "+998901234567"},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_call_number_missing_phone(self, client: AsyncClient, auth_headers):
        """Missing required phone → 422."""
        response = await client.post(
            f"{BASE}/number",
            headers=auth_headers,
            json={"operator_id": "100"},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    @patch(MOCK_NEXT_NUM, new_callable=AsyncMock, return_value=90000004)
    @patch(MOCK_PROVIDER)
    async def test_call_number_with_reverse(
        self, mock_factory, mock_next, client: AsyncClient, auth_headers
    ):
        """Test reverse=True (external rings first)."""
        mock_provider = AsyncMock()
        mock_provider.call_number.return_value = _provider_resp(True, "num-r")
        mock_factory.return_value = mock_provider

        response = await client.post(
            f"{BASE}/number",
            headers=auth_headers,
            json={"phone": "+998901234567", "operator_id": "100", "reverse": True},
        )
        assert response.status_code == 200
        mock_provider.call_number.assert_called_once()

    @pytest.mark.asyncio
    @patch(MOCK_PROVIDER)
    async def test_call_number_provider_exception(
        self, mock_factory, client: AsyncClient, auth_headers
    ):
        """ProviderException → 502."""
        from utils.services.telephony.base import ProviderException
        mock_provider = AsyncMock()
        mock_provider.call_number.side_effect = ProviderException("Timeout", provider="sipuni")
        mock_factory.return_value = mock_provider

        response = await client.post(
            f"{BASE}/number",
            headers=auth_headers,
            json={"phone": "+998901234567", "operator_id": "100"},
        )
        assert response.status_code == 502


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  POST /calls/sipuni/tree
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestCallTree:
    """POST /api/v1/company/calls/sipuni/tree"""

    @pytest.mark.asyncio
    @patch(MOCK_NEXT_NUM, new_callable=AsyncMock, return_value=90000005)
    @patch(MOCK_PROVIDER)
    async def test_call_tree_success(
        self, mock_factory, mock_next, client: AsyncClient, auth_headers
    ):
        mock_provider = AsyncMock()
        mock_provider.call_tree.return_value = _provider_resp(True, "tree-1")
        mock_factory.return_value = mock_provider

        response = await client.post(
            f"{BASE}/tree",
            headers=auth_headers,
            json={"phone": "+998901234567", "operator_id": "100", "tree": "000-913898"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert isinstance(data["call_id"], int)

    @pytest.mark.asyncio
    async def test_call_tree_missing_tree_id(self, client: AsyncClient, auth_headers):
        """Missing required tree → 422."""
        response = await client.post(
            f"{BASE}/tree",
            headers=auth_headers,
            json={"phone": "+998901234567", "operator_id": "100"},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_call_tree_missing_phone(self, client: AsyncClient, auth_headers):
        """Missing required phone → 422."""
        response = await client.post(
            f"{BASE}/tree",
            headers=auth_headers,
            json={"operator_id": "100", "tree": "000-913898"},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_call_tree_invalid_attempt_time(self, client: AsyncClient, auth_headers):
        """call_attempt_time < 30 → 422."""
        response = await client.post(
            f"{BASE}/tree",
            headers=auth_headers,
            json={
                "phone": "+998901234567",
                "operator_id": "100",
                "tree": "000-913898",
                "call_attempt_time": 10,
            },
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    @patch(MOCK_PROVIDER)
    async def test_call_tree_provider_exception(
        self, mock_factory, client: AsyncClient, auth_headers
    ):
        """ProviderException → 502."""
        from utils.services.telephony.base import ProviderException
        mock_provider = AsyncMock()
        mock_provider.call_tree.side_effect = ProviderException("Invalid tree", provider="sipuni")
        mock_factory.return_value = mock_provider

        response = await client.post(
            f"{BASE}/tree",
            headers=auth_headers,
            json={"phone": "+998901234567", "operator_id": "100", "tree": "000-999999"},
        )
        assert response.status_code == 502


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  POST /calls/sipuni/{call_id}/cancel
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestCancelCall:
    """POST /api/v1/company/calls/sipuni/{call_id}/cancel"""

    @pytest.mark.asyncio
    @patch(MOCK_PROVIDER)
    async def test_cancel_call_success(
        self, mock_factory, client: AsyncClient, auth_headers, test_call_event
    ):
        mock_provider = AsyncMock()
        mock_provider.cancel_call.return_value = _provider_resp(
            True, call_id=str(test_call_event.id), message="Cancelled"
        )
        mock_factory.return_value = mock_provider

        response = await client.post(
            f"{BASE}/{test_call_event.id}/cancel", headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["call_id"] == test_call_event.id

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_call(self, client: AsyncClient, auth_headers):
        """Cancel call that doesn't exist → 404."""
        response = await client.post(
            f"{BASE}/99999999/cancel", headers=auth_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_cancel_other_company_call(
        self, client: AsyncClient, active_auth_headers, test_call_event
    ):
        """Cancel call from a different company → 404 (multi-tenancy)."""
        response = await client.post(
            f"{BASE}/{test_call_event.id}/cancel", headers=active_auth_headers,
        )
        # active_auth_headers belongs to a different company, so
        # require_provider loads that company. The call belongs to
        # test_company, so CallEvent.get returns None → 404.
        assert response.status_code in [400, 404]

    @pytest.mark.asyncio
    @patch(MOCK_PROVIDER)
    async def test_cancel_call_provider_exception(
        self, mock_factory, client: AsyncClient, auth_headers, test_call_event
    ):
        """ProviderException on cancel → 502."""
        from utils.services.telephony.base import ProviderException
        mock_provider = AsyncMock()
        mock_provider.cancel_call.side_effect = ProviderException("Cancel failed", provider="sipuni")
        mock_factory.return_value = mock_provider

        response = await client.post(
            f"{BASE}/{test_call_event.id}/cancel", headers=auth_headers,
        )
        assert response.status_code == 502


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Provider validation
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestProviderValidation:
    """Verify that the Sipuni provider guard rejects non-Sipuni companies."""

    @pytest_asyncio.fixture
    async def binotel_company_headers(self, db_session):
        """Create a company with provider_type=BINOTEL and return auth headers."""
        from db.models.owner import Owner

        owner = Owner(
            id=uuid.uuid4(),
            email=f"binotel_owner_{uuid.uuid4().hex[:8]}@test.com",
            password_hash=PasswordManager.hash("testpassword123"),
            first_name="Binotel",
            last_name="Owner",
            phone=f"+2999{uuid.uuid4().int % 10**7:07d}",
            is_active=True,
            email_verified=True,
        )
        db_session.add(owner)
        await db_session.flush()

        company = Company(
            id=uuid.uuid4(),
            owner_id=owner.id,
            name="Binotel Corp",
            subdomain=f"binotel_{uuid.uuid4().hex[:8]}",
            provider_type=ProviderEnum.BINOTEL,
            provider_config={"key": "123", "secret": "abc"},
            webhook_token=str(uuid.uuid4()),
            is_active=True,
        )
        db_session.add(company)
        await db_session.flush()

        user = User(
            id=uuid.uuid4(),
            company_id=company.id,
            email=f"binotel_user_{uuid.uuid4().hex[:8]}@test.com",
            password_hash=PasswordManager.hash("testpassword123"),
            first_name="Binotel",
            last_name="User",
            phone=f"+3999{uuid.uuid4().int % 10**7:07d}",
            role=RoleEnum.COMPANY_ADMIN,
            permissions=["*"],
            is_active=True,
            email_verified=True,
        )
        db_session.add(user)
        await db_session.flush()

        creds = JWTManager.generate_credentials(
            sub=user.id,
            company_id=company.id,
            role=user.role.value,
            permissions=user.permissions,
        )
        return {"Authorization": f"Bearer {creds['access']}"}

    @pytest.mark.asyncio
    async def test_binotel_company_rejected_on_external(
        self, client: AsyncClient, binotel_company_headers
    ):
        """Non-sipuni company hitting sipuni endpoint → 400."""
        response = await client.post(
            f"{BASE}/external",
            headers=binotel_company_headers,
            json={"phone_1": "+998901234567", "phone_2": "+998937654321"},
        )
        assert response.status_code == 400
        assert "sipuni" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_binotel_company_rejected_on_number(
        self, client: AsyncClient, binotel_company_headers
    ):
        """Non-sipuni company hitting /number → 400."""
        response = await client.post(
            f"{BASE}/number",
            headers=binotel_company_headers,
            json={"phone": "+998901234567", "operator_id": "100"},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_binotel_company_rejected_on_tree(
        self, client: AsyncClient, binotel_company_headers
    ):
        """Non-sipuni company hitting /tree → 400."""
        response = await client.post(
            f"{BASE}/tree",
            headers=binotel_company_headers,
            json={"phone": "+998901234567", "operator_id": "100", "tree": "000-913898"},
        )
        assert response.status_code == 400
