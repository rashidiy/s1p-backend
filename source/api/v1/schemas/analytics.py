"""
Analytics schemas for dashboard and reporting
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, date
from pydantic import BaseModel, Field


# ===== Operator Analytics (Personal Performance) =====

class CallStats(BaseModel):
    """Call statistics"""
    total_calls: int = 0
    answered_calls: int = 0
    missed_calls: int = 0
    outbound_calls: int = 0
    inbound_calls: int = 0
    total_duration: int = 0  # seconds
    average_duration: float = 0.0  # seconds
    success_rate: float = 0.0  # percentage


class LeadStats(BaseModel):
    """Lead statistics"""
    total_leads: int = 0
    new_leads: int = 0
    contacted_leads: int = 0
    qualified_leads: int = 0
    converted_leads: int = 0
    lost_leads: int = 0
    conversion_rate: float = 0.0  # percentage


class DealStats(BaseModel):
    """Deal statistics"""
    total_deals: int = 0
    prospecting: int = 0
    negotiation: int = 0
    won: int = 0
    lost: int = 0
    total_value: float = 0.0
    won_value: float = 0.0
    average_deal_size: float = 0.0
    win_rate: float = 0.0  # percentage


class TaskStats(BaseModel):
    """Task statistics"""
    total_tasks: int = 0
    pending_tasks: int = 0
    completed_tasks: int = 0
    overdue_tasks: int = 0
    completion_rate: float = 0.0  # percentage


class OperatorAnalytics(BaseModel):
    """Operator personal analytics"""
    period: str = Field(..., description="today, week, month, year")
    date_from: date
    date_to: date

    calls: CallStats
    leads: LeadStats
    deals: DealStats
    tasks: TaskStats

    # Activity summary
    total_activities: int = 0
    productivity_score: float = 0.0  # 0-100


class OperatorDashboard(BaseModel):
    """Operator dashboard data"""
    today: OperatorAnalytics
    this_week: OperatorAnalytics
    this_month: OperatorAnalytics

    # Quick stats
    upcoming_tasks: int = 0
    pending_leads: int = 0
    active_deals: int = 0

    # Recent activity
    recent_calls: List[Dict[str, Any]] = []
    recent_tasks: List[Dict[str, Any]] = []

    # Mini app extras
    missed_calls_to_return: List[Dict[str, Any]] = []
    new_leads: List[Dict[str, Any]] = []


# ===== Admin Analytics (Team Performance) =====

class OperatorPerformance(BaseModel):
    """Individual operator performance"""
    user_id: str
    name: str
    email: str

    calls: CallStats
    leads: LeadStats
    deals: DealStats
    tasks: TaskStats

    productivity_score: float = 0.0


class TeamAnalytics(BaseModel):
    """Team-wide analytics (for admins)"""
    period: str
    date_from: date
    date_to: date

    # Aggregate stats
    total_operators: int = 0
    active_operators: int = 0

    calls: CallStats
    leads: LeadStats
    deals: DealStats
    tasks: TaskStats

    # Revenue metrics
    total_revenue: float = 0.0
    revenue_growth: float = 0.0  # percentage vs previous period

    # Top performers
    top_operators_by_calls: List[OperatorPerformance] = []
    top_operators_by_deals: List[OperatorPerformance] = []
    top_operators_by_revenue: List[OperatorPerformance] = []


class ConversionFunnel(BaseModel):
    """Lead conversion funnel"""
    total_leads: int = 0
    contacted: int = 0
    qualified: int = 0
    deals_created: int = 0
    deals_won: int = 0

    # Conversion rates
    contact_rate: float = 0.0
    qualification_rate: float = 0.0
    deal_rate: float = 0.0
    win_rate: float = 0.0
    overall_conversion: float = 0.0


class PipelineHealth(BaseModel):
    """Sales pipeline health"""
    total_value: float = 0.0
    weighted_value: float = 0.0  # value * probability

    by_stage: Dict[str, Any] = {}
    stuck_deals: int = 0  # deals not moving
    forecast: float = 0.0  # expected revenue


class AdminDashboard(BaseModel):
    """Admin dashboard data"""
    today: TeamAnalytics
    this_week: TeamAnalytics
    this_month: TeamAnalytics
    this_year: TeamAnalytics

    # Business intelligence
    conversion_funnel: ConversionFunnel
    pipeline_health: PipelineHealth

    # Peak hours analysis
    peak_call_hours: List[Dict[str, Any]] = []

    # Trends
    calls_trend: List[Dict[str, Any]] = []  # last 7 days
    revenue_trend: List[Dict[str, Any]] = []  # last 30 days


# ===== Owner Analytics (Platform-Wide) =====

class CompanyPerformance(BaseModel):
    """Individual company performance"""
    company_id: str
    company_name: str

    total_users: int = 0
    active_users: int = 0

    total_calls: int = 0
    total_leads: int = 0
    total_deals: int = 0
    total_revenue: float = 0.0

    growth_rate: float = 0.0  # percentage


class PlatformAnalytics(BaseModel):
    """Platform-wide analytics (for owners)"""
    period: str
    date_from: date
    date_to: date

    # Platform metrics
    total_companies: int = 0
    active_companies: int = 0
    total_users: int = 0
    active_users: int = 0

    # Aggregate stats
    total_calls: int = 0
    total_leads: int = 0
    total_deals: int = 0
    total_revenue: float = 0.0

    # Growth metrics
    new_companies: int = 0
    new_users: int = 0
    revenue_growth: float = 0.0

    # Top performers
    top_companies: List[CompanyPerformance] = []


class OwnerDashboard(BaseModel):
    """Owner platform dashboard"""
    today: PlatformAnalytics
    this_week: PlatformAnalytics
    this_month: PlatformAnalytics
    this_year: PlatformAnalytics

    # System health
    system_health: Dict[str, Any] = {}

    # Trends
    growth_trend: List[Dict[str, Any]] = []
    churn_analysis: Dict[str, Any] = {}


# ===== Common =====

class AnalyticsPeriod(BaseModel):
    """Analytics period filter"""
    period: str = Field("month", description="today, week, month, year, custom")
    date_from: Optional[date] = None
    date_to: Optional[date] = None


class ExportRequest(BaseModel):
    """Analytics export request"""
    period: str
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    format: str = Field("csv", description="csv, excel, pdf")
    filters: Optional[Dict[str, Any]] = None
