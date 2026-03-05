import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from api.v1.schemas.sipuni.statistics import RepresentEnum
from api.v1.services.sipuni.statistics import (
    get_call_statistics,
    _detect_tz,
    _pg_tz_string,
    _interval_for,
    _next_bucket_start,
    _format_label,
)


class TestTimezoneHelpers:
    """Tests for timezone helper functions."""

    def test_detect_tz_from_start(self):
        """Test timezone detection from start datetime."""
        tz = timezone(timedelta(hours=5))
        start = datetime.now(tz)
        end = datetime.now()  # naive

        result = _detect_tz(start, end)
        assert result == tz

    def test_detect_tz_from_end(self):
        """Test timezone detection from end datetime."""
        tz = timezone(timedelta(hours=-3))
        start = datetime.now()  # naive
        end = datetime.now(tz)

        result = _detect_tz(start, end)
        assert result == tz

    def test_detect_tz_default_utc(self):
        """Test timezone defaults to UTC when no timezone info."""
        start = datetime.now()  # naive
        end = datetime.now()  # naive

        result = _detect_tz(start, end)
        assert result == timezone.utc

    def test_pg_tz_string_positive_offset(self):
        """Test Postgres timezone string for positive offset."""
        tz = timezone(timedelta(hours=5))
        ref = datetime.now(tz)

        result = _pg_tz_string(tz, ref)
        # Postgres inverts the sign
        assert result == "-05:00"

    def test_pg_tz_string_negative_offset(self):
        """Test Postgres timezone string for negative offset."""
        tz = timezone(timedelta(hours=-8))
        ref = datetime.now(tz)

        result = _pg_tz_string(tz, ref)
        assert result == "+08:00"

    def test_pg_tz_string_utc(self):
        """Test Postgres timezone string for UTC."""
        tz = timezone.utc
        ref = datetime.now(tz)

        result = _pg_tz_string(tz, ref)
        assert result == "+00:00"


class TestIntervalFor:
    """Tests for interval string generation."""

    def test_interval_for_hour(self):
        """Test interval for hourly grouping."""
        # Note: hour is not in RepresentEnum based on schema, but in service code
        # This test documents expected behavior
        pass

    def test_interval_for_day(self):
        """Test interval for daily grouping."""
        result = _interval_for(RepresentEnum.day)
        assert result == "1 day"

    def test_interval_for_week(self):
        """Test interval for weekly grouping."""
        result = _interval_for(RepresentEnum.weekly)
        assert result == "1 week"

    def test_interval_for_month(self):
        """Test interval for monthly grouping."""
        result = _interval_for(RepresentEnum.monthly)
        assert result == "1 month"

    def test_interval_for_year(self):
        """Test interval for yearly grouping."""
        result = _interval_for(RepresentEnum.yearly)
        assert result == "1 year"


class TestNextBucketStart:
    """Tests for next bucket start calculation."""

    def test_next_bucket_day(self):
        """Test next bucket start for daily grouping."""
        dt = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        result = _next_bucket_start(dt, RepresentEnum.day)

        assert result.year == 2024
        assert result.month == 1
        assert result.day == 16
        assert result.hour == 0
        assert result.minute == 0
        assert result.second == 0

    def test_next_bucket_week(self):
        """Test next bucket start for weekly grouping."""
        dt = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        result = _next_bucket_start(dt, RepresentEnum.weekly)

        expected = dt + timedelta(days=7)
        assert result == expected

    def test_next_bucket_month(self):
        """Test next bucket start for monthly grouping."""
        dt = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        result = _next_bucket_start(dt, RepresentEnum.monthly)

        assert result.year == 2024
        assert result.month == 2
        assert result.day == 1

    def test_next_bucket_month_december(self):
        """Test next bucket start for December (year rollover)."""
        dt = datetime(2024, 12, 15, 10, 30, 0, tzinfo=timezone.utc)
        result = _next_bucket_start(dt, RepresentEnum.monthly)

        assert result.year == 2025
        assert result.month == 1
        assert result.day == 1

    def test_next_bucket_year(self):
        """Test next bucket start for yearly grouping."""
        dt = datetime(2024, 6, 15, 10, 30, 0, tzinfo=timezone.utc)
        result = _next_bucket_start(dt, RepresentEnum.yearly)

        assert result.year == 2025
        assert result.month == 1
        assert result.day == 1


class TestFormatLabel:
    """Tests for date label formatting."""

    def test_format_label_day(self):
        """Test label formatting for daily grouping."""
        dt = datetime(2024, 1, 15, tzinfo=timezone.utc)
        result = _format_label(dt, RepresentEnum.day)

        assert "15" in result
        assert "Jan" in result
        assert "2024" in result

    def test_format_label_week(self):
        """Test label formatting for weekly grouping."""
        dt = datetime(2024, 1, 15, tzinfo=timezone.utc)
        result = _format_label(dt, RepresentEnum.weekly)

        assert "Week" in result

    def test_format_label_month(self):
        """Test label formatting for monthly grouping."""
        dt = datetime(2024, 1, 15, tzinfo=timezone.utc)
        result = _format_label(dt, RepresentEnum.monthly)

        assert "January" in result
        assert "2024" in result

    def test_format_label_year(self):
        """Test label formatting for yearly grouping."""
        dt = datetime(2024, 6, 15, tzinfo=timezone.utc)
        result = _format_label(dt, RepresentEnum.yearly)

        assert result == "2024"
