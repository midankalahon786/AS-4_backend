"""
Pydantic v2 schemas for the Analytics and Reporting microservice.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ══════════════════════════════════════════════════════════════
#  Audit Logs & Notifications (Mapped Entities)
# ══════════════════════════════════════════════════════════════

class AuditLogBase(BaseModel):
    table_name: str
    record_id: UUID
    operation_type: str
    old_values: dict[str, Any] | None = None
    new_values: dict[str, Any] | None = None
    performed_by: UUID
    ip_address: str | None = None
    user_agent: str | None = None


class AuditLogCreate(AuditLogBase):
    pass


class AuditLogResponse(AuditLogBase):
    model_config = ConfigDict(from_attributes=True)

    audit_id: UUID
    performed_at: datetime


class NotificationBase(BaseModel):
    employee_id: UUID
    title: str
    message: str
    type: str


class NotificationCreate(NotificationBase):
    pass


class NotificationResponse(NotificationBase):
    model_config = ConfigDict(from_attributes=True)

    notification_id: UUID
    is_read: bool
    email_sent: bool
    created_at: datetime
    read_at: datetime | None = None
    send_attempts: int


# ══════════════════════════════════════════════════════════════
#  Employee Dashboard Schemas
# ══════════════════════════════════════════════════════════════

class RecentReview(BaseModel):
    """A single review received by the employee."""

    model_config = ConfigDict(from_attributes=True)

    review_id: UUID
    reviewer_name: str
    tags: list[str]
    comment: str
    review_at: datetime


class LeaderboardEntry(BaseModel):
    """A single row in the points leaderboard."""

    model_config = ConfigDict(from_attributes=True)

    rank: int
    employee_id: UUID
    username: str
    department: str
    total_earned_points: int


class MetricWithGrowth(BaseModel):
    """A numeric KPI paired with this month vs last month values."""

    value: int = Field(0, description="Lifetime / current total value")
    this_month: int = Field(0, description="Value for the current month")
    last_month: int = Field(0, description="Value for the previous month")


class PlatformStats(BaseModel):
    """Platform-wide statistics with month-over-month growth."""

    total_points: MetricWithGrowth
    rewards_redeemed: MetricWithGrowth
    reviews_received: MetricWithGrowth
    active_users: MetricWithGrowth


# ══════════════════════════════════════════════════════════════
#  Admin — Team Report Schemas
# ══════════════════════════════════════════════════════════════

class TeamMemberReport(BaseModel):
    """A single employee's stats within a team report."""

    model_config = ConfigDict(from_attributes=True)

    employee_id: UUID
    username: str
    designation: str
    total_earned_points: int
    available_points: int
    reviews_received: int
    rewards_redeemed: int
    reviews_this_month: int
    points_this_month: int
    performance_score: float = Field(
        description="0–100 composite score normalised within the team"
    )


class TeamReport(BaseModel):
    """Full report for a single department, including member breakdown."""

    model_config = ConfigDict(from_attributes=True)

    department_id: UUID
    department_name: str
    total_members: int
    total_points: int
    total_reviews: int
    total_rewards: int
    avg_performance_score: float
    members: list[TeamMemberReport]


class TeamSummary(BaseModel):
    """Lightweight card data for the admin teams overview grid."""

    model_config = ConfigDict(from_attributes=True)

    department_id: UUID
    department_name: str
    total_members: int
    total_points: int
    avg_performance_score: float


# ══════════════════════════════════════════════════════════════
#  Admin — Participation Overview Schemas
# ══════════════════════════════════════════════════════════════

class ParticipationSlice(BaseModel):
    name: str
    value: float  # percentage of total active employees


class ParticipationStats(BaseModel):
    total_employees: int
    active_participants: int
    non_participants: int
    participation_rate: float
    avg_reviews_per_employee: float
    avg_reviews_last_month: float


class DepartmentParticipation(BaseModel):
    department_id: UUID
    name: str
    rate: float   # participation % within this department
    active: int   # employees who gave or received at least one review
    total: int    # total active employees in department


class ParticipationOverview(BaseModel):
    pie: list[ParticipationSlice]
    stats: ParticipationStats
    by_department: list[DepartmentParticipation]


# ══════════════════════════════════════════════════════════════
#  Admin — Recognition Trend Schemas
# ══════════════════════════════════════════════════════════════

class TrendPoint(BaseModel):
    label: str
    given: int     # distinct reviewers in this bucket
    received: int  # total reviews in this bucket


class RecognitionTrend(BaseModel):
    data: list[TrendPoint]


# ══════════════════════════════════════════════════════════════
#  Admin — Recognition Overview Schemas
# ══════════════════════════════════════════════════════════════

class UserRecognition(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    employee_id: UUID
    username: str
    department: str
    given: int     # reviews this employee gave
    received: int  # reviews this employee received


class TeamRecognition(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    department_id: UUID
    name: str
    given: int     # total reviews given by team members
    received: int  # total reviews received by team members
    members: int   # headcount


class PaginatedUserRecognition(BaseModel):
    items: list[UserRecognition]
    total: int
    page: int
    limit: int
    pages: int


class PaginatedTeamRecognition(BaseModel):
    items: list[TeamRecognition]
    total: int
    page: int
    limit: int
    pages: int