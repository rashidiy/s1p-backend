"""
Analytics endpoints for operators and admins

Optimized for high-load production:
- SQL aggregations instead of loading all data
- Single queries for trends (GROUP BY date)
- Caching for dashboard data
- Batch operations for multi-entity stats
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from typing import Optional
from datetime import date, datetime, timedelta, timezone

from db import get_session
from db.models.user import User
from db.models.call_event import CallEvent
from db.models.contact import Contact
from db.models.lead import Lead
from db.models.task import Task
from db.models.enums import RoleEnum, TaskStatusEnum, CallStatusEnum
from api.v1.schemas.analytics import (
    OperatorAnalytics,
    OperatorDashboard,
    TeamAnalytics,
    AdminDashboard,
    OperatorPerformance,
)
from utils.services.analytics_service import AnalyticsService
from utils.services.cache_service import get_cache
from utils.permissions import require_permissions, Permissions

router = APIRouter(prefix="/analytics", tags=["Analytics"])


# ===== Operator Analytics (Own Data) =====

@router.get("/me", response_model=OperatorAnalytics)
async def get_my_analytics(
    user: User = User.current(),
    session: AsyncSession = Depends(get_session),
    period: str = Query("month", description="today, week, month, year"),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None
):
    """
    Get my personal analytics (Operator/Anyone)

    Returns performance metrics for the current user.
    Uses SQL aggregations for optimal performance.
    """
    return await AnalyticsService.get_operator_analytics(
        session=session,
        company_id=user.company_id,
        user_id=user.id,
        period=period,
        date_from=date_from,
        date_to=date_to
    )


@router.get("/me/dashboard", response_model=OperatorDashboard)
async def get_my_dashboard(
    user: User = User.current(),
    session: AsyncSession = Depends(get_session)
):
    """
    Get my dashboard data (Operator/Anyone)

    OPTIMIZED: Uses caching and SQL aggregations.
    Returns dashboard with today, week, and month analytics plus quick stats.
    """
    cache = get_cache()

    # Try to get from cache first
    cached = await cache.get_dashboard("operator", user.id)
    if cached:
        return OperatorDashboard(**cached)

    # Get analytics for different periods (4 optimized SQL queries each)
    today = await AnalyticsService.get_operator_analytics(
        session, user.company_id, user.id, "today"
    )
    this_week = await AnalyticsService.get_operator_analytics(
        session, user.company_id, user.id, "week"
    )
    this_month = await AnalyticsService.get_operator_analytics(
        session, user.company_id, user.id, "month"
    )

    # Get quick stats (single query)
    upcoming_tasks = await session.scalar(
        select(func.count()).select_from(Task).where(
            and_(
                Task.assigned_to == user.id,
                Task.status == TaskStatusEnum.PENDING,
                Task.due_date >= datetime.now(timezone.utc),
                Task.deleted_at.is_(None)
            )
        )
    ) or 0

    # Get recent calls (single query with limit) — enriched with contact_name
    recent_calls_query = (
        select(CallEvent, Contact.first_name, Contact.last_name)
        .outerjoin(Contact, and_(
            Contact.phone == CallEvent.phone_1,
            Contact.company_id == CallEvent.company_id,
            Contact.deleted_at.is_(None),
        ))
        .where(
            CallEvent.company_id == user.company_id,
            CallEvent.operator_id == user.id,
        )
        .order_by(CallEvent.created_at.desc())
        .limit(5)
    )

    result = await session.execute(recent_calls_query)
    recent_calls_rows = result.all()

    recent_calls = []
    for row in recent_calls_rows:
        call = row[0]
        c_first, c_last = row[1], row[2]
        contact_name = None
        if c_first and c_last:
            contact_name = f"{c_first} {c_last}"
        elif c_first or c_last:
            contact_name = c_first or c_last
        recent_calls.append({
            "id": call.id,
            "phone": call.phone_2 or call.phone_1,
            "direction": call.direction.value if call.direction else None,
            "duration": call.billing_sec,
            "started_at": call.created_at.isoformat() if call.created_at else None,
            "contact_name": contact_name,
        })

    # Get missed calls to return (today, NOANSWER/CANCEL, operator's calls)
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    missed_calls_query = (
        select(CallEvent, Contact.first_name, Contact.last_name, Contact.id.label("cid"))
        .outerjoin(Contact, and_(
            Contact.phone == CallEvent.phone_1,
            Contact.company_id == CallEvent.company_id,
            Contact.deleted_at.is_(None),
        ))
        .where(
            CallEvent.company_id == user.company_id,
            CallEvent.operator_id == user.id,
            CallEvent.state.in_([CallStatusEnum.NOANSWER, CallStatusEnum.CANCEL]),
            CallEvent.created_at >= today_start,
        )
        .order_by(CallEvent.created_at.desc())
        .limit(20)
    )

    result = await session.execute(missed_calls_query)
    missed_rows = result.all()

    missed_calls_to_return = []
    for row in missed_rows:
        call = row[0]
        c_first, c_last, contact_id = row[1], row[2], row[3]
        contact_name = None
        if c_first and c_last:
            contact_name = f"{c_first} {c_last}"
        elif c_first or c_last:
            contact_name = c_first or c_last
        missed_calls_to_return.append({
            "id": call.id,
            "phone": call.phone_1,
            "contact_name": contact_name,
            "contact_id": str(contact_id) if contact_id else None,
            "created_at": call.created_at.isoformat() if call.created_at else None,
        })

    # Get new leads assigned to this operator
    new_leads_query = (
        select(Lead)
        .where(
            Lead.company_id == user.company_id,
            Lead.assigned_to == user.id,
            Lead.status == "new",
            Lead.deleted_at.is_(None),
        )
        .order_by(Lead.created_at.desc())
        .limit(20)
    )

    result = await session.execute(new_leads_query)
    new_leads_objs = result.scalars().all()

    new_leads = [
        {
            "id": str(lead.id),
            "title": lead.title,
            "source": lead.source,
            "estimated_value": float(lead.estimated_value) if lead.estimated_value else None,
            "contact_name": None,  # Could be enriched via contact_id if needed
            "created_at": lead.created_at.isoformat() if lead.created_at else None,
        }
        for lead in new_leads_objs
    ]

    # Get recent tasks (single query with limit)
    recent_tasks_query = select(Task).where(
        and_(Task.company_id == user.company_id, Task.assigned_to == user.id, Task.deleted_at.is_(None))
    ).order_by(Task.created_at.desc()).limit(5)

    result = await session.execute(recent_tasks_query)
    recent_tasks_objs = result.scalars().all()

    recent_tasks = [
        {
            "id": str(task.id),
            "title": task.title,
            "status": task.status.value if task.status else None,
            "due_date": task.due_date.isoformat() if task.due_date else None
        }
        for task in recent_tasks_objs
    ]

    dashboard = OperatorDashboard(
        today=today,
        this_week=this_week,
        this_month=this_month,
        upcoming_tasks=upcoming_tasks,
        pending_leads=today.leads.new_leads,
        active_deals=this_month.deals.total_deals - this_month.deals.won - this_month.deals.lost,
        recent_calls=recent_calls,
        recent_tasks=recent_tasks,
        missed_calls_to_return=missed_calls_to_return,
        new_leads=new_leads,
    )

    # Cache for 1 minute
    await cache.set_dashboard("operator", user.id, dashboard.model_dump(), ttl=60)

    return dashboard


# ===== Admin Analytics (Team Data) =====

@router.get("/team", response_model=TeamAnalytics)
@require_permissions(Permissions.STATS_READ)
async def get_team_analytics(
    admin: User = User.current(),
    session: AsyncSession = Depends(get_session),
    period: str = Query("month", description="today, week, month, year"),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None
):
    """
    Get team analytics (Admin only)

    OPTIMIZED: Uses SQL aggregations and single query for operator stats.
    Returns aggregated performance metrics for all operators.
    """
    cache = get_cache()

    # Try cache first
    cache_key = f"analytics:team:{admin.company_id}:{period}"
    if not date_from and not date_to:
        cached = await cache.get(cache_key)
        if cached:
            return TeamAnalytics(**cached)

    start_date, end_date = AnalyticsService.get_period_dates(period, date_from, date_to)

    # Get all active operators count (single query)
    operators_query = select(
        func.count().label('total'),
        func.count().filter(User.is_suspended == False).label('active')
    ).where(
        and_(
            User.company_id == admin.company_id,
            User.role == RoleEnum.COMPANY_OPERATOR,
            User.is_active == True,
            User.deleted_at.is_(None)
        )
    )
    result = await session.execute(operators_query)
    op_counts = result.one()

    # Get aggregate stats using optimized methods (4 queries total)
    calls = await AnalyticsService.get_call_stats(
        session, admin.company_id, None, start_date, end_date
    )
    leads = await AnalyticsService.get_lead_stats(
        session, admin.company_id, None, start_date, end_date
    )
    deals = await AnalyticsService.get_deal_stats(
        session, admin.company_id, None, start_date, end_date
    )
    tasks = await AnalyticsService.get_task_stats(
        session, admin.company_id, None, start_date, end_date
    )

    # Get top operators using optimized batch query (2 queries instead of N)
    top_operators = await AnalyticsService.get_top_operators_stats(
        session, admin.company_id, start_date, end_date, limit=5
    )

    # Build top performers list from aggregated data
    top_by_calls = top_operators.get("by_calls", [])
    top_by_revenue = top_operators.get("by_revenue", [])

    # Get user details for top performers (single query)
    user_ids = set()
    for item in top_by_calls + top_by_revenue:
        user_ids.add(item["user_id"])

    users_query = select(User).where(User.id.in_(list(user_ids)))
    result = await session.execute(users_query)
    users_map = {str(u.id): u for u in result.scalars().all()}

    # Build performance objects
    top_performers_by_calls = []
    top_performers_by_revenue = []

    for item in top_by_calls[:5]:
        user = users_map.get(item["user_id"])
        if user:
            top_performers_by_calls.append(OperatorPerformance(
                user_id=item["user_id"],
                name=user.full_name,
                email=user.email,
                calls=calls,  # Company-wide for now
                leads=leads,
                deals=deals,
                tasks=tasks,
                productivity_score=0
            ))

    for item in top_by_revenue[:5]:
        user = users_map.get(item["user_id"])
        if user:
            top_performers_by_revenue.append(OperatorPerformance(
                user_id=item["user_id"],
                name=user.full_name,
                email=user.email,
                calls=calls,
                leads=leads,
                deals=deals,
                tasks=tasks,
                productivity_score=0
            ))

    team_analytics = TeamAnalytics(
        period=period,
        date_from=start_date,
        date_to=end_date,
        total_operators=op_counts.total or 0,
        active_operators=op_counts.active or 0,
        calls=calls,
        leads=leads,
        deals=deals,
        tasks=tasks,
        total_revenue=deals.won_value,
        revenue_growth=0.0,
        top_operators_by_calls=top_performers_by_calls,
        top_operators_by_deals=top_performers_by_revenue,
        top_operators_by_revenue=top_performers_by_revenue
    )

    # Cache for 5 minutes
    if not date_from and not date_to:
        await cache.set(cache_key, team_analytics.model_dump(), ttl=300)

    return team_analytics


@router.get("/team/dashboard", response_model=AdminDashboard)
@require_permissions(Permissions.STATS_READ)
async def get_admin_dashboard(
    admin: User = User.current(),
    session: AsyncSession = Depends(get_session)
):
    """
    Get admin dashboard (Admin only)

    OPTIMIZED:
    - Uses caching (5 minute TTL)
    - Single query for trends instead of N queries
    - SQL aggregations for all stats
    """
    cache = get_cache()

    # Try cache first
    cached = await cache.get_dashboard("admin", admin.id)
    if cached:
        return AdminDashboard(**cached)

    # Get analytics for different periods (4 optimized SQL queries each)
    today = await AnalyticsService.get_operator_analytics(
        session, admin.company_id, None, "today"
    )
    this_week = await AnalyticsService.get_operator_analytics(
        session, admin.company_id, None, "week"
    )
    this_month = await AnalyticsService.get_operator_analytics(
        session, admin.company_id, None, "month"
    )
    this_year = await AnalyticsService.get_operator_analytics(
        session, admin.company_id, None, "year"
    )

    # Get business intelligence
    start_date, end_date = AnalyticsService.get_period_dates("month")
    conversion_funnel = await AnalyticsService.get_conversion_funnel(
        session, admin.company_id, start_date, end_date
    )
    pipeline_health = await AnalyticsService.get_pipeline_health(
        session, admin.company_id
    )

    # Get trends using SINGLE queries (not N queries!)
    calls_trend = await AnalyticsService.get_calls_trend(
        session, admin.company_id, days=7
    )
    revenue_trend = await AnalyticsService.get_revenue_trend(
        session, admin.company_id, days=30
    )

    # Get peak call hours (single query)
    peak_call_hours = await AnalyticsService.get_hourly_call_distribution(
        session, admin.company_id, days=7
    )

    now = datetime.now(timezone.utc)
    dashboard = AdminDashboard(
        today=TeamAnalytics(
            period="today",
            date_from=now.date(),
            date_to=now.date(),
            total_operators=0,
            active_operators=0,
            calls=today.calls,
            leads=today.leads,
            deals=today.deals,
            tasks=today.tasks,
            total_revenue=today.deals.won_value,
            revenue_growth=0.0
        ),
        this_week=TeamAnalytics(
            period="week",
            date_from=now.date() - timedelta(days=now.weekday()),
            date_to=now.date(),
            total_operators=0,
            active_operators=0,
            calls=this_week.calls,
            leads=this_week.leads,
            deals=this_week.deals,
            tasks=this_week.tasks,
            total_revenue=this_week.deals.won_value,
            revenue_growth=0.0
        ),
        this_month=TeamAnalytics(
            period="month",
            date_from=now.date().replace(day=1),
            date_to=now.date(),
            total_operators=0,
            active_operators=0,
            calls=this_month.calls,
            leads=this_month.leads,
            deals=this_month.deals,
            tasks=this_month.tasks,
            total_revenue=this_month.deals.won_value,
            revenue_growth=0.0
        ),
        this_year=TeamAnalytics(
            period="year",
            date_from=now.date().replace(month=1, day=1),
            date_to=now.date(),
            total_operators=0,
            active_operators=0,
            calls=this_year.calls,
            leads=this_year.leads,
            deals=this_year.deals,
            tasks=this_year.tasks,
            total_revenue=this_year.deals.won_value,
            revenue_growth=0.0
        ),
        conversion_funnel=conversion_funnel,
        pipeline_health=pipeline_health,
        peak_call_hours=peak_call_hours,
        calls_trend=calls_trend,
        revenue_trend=revenue_trend
    )

    # Cache for 5 minutes
    await cache.set_dashboard("admin", admin.id, dashboard.model_dump(), ttl=300)

    return dashboard


@router.get("/operator/{user_id}", response_model=OperatorAnalytics)
@require_permissions(Permissions.STATS_READ)
async def get_operator_analytics(
    user_id: str,
    admin: User = User.current(),
    session: AsyncSession = Depends(get_session),
    period: str = Query("month", description="today, week, month, year"),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None
):
    """
    Get specific operator analytics (Admin only)

    Returns performance metrics for a specific operator.
    Uses SQL aggregations for optimal performance.
    """
    from uuid import UUID

    # Verify operator belongs to same company
    operator = await User.get_or_404(
        session=session,
        id=UUID(user_id),
        company_id=admin.company_id
    )

    return await AnalyticsService.get_operator_analytics(
        session=session,
        company_id=admin.company_id,
        user_id=operator.id,
        period=period,
        date_from=date_from,
        date_to=date_to
    )


@router.delete("/cache")
@require_permissions(Permissions.STATS_READ)
async def clear_analytics_cache(
    admin: User = User.current()
):
    """
    Clear analytics cache for this company

    Use this after bulk data imports or when you need fresh data.
    """
    cache = get_cache()
    count = await cache.invalidate_company(admin.company_id)
    return {"cleared": count, "message": "Analytics cache cleared"}
