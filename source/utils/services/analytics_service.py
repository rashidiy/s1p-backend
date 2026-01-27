"""
Analytics Service - Calculate metrics and statistics

Optimized for high-load production:
- Uses SQL aggregations instead of loading data into memory
- Single queries with GROUP BY for trends
- Batch operations for multi-entity stats
"""

from datetime import datetime, date, timedelta
from typing import Optional, Dict, Any, List, Tuple
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, case, literal_column
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
    """
    Service for calculating analytics and statistics

    Optimized for production:
    - All aggregations done in SQL (not Python)
    - Single query per stat type
    - Batch queries for multiple periods
    """

    @staticmethod
    def get_period_dates(period: str, date_from: Optional[date] = None, date_to: Optional[date] = None) -> Tuple[date, date]:
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
        Calculate call statistics using SQL aggregations

        Single query returns all metrics - no data loaded into Python memory.
        """
        # Build filter conditions
        conditions = [CallEvent.company_id == company_id]
        if user_id:
            conditions.append(CallEvent.operator_id == user_id)
        if date_from:
            conditions.append(func.date(CallEvent.created_at) >= date_from)
        if date_to:
            conditions.append(func.date(CallEvent.created_at) <= date_to)

        # Single aggregation query
        query = select(
            func.count().label('total_calls'),
            func.count().filter(CallEvent.state == 'ANSWER').label('answered_calls'),
            func.count().filter(CallEvent.state.in_(['NOANSWER', 'BUSY', 'CANCEL'])).label('missed_calls'),
            func.count().filter(CallEvent.direction == CallDirectionEnum.OUTBOUND).label('outbound_calls'),
            func.count().filter(CallEvent.direction == CallDirectionEnum.INBOUND).label('inbound_calls'),
            func.coalesce(func.sum(CallEvent.billing_sec), 0).label('total_duration'),
            func.coalesce(func.avg(CallEvent.billing_sec), 0).label('average_duration')
        ).where(and_(*conditions))

        result = await session.execute(query)
        row = result.one()

        total_calls = row.total_calls or 0
        answered_calls = row.answered_calls or 0

        success_rate = (answered_calls / total_calls * 100) if total_calls > 0 else 0

        return CallStats(
            total_calls=total_calls,
            answered_calls=answered_calls,
            missed_calls=row.missed_calls or 0,
            outbound_calls=row.outbound_calls or 0,
            inbound_calls=row.inbound_calls or 0,
            total_duration=int(row.total_duration or 0),
            average_duration=float(row.average_duration or 0),
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
        """Calculate lead statistics using SQL aggregations"""
        conditions = [Lead.company_id == company_id, Lead.deleted_at.is_(None)]
        if user_id:
            conditions.append(Lead.assigned_to == user_id)
        if date_from:
            conditions.append(func.date(Lead.created_at) >= date_from)
        if date_to:
            conditions.append(func.date(Lead.created_at) <= date_to)

        query = select(
            func.count().label('total_leads'),
            func.count().filter(Lead.status == LeadStatusEnum.NEW).label('new_leads'),
            func.count().filter(Lead.status == LeadStatusEnum.CONTACTED).label('contacted_leads'),
            func.count().filter(Lead.status == LeadStatusEnum.QUALIFIED).label('qualified_leads'),
            func.count().filter(Lead.status == LeadStatusEnum.CONVERTED).label('converted_leads'),
            func.count().filter(Lead.status == LeadStatusEnum.LOST).label('lost_leads')
        ).where(and_(*conditions))

        result = await session.execute(query)
        row = result.one()

        total_leads = row.total_leads or 0
        converted_leads = row.converted_leads or 0
        conversion_rate = (converted_leads / total_leads * 100) if total_leads > 0 else 0

        return LeadStats(
            total_leads=total_leads,
            new_leads=row.new_leads or 0,
            contacted_leads=row.contacted_leads or 0,
            qualified_leads=row.qualified_leads or 0,
            converted_leads=converted_leads,
            lost_leads=row.lost_leads or 0,
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
        """Calculate deal statistics using SQL aggregations"""
        conditions = [Deal.company_id == company_id, Deal.deleted_at.is_(None)]
        if user_id:
            conditions.append(Deal.assigned_to == user_id)
        if date_from:
            conditions.append(func.date(Deal.created_at) >= date_from)
        if date_to:
            conditions.append(func.date(Deal.created_at) <= date_to)

        query = select(
            func.count().label('total_deals'),
            func.count().filter(Deal.stage == DealStageEnum.PROSPECTING).label('prospecting'),
            func.count().filter(Deal.stage == DealStageEnum.NEGOTIATION).label('negotiation'),
            func.count().filter(Deal.stage == DealStageEnum.CLOSED_WON).label('won'),
            func.count().filter(Deal.stage == DealStageEnum.CLOSED_LOST).label('lost'),
            func.coalesce(func.sum(Deal.amount), 0).label('total_value'),
            func.coalesce(
                func.sum(case((Deal.stage == DealStageEnum.CLOSED_WON, Deal.amount), else_=0)),
                0
            ).label('won_value')
        ).where(and_(*conditions))

        result = await session.execute(query)
        row = result.one()

        total_deals = row.total_deals or 0
        won = row.won or 0
        total_value = float(row.total_value or 0)

        average_deal_size = total_value / total_deals if total_deals > 0 else 0
        win_rate = (won / total_deals * 100) if total_deals > 0 else 0

        return DealStats(
            total_deals=total_deals,
            prospecting=row.prospecting or 0,
            negotiation=row.negotiation or 0,
            won=won,
            lost=row.lost or 0,
            total_value=total_value,
            won_value=float(row.won_value or 0),
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
        """Calculate task statistics using SQL aggregations"""
        conditions = [Task.company_id == company_id, Task.deleted_at.is_(None)]
        if user_id:
            conditions.append(Task.assigned_to == user_id)
        if date_from:
            conditions.append(func.date(Task.created_at) >= date_from)
        if date_to:
            conditions.append(func.date(Task.created_at) <= date_to)

        now = datetime.now()

        query = select(
            func.count().label('total_tasks'),
            func.count().filter(Task.status == TaskStatusEnum.PENDING).label('pending_tasks'),
            func.count().filter(Task.status == TaskStatusEnum.COMPLETED).label('completed_tasks'),
            func.count().filter(
                and_(
                    Task.due_date < now,
                    Task.status != TaskStatusEnum.COMPLETED
                )
            ).label('overdue_tasks')
        ).where(and_(*conditions))

        result = await session.execute(query)
        row = result.one()

        total_tasks = row.total_tasks or 0
        completed_tasks = row.completed_tasks or 0
        completion_rate = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0

        return TaskStats(
            total_tasks=total_tasks,
            pending_tasks=row.pending_tasks or 0,
            completed_tasks=completed_tasks,
            overdue_tasks=row.overdue_tasks or 0,
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

        Makes 4 optimized SQL queries (one per entity type).
        """
        start_date, end_date = AnalyticsService.get_period_dates(period, date_from, date_to)

        # Run all stats queries (each is now a single optimized SQL query)
        calls = await AnalyticsService.get_call_stats(session, company_id, user_id, start_date, end_date)
        leads = await AnalyticsService.get_lead_stats(session, company_id, user_id, start_date, end_date)
        deals = await AnalyticsService.get_deal_stats(session, company_id, user_id, start_date, end_date)
        tasks = await AnalyticsService.get_task_stats(session, company_id, user_id, start_date, end_date)

        # Calculate productivity score (0-100)
        productivity_score = 0
        if calls.total_calls > 0:
            productivity_score += min(calls.total_calls / 10, 25)
        if leads.conversion_rate > 0:
            productivity_score += min(leads.conversion_rate, 25)
        if deals.win_rate > 0:
            productivity_score += min(deals.win_rate, 25)
        if tasks.completion_rate > 0:
            productivity_score += min(tasks.completion_rate * 0.25, 25)

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
    async def get_all_stats_batch(
        session: AsyncSession,
        company_id: UUID,
        user_id: Optional[UUID] = None,
        date_from: date = None,
        date_to: date = None
    ) -> Dict[str, Any]:
        """
        Get all stats in a single batch operation

        More efficient than calling individual methods when you need all stats.
        """
        calls = await AnalyticsService.get_call_stats(session, company_id, user_id, date_from, date_to)
        leads = await AnalyticsService.get_lead_stats(session, company_id, user_id, date_from, date_to)
        deals = await AnalyticsService.get_deal_stats(session, company_id, user_id, date_from, date_to)
        tasks = await AnalyticsService.get_task_stats(session, company_id, user_id, date_from, date_to)

        return {
            "calls": calls,
            "leads": leads,
            "deals": deals,
            "tasks": tasks
        }

    @staticmethod
    async def get_calls_trend(
        session: AsyncSession,
        company_id: UUID,
        days: int = 7
    ) -> List[Dict[str, Any]]:
        """
        Get calls trend for the last N days in a SINGLE query

        Uses GROUP BY date instead of N separate queries.
        """
        start_date = datetime.now().date() - timedelta(days=days - 1)

        query = select(
            func.date(CallEvent.created_at).label('date'),
            func.count().label('calls')
        ).where(
            and_(
                CallEvent.company_id == company_id,
                func.date(CallEvent.created_at) >= start_date
            )
        ).group_by(
            func.date(CallEvent.created_at)
        ).order_by(
            func.date(CallEvent.created_at)
        )

        result = await session.execute(query)
        rows = result.all()

        # Build complete date range (fill missing dates with 0)
        trend_dict = {row.date: row.calls for row in rows}
        trend = []
        for i in range(days):
            day = start_date + timedelta(days=i)
            trend.append({
                "date": day.isoformat(),
                "calls": trend_dict.get(day, 0)
            })

        return trend

    @staticmethod
    async def get_revenue_trend(
        session: AsyncSession,
        company_id: UUID,
        days: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Get revenue trend for the last N days in a SINGLE query

        Uses GROUP BY date instead of N separate queries.
        """
        start_date = datetime.now().date() - timedelta(days=days - 1)

        query = select(
            func.date(Deal.created_at).label('date'),
            func.coalesce(
                func.sum(case((Deal.stage == DealStageEnum.CLOSED_WON, Deal.amount), else_=0)),
                0
            ).label('revenue')
        ).where(
            and_(
                Deal.company_id == company_id,
                Deal.deleted_at.is_(None),
                func.date(Deal.created_at) >= start_date
            )
        ).group_by(
            func.date(Deal.created_at)
        ).order_by(
            func.date(Deal.created_at)
        )

        result = await session.execute(query)
        rows = result.all()

        # Build complete date range
        trend_dict = {row.date: float(row.revenue) for row in rows}
        trend = []
        for i in range(days):
            day = start_date + timedelta(days=i)
            trend.append({
                "date": day.isoformat(),
                "revenue": trend_dict.get(day, 0.0)
            })

        return trend

    @staticmethod
    async def get_platform_stats_aggregated(
        session: AsyncSession,
        company_ids: List[UUID],
        date_from: date,
        date_to: date
    ) -> Dict[str, Any]:
        """
        Get aggregated stats across multiple companies in SINGLE queries

        Used by owner analytics - avoids N queries per company.
        """
        if not company_ids:
            return {
                "total_calls": 0,
                "total_leads": 0,
                "total_deals": 0,
                "total_revenue": 0.0
            }

        # Calls aggregation across all companies
        calls_query = select(
            func.count().label('total_calls')
        ).where(
            and_(
                CallEvent.company_id.in_(company_ids),
                func.date(CallEvent.created_at) >= date_from,
                func.date(CallEvent.created_at) <= date_to
            )
        )

        # Leads aggregation
        leads_query = select(
            func.count().label('total_leads')
        ).where(
            and_(
                Lead.company_id.in_(company_ids),
                Lead.deleted_at.is_(None),
                func.date(Lead.created_at) >= date_from,
                func.date(Lead.created_at) <= date_to
            )
        )

        # Deals aggregation
        deals_query = select(
            func.count().label('total_deals'),
            func.coalesce(
                func.sum(case((Deal.stage == DealStageEnum.CLOSED_WON, Deal.amount), else_=0)),
                0
            ).label('total_revenue')
        ).where(
            and_(
                Deal.company_id.in_(company_ids),
                Deal.deleted_at.is_(None),
                func.date(Deal.created_at) >= date_from,
                func.date(Deal.created_at) <= date_to
            )
        )

        # Execute all queries
        calls_result = await session.execute(calls_query)
        leads_result = await session.execute(leads_query)
        deals_result = await session.execute(deals_query)

        calls_row = calls_result.one()
        leads_row = leads_result.one()
        deals_row = deals_result.one()

        return {
            "total_calls": calls_row.total_calls or 0,
            "total_leads": leads_row.total_leads or 0,
            "total_deals": deals_row.total_deals or 0,
            "total_revenue": float(deals_row.total_revenue or 0)
        }

    @staticmethod
    async def get_top_companies_stats(
        session: AsyncSession,
        company_ids: List[UUID],
        date_from: date,
        date_to: date,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get stats per company with ranking in a SINGLE query

        Uses GROUP BY company_id instead of N queries.
        """
        if not company_ids:
            return []

        # Get deal stats grouped by company
        query = select(
            Deal.company_id,
            func.count().label('total_deals'),
            func.coalesce(
                func.sum(case((Deal.stage == DealStageEnum.CLOSED_WON, Deal.amount), else_=0)),
                0
            ).label('total_revenue')
        ).where(
            and_(
                Deal.company_id.in_(company_ids),
                Deal.deleted_at.is_(None),
                func.date(Deal.created_at) >= date_from,
                func.date(Deal.created_at) <= date_to
            )
        ).group_by(Deal.company_id).order_by(
            func.sum(case((Deal.stage == DealStageEnum.CLOSED_WON, Deal.amount), else_=0)).desc()
        ).limit(limit)

        result = await session.execute(query)
        rows = result.all()

        return [
            {
                "company_id": str(row.company_id),
                "total_deals": row.total_deals,
                "total_revenue": float(row.total_revenue)
            }
            for row in rows
        ]

    @staticmethod
    async def get_top_operators_stats(
        session: AsyncSession,
        company_id: UUID,
        date_from: date,
        date_to: date,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Get top operators by various metrics in optimized queries

        Returns operators ranked by calls, deals, and revenue.
        """
        # Top by calls
        calls_query = select(
            CallEvent.operator_id,
            func.count().label('total_calls')
        ).where(
            and_(
                CallEvent.company_id == company_id,
                CallEvent.operator_id.isnot(None),
                func.date(CallEvent.created_at) >= date_from,
                func.date(CallEvent.created_at) <= date_to
            )
        ).group_by(CallEvent.operator_id).order_by(
            func.count().desc()
        ).limit(limit)

        # Top by deals/revenue
        deals_query = select(
            Deal.assigned_to,
            func.count().label('total_deals'),
            func.coalesce(
                func.sum(case((Deal.stage == DealStageEnum.CLOSED_WON, Deal.amount), else_=0)),
                0
            ).label('total_revenue')
        ).where(
            and_(
                Deal.company_id == company_id,
                Deal.assigned_to.isnot(None),
                Deal.deleted_at.is_(None),
                func.date(Deal.created_at) >= date_from,
                func.date(Deal.created_at) <= date_to
            )
        ).group_by(Deal.assigned_to).order_by(
            func.sum(case((Deal.stage == DealStageEnum.CLOSED_WON, Deal.amount), else_=0)).desc()
        ).limit(limit)

        calls_result = await session.execute(calls_query)
        deals_result = await session.execute(deals_query)

        return {
            "by_calls": [
                {"user_id": str(row.operator_id), "total_calls": row.total_calls}
                for row in calls_result.all()
            ],
            "by_revenue": [
                {
                    "user_id": str(row.assigned_to),
                    "total_deals": row.total_deals,
                    "total_revenue": float(row.total_revenue)
                }
                for row in deals_result.all()
            ]
        }

    @staticmethod
    async def get_conversion_funnel(
        session: AsyncSession,
        company_id: UUID,
        date_from: date,
        date_to: date
    ) -> ConversionFunnel:
        """Calculate conversion funnel metrics using SQL aggregations"""
        # Get lead stats by status
        leads_query = select(
            func.count().label('total_leads'),
            func.count().filter(
                Lead.status.in_([LeadStatusEnum.CONTACTED, LeadStatusEnum.QUALIFIED, LeadStatusEnum.CONVERTED])
            ).label('contacted'),
            func.count().filter(
                Lead.status.in_([LeadStatusEnum.QUALIFIED, LeadStatusEnum.CONVERTED])
            ).label('qualified'),
            func.count().filter(Lead.status == LeadStatusEnum.CONVERTED).label('converted')
        ).where(
            and_(
                Lead.company_id == company_id,
                Lead.deleted_at.is_(None),
                func.date(Lead.created_at) >= date_from,
                func.date(Lead.created_at) <= date_to
            )
        )

        result = await session.execute(leads_query)
        row = result.one()

        total_leads = row.total_leads or 0
        contacted = row.contacted or 0
        qualified = row.qualified or 0
        converted = row.converted or 0

        if total_leads == 0:
            return ConversionFunnel()

        # Get deals created from leads in this period
        deals_query = select(
            func.count().label('deals_created'),
            func.count().filter(Deal.stage == DealStageEnum.CLOSED_WON).label('deals_won')
        ).where(
            and_(
                Deal.company_id == company_id,
                Deal.lead_id.isnot(None),
                Deal.deleted_at.is_(None),
                func.date(Deal.created_at) >= date_from,
                func.date(Deal.created_at) <= date_to
            )
        )

        deals_result = await session.execute(deals_query)
        deals_row = deals_result.one()

        deals_created = deals_row.deals_created or 0
        deals_won = deals_row.deals_won or 0

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
        """Calculate pipeline health metrics using SQL aggregations"""
        seven_days_ago = datetime.now() - timedelta(days=7)

        # Get pipeline stats in a single query
        query = select(
            func.count().label('total_deals'),
            func.coalesce(func.sum(Deal.amount), 0).label('total_value'),
            func.coalesce(
                func.sum(Deal.amount * Deal.probability / 100),
                0
            ).label('weighted_value'),
            func.count().filter(Deal.updated_at < seven_days_ago).label('stuck_deals'),
            func.coalesce(
                func.sum(
                    case(
                        (Deal.stage.in_([DealStageEnum.NEGOTIATION, DealStageEnum.PROPOSAL]),
                         Deal.amount * Deal.probability / 100),
                        else_=0
                    )
                ),
                0
            ).label('forecast')
        ).where(
            and_(
                Deal.company_id == company_id,
                Deal.deleted_at.is_(None),
                Deal.stage.notin_([DealStageEnum.CLOSED_WON, DealStageEnum.CLOSED_LOST])
            )
        )

        result = await session.execute(query)
        row = result.one()

        # Get by-stage breakdown
        stage_query = select(
            Deal.stage,
            func.count().label('count'),
            func.coalesce(func.sum(Deal.amount), 0).label('value')
        ).where(
            and_(
                Deal.company_id == company_id,
                Deal.deleted_at.is_(None),
                Deal.stage.notin_([DealStageEnum.CLOSED_WON, DealStageEnum.CLOSED_LOST])
            )
        ).group_by(Deal.stage)

        stage_result = await session.execute(stage_query)

        by_stage = {}
        for stage in DealStageEnum:
            by_stage[stage.value] = {"count": 0, "value": 0}

        for stage_row in stage_result.all():
            by_stage[stage_row.stage.value] = {
                "count": stage_row.count,
                "value": float(stage_row.value)
            }

        return PipelineHealth(
            total_value=float(row.total_value or 0),
            weighted_value=round(float(row.weighted_value or 0), 2),
            by_stage=by_stage,
            stuck_deals=row.stuck_deals or 0,
            forecast=round(float(row.forecast or 0), 2)
        )

    @staticmethod
    async def get_hourly_call_distribution(
        session: AsyncSession,
        company_id: UUID,
        days: int = 7
    ) -> List[Dict[str, int]]:
        """
        Get call distribution by hour of day

        Useful for identifying peak call hours.
        """
        start_date = datetime.now() - timedelta(days=days)

        query = select(
            func.extract('hour', CallEvent.created_at).label('hour'),
            func.count().label('calls')
        ).where(
            and_(
                CallEvent.company_id == company_id,
                CallEvent.created_at >= start_date
            )
        ).group_by(
            func.extract('hour', CallEvent.created_at)
        ).order_by(
            func.extract('hour', CallEvent.created_at)
        )

        result = await session.execute(query)
        rows = result.all()

        # Build complete 24-hour distribution
        hour_dict = {int(row.hour): row.calls for row in rows}
        return [
            {"hour": h, "calls": hour_dict.get(h, 0)}
            for h in range(24)
        ]
