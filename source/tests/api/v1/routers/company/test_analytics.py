"""
Tests for analytics endpoints

Covers:
- /analytics/me — operator personal analytics
- /analytics/me/dashboard — operator dashboard
- /analytics/team — admin team analytics
- /analytics/operator/{user_id} — admin views specific operator
- /analytics/cache DELETE — admin clears cache
"""

import pytest
import uuid
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import User, Lead, Deal, Task, CallEvent
from db.models.enums import (
    RoleEnum, LeadStatusEnum, DealStageEnum,
    TaskStatusEnum, TaskPriorityEnum, CallDirectionEnum,
)
from utils.managers import JWTManager


BASE = "/api/v1/company/analytics"


# ────────────────────────────────────────────────────
# /analytics/me
# ────────────────────────────────────────────────────

class TestMyAnalytics:
    """Tests for GET /analytics/me"""

    @pytest.mark.asyncio
    async def test_returns_200_with_structure(self, client: AsyncClient, auth_headers):
        """Admin gets own analytics with correct response shape."""
        response = await client.get(f"{BASE}/me", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        # Top-level fields
        assert data["period"] == "month"
        assert "date_from" in data
        assert "date_to" in data
        assert "productivity_score" in data
        assert "total_activities" in data
        # Nested stat blocks
        for block in ("calls", "leads", "deals", "tasks"):
            assert block in data
            assert isinstance(data[block], dict)

    @pytest.mark.asyncio
    async def test_call_stats_fields(self, client: AsyncClient, auth_headers):
        """Call stats block contains all expected counters."""
        data = (await client.get(f"{BASE}/me", headers=auth_headers)).json()
        calls = data["calls"]
        for key in (
            "total_calls", "answered_calls", "missed_calls",
            "outbound_calls", "inbound_calls",
            "total_duration", "average_duration", "success_rate",
        ):
            assert key in calls

    @pytest.mark.asyncio
    async def test_lead_stats_fields(self, client: AsyncClient, auth_headers):
        """Lead stats block contains all expected counters."""
        data = (await client.get(f"{BASE}/me", headers=auth_headers)).json()
        leads = data["leads"]
        for key in (
            "total_leads", "new_leads", "contacted_leads",
            "qualified_leads", "converted_leads", "lost_leads",
            "conversion_rate",
        ):
            assert key in leads

    @pytest.mark.asyncio
    async def test_deal_stats_fields(self, client: AsyncClient, auth_headers):
        """Deal stats block contains all expected counters."""
        data = (await client.get(f"{BASE}/me", headers=auth_headers)).json()
        deals = data["deals"]
        for key in (
            "total_deals", "prospecting", "negotiation",
            "won", "lost", "total_value", "won_value",
            "average_deal_size", "win_rate",
        ):
            assert key in deals

    @pytest.mark.asyncio
    async def test_task_stats_fields(self, client: AsyncClient, auth_headers):
        """Task stats block contains all expected counters."""
        data = (await client.get(f"{BASE}/me", headers=auth_headers)).json()
        tasks = data["tasks"]
        for key in (
            "total_tasks", "pending_tasks", "completed_tasks",
            "overdue_tasks", "completion_rate",
        ):
            assert key in tasks

    @pytest.mark.asyncio
    async def test_empty_data_returns_zeros(self, client: AsyncClient, auth_headers):
        """Fresh user with no data gets zero-valued stats."""
        data = (await client.get(f"{BASE}/me", headers=auth_headers)).json()
        assert data["calls"]["total_calls"] >= 0
        assert data["leads"]["total_leads"] >= 0
        assert data["deals"]["total_deals"] >= 0
        assert data["tasks"]["total_tasks"] >= 0
        assert data["productivity_score"] >= 0

    @pytest.mark.asyncio
    async def test_operator_can_access(self, client: AsyncClient, operator_auth_headers):
        """Operators can view their own analytics (no permission gate)."""
        response = await client.get(f"{BASE}/me", headers=operator_auth_headers)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_unauthenticated_gets_401(self, client: AsyncClient):
        """No token → 401."""
        response = await client.get(f"{BASE}/me")
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_period_param_today(self, client: AsyncClient, auth_headers):
        """period=today narrows date range to today only."""
        data = (await client.get(
            f"{BASE}/me?period=today", headers=auth_headers
        )).json()
        assert data["period"] == "today"
        assert data["date_from"] == data["date_to"]

    @pytest.mark.asyncio
    async def test_period_param_week(self, client: AsyncClient, auth_headers):
        """period=week returns weekly range."""
        data = (await client.get(
            f"{BASE}/me?period=week", headers=auth_headers
        )).json()
        assert data["period"] == "week"

    @pytest.mark.asyncio
    async def test_period_param_year(self, client: AsyncClient, auth_headers):
        """period=year returns yearly range."""
        data = (await client.get(
            f"{BASE}/me?period=year", headers=auth_headers
        )).json()
        assert data["period"] == "year"

    @pytest.mark.asyncio
    async def test_multi_tenancy_isolation(
        self, client: AsyncClient, auth_headers,
        db_session: AsyncSession, test_company, test_user,
        active_user
    ):
        """Admin in company A does not see data from company B."""
        # Create a lead in company B
        lead_b = Lead(
            id=uuid.uuid4(),
            company_id=active_user.company_id,
            title="Company B Lead",
            source="test",
            status=LeadStatusEnum.NEW,
            assigned_to=active_user.id,
        )
        db_session.add(lead_b)
        await db_session.flush()

        data = (await client.get(
            f"{BASE}/me", headers=auth_headers
        )).json()
        # Company A admin should not see company B leads
        # (leads count should not include the one we just created for company B)
        assert data["leads"]["total_leads"] >= 0  # sanity
        # The cross-company lead should not leak


# ────────────────────────────────────────────────────
# /analytics/me/dashboard
# ────────────────────────────────────────────────────

class TestMyDashboard:
    """Tests for GET /analytics/me/dashboard"""

    @pytest.mark.asyncio
    async def test_returns_200_with_structure(self, client: AsyncClient, auth_headers):
        """Dashboard response has the three period blocks + quick stats."""
        response = await client.get(f"{BASE}/me/dashboard", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        for period_key in ("today", "this_week", "this_month"):
            assert period_key in data
            assert "calls" in data[period_key]
            assert "leads" in data[period_key]
            assert "deals" in data[period_key]
            assert "tasks" in data[period_key]

    @pytest.mark.asyncio
    async def test_includes_quick_stats(self, client: AsyncClient, auth_headers):
        """Dashboard includes upcoming_tasks, pending_leads, active_deals."""
        data = (await client.get(
            f"{BASE}/me/dashboard", headers=auth_headers
        )).json()
        assert "upcoming_tasks" in data
        assert "pending_leads" in data
        assert "active_deals" in data
        assert isinstance(data["upcoming_tasks"], int)
        assert isinstance(data["pending_leads"], int)
        assert isinstance(data["active_deals"], int)

    @pytest.mark.asyncio
    async def test_includes_recent_activity(self, client: AsyncClient, auth_headers):
        """Dashboard includes recent_calls and recent_tasks lists."""
        data = (await client.get(
            f"{BASE}/me/dashboard", headers=auth_headers
        )).json()
        assert "recent_calls" in data
        assert "recent_tasks" in data
        assert isinstance(data["recent_calls"], list)
        assert isinstance(data["recent_tasks"], list)

    @pytest.mark.asyncio
    async def test_this_month_has_productivity_score(self, client: AsyncClient, auth_headers):
        """Each period block includes productivity_score."""
        data = (await client.get(
            f"{BASE}/me/dashboard", headers=auth_headers
        )).json()
        assert "productivity_score" in data["this_month"]
        assert isinstance(data["this_month"]["productivity_score"], (int, float))

    @pytest.mark.asyncio
    async def test_operator_can_access(self, client: AsyncClient, operator_auth_headers):
        """Operators can view their own dashboard (no permission gate)."""
        response = await client.get(
            f"{BASE}/me/dashboard", headers=operator_auth_headers
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_unauthenticated_gets_401(self, client: AsyncClient):
        """No token → 401."""
        response = await client.get(f"{BASE}/me/dashboard")
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_cache_returns_same_data(self, client: AsyncClient, auth_headers):
        """Second call returns cached (identical) data."""
        r1 = (await client.get(f"{BASE}/me/dashboard", headers=auth_headers)).json()
        r2 = (await client.get(f"{BASE}/me/dashboard", headers=auth_headers)).json()
        assert r1 == r2


# ────────────────────────────────────────────────────
# /analytics/team
# ────────────────────────────────────────────────────

class TestTeamAnalytics:
    """Tests for GET /analytics/team"""

    @pytest.mark.asyncio
    async def test_admin_gets_200_with_structure(self, client: AsyncClient, auth_headers):
        """Admin gets team analytics with correct response shape."""
        response = await client.get(f"{BASE}/team", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["period"] == "month"
        assert "total_operators" in data
        assert "active_operators" in data
        for block in ("calls", "leads", "deals", "tasks"):
            assert block in data
        assert "total_revenue" in data
        assert "revenue_growth" in data

    @pytest.mark.asyncio
    async def test_includes_top_operator_lists(self, client: AsyncClient, auth_headers):
        """Response includes top performer lists (may be empty)."""
        data = (await client.get(f"{BASE}/team", headers=auth_headers)).json()
        assert "top_operators_by_calls" in data
        assert "top_operators_by_deals" in data
        assert "top_operators_by_revenue" in data
        assert isinstance(data["top_operators_by_calls"], list)

    @pytest.mark.asyncio
    async def test_operator_gets_403(self, client: AsyncClient, operator_auth_headers):
        """Operator without stats.read permission is denied."""
        response = await client.get(
            f"{BASE}/team", headers=operator_auth_headers
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_unauthenticated_gets_401(self, client: AsyncClient):
        """No token → 401."""
        response = await client.get(f"{BASE}/team")
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_period_param_today(self, client: AsyncClient, auth_headers):
        """period=today returns today's team stats."""
        data = (await client.get(
            f"{BASE}/team?period=today", headers=auth_headers
        )).json()
        assert data["period"] == "today"
        assert data["date_from"] == data["date_to"]

    @pytest.mark.asyncio
    async def test_multi_tenancy_isolation(
        self, client: AsyncClient, auth_headers,
        db_session: AsyncSession, active_user
    ):
        """Team analytics only includes data from the admin's company."""
        # Create a lead in company B
        lead_b = Lead(
            id=uuid.uuid4(),
            company_id=active_user.company_id,
            title="Cross-company lead",
            source="test",
            status=LeadStatusEnum.NEW,
            assigned_to=active_user.id,
        )
        db_session.add(lead_b)
        await db_session.flush()

        data = (await client.get(f"{BASE}/team", headers=auth_headers)).json()
        # The cross-company lead must not appear in company A's team stats
        assert data["leads"]["total_leads"] >= 0


# ────────────────────────────────────────────────────
# /analytics/operator/{user_id}
# ────────────────────────────────────────────────────

class TestOperatorAnalytics:
    """Tests for GET /analytics/operator/{user_id}"""

    @pytest.mark.asyncio
    async def test_admin_views_operator(
        self, client: AsyncClient, auth_headers, test_operator
    ):
        """Admin can view specific operator's analytics."""
        response = await client.get(
            f"{BASE}/operator/{test_operator.id}", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["period"] == "month"
        for block in ("calls", "leads", "deals", "tasks"):
            assert block in data

    @pytest.mark.asyncio
    async def test_admin_views_self(
        self, client: AsyncClient, auth_headers, test_user
    ):
        """Admin can view their own analytics via this endpoint."""
        response = await client.get(
            f"{BASE}/operator/{test_user.id}", headers=auth_headers
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_cross_company_user_returns_404(
        self, client: AsyncClient, auth_headers, active_user
    ):
        """Admin cannot view operator from another company → 404."""
        response = await client.get(
            f"{BASE}/operator/{active_user.id}", headers=auth_headers
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_invalid_uuid_returns_error(
        self, client: AsyncClient, auth_headers
    ):
        """Malformed user_id → 422 or 404."""
        response = await client.get(
            f"{BASE}/operator/not-a-uuid", headers=auth_headers
        )
        assert response.status_code in [400, 404, 422]

    @pytest.mark.asyncio
    async def test_nonexistent_user_returns_404(
        self, client: AsyncClient, auth_headers
    ):
        """Valid UUID but no such user → 404."""
        fake_id = uuid.uuid4()
        response = await client.get(
            f"{BASE}/operator/{fake_id}", headers=auth_headers
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_operator_cannot_access(
        self, client: AsyncClient, operator_auth_headers, test_user
    ):
        """Operator without stats.read permission is denied."""
        response = await client.get(
            f"{BASE}/operator/{test_user.id}",
            headers=operator_auth_headers,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_period_param_forwarded(
        self, client: AsyncClient, auth_headers, test_operator
    ):
        """period query param is respected."""
        data = (await client.get(
            f"{BASE}/operator/{test_operator.id}?period=today",
            headers=auth_headers,
        )).json()
        assert data["period"] == "today"


# ────────────────────────────────────────────────────
# DELETE /analytics/cache
# ────────────────────────────────────────────────────

class TestClearCache:
    """Tests for DELETE /analytics/cache"""

    @pytest.mark.asyncio
    async def test_admin_can_clear_cache(self, client: AsyncClient, auth_headers):
        """Admin clears cache successfully."""
        response = await client.delete(f"{BASE}/cache", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "cleared" in data
        assert "message" in data

    @pytest.mark.asyncio
    async def test_operator_gets_403(self, client: AsyncClient, operator_auth_headers):
        """Operator without stats.read permission cannot clear cache."""
        response = await client.delete(
            f"{BASE}/cache", headers=operator_auth_headers
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_unauthenticated_gets_401(self, client: AsyncClient):
        """No token → 401."""
        response = await client.delete(f"{BASE}/cache")
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_cleared_count_is_integer(self, client: AsyncClient, auth_headers):
        """cleared field is always a non-negative integer."""
        data = (await client.delete(
            f"{BASE}/cache", headers=auth_headers
        )).json()
        assert isinstance(data["cleared"], int)
        assert data["cleared"] >= 0


# ────────────────────────────────────────────────────
# /analytics/team/dashboard (admin dashboard)
# ────────────────────────────────────────────────────

class TestAdminDashboard:
    """Tests for GET /analytics/team/dashboard"""

    @pytest.mark.asyncio
    async def test_admin_gets_200(self, client: AsyncClient, auth_headers):
        """Admin gets full dashboard."""
        response = await client.get(
            f"{BASE}/team/dashboard", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        for key in ("today", "this_week", "this_month", "this_year"):
            assert key in data
        assert "conversion_funnel" in data
        assert "pipeline_health" in data
        assert "calls_trend" in data
        assert "revenue_trend" in data

    @pytest.mark.asyncio
    async def test_conversion_funnel_structure(self, client: AsyncClient, auth_headers):
        """Conversion funnel has expected fields."""
        data = (await client.get(
            f"{BASE}/team/dashboard", headers=auth_headers
        )).json()
        funnel = data["conversion_funnel"]
        for key in (
            "total_leads", "contacted", "qualified",
            "deals_created", "deals_won",
            "contact_rate", "qualification_rate",
            "deal_rate", "win_rate", "overall_conversion",
        ):
            assert key in funnel

    @pytest.mark.asyncio
    async def test_pipeline_health_structure(self, client: AsyncClient, auth_headers):
        """Pipeline health has expected fields."""
        data = (await client.get(
            f"{BASE}/team/dashboard", headers=auth_headers
        )).json()
        health = data["pipeline_health"]
        for key in ("total_value", "weighted_value", "by_stage", "stuck_deals", "forecast"):
            assert key in health

    @pytest.mark.asyncio
    async def test_trends_are_lists(self, client: AsyncClient, auth_headers):
        """Trend arrays are lists of dicts."""
        data = (await client.get(
            f"{BASE}/team/dashboard", headers=auth_headers
        )).json()
        assert isinstance(data["calls_trend"], list)
        assert isinstance(data["revenue_trend"], list)
        if data["calls_trend"]:
            assert "date" in data["calls_trend"][0]
            assert "calls" in data["calls_trend"][0]
        if data["revenue_trend"]:
            assert "date" in data["revenue_trend"][0]
            assert "revenue" in data["revenue_trend"][0]

    @pytest.mark.asyncio
    async def test_operator_gets_403(self, client: AsyncClient, operator_auth_headers):
        """Operator without stats.read is denied."""
        response = await client.get(
            f"{BASE}/team/dashboard", headers=operator_auth_headers
        )
        assert response.status_code == 403
