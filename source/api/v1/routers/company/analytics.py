"""
Analytics endpoints for operators and admins
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from typing import Optional
from datetime import date, datetime, timedelta

from db import get_session
from db.models.user import User
from db.models.call_event import CallEvent
from db.models.task import Task
from db.models.enums import RoleEnum, TaskStatusEnum
from api.v1.schemas.analytics import (
    OperatorAnalytics,
    OperatorDashboard,
    TeamAnalytics,
    AdminDashboard,
    OperatorPerformance,
    AnalyticsPeriod
)
from utils.services.analytics_service import AnalyticsService
from utils.permissions import require_permissions, Permissions

router = APIRouter(prefix="/analytics", tags=["Analytics"])


# ===== Operator Analytics (Own Data) =====

@router.get("/me", response_model=OperatorAnalytics)
async def get_my_analytics(
    user: User = Depends(User.current),
    session: AsyncSession = Depends(get_session),
    period: str = Query("month", description="today, week, month, year"),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None
):
    """
    Get my personal analytics (Operator/Anyone)

    Returns performance metrics for the current user.
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
    user: User = Depends(User.current),
    session: AsyncSession = Depends(get_session)
):
    """
    Get my dashboard data (Operator/Anyone)

    Returns dashboard with today, week, and month analytics plus quick stats.
    """
    # Get analytics for different periods
    today = await AnalyticsService.get_operator_analytics(
        session, user.company_id, user.id, "today"
    )
    this_week = await AnalyticsService.get_operator_analytics(
        session, user.company_id, user.id, "week"
    )
    this_month = await AnalyticsService.get_operator_analytics(
        session, user.company_id, user.id, "month"
    )

    # Get quick stats
    upcoming_tasks = await session.scalar(
        select(func.count()).select_from(Task).where(
            and_(
                Task.assigned_to == user.id,
                Task.status == TaskStatusEnum.PENDING,
                Task.due_date >= datetime.now()
            )
        )
    ) or 0

    # Get recent calls (last 5)
    recent_calls_query = select(CallEvent).where(
        CallEvent.operator_id == user.id
    ).order_by(CallEvent.started_at.desc()).limit(5)

    result = await session.execute(recent_calls_query)
    recent_calls_objs = result.scalars().all()

    recent_calls = [
        {
            "id": str(call.id),
            "phone": call.phone_2 or call.phone_1,
            "direction": call.direction.value if call.direction else None,
            "duration": call.duration,
            "started_at": call.started_at.isoformat() if call.started_at else None
        }
        for call in recent_calls_objs
    ]

    # Get recent tasks (last 5)
    recent_tasks_query = select(Task).where(
        Task.assigned_to == user.id
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

    return OperatorDashboard(
        today=today,
        this_week=this_week,
        this_month=this_month,
        upcoming_tasks=upcoming_tasks,
        pending_leads=today.leads.new_leads,
        active_deals=this_month.deals.total_deals - this_month.deals.won - this_month.deals.lost,
        recent_calls=recent_calls,
        recent_tasks=recent_tasks
    )


# ===== Admin Analytics (Team Data) =====

@router.get("/team", response_model=TeamAnalytics)
@require_permissions(Permissions.STATS_READ)
async def get_team_analytics(
    admin: User = Depends(User.current),
    session: AsyncSession = Depends(get_session),
    period: str = Query("month", description="today, week, month, year"),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None
):
    """
    Get team analytics (Admin only)

    Returns aggregated performance metrics for all operators.
    """
    start_date, end_date = AnalyticsService.get_period_dates(period, date_from, date_to)

    # Get all active operators
    operators_query = select(User).where(
        and_(
            User.company_id == admin.company_id,
            User.role == RoleEnum.COMPANY_OPERATOR,
            User.is_active == True
        )
    )
    result = await session.execute(operators_query)
    operators = result.scalars().all()

    total_operators = len(operators)
    active_operators = sum(1 for op in operators if not op.is_suspended)

    # Aggregate stats
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

    # Get top performers
    top_performers_by_calls = []
    top_performers_by_deals = []
    top_performers_by_revenue = []

    for operator in operators[:5]:  # Top 5
        op_analytics = await AnalyticsService.get_operator_analytics(
            session, admin.company_id, operator.id, period, date_from, date_to
        )

        perf = OperatorPerformance(
            user_id=str(operator.id),
            name=operator.full_name,
            email=operator.email,
            calls=op_analytics.calls,
            leads=op_analytics.leads,
            deals=op_analytics.deals,
            tasks=op_analytics.tasks,
            productivity_score=op_analytics.productivity_score
        )

        top_performers_by_calls.append(perf)
        top_performers_by_deals.append(perf)
        top_performers_by_revenue.append(perf)

    # Sort top performers
    top_performers_by_calls.sort(key=lambda x: x.calls.total_calls, reverse=True)
    top_performers_by_deals.sort(key=lambda x: x.deals.total_deals, reverse=True)
    top_performers_by_revenue.sort(key=lambda x: x.deals.won_value, reverse=True)

    return TeamAnalytics(
        period=period,
        date_from=start_date,
        date_to=end_date,
        total_operators=total_operators,
        active_operators=active_operators,
        calls=calls,
        leads=leads,
        deals=deals,
        tasks=tasks,
        total_revenue=deals.won_value,
        revenue_growth=0.0,  # TODO: Calculate vs previous period
        top_operators_by_calls=top_performers_by_calls[:5],
        top_operators_by_deals=top_performers_by_deals[:5],
        top_operators_by_revenue=top_performers_by_revenue[:5]
    )


@router.get("/team/dashboard", response_model=AdminDashboard)
@require_permissions(Permissions.STATS_READ)
async def get_admin_dashboard(
    admin: User = Depends(User.current),
    session: AsyncSession = Depends(get_session)
):
    """
    Get admin dashboard (Admin only)

    Returns comprehensive business intelligence dashboard.
    """
    # Get analytics for different periods
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

    # Generate trends (last 7 days for calls, last 30 days for revenue)
    calls_trend = []
    for i in range(7):
        day = datetime.now().date() - timedelta(days=6 - i)
        day_calls = await AnalyticsService.get_call_stats(
            session, admin.company_id, None, day, day
        )
        calls_trend.append({
            "date": day.isoformat(),
            "calls": day_calls.total_calls
        })

    revenue_trend = []
    for i in range(30):
        day = datetime.now().date() - timedelta(days=29 - i)
        day_deals = await AnalyticsService.get_deal_stats(
            session, admin.company_id, None, day, day
        )
        revenue_trend.append({
            "date": day.isoformat(),
            "revenue": day_deals.won_value
        })

    # Peak call hours (mock data for now - would need hourly aggregation)
    peak_call_hours = [
        {"hour": h, "calls": 0} for h in range(24)
    ]

    return AdminDashboard(
        today=TeamAnalytics(
            period="today",
            date_from=datetime.now().date(),
            date_to=datetime.now().date(),
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
            date_from=datetime.now().date() - timedelta(days=datetime.now().weekday()),
            date_to=datetime.now().date(),
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
            date_from=datetime.now().date().replace(day=1),
            date_to=datetime.now().date(),
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
            date_from=datetime.now().date().replace(month=1, day=1),
            date_to=datetime.now().date(),
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


@router.get("/operator/{user_id}", response_model=OperatorAnalytics)
@require_permissions(Permissions.STATS_READ)
async def get_operator_analytics(
    user_id: str,
    admin: User = Depends(User.current),
    session: AsyncSession = Depends(get_session),
    period: str = Query("month", description="today, week, month, year"),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None
):
    """
    Get specific operator analytics (Admin only)

    Returns performance metrics for a specific operator.
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
