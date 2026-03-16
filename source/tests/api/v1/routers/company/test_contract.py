"""
Tests for company contract status endpoint
"""

import uuid
from datetime import date, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.contract import Contract
from db.models.enums import ContractStatusEnum, BillingPeriodEnum, PaymentStatusEnum


@pytest_asyncio.fixture
async def test_contract(db_session: AsyncSession, test_owner, test_company) -> Contract:
    """Create a test contract for the test company."""
    contract = Contract(
        id=uuid.uuid4(),
        owner_id=test_owner.id,
        company_id=test_company.id,
        name="Standard Plan",
        max_admins=3,
        max_managers=5,
        max_operators=10,
        max_storage_gb=50,
        price=99.99,
        currency="USD",
        billing_period=BillingPeriodEnum.MONTHLY,
        status=ContractStatusEnum.ACTIVE,
        payment_status=PaymentStatusEnum.PAID,
        start_date=date.today() - timedelta(days=30),
        end_date=date.today() + timedelta(days=335),
        is_active=True,
        auto_renew=False,
    )
    db_session.add(contract)
    await db_session.flush()
    return contract


class TestGetContractStatus:
    """Tests for GET /api/v1/company/contract"""

    @pytest.mark.asyncio
    async def test_get_contract_status_success(
        self, client: AsyncClient, auth_headers, test_contract
    ):
        """Admin can view contract status."""
        response = await client.get(
            "/api/v1/company/contract",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Standard Plan"
        assert data["status"] == "active"
        assert data["payment_status"] == "paid"
        assert data["max_admins"] == 3
        assert data["max_managers"] == 5
        assert data["max_operators"] == 10
        assert data["max_storage_gb"] == 50

    @pytest.mark.asyncio
    async def test_contract_includes_user_counts(
        self, client: AsyncClient, auth_headers, test_contract
    ):
        """Contract response includes current user counts."""
        response = await client.get(
            "/api/v1/company/contract",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "current_admins" in data
        assert "current_managers" in data
        assert "current_operators" in data
        # The test_user is a COMPANY_ADMIN, so at least 1 admin
        assert data["current_admins"] >= 1

    @pytest.mark.asyncio
    async def test_contract_includes_dates_and_expiry(
        self, client: AsyncClient, auth_headers, test_contract
    ):
        """Contract response includes dates and days until expiry."""
        response = await client.get(
            "/api/v1/company/contract",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "start_date" in data
        assert "end_date" in data
        assert "days_until_expiry" in data
        assert data["days_until_expiry"] > 0

    @pytest.mark.asyncio
    async def test_contract_not_found(self, client: AsyncClient, auth_headers):
        """Returns 404 when no contract exists."""
        response = await client.get(
            "/api/v1/company/contract",
            headers=auth_headers
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_contract_unauthorized(self, client: AsyncClient):
        """Unauthenticated request should fail."""
        response = await client.get("/api/v1/company/contract")
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_contract_operator_forbidden(
        self, client: AsyncClient, operator_auth_headers, test_contract
    ):
        """Operator cannot view contract (requires contract.read)."""
        response = await client.get(
            "/api/v1/company/contract",
            headers=operator_auth_headers
        )
        assert response.status_code == 403


class TestContractMultiTenancy:
    """Multi-tenancy isolation for contract endpoint"""

    @pytest.mark.asyncio
    async def test_cannot_see_other_company_contract(
        self, client: AsyncClient, active_auth_headers, test_contract
    ):
        """Company B cannot see Company A's contract."""
        response = await client.get(
            "/api/v1/company/contract",
            headers=active_auth_headers
        )
        # Company B has no contract, so 404
        assert response.status_code == 404
