"""
src/analytics/router.py
───────────────────────
Router for dashboard analytics, team reporting, audit logs, and notifications.
"""
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.analytics.dependencies import get_analytics_service
from src.analytics.schemas import (
    AuditLogCreate,
    AuditLogResponse,
    LeaderboardEntry,
    NotificationResponse,
    PaginatedTeamRecognition,
    PaginatedUserRecognition,
    ParticipationOverview,
    PlatformStats,
    RecentReview,
    RecognitionTrend,
    TeamMemberReport,
    TeamReport,
    TeamSummary,
)
from src.analytics.service import AnalyticsService
from src.common.dependencies import CurrentUser, check_route_permission

router = APIRouter(tags=["Analytics"])

_auth = Depends(check_route_permission)


# ══════════════════════════════════════════════════════════════
#  Employee Dashboard Routes
# ══════════════════════════════════════════════════════════════

@router.get(
    "/recent-reviews",
    response_model=list[RecentReview],
    summary="Recent Reviews",
    description="Get the last 5 reviews received by the authenticated employee, or organization-wide if admin",
)
async def recent_reviews(
    employee_id: UUID | None = Query(None, description="Optional target employee UUID (admins only)"),
    current_user: CurrentUser = _auth,
    service: AnalyticsService = Depends(get_analytics_service),
):
    """Return up to 5 most recent reviews, newest first."""
    is_admin = any(r in current_user.roles for r in ("SUPER_ADMIN", "ADMIN", "HR_ADMIN", "HR_MANAGER"))
    if is_admin:
        target_id = str(employee_id) if employee_id else None
    else:
        target_id = str(current_user.id)
    return await service.get_recent_reviews_list(target_id)


@router.get(
    "/leaderboard",
    response_model=list[LeaderboardEntry],
    summary="Leaderboard",
    description="Get the top 10 employees ranked by total earned points",
)
async def leaderboard(
    current_user: CurrentUser = _auth,
    service: AnalyticsService = Depends(get_analytics_service),
):
    """Return the top 10 employees ranked by total earned points."""
    return await service.get_leaderboard_list()


@router.get(
    "/platform-stats",
    response_model=PlatformStats,
    summary="Platform Stats",
    description="Get platform KPIs with month-over-month growth for the authenticated user, or platform-wide for admin",
)
async def platform_stats(
    employee_id: UUID | None = Query(None, description="Optional target employee UUID (admins only)"),
    current_user: CurrentUser = _auth,
    service: AnalyticsService = Depends(get_analytics_service),
):
    """Return four KPIs (total_points, rewards_redeemed, reviews_received, active_users)."""
    is_admin = any(r in current_user.roles for r in ("SUPER_ADMIN", "ADMIN", "HR_ADMIN", "HR_MANAGER"))
    if is_admin:
        target_id = str(employee_id) if employee_id else None
        return await service.get_platform_stats(employee_id=target_id, is_admin=employee_id is None)
    else:
        return await service.get_platform_stats(employee_id=str(current_user.id), is_admin=False)


# ══════════════════════════════════════════════════════════════
#  Admin — Team Report Routes (HR_ADMIN / SUPER_ADMIN)
# ══════════════════════════════════════════════════════════════

@router.get(
    "/teams",
    response_model=list[TeamSummary],
    summary="All Teams Summary",
    description=(
        "Returns a summary card for every department. "
        "Accessible by HR_ADMIN and SUPER_ADMIN only."
    ),
)
async def list_teams(
    current_user: CurrentUser = _auth,
    service: AnalyticsService = Depends(get_analytics_service),
):
    """Return lightweight summary cards for all departments."""
    return await service.get_teams_summary()


@router.get(
    "/teams/{department_id}",
    response_model=TeamReport,
    summary="Team Detail Report",
    description=(
        "Returns a full report for one department, including per-member "
        "stats and performance scores. HR_ADMIN / SUPER_ADMIN only."
    ),
)
async def team_detail(
    department_id: UUID,
    current_user: CurrentUser = _auth,
    service: AnalyticsService = Depends(get_analytics_service),
):
    """Return full team report with member breakdown ordered by performance score."""
    report = await service.get_team_report(str(department_id))
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Department '{department_id}' not found",
        )
    return report


# ══════════════════════════════════════════════════════════════
#  Admin — Participation Overview (HR_ADMIN / SUPER_ADMIN)
# ══════════════════════════════════════════════════════════════

@router.get(
    "/participation",
    response_model=ParticipationOverview,
    summary="Participation Overview",
    description=(
        "Returns pie-chart slices, key stats cards, and per-department "
        "participation rates. SUPER_ADMIN / HR_ADMIN only."
    ),
)
async def participation_overview(
    current_user: CurrentUser = _auth,
    service: AnalyticsService = Depends(get_analytics_service),
):
    """Return participation breakdown for the admin overview tab."""
    return await service.get_participation_overview()


# ══════════════════════════════════════════════════════════════
#  Admin — Recognition Trend (HR_ADMIN / SUPER_ADMIN)
# ══════════════════════════════════════════════════════════════

@router.get(
    "/recognition-trend",
    response_model=RecognitionTrend,
    summary="Recognition Trend",
    description=(
        "Returns time-series review activity. "
        "range=3m -> 12 weekly buckets; range=6m -> 6 monthly; range=1y -> 12 monthly. "
        "SUPER_ADMIN / HR_ADMIN only."
    ),
)
async def recognition_trend(
    range: Literal["3m", "6m", "1y"] = Query("6m", description="Time range: 3m | 6m | 1y"),
    current_user: CurrentUser = _auth,
    service: AnalyticsService = Depends(get_analytics_service),
):
    return await service.get_recognition_trend(range_=range)


# ══════════════════════════════════════════════════════════════
#  Admin — Recognition Breakdown (HR_ADMIN / SUPER_ADMIN)
# ══════════════════════════════════════════════════════════════

@router.get(
    "/recognition/users",
    response_model=PaginatedUserRecognition,
    summary="Recognition — Per User",
    description=(
        "Paginated list of employees with given/received review counts for the period. "
        "Sorted by given descending. "
        "range: week | month | quarter | year. SUPER_ADMIN / HR_ADMIN only."
    ),
)
async def recognition_users(
    range: Literal["week", "month", "quarter", "year"] = Query(
        "month", description="week | month | quarter | year"
    ),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: CurrentUser = _auth,
    service: AnalyticsService = Depends(get_analytics_service),
):
    return await service.get_recognition_users(range_=range, page=page, limit=limit)


@router.get(
    "/recognition/teams",
    response_model=PaginatedTeamRecognition,
    summary="Recognition — Per Team",
    description=(
        "Paginated list of departments with aggregated given/received review counts and headcount. "
        "Sorted by given descending. "
        "range: week | month | quarter | year. SUPER_ADMIN / HR_ADMIN only."
    ),
)
async def recognition_teams(
    range: Literal["week", "month", "quarter", "year"] = Query(
        "month", description="week | month | quarter | year"
    ),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    limit: int = Query(10, ge=1, le=50, description="Items per page"),
    current_user: CurrentUser = _auth,
    service: AnalyticsService = Depends(get_analytics_service),
):
    return await service.get_recognition_teams(range_=range, page=page, limit=limit)


# ══════════════════════════════════════════════════════════════
#  Audit Logs & Notifications (Local Table Management)
# ══════════════════════════════════════════════════════════════

@router.post(
    "/audit-logs",
    response_model=AuditLogResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Audit Log",
)
async def create_audit_log(
    payload: AuditLogCreate,
    current_user: CurrentUser = _auth,
    service: AnalyticsService = Depends(get_analytics_service),
):
    return await service.record_audit(payload)


@router.get(
    "/audit-logs/{table_name}/{record_id}",
    response_model=list[AuditLogResponse],
    summary="Get Record Audit History",
)
async def get_audit_history(
    table_name: str,
    record_id: UUID,
    limit: int = Query(default=50, ge=1, le=100),
    current_user: CurrentUser = _auth,
    service: AnalyticsService = Depends(get_analytics_service),
):
    return await service.list_audit_history(table_name=table_name, record_id=record_id, limit=limit)


@router.get(
    "/notifications/{employee_id}",
    response_model=list[NotificationResponse],
    summary="Get Employee Notifications",
)
async def get_notifications(
    employee_id: UUID,
    unread_only: bool = Query(default=False),
    current_user: CurrentUser = _auth,
    service: AnalyticsService = Depends(get_analytics_service),
):
    return await service.get_notifications(employee_id=employee_id, unread_only=unread_only)


@router.patch(
    "/notifications/{notification_id}/read",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Mark Notification as Read",
)
async def mark_notification_read(
    notification_id: UUID,
    current_user: CurrentUser = _auth,
    service: AnalyticsService = Depends(get_analytics_service),
):
    success = await service.read_notification(notification_id=notification_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )