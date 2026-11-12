"""
src/analytics/service.py
─────────────────────────
Loosely coupled Analytics Service.
Accepts contracts (IAnalyticsDataProvider, IAnalyticsRepository) for all data acquisition.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any
import uuid

from src.analytics.interfaces import IAnalyticsDataProvider, IAnalyticsRepository
from src.analytics.models import AuditLog, Notification
from src.analytics.schemas import (
    AuditLogCreate,
    LeaderboardEntry,
    MetricWithGrowth,
    NotificationCreate,
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
from src.common.cache import (
    L1_SHORT,
    L1_VOLATILE,
    TTL_SHORT,
    TTL_VOLATILE,
    cache_delete,
    cache_get,
    cache_set,
    invalidate_pattern,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Cache-key helpers
# ─────────────────────────────────────────────────────────────────────────────

def _key_reviews(employee_id: str | None)  -> str: return f"dashboard:reviews:{employee_id or 'all'}"
def _key_leaderboard()                     -> str: return "dashboard:leaderboard"
def _key_platform(employee_id: str | None) -> str: return f"dashboard:platform:{employee_id or 'all'}"
def _key_teams()                           -> str: return "dashboard:teams"
def _key_team(dept_id: str)                -> str: return f"dashboard:team:{dept_id}"


class AnalyticsService:
    def __init__(
        self,
        provider: IAnalyticsDataProvider,
        repo: IAnalyticsRepository | None = None,
    ) -> None:
        self.provider = provider
        self.repo = repo

    # ─────────────────────────────────────────────────────────────────────────
    # Local Entity Methods (Audit & Notifications)
    # ─────────────────────────────────────────────────────────────────────────

    async def record_audit(self, payload: AuditLogCreate) -> AuditLog:
        if not self.repo:
            raise RuntimeError("Repository was not provided to AnalyticsService")
        return await self.repo.create_audit_log(payload)

    async def list_audit_history(
        self, table_name: str, record_id: uuid.UUID, limit: int = 50
    ) -> list[AuditLog]:
        if not self.repo:
            raise RuntimeError("Repository was not provided to AnalyticsService")
        return await self.repo.get_audit_logs(table_name, record_id, limit)

    async def notify_employee(self, payload: NotificationCreate) -> Notification:
        if not self.repo:
            raise RuntimeError("Repository was not provided to AnalyticsService")
        return await self.repo.create_notification(payload)

    async def get_notifications(
        self, employee_id: uuid.UUID, unread_only: bool = False
    ) -> list[Notification]:
        if not self.repo:
            raise RuntimeError("Repository was not provided to AnalyticsService")
        return await self.repo.get_employee_notifications(employee_id, unread_only)

    async def read_notification(self, notification_id: uuid.UUID) -> bool:
        if not self.repo:
            raise RuntimeError("Repository was not provided to AnalyticsService")
        return await self.repo.mark_notification_read(notification_id)

    # ─────────────────────────────────────────────────────────────────────────
    # Cache Invalidation Helpers
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    async def invalidate_reviews(employee_id: str) -> None:
        await cache_delete(_key_reviews(employee_id))
        await cache_delete(_key_platform(employee_id))

    @staticmethod
    async def invalidate_leaderboard() -> None:
        await cache_delete(_key_leaderboard())

    @staticmethod
    async def invalidate_teams() -> None:
        await cache_delete(_key_teams())
        await invalidate_pattern("dashboard:team:*")

    # ─────────────────────────────────────────────────────────────────────────
    # Dashboard Aggregations (Foreign Domain Queries)
    # ─────────────────────────────────────────────────────────────────────────

    async def get_recent_reviews_list(self, employee_id: str | None = None) -> list[RecentReview]:
        key = _key_reviews(employee_id)
        cached = await cache_get(key, l1_ttl=L1_VOLATILE)
        if cached is not None:
            return [RecentReview(**r) for r in cached]

        raw = await self.provider.get_recent_reviews(employee_id, limit=5)
        out = [
            RecentReview(
                review_id=r["review_id"],
                reviewer_name=r.get("reviewer_name") or "Unknown",
                tags=r.get("category_codes") or [t.get("category_code", "") for t in r.get("category_tags", []) if t.get("category_code")],
                comment=r["comment"],
                review_at=r["review_at"],
            )
            for r in raw
        ]

        await cache_set(key, [o.model_dump(mode="json") for o in out], ttl=TTL_VOLATILE, l1_ttl=L1_VOLATILE)
        return out

    async def get_leaderboard_list(self) -> list[LeaderboardEntry]:
        key = _key_leaderboard()
        cached = await cache_get(key, l1_ttl=L1_SHORT)
        if cached is not None:
            return [LeaderboardEntry(**e) for e in cached]

        raw = await self.provider.get_leaderboard_data(limit=10)
        out = [LeaderboardEntry(**row) for row in raw]

        await cache_set(key, [o.model_dump(mode="json") for o in out], ttl=TTL_SHORT, l1_ttl=L1_SHORT)
        return out

    async def get_platform_stats(self, employee_id: str | None = None, is_admin: bool = False) -> PlatformStats:
        target_id = None if is_admin else employee_id
        key = _key_platform(target_id)
        cached = await cache_get(key, l1_ttl=L1_VOLATILE)
        if cached is not None:
            return PlatformStats(**cached)

        wallet_stats, review_stats, active_counts = await asyncio.gather(
            self.provider.get_wallet_stats(target_id),
            self.provider.get_review_stats(target_id),
            self.provider.get_active_users_count(),
        )

        result = PlatformStats(
            total_points=MetricWithGrowth(
                value=wallet_stats.get("total_earned_points", 0),
                this_month=wallet_stats.get("pts_this_month", 0),
                last_month=wallet_stats.get("pts_last_month", 0),
            ),
            rewards_redeemed=MetricWithGrowth(
                value=wallet_stats.get("rewards_total", 0),
                this_month=wallet_stats.get("rewards_this_month", 0),
                last_month=wallet_stats.get("rewards_last_month", 0),
            ),
            reviews_received=MetricWithGrowth(
                value=review_stats.get("reviews_total", 0),
                this_month=review_stats.get("reviews_this_month", 0),
                last_month=review_stats.get("reviews_last_month", 0),
            ),
            active_users=MetricWithGrowth(
                value=active_counts.get("now", 0),
                this_month=active_counts.get("now", 0),
                last_month=active_counts.get("last_month", 0),
            ),
        )

        await cache_set(key, result.model_dump(mode="json"), ttl=TTL_VOLATILE, l1_ttl=L1_VOLATILE)
        return result

    async def get_teams_summary(self) -> list[TeamSummary]:
        key = _key_teams()
        cached = await cache_get(key, l1_ttl=L1_SHORT)
        if cached is not None:
            return [TeamSummary(**t) for t in cached]

        departments_data = await self.provider.get_departments_with_members()

        all_emp_ids = [
            m["employee_id"]
            for dept in departments_data
            for m in dept.get("members", [])
        ]

        wallet_map, review_map = await asyncio.gather(
            self.provider.get_wallet_stats_batch(all_emp_ids),
            self.provider.get_review_stats_batch(all_emp_ids),
        )

        out = []
        for dept in departments_data:
            report = self._build_team_report_from_maps(dept, wallet_map, review_map)
            out.append(TeamSummary(
                department_id=dept["department_id"],
                department_name=dept["department_name"],
                total_members=report.total_members,
                total_points=report.total_points,
                avg_performance_score=report.avg_performance_score,
            ))

        await cache_set(key, [o.model_dump(mode="json") for o in out], ttl=TTL_SHORT, l1_ttl=L1_SHORT)
        return out

    async def get_team_report(self, department_id: str) -> TeamReport | None:
        key = _key_team(department_id)
        cached = await cache_get(key, l1_ttl=L1_SHORT)
        if cached is not None:
            return TeamReport(**cached)

        departments_data = await self.provider.get_departments_with_members()
        dept = next(
            (d for d in departments_data if str(d["department_id"]) == str(department_id)),
            None,
        )
        if dept is None:
            return None

        emp_ids = [m["employee_id"] for m in dept.get("members", [])]

        wallet_map, review_map = await asyncio.gather(
            self.provider.get_wallet_stats_batch(emp_ids),
            self.provider.get_review_stats_batch(emp_ids),
        )

        report = self._build_team_report_from_maps(dept, wallet_map, review_map)
        await cache_set(key, report.model_dump(mode="json"), ttl=TTL_SHORT, l1_ttl=L1_SHORT)
        return report

    @staticmethod
    def _build_team_report_from_maps(
        dept: dict[str, Any],
        wallet_map: dict[str, Any],
        review_map: dict[str, Any],
    ) -> TeamReport:
        members_info = dept.get("members", [])
        if not members_info:
            return TeamReport(
                department_id=dept["department_id"],
                department_name=dept["department_name"],
                total_members=0,
                total_points=0,
                total_reviews=0,
                total_rewards=0,
                avg_performance_score=0.0,
                members=[],
            )

        members_raw = []
        for m in members_info:
            eid = str(m["employee_id"])
            wallet_s = wallet_map.get(eid, {})
            review_s = review_map.get(eid, {})
            members_raw.append({
                "employee_id": eid,
                "username": m["username"],
                "designation": m["designation_name"],
                "total_earned_points": wallet_s.get("total_earned_points", 0),
                "available_points": wallet_s.get("available_points", 0),
                "reviews_received": review_s.get("reviews_total", 0),
                "rewards_redeemed": wallet_s.get("rewards_total", 0),
                "reviews_this_month": review_s.get("reviews_this_month", 0),
                "points_this_month": wallet_s.get("pts_this_month", 0),
            })

        max_pts = max(m["total_earned_points"] for m in members_raw) or 1
        max_rev = max(m["reviews_received"] for m in members_raw) or 1

        members_scored = [
            TeamMemberReport(
                **m,
                performance_score=round(
                    (0.70 * m["total_earned_points"] / max_pts
                     + 0.30 * m["reviews_received"] / max_rev) * 100,
                    1,
                ),
            )
            for m in members_raw
        ]
        members_scored.sort(key=lambda x: x.performance_score, reverse=True)

        total_points = sum(m["total_earned_points"] for m in members_raw)
        total_reviews = sum(m["reviews_received"] for m in members_raw)
        total_rewards = sum(m["rewards_redeemed"] for m in members_raw)
        avg_score = round(
            sum(m.performance_score for m in members_scored) / len(members_scored), 1
        )

        return TeamReport(
            department_id=dept["department_id"],
            department_name=dept["department_name"],
            total_members=len(members_info),
            total_points=total_points,
            total_reviews=total_reviews,
            total_rewards=total_rewards,
            avg_performance_score=avg_score,
            members=members_scored,
        )

    async def get_participation_overview(self) -> ParticipationOverview:
        key = "dashboard:participation"
        cached = await cache_get(key, l1_ttl=L1_SHORT)
        if cached is not None:
            return ParticipationOverview(**cached)

        data = await self.provider.get_participation_overview()
        result = ParticipationOverview(**data)

        await cache_set(key, result.model_dump(mode="json"), ttl=TTL_SHORT, l1_ttl=L1_SHORT)
        return result

    async def get_recognition_trend(self, range_: str) -> RecognitionTrend:
        key = f"dashboard:trend:{range_}"
        cached = await cache_get(key, l1_ttl=L1_SHORT)
        if cached is not None:
            return RecognitionTrend(**cached)

        data = await self.provider.get_recognition_trend(range_)
        result = RecognitionTrend(**data)

        await cache_set(key, result.model_dump(mode="json"), ttl=TTL_SHORT, l1_ttl=L1_SHORT)
        return result

    async def get_recognition_users(
        self, range_: str, page: int, limit: int
    ) -> PaginatedUserRecognition:
        key = f"dashboard:recognition_users:{range_}:{page}:{limit}"
        cached = await cache_get(key, l1_ttl=L1_SHORT)
        if cached is not None:
            return PaginatedUserRecognition(**cached)

        data = await self.provider.get_recognition_by_user(range_, page, limit)
        result = PaginatedUserRecognition(**data)

        await cache_set(key, result.model_dump(mode="json"), ttl=TTL_SHORT, l1_ttl=L1_SHORT)
        return result

    async def get_recognition_teams(
        self, range_: str, page: int, limit: int
    ) -> PaginatedTeamRecognition:
        key = f"dashboard:recognition_teams:{range_}:{page}:{limit}"
        cached = await cache_get(key, l1_ttl=L1_SHORT)
        if cached is not None:
            return PaginatedTeamRecognition(**cached)

        data = await self.provider.get_recognition_by_team(range_, page, limit)
        result = PaginatedTeamRecognition(**data)

        await cache_set(key, result.model_dump(mode="json"), ttl=TTL_SHORT, l1_ttl=L1_SHORT)
        return result