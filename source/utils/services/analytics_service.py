"""
Analytics Service - Calculate metrics and statistics

Provides analytics for operators, admins, and owners.
"""

from datetime import datetime, date, timedelta
from typing import Optional, Dict, Any, List
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from sqlalchemy.sql import text

from db.models.user import User
from db.models.call_event import CallEvent
from db.models.lead import Lead
from db.models.deal import Deal
from db.models.task import Task
from db.models.company import Company
from db.models.enums import CallDirectionEnum, LeadStatusEnum, DealStageEnum, TaskStatusEnum
from api.v1.schemas.analytics import (
    CallStats, LeadStats, DealStats, TaskStats,
    OperatorAnalytics, ConversionFunnel, PipelineHealth
)


class AnalyticsService:
    """Service for calculating analytics and statistics"""

    @staticmethod
    def get_period_dates(period: str, date_from: Optional[date] = None, date_to: Optional[date] = None) -> tuple:
        """
        Get start and end dates for a period

        Args:
            period: today, week, month, year, custom
            date_from: Custom start date (for period=custom)
            date_to: Custom end date (for period=custom)

        Returns:
            Tuple of (start_date, end_date)
        """
        now = datetime.now()
        today = now.date()

        if period == "today":
            return today, today
        elif period == "week":
            start = today - timedelta(days=today.weekday())
            return start, today
        elif period == "month":
            start = today.replace(day=1)
            return start, today
        elif period == "year":
            start = today.replace(month=1, day=1)
            return start, today
        elif period == "custom":
            if not date_from or not date_to:
                raise ValueError("date_from and date_to required for custom period")
            return date_from, date_to
        else:
            raise ValueError(f"Invalid period: {period}")

    @staticmethod
    async def get_call_stats(
        session: AsyncSession,
        company_id: UUID,
        user_id: Optional[UUID] = None,
        date_from: date = None,
        date_to: date = None
    ) -> CallStats:
        """
        Calculate call statistics

        Args:
            session: Database session
            company_id: Company ID
            user_id: Optional user ID (for operator-specific stats)
            date_from: Start date
            date_to: End date

        Returns:
            CallStats object
        """
        query = select(CallEvent).where(CallEvent.company_id == company_id)

        if user_id:
            query = query.where(CallEvent.operator_id == user_id)

        if date_from:
            query = query.where(func.date(CallEvent.started_at) >= date_from)
        if date_to:
            query = query.where(func.date(CallEvent.started_at) <= date_to)

        result = await session.execute(query)
        calls = result.scalars().all()

        total_calls = len(calls)
        if total_calls == 0:
            return CallStats()

        answered_calls = sum(1 for c in calls if c.status == "answered")
        missed_calls = sum(1 for c in calls if c.status in ["missed", "no_answer"])
        outbound_calls = sum(1 for c in calls if c.direction == CallDirectionEnum.OUTBOUND)
        inbound_calls = sum(1 for c in calls if c.direction == CallDirectionEnum.INBOUND)

        total_duration = sum(c.duration or 0 for c in calls)
        average_duration = total_duration / total_calls if total_calls > 0 else 0
        success_rate = (answered_calls / total_calls * 100) if total_calls > 0 else 0

        return CallStats(
            total_calls=total_calls,
            answered_calls=answered_calls,
            missed_calls=missed_calls,
            outbound_calls=outbound_calls,
            inbound_calls=inbound_calls,
            total_duration=total_duration,
            average_duration=average_duration,
            success_rate=round(success_rate, 2)
        )

    @staticmethod
    async def get_lead_stats(
        session: AsyncSession,
        company_id: UUID,
        user_id: Optional[UUID] = None,
        date_from: date = None,
        date_to: date = None
    ) -> LeadStats:
        """Calculate lead statistics"""
        query = select(Lead).where(Lead.company_id == company_id)

        if user_id:
            query = query.where(Lead.assigned_to == user_id)

        if date_from:
            query = query.where(func.date(Lead.created_at) >= date_from)
        if date_to:
            query = query.where(func.date(Lead.created_at) <= date_to)

        result = await session.execute(query)
        leads = result.scalars().all()

        total_leads = len(leads)
        if total_leads == 0:
            return LeadStats()

        new_leads = sum(1 for l in leads if l.status == LeadStatusEnum.NEW)
        contacted_leads = sum(1 for l in leads if l.status == LeadStatusEnum.CONTACTED)
        qualified_leads = sum(1 for l in leads if l.status == LeadStatusEnum.QUALIFIED)
        converted_leads = sum(1 for l in leads if l.status == LeadStatusEnum.CONVERTED)
        lost_leads = sum(1 for l in leads if l.status == LeadStatusEnum.LOST)

        conversion_rate = (converted_leads / total_leads * 100) if total_leads > 0 else 0

        return LeadStats(
            total_leads=total_leads,
            new_leads=new_leads,
            contacted_leads=contacted_leads,
            qualified_leads=qualified_leads,
            converted_leads=converted_leads,
            lost_leads=lost_leads,
            conversion_rate=round(conversion_rate, 2)
        )

    @staticmethod
    async def get_deal_stats(
        session: AsyncSession,
        company_id: UUID,
        user_id: Optional[UUID] = None,
        date_from: date = None,
        date_to: date = None
    ) -> DealStats:
        """Calculate deal statistics"""
        query = select(Deal).where(Deal.company_id == company_id)

        if user_id:
            query = query.where(Deal.assigned_to == user_id)

        if date_from:
            query = query.where(func.date(Deal.created_at) >= date_from)
        if date_to:
            query = query.where(func.date(Deal.created_at) <= date_to)

        result = await session.execute(query)
        deals = result.scalars().all()

        total_deals = len(deals)
        if total_deals == 0:
            return DealStats()

        prospecting = sum(1 for d in deals if d.stage == DealStageEnum.PROSPECTING)
        negotiation = sum(1 for d in deals if d.stage == DealStageEnum.NEGOTIATION)
        won = sum(1 for d in deals if d.stage == DealStageEnum.WON)
        lost = sum(1 for d in deals if d.stage == DealStageEnum.LOST)

        total_value = sum(d.value or 0 for d in deals)
        won_value = sum(d.value or 0 for d in deals if d.stage == DealStageEnum.WON)
        average_deal_size = total_value / total_deals if total_deals > 0 else 0
        win_rate = (won / total_deals * 100) if total_deals > 0 else 0

        return DealStats(
            total_deals=total_deals,
            prospecting=prospecting,
            negotiation=negotiation,
            won=won,
            lost=lost,
            total_value=total_value,
            won_value=won_value,
            average_deal_size=round(average_deal_size, 2),
            win_rate=round(win_rate, 2)
        )

    @staticmethod
    async def get_task_stats(
        session: AsyncSession,
        company_id: UUID,
        user_id: Optional[UUID] = None,
        date_from: date = None,
        date_to: date = None
    ) -> TaskStats:
        """Calculate task statistics"""
        query = select(Task).where(Task.company_id == company_id)

        if user_id:
            query = query.where(Task.assigned_to == user_id)

        if date_from:
            query = query.where(func.date(Task.created_at) >= date_from)
        if date_to:
            query = query.where(func.date(Task.created_at) <= date_to)

        result = await session.execute(query)
        tasks = result.scalars().all()

        total_tasks = len(tasks)
        if total_tasks == 0:
            return TaskStats()

        pending_tasks = sum(1 for t in tasks if t.status == TaskStatusEnum.PENDING)
        completed_tasks = sum(1 for t in tasks if t.status == TaskStatusEnum.COMPLETED)
        overdue_tasks = sum(1 for t in tasks if t.due_date and t.due_date < datetime.now() and t.status != TaskStatusEnum.COMPLETED)

        completion_rate = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0

        return TaskStats(
            total_tasks=total_tasks,
            pending_tasks=pending_tasks,
            completed_tasks=completed_tasks,
            overdue_tasks=overdue_tasks,
            completion_rate=round(completion_rate, 2)
        )

    @staticmethod
    async def get_operator_analytics(
        session: AsyncSession,
        company_id: UUID,
        user_id: UUID,
        period: str = "month",
        date_from: Optional[date] = None,
        date_to: Optional[date] = None
    ) -> OperatorAnalytics:
        """
        Get complete analytics for an operator

        Args:
            session: Database session
            company_id: Company ID
            user_id: User ID
            period: Period (today, week, month, year, custom)
            date_from: Custom start date
            date_to: Custom end date

        Returns:
            OperatorAnalytics object
        """
        start_date, end_date = AnalyticsService.get_period_dates(period, date_from, date_to)

        calls = await AnalyticsService.get_call_stats(session, company_id, user_id, start_date, end_date)
        leads = await AnalyticsService.get_lead_stats(session, company_id, user_id, start_date, end_date)
        deals = await AnalyticsService.get_deal_stats(session, company_id, user_id, start_date, end_date)
        tasks = await AnalyticsService.get_task_stats(session, company_id, user_id, start_date, end_date)

        # Calculate productivity score (0-100)
        # Based on: calls made, leads converted, deals won, tasks completed
        productivity_score = 0
        if calls.total_calls > 0:
            productivity_score += min(calls.total_calls / 10, 25)  # Up to 25 points for calls
        if leads.conversion_rate > 0:
            productivity_score += min(leads.conversion_rate, 25)  # Up to 25 points for lead conversion
        if deals.win_rate > 0:
            productivity_score += min(deals.win_rate, 25)  # Up to 25 points for deal win rate
        if tasks.completion_rate > 0:
            productivity_score += min(tasks.completion_rate * 0.25, 25)  # Up to 25 points for task completion

        total_activities = calls.total_calls + leads.total_leads + deals.total_deals + tasks.total_tasks

        return OperatorAnalytics(
            period=period,
            date_from=start_date,
            date_to=end_date,
            calls=calls,
            leads=leads,
            deals=deals,
            tasks=tasks,
            total_activities=total_activities,
            productivity_score=round(productivity_score, 2)
        )

    @staticmethod
    async def get_conversion_funnel(
        session: AsyncSession,
        company_id: UUID,
        date_from: date,
        date_to: date
    ) -> ConversionFunnel:
        """Calculate conversion funnel metrics"""
        # Get all leads in period
        leads_query = select(Lead).where(
            and_(
                Lead.company_id == company_id,
                func.date(Lead.created_at) >= date_from,
                func.date(Lead.created_at) <= date_to
            )
        )
        result = await session.execute(leads_query)
        leads = result.scalars().all()

        total_leads = len(leads)
        if total_leads == 0:
            return ConversionFunnel()

        contacted = sum(1 for l in leads if l.status in [LeadStatusEnum.CONTACTED, LeadStatusEnum.QUALIFIED, LeadStatusEnum.CONVERTED])
        qualified = sum(1 for l in leads if l.status in [LeadStatusEnum.QUALIFIED, LeadStatusEnum.CONVERTED])
        converted = sum(1 for l in leads if l.status == LeadStatusEnum.CONVERTED)

        # Get deals created from these leads
        deals_query = select(func.count()).select_from(Deal).where(
            and_(
                Deal.company_id == company_id,
                Deal.lead_id.in_([l.id for l in leads if l.id])
            )
        )
        deals_created = await session.scalar(deals_query) or 0

        deals_won = sum(1 for l in leads if l.status == LeadStatusEnum.CONVERTED)  # Assuming converted = deal won

        # Calculate rates
        contact_rate = (contacted / total_leads * 100) if total_leads > 0 else 0
        qualification_rate = (qualified / contacted * 100) if contacted > 0 else 0
        deal_rate = (deals_created / qualified * 100) if qualified > 0 else 0
        win_rate = (deals_won / deals_created * 100) if deals_created > 0 else 0
        overall_conversion = (deals_won / total_leads * 100) if total_leads > 0 else 0

        return ConversionFunnel(
            total_leads=total_leads,
            contacted=contacted,
            qualified=qualified,
            deals_created=deals_created,
            deals_won=deals_won,
            contact_rate=round(contact_rate, 2),
            qualification_rate=round(qualification_rate, 2),
            deal_rate=round(deal_rate, 2),
            win_rate=round(win_rate, 2),
            overall_conversion=round(overall_conversion, 2)
        )

    @staticmethod
    async def get_pipeline_health(
        session: AsyncSession,
        company_id: UUID
    ) -> PipelineHealth:
        """Calculate pipeline health metrics"""
        # Get all active deals
        query = select(Deal).where(
            and_(
                Deal.company_id == company_id,
                Deal.stage.notin_([DealStageEnum.WON, DealStageEnum.LOST])
            )
        )
        result = await session.execute(query)
        deals = result.scalars().all()

        total_value = sum(d.value or 0 for d in deals)
        weighted_value = sum((d.value or 0) * (d.probability or 0) / 100 for d in deals)

        # Group by stage
        by_stage = {}
        for stage in DealStageEnum:
            stage_deals = [d for d in deals if d.stage == stage]
            by_stage[stage.value] = {
                "count": len(stage_deals),
                "value": sum(d.value or 0 for d in stage_deals)
            }

        # Find stuck deals (no activity in 7+ days)
        seven_days_ago = datetime.now() - timedelta(days=7)
        stuck_deals = sum(1 for d in deals if d.updated_at < seven_days_ago)

        # Forecast (weighted value of deals in advanced stages)
        forecast = sum(
            (d.value or 0) * (d.probability or 0) / 100
            for d in deals
            if d.stage in [DealStageEnum.NEGOTIATION, DealStageEnum.PROPOSAL]
        )

        return PipelineHealth(
            total_value=total_value,
            weighted_value=round(weighted_value, 2),
            by_stage=by_stage,
            stuck_deals=stuck_deals,
            forecast=round(forecast, 2)
        )
