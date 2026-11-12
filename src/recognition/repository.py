"""
src/recognition/repository.py
──────────────────────────────
SQLAlchemy 2.0 implementation of IRecognitionRepository.
"""
from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone
from typing import Any

from dateutil.relativedelta import relativedelta
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.employees.models import Employee, StatusMaster
from src.organization.models import Department
from src.recognition import schemas
from src.recognition.models import Review, ReviewCategory, ReviewCategoryTag
from src.roles.models import EmployeeRole, Role


class SQLAlchemyRecognitionRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Categories ───────────────────────────────────────────
    async def list_categories(
        self, page: int, limit: int, active_only: bool
    ) -> tuple[list[ReviewCategory], int]:
        stmt = select(ReviewCategory)
        if active_only:
            stmt = stmt.where(ReviewCategory.is_active.is_(True))

        count_query = select(func.count()).select_from(stmt.subquery())
        total = (await self.db.execute(count_query)).scalar() or 0
        offset = (page - 1) * limit

        ordered_stmt = (
            stmt.order_by(ReviewCategory.category_name.asc())
            .offset(offset)
            .limit(limit)
        )
        res = await self.db.execute(ordered_stmt)
        return list(res.scalars().all()), total

    async def get_category_by_id(
        self, category_id: uuid.UUID
    ) -> ReviewCategory | None:
        stmt = select(ReviewCategory).where(
            ReviewCategory.category_id == category_id
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_category_by_code_or_name(
        self, code: str, name: str
    ) -> ReviewCategory | None:
        stmt = select(ReviewCategory).where(
            or_(
                func.upper(ReviewCategory.category_code) == code.strip().upper(),
                func.lower(ReviewCategory.category_name) == name.strip().lower(),
            )
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def create_category(
        self, body: schemas.ReviewCategoryCreateRequest, current_user_id: uuid.UUID
    ) -> ReviewCategory:
        now = datetime.now(timezone.utc)
        cat = ReviewCategory(
            category_code=body.category_code.strip().upper(),
            category_name=body.category_name.strip(),
            multiplier=body.multiplier,
            description=body.description,
            is_active=True,
            created_by=current_user_id,
            updated_by=current_user_id,
            created_at=now,
            updated_at=now,
        )
        self.db.add(cat)
        await self.db.flush()
        return cat

    async def update_category(
        self,
        category_id: uuid.UUID,
        update_data: dict[str, Any],
        current_user_id: uuid.UUID,
    ) -> ReviewCategory | None:
        now = datetime.now(timezone.utc)
        update_data["updated_by"] = current_user_id
        update_data["updated_at"] = now

        stmt = (
            update(ReviewCategory)
            .where(ReviewCategory.category_id == category_id)
            .values(**update_data)
        )
        await self.db.execute(stmt)
        return await self.get_category_by_id(category_id)

    async def get_active_categories_by_ids(
        self, category_ids: list[uuid.UUID]
    ) -> list[ReviewCategory]:
        stmt = select(ReviewCategory).where(
            ReviewCategory.category_id.in_(category_ids),
            ReviewCategory.is_active.is_(True),
        )
        return list((await self.db.execute(stmt)).scalars().all())

    # ── Reviews ──────────────────────────────────────────────
    async def get_reviewer_weight(self, reviewer_id: uuid.UUID) -> float:
        stmt = (
            select(Role.reviewer_weight)
            .join(EmployeeRole, EmployeeRole.role_id == Role.role_id)
            .where(
                EmployeeRole.employee_id == reviewer_id,
                EmployeeRole.is_active.is_(True),
            )
        )
        weights = (await self.db.execute(stmt)).scalars().all()
        return float(max(weights)) if weights else 1.0

    async def get_default_active_status_id(self) -> uuid.UUID:
        stmt = select(StatusMaster.status_id).where(
            StatusMaster.status_code == "ACTIVE",
            StatusMaster.entity_type == "REVIEW",
        )
        status_id = (await self.db.execute(stmt)).scalar_one_or_none()
        if not status_id:
            fallback_stmt = select(StatusMaster.status_id).where(
                StatusMaster.status_code == "ACTIVE"
            )
            status_id = (await self.db.execute(fallback_stmt)).scalar_one_or_none()
        if not status_id:
            raise RuntimeError("ACTIVE status not found in status_master")
        return status_id

    async def list_reviews(
        self,
        page: int,
        limit: int,
        reviewer_id: uuid.UUID | None = None,
        receiver_id: uuid.UUID | None = None,
    ) -> tuple[list[Review], int]:
        stmt = select(Review).options(selectinload(Review.review_category_tags))
        filters = []
        if reviewer_id:
            filters.append(Review.reviewer_id == reviewer_id)
        if receiver_id:
            filters.append(Review.receiver_id == receiver_id)
        if filters:
            stmt = stmt.where(*filters)

        count_query = select(func.count()).select_from(stmt.subquery())
        total = (await self.db.execute(count_query)).scalar() or 0
        offset = (page - 1) * limit

        ordered_stmt = (
            stmt.order_by(Review.review_at.desc()).offset(offset).limit(limit)
        )
        rows = list((await self.db.execute(ordered_stmt)).scalars().all())
        return rows, total

    async def get_review_by_id(self, review_id: uuid.UUID) -> Review | None:
        stmt = (
            select(Review)
            .options(selectinload(Review.review_category_tags))
            .where(Review.review_id == review_id)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def create_review_with_tags(
        self,
        reviewer_id: uuid.UUID,
        receiver_id: uuid.UUID,
        comment: str,
        image_url: str | None,
        video_url: str | None,
        status_id: uuid.UUID,
        raw_points: float,
        categories: list[ReviewCategory],
    ) -> Review:
        now = datetime.now(timezone.utc)
        review = Review(
            reviewer_id=reviewer_id,
            receiver_id=receiver_id,
            comment=comment,
            image_url=image_url,
            video_url=video_url,
            status_id=status_id,
            raw_points=raw_points,
            review_at=now,
            created_at=now,
            created_by=reviewer_id,
            updated_at=now,
            updated_by=reviewer_id,
        )
        self.db.add(review)
        await self.db.flush()

        for cat in categories:
            tag = ReviewCategoryTag(
                review_id=review.review_id,
                category_id=cat.category_id,
                category_code_snapshot=cat.category_code,
                multiplier_snapshot=cat.multiplier,
                created_at=now,
            )
            self.db.add(tag)

        await self.db.flush()
        return await self.get_review_by_id(review.review_id)  # type: ignore

    async def update_review_and_tags(
        self,
        review_id: uuid.UUID,
        update_data: dict[str, Any],
        new_categories: list[ReviewCategory] | None,
        new_raw_points: float | None,
        current_user_id: uuid.UUID,
    ) -> Review | None:
        now = datetime.now(timezone.utc)
        update_data["updated_by"] = current_user_id
        update_data["updated_at"] = now
        if new_raw_points is not None:
            update_data["raw_points"] = new_raw_points

        stmt = update(Review).where(Review.review_id == review_id).values(**update_data)
        await self.db.execute(stmt)

        if new_categories is not None:
            # Replace tag snapshots
            await self.db.execute(
                delete(ReviewCategoryTag).where(ReviewCategoryTag.review_id == review_id)
            )
            for cat in new_categories:
                tag = ReviewCategoryTag(
                    review_id=review_id,
                    category_id=cat.category_id,
                    category_code_snapshot=cat.category_code,
                    multiplier_snapshot=cat.multiplier,
                    created_at=now,
                )
                self.db.add(tag)
            await self.db.flush()

        return await self.get_review_by_id(review_id)

    # ── Internal Service Aggregations ────────────────────────
    async def get_review_stats_internal(
        self, employee_id: uuid.UUID | None = None
    ) -> dict[str, int]:
        now = datetime.now(timezone.utc)
        start_this = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        start_last = start_this - relativedelta(months=1)

        if employee_id is not None:
            total_stmt = select(func.count(Review.review_id)).where(
                Review.receiver_id == employee_id
            )
            this_stmt = select(func.count(Review.review_id)).where(
                Review.receiver_id == employee_id,
                Review.review_at >= start_this,
                Review.review_at < now,
            )
            last_stmt = select(func.count(Review.review_id)).where(
                Review.receiver_id == employee_id,
                Review.review_at >= start_last,
                Review.review_at < start_this,
            )
        else:
            total_stmt = select(func.count(Review.review_id))
            this_stmt = select(func.count(Review.review_id)).where(
                Review.review_at >= start_this,
                Review.review_at < now,
            )
            last_stmt = select(func.count(Review.review_id)).where(
                Review.review_at >= start_last,
                Review.review_at < start_this,
            )

        total = (await self.db.execute(total_stmt)).scalar() or 0
        this_m = (await self.db.execute(this_stmt)).scalar() or 0
        last_m = (await self.db.execute(last_stmt)).scalar() or 0

        return {
            "reviews_total": total,
            "reviews_this_month": this_m,
            "reviews_last_month": last_m,
        }

    async def get_review_stats_batch_internal(
        self, employee_ids: list[uuid.UUID]
    ) -> dict[str, dict[str, int]]:
        if not employee_ids:
            return {}

        now = datetime.now(timezone.utc)
        start_this = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        start_last = start_this - relativedelta(months=1)

        # Batch aggregation queries using GROUP BY
        total_stmt = (
            select(Review.receiver_id, func.count(Review.review_id))
            .where(Review.receiver_id.in_(employee_ids))
            .group_by(Review.receiver_id)
        )
        this_stmt = (
            select(Review.receiver_id, func.count(Review.review_id))
            .where(
                Review.receiver_id.in_(employee_ids),
                Review.review_at >= start_this,
            )
            .group_by(Review.receiver_id)
        )
        last_stmt = (
            select(Review.receiver_id, func.count(Review.review_id))
            .where(
                Review.receiver_id.in_(employee_ids),
                Review.review_at >= start_last,
                Review.review_at < start_this,
            )
            .group_by(Review.receiver_id)
        )

        totals = dict((await self.db.execute(total_stmt)).all())
        this_month = dict((await self.db.execute(this_stmt)).all())
        last_month = dict((await self.db.execute(last_stmt)).all())

        return {
            str(eid): {
                "reviews_total": totals.get(eid, 0),
                "reviews_this_month": this_month.get(eid, 0),
                "reviews_last_month": last_month.get(eid, 0),
            }
            for eid in employee_ids
        }

    async def get_recent_reviews_internal(
        self, employee_id: uuid.UUID | None = None, limit: int = 5
    ) -> list[Review]:
        stmt = (
            select(Review)
            .options(
                selectinload(Review.review_category_tags),
                selectinload(Review.reviewer_employee),
                selectinload(Review.receiver_employee),
            )
            .order_by(Review.review_at.desc())
            .limit(limit)
        )
        if employee_id is not None:
            stmt = stmt.where(Review.receiver_id == employee_id)
        return list((await self.db.execute(stmt)).scalars().all())

    async def get_recognition_trend_internal(self, range_: str) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        if range_ == "3m":
            n_buckets = 12
            start = now - relativedelta(weeks=n_buckets)
            stmt = (
                select(Review.reviewer_id, Review.review_at)
                .where(Review.review_at >= start)
                .order_by(Review.review_at.asc())
            )
            reviews = (await self.db.execute(stmt)).all()
            points = []
            for i in range(n_buckets):
                b_start = start + relativedelta(weeks=i)
                b_end = b_start + relativedelta(weeks=1)
                bucket = [r for r in reviews if b_start <= r.review_at < b_end]
                points.append({
                    "label": b_start.strftime("%b %d"),
                    "given": len({r.reviewer_id for r in bucket}),
                    "received": len(bucket),
                })
        else:
            n_buckets = 6 if range_ == "6m" else 12
            bucket_starts = [
                (now - relativedelta(months=i)).replace(
                    day=1, hour=0, minute=0, second=0, microsecond=0
                )
                for i in range(n_buckets - 1, -1, -1)
            ]
            start = bucket_starts[0]
            stmt = (
                select(Review.reviewer_id, Review.review_at)
                .where(Review.review_at >= start)
                .order_by(Review.review_at.asc())
            )
            reviews = (await self.db.execute(stmt)).all()
            points = []
            for b_start in bucket_starts:
                b_end = b_start + relativedelta(months=1)
                bucket = [r for r in reviews if b_start <= r.review_at < b_end]
                points.append({
                    "label": b_start.strftime("%b %Y"),
                    "given": len({r.reviewer_id for r in bucket}),
                    "received": len(bucket),
                })

        return {"data": points}

    async def get_recognition_by_user_internal(
        self, range_: str, page: int, limit: int
    ) -> dict[str, Any]:
        mapping = {
            "week": relativedelta(weeks=1),
            "month": relativedelta(months=1),
            "quarter": relativedelta(months=3),
            "year": relativedelta(years=1),
        }
        start = datetime.now(timezone.utc) - mapping.get(range_, relativedelta(months=1))

        emp_stmt = select(Employee, Department.department_name).outerjoin(
            Department, Employee.department_id == Department.department_id
        )
        employees = (await self.db.execute(emp_stmt)).all()

        rev_stmt = select(Review.reviewer_id, Review.receiver_id).where(
            Review.review_at >= start
        )
        reviews = (await self.db.execute(rev_stmt)).all()

        given_map: dict[uuid.UUID, int] = {}
        recv_map: dict[uuid.UUID, int] = {}
        for r_reviewer, r_receiver in reviews:
            given_map[r_reviewer] = given_map.get(r_reviewer, 0) + 1
            recv_map[r_receiver] = recv_map.get(r_receiver, 0) + 1

        rows = sorted(
            [
                {
                    "employee_id": str(emp.employee_id),
                    "username": emp.username,
                    "department": dept_name or "Unknown",
                    "given": given_map.get(emp.employee_id, 0),
                    "received": recv_map.get(emp.employee_id, 0),
                }
                for emp, dept_name in employees
            ],
            key=lambda x: x["given"],
            reverse=True,
        )

        total = len(rows)
        offset = (page - 1) * limit
        return {
            "items": rows[offset : offset + limit],
            "total": total,
            "page": page,
            "limit": limit,
            "pages": math.ceil(total / limit) if total else 0,
        }

    async def get_recognition_by_team_internal(
        self, range_: str, page: int, limit: int
    ) -> dict[str, Any]:
        mapping = {
            "week": relativedelta(weeks=1),
            "month": relativedelta(months=1),
            "quarter": relativedelta(months=3),
            "year": relativedelta(years=1),
        }
        start = datetime.now(timezone.utc) - mapping.get(range_, relativedelta(months=1))

        dept_stmt = select(Department)
        departments = (await self.db.execute(dept_stmt)).scalars().all()

        emp_stmt = select(Employee.employee_id, Employee.department_id)
        emp_rows = (await self.db.execute(emp_stmt)).all()
        emp_dept = {e_id: d_id for e_id, d_id in emp_rows if d_id}

        dept_members: dict[uuid.UUID, int] = {}
        for _, d_id in emp_rows:
            if d_id:
                dept_members[d_id] = dept_members.get(d_id, 0) + 1

        rev_stmt = select(Review.reviewer_id, Review.receiver_id).where(
            Review.review_at >= start
        )
        reviews = (await self.db.execute(rev_stmt)).all()

        dept_given: dict[uuid.UUID, int] = {}
        dept_received: dict[uuid.UUID, int] = {}
        for r_rev, r_rec in reviews:
            if d := emp_dept.get(r_rev):
                dept_given[d] = dept_given.get(d, 0) + 1
            if d := emp_dept.get(r_rec):
                dept_received[d] = dept_received.get(d, 0) + 1

        rows = sorted(
            [
                {
                    "department_id": str(d.department_id),
                    "name": d.department_name,
                    "members": dept_members.get(d.department_id, 0),
                    "given": dept_given.get(d.department_id, 0),
                    "received": dept_received.get(d.department_id, 0),
                }
                for d in departments
            ],
            key=lambda x: x["given"],
            reverse=True,
        )

        total = len(rows)
        offset = (page - 1) * limit
        return {
            "items": rows[offset : offset + limit],
            "total": total,
            "page": page,
            "limit": limit,
            "pages": math.ceil(total / limit) if total else 0,
        }

    async def get_participation_internal(self) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        month_ago = now - relativedelta(months=1)

        rev_stmt = select(Review.reviewer_id, Review.receiver_id, Review.review_at)
        all_reviews = (await self.db.execute(rev_stmt)).all()
        recent_reviews = [r for r in all_reviews if r.review_at >= month_ago]

        dept_stmt = select(Department)
        departments = (await self.db.execute(dept_stmt)).scalars().all()

        active_status_stmt = select(StatusMaster.status_id).where(
            StatusMaster.status_code.in_(("ACTIVE", "EMP_ACTIVE", "GEN_ACTIVE")),
        )
        active_status_ids = (await self.db.execute(active_status_stmt)).scalars().all()

        emp_stmt = select(Employee.employee_id, Employee.department_id).where(
            Employee.status_id.in_(active_status_ids)
        )
        active_emps = (await self.db.execute(emp_stmt)).all()

        total_active = len(active_emps)
        active_ids = {e_id for e_id, _ in active_emps}
        review_participants = {r.reviewer_id for r in all_reviews} | {
            r.receiver_id for r in all_reviews
        }
        participants = review_participants & active_ids
        active_p = len(participants)
        rate = round(active_p / total_active * 100, 1) if total_active else 0.0

        emp_dept = {e_id: d_id for e_id, d_id in active_emps if d_id}
        dept_members: dict[uuid.UUID, int] = {}
        for _, d_id in active_emps:
            if d_id:
                dept_members[d_id] = dept_members.get(d_id, 0) + 1

        dept_p: dict[uuid.UUID, set[uuid.UUID]] = {}
        for r in all_reviews:
            for eid in (r.reviewer_id, r.receiver_id):
                if d := emp_dept.get(eid):
                    dept_p.setdefault(d, set()).add(eid)

        return {
            "pie": [
                {"name": "Active participants", "value": rate},
                {"name": "Non-participants", "value": round(100 - rate, 1)},
            ],
            "stats": {
                "total_employees": total_active,
                "active_participants": active_p,
                "non_participants": total_active - active_p,
                "participation_rate": rate,
                "avg_reviews_per_employee": (
                    round(len(all_reviews) / total_active, 2) if total_active else 0.0
                ),
                "avg_reviews_last_month": (
                    round(len(recent_reviews) / total_active, 2) if total_active else 0.0
                ),
            },
            "by_department": [
                {
                    "department_id": str(d.department_id),
                    "name": d.department_name,
                    "active": len(dept_p.get(d.department_id, set())),
                    "total": dept_members.get(d.department_id, 0),
                    "rate": (
                        round(
                            len(dept_p.get(d.department_id, set()))
                            / dept_members[d.department_id]
                            * 100,
                            1,
                        )
                        if dept_members.get(d.department_id, 0)
                        else 0.0
                    ),
                }
                for d in departments
            ],
        }