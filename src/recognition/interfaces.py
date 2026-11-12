"""
src/recognition/interfaces.py
──────────────────────────────
Abstract repository contract for peer recognitions and review categories.
"""
from __future__ import annotations

import uuid
from typing import Any, Protocol

from src.recognition import schemas
from src.recognition.models import Review, ReviewCategory


class IRecognitionRepository(Protocol):
    # ── Categories ───────────────────────────────────────────
    async def list_categories(
        self, page: int, limit: int, active_only: bool
    ) -> tuple[list[ReviewCategory], int]: ...

    async def get_category_by_id(
        self, category_id: uuid.UUID
    ) -> ReviewCategory | None: ...

    async def get_category_by_code_or_name(
        self, code: str, name: str
    ) -> ReviewCategory | None: ...

    async def create_category(
        self, body: schemas.ReviewCategoryCreateRequest, current_user_id: uuid.UUID
    ) -> ReviewCategory: ...

    async def update_category(
        self,
        category_id: uuid.UUID,
        update_data: dict[str, Any],
        current_user_id: uuid.UUID,
    ) -> ReviewCategory | None: ...

    async def get_active_categories_by_ids(
        self, category_ids: list[uuid.UUID]
    ) -> list[ReviewCategory]: ...

    # ── Reviews ──────────────────────────────────────────────
    async def get_reviewer_weight(self, reviewer_id: uuid.UUID) -> float: ...

    async def get_default_active_status_id(self) -> uuid.UUID: ...

    async def list_reviews(
        self,
        page: int,
        limit: int,
        reviewer_id: uuid.UUID | None = None,
        receiver_id: uuid.UUID | None = None,
    ) -> tuple[list[Review], int]: ...

    async def get_review_by_id(self, review_id: uuid.UUID) -> Review | None: ...

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
    ) -> Review: ...

    async def update_review_and_tags(
        self,
        review_id: uuid.UUID,
        update_data: dict[str, Any],
        new_categories: list[ReviewCategory] | None,
        new_raw_points: float | None,
        current_user_id: uuid.UUID,
    ) -> Review | None: ...

    # ── Internal Service Aggregations ────────────────────────
    async def get_review_stats_internal(
        self, employee_id: uuid.UUID | None = None
    ) -> dict[str, int]: ...

    async def get_review_stats_batch_internal(
        self, employee_ids: list[uuid.UUID]
    ) -> dict[str, dict[str, int]]: ...

    async def get_recent_reviews_internal(
        self, employee_id: uuid.UUID | None = None, limit: int = 5
    ) -> list[Review]: ...

    async def get_recognition_trend_internal(self, range_: str) -> dict[str, Any]: ...

    async def get_recognition_by_user_internal(
        self, range_: str, page: int, limit: int
    ) -> dict[str, Any]: ...

    async def get_recognition_by_team_internal(
        self, range_: str, page: int, limit: int
    ) -> dict[str, Any]: ...

    async def get_participation_internal(self) -> dict[str, Any]: ...