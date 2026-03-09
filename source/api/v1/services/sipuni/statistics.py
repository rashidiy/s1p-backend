"""
Call statistics module for retrieving and aggregating call event data.

- Calculates call statistics (total, accepted, internal/external, avg duration)
- Groups by hour/day/week/month/year
- Buckets are computed in the SAME timezone as the request datetimes
- We join on timestamptz-aligned bucket boundaries (no off-by-one day)
- Response timestamps keep the SAME timezone and have no microseconds
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Sequence

from sqlalchemy import select, func, true, RowMapping, literal, cast
from sqlalchemy.dialects.postgresql import INTERVAL, TIMESTAMP as PG_TIMESTAMPTZ
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.schemas.sipuni.statistics import RepresentEnum
from db.models.enums import CallStatusEnum
from db.models.call_event import CallEvent


# ────────────────────────────────────────────
# Timezone helpers
# ────────────────────────────────────────────

def _detect_tz(time_start: datetime, time_end: datetime) -> timezone:
    """Detect timezone from request datetimes; default to UTC."""
    return (time_start.tzinfo or time_end.tzinfo) or timezone.utc


def _pg_tz_string(tz: timezone, ref: datetime) -> str:
    """
    Build a Postgres-compatible timezone displacement string for timezone(...).
    NOTE: Postgres' timezone(text, ...) treats positive offsets as a *westward*
    displacement. Therefore we must invert the sign relative to Python's tz offset.
    """
    offset = tz.utcoffset(ref) or timedelta(0)
    seconds = int(offset.total_seconds())

    # Invert the sign for Postgres' timezone(text, ...)
    seconds = -seconds

    sign = '+' if seconds >= 0 else '-'
    seconds = abs(seconds)
    hh = seconds // 3600
    mm = (seconds % 3600) // 60
    return f"{sign}{hh:02d}:{mm:02d}"



# ────────────────────────────────────────────
# Filters and Base Selects
# ────────────────────────────────────────────

def _get_base_filters(
    sipuni_id: uuid.UUID,
    time_start: datetime,
    time_end: datetime
) -> tuple[Any, ...]:
    return (
        CallEvent.sipuni_id == sipuni_id,
        CallEvent.created_at >= time_start,
        CallEvent.created_at <= time_end,
    )


def _get_base_select_columns() -> tuple[Any, ...]:
    """Common aggregate select columns for call statistics."""
    accepted_filter = CallEvent.status == CallStatusEnum.ANSWER

    return (
        func.count(CallEvent.id).label("total"),
        func.count(CallEvent.id).filter(accepted_filter).label("accepted"),
        func.count(CallEvent.id)
        .filter(accepted_filter, CallEvent.src_type == "2")
        .label("internal"),
        func.count(CallEvent.id)
        .filter(accepted_filter, CallEvent.src_type == "1")
        .label("external"),
        func.coalesce(
            func.round(
                func.avg(
                    func.extract("epoch", CallEvent.call_end - CallEvent.call_start)
                ).filter(accepted_filter)
            ),
            0,
        ).label("avg_duration"),
    )


# ────────────────────────────────────────────
# Time utilities
# ────────────────────────────────────────────

def _interval_for(represent: RepresentEnum) -> str:
    """Return interval string for generate_series()."""
    match represent.value:
        case "hour": return "1 hour"
        case "day": return "1 day"
        case "week": return "1 week"
        case "month": return "1 month"
        case "year": return "1 year"
        case _: return "1 day"


def _next_bucket_start(dt: datetime, represent: RepresentEnum) -> datetime:
    """Compute next bucket start, keeping tzinfo."""
    match represent.value:
        case "hour":
            return (dt + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        case "day":
            return (dt + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        case "week":
            return dt + timedelta(days=7)
        case "month":
            year = dt.year + (1 if dt.month == 12 else 0)
            month = 1 if dt.month == 12 else dt.month + 1
            return dt.replace(year=year, month=month, day=1, hour=0, minute=0, second=0, microsecond=0)
        case "year":
            return dt.replace(year=dt.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        case _:
            return (dt + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


def _format_label(date_group: datetime, represent: RepresentEnum) -> str:
    """Readable date label for each bucket."""
    match represent.value:
        case "hour": return date_group.strftime("%d %b %Y, %H:00")
        case "day": return date_group.strftime("%d %b %Y")
        case "week":
            year, week_num, _ = date_group.isocalendar()
            week_start = date_group
            week_end = date_group + timedelta(days=6)
            return f"Week {week_num} ({week_start.strftime('%d %b')}–{week_end.strftime('%d %b %Y')})"
        case "month": return date_group.strftime("%B %Y")
        case "year": return date_group.strftime("%Y")
        case _: return date_group.isoformat()


# ────────────────────────────────────────────
# Core Queries (local-time bucketing, timestamptz join)
# ────────────────────────────────────────────

async def _get_stats_general(
    sipuni_id: uuid.UUID,
    from_: datetime,
    to_: datetime,
    session: AsyncSession,
) -> dict[str, Any]:
    """Retrieve overall call stats; returns zero-filled dict if none."""
    base_filters = _get_base_filters(sipuni_id, from_, to_)
    accepted_filter = CallEvent.status == CallStatusEnum.ANSWER

    top_operator_subquery = (
        select(
            CallEvent.operator,
            func.count(CallEvent.id).label("total_accepted"),
        )
        .where(*base_filters, accepted_filter)
        .group_by(CallEvent.operator)
        .order_by(func.count(CallEvent.id).desc())
        .limit(1)
        .subquery()
    )

    query = (
        select(
            *_get_base_select_columns(),
            top_operator_subquery.c.operator.label("top_operator"),
            top_operator_subquery.c.total_accepted.label("top_operator_accepted"),
        )
        .where(*base_filters)
        .group_by(
            top_operator_subquery.c.operator,
            top_operator_subquery.c.total_accepted,
        )
        .join(top_operator_subquery, true(), isouter=True)
    )

    result = await session.execute(query)
    data = result.mappings().one_or_none()

    if not data:
        return {
            "total": 0,
            "accepted": 0,
            "internal": 0,
            "external": 0,
            "avg_duration": 0,
            "top_operator": None,
            "top_operator_accepted": 0,
        }

    return dict(data)


async def _get_stats_date_groups(
    sipuni_id: uuid.UUID,
    from_: datetime,
    to_: datetime,
    represent: RepresentEnum,
    tz: timezone,
    session: AsyncSession,
) -> list[dict[str, Any]]:
    """
    Retrieve grouped call stats and zero-fill missing buckets.

    We:
      1) Convert created_at to local wall time via timezone('<offset>', created_at)
      2) date_trunc(...) in local time (timestamp w/o tz)
      3) Convert that local-truncated value back to timestamptz via timezone('<offset>', local_trunc)
      4) Build the series in local time, then also convert each series step to timestamptz
      5) Join on timestamptz columns, so Python receives exact instants
    """
    base_filters = _get_base_filters(sipuni_id, from_, to_)
    accepted_filter = CallEvent.status == CallStatusEnum.ANSWER

    tz_str = _pg_tz_string(tz, from_)

    # Local-time versions (timestamp WITHOUT time zone)
    local_created = func.timezone(tz_str, CallEvent.created_at)
    local_from = func.timezone(tz_str, cast(literal(from_), PG_TIMESTAMPTZ(timezone=True)))
    local_to = func.timezone(tz_str, cast(literal(to_), PG_TIMESTAMPTZ(timezone=True)))

    # Truncate in local time (timestamp w/o tz)
    local_trunc = func.date_trunc(represent.value, local_created)

    # Convert local truncated time back to timestamptz (an absolute instant)
    trunc_ts = func.timezone(tz_str, local_trunc)

    # Step for generate_series
    step_interval = cast(literal(_interval_for(represent)), INTERVAL)

    # Generate local series (timestamp w/o tz), then convert each step to timestamptz
    local_series = func.generate_series(
        func.date_trunc(represent.value, local_from),
        func.date_trunc(represent.value, local_to),
        step_interval,
    )
    series_cte = select(local_series.label("local_date_group")).cte("series")
    series_ts = func.timezone(tz_str, series_cte.c.local_date_group)  # timestamptz

    # Per-bucket aggregates grouped by local truncated time (join via timestamptz)
    per_bucket_stats = (
        select(
            trunc_ts.label("bucket_ts"),  # timestamptz
            func.count(CallEvent.id).label("total"),
            func.count(CallEvent.id).filter(accepted_filter).label("accepted"),
            func.count(CallEvent.id).filter(accepted_filter, CallEvent.src_type == "2").label("internal"),
            func.count(CallEvent.id).filter(accepted_filter, CallEvent.src_type == "1").label("external"),
            func.coalesce(
                func.round(
                    func.avg(
                        func.extract("epoch", CallEvent.call_end - CallEvent.call_start)
                    ).filter(accepted_filter)
                ),
                0,
            ).label("avg_duration"),
        )
        .where(*base_filters)
        .group_by(trunc_ts)
        .subquery()
    )

    # Top operator per bucket (also grouped by local time, joined via timestamptz)
    operator_ranking_subquery = (
        select(
            trunc_ts.label("bucket_ts"),  # timestamptz
            CallEvent.operator.label("top_operator"),
            func.count(CallEvent.id).label("top_operator_accepted"),
        )
        .where(*base_filters, accepted_filter)
        .group_by(trunc_ts, CallEvent.operator)
        .order_by(
            trunc_ts,
            func.count(CallEvent.id).desc(),
            CallEvent.operator.asc(),
        )
        .distinct(trunc_ts)
        .subquery()
    )

    # Join on timestamptz keys
    query = (
        select(
            series_ts.label("bucket_ts"),  # timestamptz
            func.coalesce(per_bucket_stats.c.total, 0).label("total"),
            func.coalesce(per_bucket_stats.c.accepted, 0).label("accepted"),
            func.coalesce(per_bucket_stats.c.internal, 0).label("internal"),
            func.coalesce(per_bucket_stats.c.external, 0).label("external"),
            func.coalesce(per_bucket_stats.c.avg_duration, 0).label("avg_duration"),
            operator_ranking_subquery.c.top_operator,
            operator_ranking_subquery.c.top_operator_accepted,
        )
        .select_from(series_cte)
        .join(per_bucket_stats, per_bucket_stats.c.bucket_ts == series_ts, isouter=True)
        .join(operator_ranking_subquery, operator_ranking_subquery.c.bucket_ts == series_ts, isouter=True)
        .order_by(series_ts)
    )

    result = await session.execute(query)
    rows: Sequence[RowMapping] = result.mappings().all()

    # Shape output: convert bucket_ts (timestamptz) to the response tz, drop microseconds
    output: list[dict[str, Any]] = []
    for row in rows:
        bucket_instant: datetime = row["bucket_ts"]  # tz-aware from DB
        start_dt = bucket_instant.astimezone(tz).replace(microsecond=0)
        next_start = _next_bucket_start(start_dt, represent)
        end_dt = (next_start - timedelta(seconds=1)).replace(microsecond=0)

        output.append({
            "date_group": {
                "from": start_dt.isoformat(),
                "to": end_dt.isoformat(),
                "label": _format_label(start_dt, represent),
            },
            "total": row["total"],
            "accepted": row["accepted"],
            "internal": row["internal"],
            "external": row["external"],
            "avg_duration": row["avg_duration"],
            "top_operator": row["top_operator"],
            "top_operator_accepted": row["top_operator_accepted"],
        })

    return output


# ────────────────────────────────────────────
# Public API
# ────────────────────────────────────────────

async def get_call_statistics(
    *,
    sipuni_id: uuid.UUID,
    represent: RepresentEnum,
    time_start: datetime,
    time_end: datetime,
    session: AsyncSession,
) -> dict[str, Any]:
    """
    Return combined call stats (calls + grouped) using the request timezone.

    Buckets and labels are computed in the SAME timezone as the input,
    and joins are performed using timestamptz to avoid off-by-one buckets.
    """
    tz = _detect_tz(time_start, time_end)

    calls = await _get_stats_general(sipuni_id, time_start, time_end, session)
    if calls is None:
        calls = {
            "total": 0,
            "accepted": 0,
            "internal": 0,
            "external": 0,
            "avg_duration": 0,
            "top_operator": None,
            "top_operator_accepted": 0,
        }

    date_groups = await _get_stats_date_groups(
        sipuni_id=sipuni_id,
        from_=time_start,
        to_=time_end,
        represent=represent,
        tz=tz,
        session=session,
    )

    return {"calls": calls, "date_groups": date_groups}