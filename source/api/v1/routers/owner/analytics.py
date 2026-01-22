"""
Owner analytics endpoints (Platform-wide)
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional
from datetime import date, datetime

from db import get_session
from db.models.owner import Owner
from db.models.company import Company
from db.models.user import User
from db.models.call_event import CallEvent
from db.models.lead import Lead
from db.models.deal import Deal
from api.v1.schemas.analytics import (
    PlatformAnalytics,
    OwnerDashboard,
    CompanyPerformance
)
from utils.services.analytics_service import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["Owner Analytics"])


@router.get("/platform", response_model=PlatformAnalytics)
async def get_platform_analytics(
    owner: Owner = Depends(Owner.current),
    session: AsyncSession = Depends(get_session),
    period: str = Query("month", description="today, week, month, year"),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None
):
    """
    Get platform-wide analytics (Owner only)

    Returns aggregated metrics across all companies.
    """
    start_date, end_date = AnalyticsService.get_period_dates(period, date_from, date_to)

    # Get all companies owned by this owner
    companies_query = select(Company).where(Company.owner_id == owner.id)
    result = await session.execute(companies_query)
    companies = result.scalars().all()

    total_companies = len(companies)
    active_companies = sum(1 for c in companies if c.is_active)

    # Get all users across all companies
    users_query = select(User).where(User.company_id.in_([c.id for c in companies]))
    result = await session.execute(users_query)
    users = result.scalars().all()

    total_users = len(users)
    active_users = sum(1 for u in users if u.is_active and not u.is_suspended)

    # Aggregate platform-wide stats
    total_calls = 0
    total_leads = 0
    total_deals = 0
    total_revenue = 0.0

    for company in companies:
        # Get company stats
        calls = await AnalyticsService.get_call_stats(
            session, company.id, None, start_date, end_date
        )
        leads = await AnalyticsService.get_lead_stats(
            session, company.id, None, start_date, end_date
        )
        deals = await AnalyticsService.get_deal_stats(
            session, company.id, None, start_date, end_date
        )

        total_calls += calls.total_calls
        total_leads += leads.total_leads
        total_deals += deals.total_deals
        total_revenue += deals.won_value

    # Calculate new companies/users in period
    new_companies_query = select(func.count()).select_from(Company).where(
        Company.owner_id == owner.id,
        func.date(Company.created_at) >= start_date,
        func.date(Company.created_at) <= end_date
    )
    new_companies = await session.scalar(new_companies_query) or 0

    new_users_query = select(func.count()).select_from(User).where(
        User.company_id.in_([c.id for c in companies]),
        func.date(User.created_at) >= start_date,
        func.date(User.created_at) <= end_date
    )
    new_users = await session.scalar(new_users_query) or 0

    # Get top companies
    top_companies = []
    for company in companies[:10]:  # Top 10
        company_users = [u for u in users if u.company_id == company.id]
        company_calls = await AnalyticsService.get_call_stats(
            session, company.id, None, start_date, end_date
        )
        company_leads = await AnalyticsService.get_lead_stats(
            session, company.id, None, start_date, end_date
        )
        company_deals = await AnalyticsService.get_deal_stats(
            session, company.id, None, start_date, end_date
        )

        top_companies.append(CompanyPerformance(
            company_id=str(company.id),
            company_name=company.name,
            total_users=len(company_users),
            active_users=sum(1 for u in company_users if u.is_active),
            total_calls=company_calls.total_calls,
            total_leads=company_leads.total_leads,
            total_deals=company_deals.total_deals,
            total_revenue=company_deals.won_value,
            growth_rate=0.0  # TODO: Calculate vs previous period
        ))

    # Sort by revenue
    top_companies.sort(key=lambda x: x.total_revenue, reverse=True)

    return PlatformAnalytics(
        period=period,
        date_from=start_date,
        date_to=end_date,
        total_companies=total_companies,
        active_companies=active_companies,
        total_users=total_users,
        active_users=active_users,
        total_calls=total_calls,
        total_leads=total_leads,
        total_deals=total_deals,
        total_revenue=total_revenue,
        new_companies=new_companies,
        new_users=new_users,
        revenue_growth=0.0,  # TODO: Calculate vs previous period
        top_companies=top_companies[:10]
    )


@router.get("/dashboard", response_model=OwnerDashboard)
async def get_owner_dashboard(
    owner: Owner = Depends(Owner.current),
    session: AsyncSession = Depends(get_session)
):
    """
    Get owner dashboard (Owner only)

    Returns comprehensive platform health and trends.
    """
    # Get analytics for different periods (using a helper function to avoid duplication)
    async def get_platform_data(period: str) -> PlatformAnalytics:
        start_date, end_date = AnalyticsService.get_period_dates(period)

        companies_query = select(Company).where(Company.owner_id == owner.id)
        result = await session.execute(companies_query)
        companies = result.scalars().all()

        total_companies = len(companies)
        active_companies = sum(1 for c in companies if c.is_active)

        users_query = select(User).where(User.company_id.in_([c.id for c in companies]))
        result = await session.execute(users_query)
        users = result.scalars().all()

        total_users = len(users)
        active_users = sum(1 for u in users if u.is_active)

        total_calls = 0
        total_leads = 0
        total_deals = 0
        total_revenue = 0.0

        for company in companies:
            calls = await AnalyticsService.get_call_stats(session, company.id, None, start_date, end_date)
            leads = await AnalyticsService.get_lead_stats(session, company.id, None, start_date, end_date)
            deals = await AnalyticsService.get_deal_stats(session, company.id, None, start_date, end_date)

            total_calls += calls.total_calls
            total_leads += leads.total_leads
            total_deals += deals.total_deals
            total_revenue += deals.won_value

        return PlatformAnalytics(
            period=period,
            date_from=start_date,
            date_to=end_date,
            total_companies=total_companies,
            active_companies=active_companies,
            total_users=total_users,
            active_users=active_users,
            total_calls=total_calls,
            total_leads=total_leads,
            total_deals=total_deals,
            total_revenue=total_revenue,
            new_companies=0,
            new_users=0,
            revenue_growth=0.0
        )

    today = await get_platform_data("today")
    this_week = await get_platform_data("week")
    this_month = await get_platform_data("month")
    this_year = await get_platform_data("year")

    # System health (placeholder)
    system_health = {
        "status": "healthy",
        "uptime": "99.9%",
        "total_api_calls": 0,
        "average_response_time": "120ms"
    }

    # Growth trend (last 30 days)
    growth_trend = []
    from datetime import timedelta
    for i in range(30):
        day = datetime.now().date() - timedelta(days=29 - i)
        day_data = await get_platform_data("custom")
        growth_trend.append({
            "date": day.isoformat(),
            "companies": day_data.total_companies,
            "users": day_data.total_users,
            "revenue": day_data.total_revenue
        })

    # Churn analysis (placeholder)
    churn_analysis = {
        "churned_companies": 0,
        "churn_rate": 0.0,
        "reasons": []
    }

    return OwnerDashboard(
        today=today,
        this_week=this_week,
        this_month=this_month,
        this_year=this_year,
        system_health=system_health,
        growth_trend=growth_trend,
        churn_analysis=churn_analysis
    )
