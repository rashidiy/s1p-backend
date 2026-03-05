import uuid
from datetime import datetime, timezone, timedelta

import pytest
from httpx import AsyncClient

# Statistics endpoint uses PostgreSQL-specific features (INTERVAL, generate_series, etc.)
# These tests require PostgreSQL and will be skipped when using SQLite
pytestmark = pytest.mark.skip(
    reason="Statistics API uses PostgreSQL-specific features (INTERVAL, generate_series)"
)


class TestCallStatistics:
    """Tests for the /api/v1/statistics/calls endpoint."""

    async def test_statistics_success(
        self, client: AsyncClient, test_sipuni, test_call_events
    ):
        """Test successful statistics retrieval."""
        now = datetime.now(timezone.utc)
        start = (now - timedelta(hours=1)).isoformat()
        end = now.isoformat()

        response = await client.get(
            "/api/v1/statistics/calls",
            params={
                "sipuni_id": str(test_sipuni.id),
                "represent": "day",
                "start": start,
                "end": end,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "calls" in data
        assert "date_groups" in data

    async def test_statistics_with_different_represent_values(
        self, client: AsyncClient, test_sipuni
    ):
        """Test statistics with different represent (grouping) values."""
        now = datetime.now(timezone.utc)
        start = (now - timedelta(days=30)).isoformat()
        end = now.isoformat()

        represent_values = ["day", "week", "month", "year"]

        for represent in represent_values:
            response = await client.get(
                "/api/v1/statistics/calls",
                params={
                    "sipuni_id": str(test_sipuni.id),
                    "represent": represent,
                    "start": start,
                    "end": end,
                },
            )
            assert response.status_code == 200, f"Failed for represent={represent}"
            data = response.json()
            assert "calls" in data
            assert "date_groups" in data

    async def test_statistics_default_time_range(
        self, client: AsyncClient, test_sipuni
    ):
        """Test statistics with default time range (today)."""
        response = await client.get(
            "/api/v1/statistics/calls",
            params={
                "sipuni_id": str(test_sipuni.id),
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "calls" in data
        assert "date_groups" in data

    async def test_statistics_empty_result(self, client: AsyncClient, test_sipuni):
        """Test statistics when no call events exist in range."""
        # Use a date range in the past where no events exist
        past_date = datetime.now(timezone.utc) - timedelta(days=365)
        start = past_date.isoformat()
        end = (past_date + timedelta(hours=1)).isoformat()

        response = await client.get(
            "/api/v1/statistics/calls",
            params={
                "sipuni_id": str(test_sipuni.id),
                "start": start,
                "end": end,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "calls" in data
        # Empty stats should have zero values
        calls = data["calls"]
        assert calls["total"] == 0
        assert calls["accepted"] == 0

    async def test_statistics_invalid_sipuni_id(self, client: AsyncClient):
        """Test statistics with non-existent Sipuni ID."""
        random_id = uuid.uuid4()

        response = await client.get(
            "/api/v1/statistics/calls",
            params={
                "sipuni_id": str(random_id),
            },
        )
        # The endpoint returns stats even for non-existent sipuni (empty result)
        assert response.status_code == 200

    async def test_statistics_missing_sipuni_id(self, client: AsyncClient):
        """Test statistics without required sipuni_id parameter."""
        response = await client.get("/api/v1/statistics/calls")
        assert response.status_code == 422

    async def test_statistics_invalid_represent(
        self, client: AsyncClient, test_sipuni
    ):
        """Test statistics with invalid represent value."""
        response = await client.get(
            "/api/v1/statistics/calls",
            params={
                "sipuni_id": str(test_sipuni.id),
                "represent": "invalid_value",
            },
        )
        assert response.status_code == 422

    async def test_statistics_invalid_date_format(
        self, client: AsyncClient, test_sipuni
    ):
        """Test statistics with invalid date format."""
        response = await client.get(
            "/api/v1/statistics/calls",
            params={
                "sipuni_id": str(test_sipuni.id),
                "start": "not-a-date",
            },
        )
        assert response.status_code == 422

    async def test_statistics_structure(
        self, client: AsyncClient, test_sipuni, test_call_events
    ):
        """Test the structure of the statistics response."""
        now = datetime.now(timezone.utc)
        start = (now - timedelta(hours=2)).isoformat()
        end = now.isoformat()

        response = await client.get(
            "/api/v1/statistics/calls",
            params={
                "sipuni_id": str(test_sipuni.id),
                "represent": "day",
                "start": start,
                "end": end,
            },
        )
        assert response.status_code == 200
        data = response.json()

        # Check calls structure
        calls = data["calls"]
        assert "total" in calls
        assert "accepted" in calls
        assert "internal" in calls
        assert "external" in calls
        assert "avg_duration" in calls
        assert "top_operator" in calls

        # Check date_groups structure
        date_groups = data["date_groups"]
        assert isinstance(date_groups, list)

        if len(date_groups) > 0:
            group = date_groups[0]
            assert "date_group" in group
            assert "total" in group
            assert "accepted" in group
            assert "internal" in group
            assert "external" in group
            assert "avg_duration" in group

    async def test_statistics_hour_grouping(
        self, client: AsyncClient, test_sipuni, test_call_events
    ):
        """Test statistics with hourly grouping."""
        now = datetime.now(timezone.utc)
        start = (now - timedelta(hours=6)).isoformat()
        end = now.isoformat()

        response = await client.get(
            "/api/v1/statistics/calls",
            params={
                "sipuni_id": str(test_sipuni.id),
                "represent": "day",  # Note: There's no "hour" in RepresentEnum based on schema
                "start": start,
                "end": end,
            },
        )
        assert response.status_code == 200

    async def test_statistics_with_timezone(
        self, client: AsyncClient, test_sipuni
    ):
        """Test statistics respects timezone in datetime params."""
        # Use a specific timezone offset
        tz = timezone(timedelta(hours=5))
        now = datetime.now(tz)
        start = (now - timedelta(days=1)).isoformat()
        end = now.isoformat()

        response = await client.get(
            "/api/v1/statistics/calls",
            params={
                "sipuni_id": str(test_sipuni.id),
                "start": start,
                "end": end,
            },
        )
        assert response.status_code == 200

    async def test_statistics_weekly_grouping(
        self, client: AsyncClient, test_sipuni
    ):
        """Test statistics with weekly grouping."""
        now = datetime.now(timezone.utc)
        start = (now - timedelta(weeks=4)).isoformat()
        end = now.isoformat()

        response = await client.get(
            "/api/v1/statistics/calls",
            params={
                "sipuni_id": str(test_sipuni.id),
                "represent": "week",
                "start": start,
                "end": end,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "date_groups" in data

    async def test_statistics_monthly_grouping(
        self, client: AsyncClient, test_sipuni
    ):
        """Test statistics with monthly grouping."""
        now = datetime.now(timezone.utc)
        start = (now - timedelta(days=90)).isoformat()
        end = now.isoformat()

        response = await client.get(
            "/api/v1/statistics/calls",
            params={
                "sipuni_id": str(test_sipuni.id),
                "represent": "month",
                "start": start,
                "end": end,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "date_groups" in data

    async def test_statistics_yearly_grouping(
        self, client: AsyncClient, test_sipuni
    ):
        """Test statistics with yearly grouping."""
        now = datetime.now(timezone.utc)
        start = (now - timedelta(days=365)).isoformat()
        end = now.isoformat()

        response = await client.get(
            "/api/v1/statistics/calls",
            params={
                "sipuni_id": str(test_sipuni.id),
                "represent": "year",
                "start": start,
                "end": end,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "date_groups" in data
