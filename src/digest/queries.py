"""
src/digest/queries.py
─────────────────────
SQLAlchemy 2.0 async database queries for the weekly recognition digest[cite: 34].
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from src.digest.schemas import TopPerformer, WeeklyDigestData
from src.employees.models import Employee, StatusMaster
from src.recognition.models import Review


def get_week_boundaries(week_start: datetime | None = None) -> tuple[datetime, datetime]:
    """Return Monday 00:00:00 UTC → Sunday 23:59:59 UTC[cite: 34]."""
    if week_start is None:
        today = datetime.now(tz=timezone.utc).date()
        days_since_monday = today.weekday()
        last_monday = today - timedelta(days=days_since_monday + 7)
        start = datetime(last_monday.year, last_monday.month, last_monday.day, tzinfo=timezone.utc)
    else:
        start = week_start.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)

    end = start + timedelta(days=7) - timedelta(seconds=1)
    return start, end


async def get_direct_report_ids(session: AsyncSession, manager_id: UUID) -> list[UUID]:
    """Return employee_ids of all direct reports of the given manager[cite: 34]."""
    stmt = select(Employee.employee_id).where(Employee.manager_id == manager_id)
    return list((await session.execute(stmt)).scalars().all())


async def fetch_weekly_digest_data(
    session: AsyncSession,
    week_start: datetime | None = None,
    manager_id: UUID | None = None,
) -> WeeklyDigestData:
    start, end = get_week_boundaries(week_start)

    empty = WeeklyDigestData(
        week_start=start,
        week_end=end,
        total_recognitions=0,
        total_points_awarded=0.0,
        unique_givers=0,
        unique_receivers=0,
    )

    # 1. Resolve approved status IDs
    status_stmt = select(StatusMaster.status_id).where(
        StatusMaster.status_code.in_(["REVIEW_ACTIVE", "ACTIVE"]),
        StatusMaster.entity_type == "REVIEW",
    )
    approved_status_ids = list((await session.execute(status_stmt)).scalars().all())
    if not approved_status_ids:
        # Fallback to any active review status
        fallback_stmt = select(StatusMaster.status_id).where(
            StatusMaster.status_code.in_(["REVIEW_ACTIVE", "ACTIVE"])
        )
        approved_status_ids = list((await session.execute(fallback_stmt)).scalars().all())
        if not approved_status_ids:
            return empty

    # 2. Scope to team if manager_id is specified
    team_ids: set[UUID] = set()
    if manager_id:
        direct_reports = await get_direct_report_ids(session, manager_id)
        if not direct_reports:
            return empty
        team_ids = set(direct_reports)

    # 3. Query reviews joining reviewer and receiver employee names
    reviewer_alias = aliased(Employee)
    receiver_alias = aliased(Employee)

    stmt = (
        select(
            Review.review_id,
            Review.reviewer_id,
            Review.receiver_id,
            Review.raw_points,
            reviewer_alias.username.label("reviewer_name"),
            receiver_alias.username.label("receiver_name"),
        )
        .outerjoin(reviewer_alias, Review.reviewer_id == reviewer_alias.employee_id)
        .outerjoin(receiver_alias, Review.receiver_id == receiver_alias.employee_id)
        .where(
            Review.review_at >= start,
            Review.review_at <= end,
            Review.status_id.in_(approved_status_ids),
        )
    )

    if team_ids:
        team_list = list(team_ids)
        stmt = stmt.where(
            or_(
                Review.reviewer_id.in_(team_list),
                Review.receiver_id.in_(team_list),
            )
        )

    rows = (await session.execute(stmt)).all()
    if not rows:
        return empty

    # 4. Aggregations
    total_points = sum(float(r.raw_points or 0.0) for r in rows)

    giver_counts: dict[UUID, int] = {}
    giver_names: dict[UUID, str] = {}
    receiver_counts: dict[UUID, int] = {}
    receiver_names: dict[UUID, str] = {}

    for row in rows:
        r_reviewer_id = row.reviewer_id
        r_receiver_id = row.receiver_id

        # Only tally team members for top slots when scoped to a team[cite: 34]
        if not team_ids or r_reviewer_id in team_ids:
            giver_counts[r_reviewer_id] = giver_counts.get(r_reviewer_id, 0) + 1
            if row.reviewer_name:
                giver_names[r_reviewer_id] = row.reviewer_name

        if not team_ids or r_receiver_id in team_ids:
            receiver_counts[r_receiver_id] = receiver_counts.get(r_receiver_id, 0) + 1
            if row.receiver_name:
                receiver_names[r_receiver_id] = row.receiver_name

    top_giver: TopPerformer | None = None
    if giver_counts:
        top_giver_id = max(giver_counts, key=lambda k: giver_counts[k])
        top_giver = TopPerformer(
            employee_id=top_giver_id,
            username=giver_names.get(top_giver_id, "Unknown"),
            count=giver_counts[top_giver_id],
        )

    top_receiver: TopPerformer | None = None
    if receiver_counts:
        top_receiver_id = max(receiver_counts, key=lambda k: receiver_counts[k])
        top_receiver = TopPerformer(
            employee_id=top_receiver_id,
            username=receiver_names.get(top_receiver_id, "Unknown"),
            count=receiver_counts[top_receiver_id],
        )

    return WeeklyDigestData(
        week_start=start,
        week_end=end,
        total_recognitions=len(rows),
        total_points_awarded=round(total_points, 2),
        unique_givers=len(giver_counts),
        unique_receivers=len(receiver_counts),
        top_giver=top_giver,
        top_receiver=top_receiver,
    )