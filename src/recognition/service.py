"""
src/recognition/service.py
───────────────────────────
Recognition service handling peer reviews, category administration,
points computation, and async event publishing.
Loosely coupled via IRecognitionRepository.
"""
from __future__ import annotations

import logging
import math
import uuid
from typing import Any

from fastapi import HTTPException, status

from src.common.event_publisher import publish
from src.recognition import schemas
from src.recognition.interfaces import IRecognitionRepository
from src.recognition.models import Review, ReviewCategory
from src.recognition.points_engine import calculate_points

logger = logging.getLogger(__name__)


class RecognitionService:
    def __init__(self, repo: IRecognitionRepository) -> None:
        self.repo = repo

    @staticmethod
    def _serialize_review(row: Review) -> schemas.ReviewResponse:
        tags = row.review_category_tags or []
        tag_responses = [
            schemas.ReviewCategoryTagResponse(
                category_id=t.category_id,
                category_code=t.category_code_snapshot,
                multiplier_snapshot=float(t.multiplier_snapshot),
            )
            for t in tags
        ]
        reviewer_name = row.reviewer_employee.username if getattr(row, "reviewer_employee", None) else None
        receiver_name = row.receiver_employee.username if getattr(row, "receiver_employee", None) else None
        return schemas.ReviewResponse(
            review_id=row.review_id,
            reviewer_id=row.reviewer_id,
            receiver_id=row.receiver_id,
            reviewer_name=reviewer_name,
            receiver_name=receiver_name,
            comment=row.comment,
            image_url=row.image_url,
            video_url=row.video_url,
            status_id=row.status_id,
            review_at=row.review_at,
            created_at=row.created_at,
            created_by=row.created_by,
            updated_at=row.updated_at,
            updated_by=row.updated_by,
            raw_points=float(row.raw_points) if row.raw_points is not None else None,
            category_tags=tag_responses,
            category_ids=[t.category_id for t in tags],
            category_codes=[t.category_code_snapshot for t in tags],
        )

    # ══════════════════════════════════════════════
    #  Review Categories
    # ══════════════════════════════════════════════

    async def list_review_categories(
        self, page: int = 1, limit: int = 20, active_only: bool = False
    ) -> schemas.PaginatedReviewCategoryResponse:
        rows, total = await self.repo.list_categories(
            page=page, limit=limit, active_only=active_only
        )
        return schemas.PaginatedReviewCategoryResponse(
            data=[schemas.ReviewCategoryResponse.model_validate(r) for r in rows],
            pagination=schemas.PaginationMeta(
                current_page=page,
                per_page=limit,
                total=total,
                total_pages=math.ceil(total / limit) if total else 0,
                has_next=(page * limit) < total,
                has_previous=page > 1,
            ),
        )

    async def create_review_category(
        self, body: schemas.ReviewCategoryCreateRequest, current_user_id: uuid.UUID
    ) -> schemas.ReviewCategoryResponse:
        existing = await self.repo.get_category_by_code_or_name(
            body.category_code, body.category_name
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Category code or name already exists",
            )
        category = await self.repo.create_category(body, current_user_id)
        return schemas.ReviewCategoryResponse.model_validate(category)

    async def update_review_category(
        self,
        category_id: uuid.UUID,
        body: schemas.ReviewCategoryUpdateRequest,
        current_user_id: uuid.UUID,
    ) -> schemas.ReviewCategoryResponse:
        existing = await self.repo.get_category_by_id(category_id)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Category not found",
            )
        update_data = body.model_dump(exclude_unset=True)
        updated = await self.repo.update_category(
            category_id, update_data, current_user_id
        )
        return schemas.ReviewCategoryResponse.model_validate(updated)

    # ══════════════════════════════════════════════
    #  Reviews
    # ══════════════════════════════════════════════

    async def list_reviews(
        self,
        page: int = 1,
        limit: int = 20,
        reviewer_id: uuid.UUID | None = None,
        receiver_id: uuid.UUID | None = None,
    ) -> schemas.PaginatedReviewResponse:
        rows, total = await self.repo.list_reviews(
            page=page,
            limit=limit,
            reviewer_id=reviewer_id,
            receiver_id=receiver_id,
        )
        return schemas.PaginatedReviewResponse(
            data=[self._serialize_review(r) for r in rows],
            pagination=schemas.PaginationMeta(
                current_page=page,
                per_page=limit,
                total=total,
                total_pages=math.ceil(total / limit) if total else 0,
                has_next=(page * limit) < total,
                has_previous=page > 1,
            ),
        )

    async def get_review(self, review_id: uuid.UUID) -> schemas.ReviewResponse:
        row = await self.repo.get_review_by_id(review_id)
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Review not found",
            )
        return self._serialize_review(row)

    async def create_review(
        self, body: schemas.ReviewCreateRequest, reviewer_id: uuid.UUID
    ) -> schemas.ReviewResponse:
        if reviewer_id == body.receiver_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Self-recognition is not permitted",
            )

        categories = await self.repo.get_active_categories_by_ids(body.category_ids)
        if len(categories) != len(body.category_ids):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="One or more category IDs are invalid or inactive",
            )

        reviewer_weight = await self.repo.get_reviewer_weight(reviewer_id)
        total_multiplier = sum(float(c.multiplier) for c in categories)
        pts_result = calculate_points(
            total_category_multiplier=total_multiplier,
            reviewer_weight=reviewer_weight,
            category_code=",".join(c.category_code for c in categories),
        )
        raw_points = round(pts_result.raw_points)
        status_id = await self.repo.get_default_active_status_id()

        review = await self.repo.create_review_with_tags(
            reviewer_id=reviewer_id,
            receiver_id=body.receiver_id,
            comment=body.comment,
            image_url=str(body.image_url) if body.image_url else None,
            video_url=str(body.video_url) if body.video_url else None,
            status_id=status_id,
            raw_points=float(raw_points),
            categories=categories,
        )

        # Asynchronous event publishing: Wallet listens on 'events:review.created'
        try:
            await publish("events:review.created", {
                "review_id": str(review.review_id),
                "reviewer_id": str(reviewer_id),
                "receiver_id": str(body.receiver_id),
                "raw_points": str(raw_points),
            })
            logger.info(
                "Published review.created event for review %s (receiver=%s, points=%d)",
                review.review_id,
                body.receiver_id,
                raw_points,
            )
        except Exception:
            logger.exception("Failed to publish review.created event")

        return self._serialize_review(review)

    async def update_review(
        self,
        review_id: uuid.UUID,
        body: schemas.ReviewUpdateRequest,
        current_user_id: uuid.UUID,
    ) -> schemas.ReviewResponse:
        existing = await self.repo.get_review_by_id(review_id)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Review not found",
            )
        if existing.reviewer_id != current_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorised to edit this review",
            )

        update_data: dict[str, Any] = {}
        if body.comment is not None:
            update_data["comment"] = body.comment
        if body.image_url is not None:
            update_data["image_url"] = str(body.image_url)
        if body.video_url is not None:
            update_data["video_url"] = str(body.video_url)

        new_categories: list[ReviewCategory] | None = None
        new_raw_points: float | None = None

        if body.category_ids is not None:
            new_categories = await self.repo.get_active_categories_by_ids(
                body.category_ids
            )
            if len(new_categories) != len(body.category_ids):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="One or more category IDs invalid or inactive",
                )
            reviewer_weight = await self.repo.get_reviewer_weight(current_user_id)
            total_multiplier = sum(float(c.multiplier) for c in new_categories)
            pts_result = calculate_points(
                total_category_multiplier=total_multiplier,
                reviewer_weight=reviewer_weight,
            )
            new_raw_points = float(round(pts_result.raw_points))

        updated = await self.repo.update_review_and_tags(
            review_id=review_id,
            update_data=update_data,
            new_categories=new_categories,
            new_raw_points=new_raw_points,
            current_user_id=current_user_id,
        )
        return self._serialize_review(updated)  # type: ignore

    # ══════════════════════════════════════════════
    #  Internal Query Adapters
    # ══════════════════════════════════════════════

    async def get_review_stats_internal(
        self, employee_id: uuid.UUID | None = None
    ) -> dict[str, int]:
        return await self.repo.get_review_stats_internal(employee_id)

    async def get_review_stats_batch_internal(
        self, employee_ids: list[uuid.UUID]
    ) -> dict[str, dict[str, int]]:
        return await self.repo.get_review_stats_batch_internal(employee_ids)

    async def get_recent_reviews_internal(
        self, employee_id: uuid.UUID | None = None, limit: int = 5
    ) -> list[dict[str, Any]]:
        rows = await self.repo.get_recent_reviews_internal(employee_id, limit=limit)
        return [self._serialize_review(r).model_dump(mode="json") for r in rows]

    async def get_recognition_trend_internal(self, range_: str) -> dict[str, Any]:
        return await self.repo.get_recognition_trend_internal(range_)

    async def get_recognition_by_user_internal(
        self, range_: str, page: int, limit: int
    ) -> dict[str, Any]:
        return await self.repo.get_recognition_by_user_internal(range_, page, limit)

    async def get_recognition_by_team_internal(
        self, range_: str, page: int, limit: int
    ) -> dict[str, Any]:
        return await self.repo.get_recognition_by_team_internal(range_, page, limit)

    async def get_participation_internal(self) -> dict[str, Any]:
        return await self.repo.get_participation_internal()