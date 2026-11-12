"""
src/recognition/schemas.py
──────────────────────────
Pydantic v2 request, response, and pagination schemas for the Recognition microservice.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    field_validator,
    model_validator,
)


# ══════════════════════════════════════════════════════════════
#  Review Create / Update Requests
# ══════════════════════════════════════════════════════════════

class ReviewCreateRequest(BaseModel):
    """
    Request schema for creating a new peer review.

    - receiver_id  : UUID of the employee receiving the review
    - comment      : 10–2000 characters
    - category_ids : 1–5 unique UUIDs from review categories
    - image_url    : Optional HTTPS URL (max 500 chars)
    - video_url    : Optional HTTPS URL (max 500 chars)
    """
    model_config = ConfigDict(extra="forbid")

    receiver_id: UUID = Field(..., description="UUID of the employee receiving the review")
    comment: str = Field(..., min_length=10, max_length=2000, description="Review comment (10–2000 chars)")
    category_ids: list[UUID] = Field(
        ...,
        min_length=1,
        max_length=5,
        description=(
            "1–5 review category UUIDs. "
            "Points = sum of selected category multipliers × reviewer weight."
        ),
    )
    image_url: HttpUrl | None = Field(None, description="Optional image URL (max 500 chars)")
    video_url: HttpUrl | None = Field(None, description="Optional video URL (max 500 chars)")

    @field_validator("category_ids")
    @classmethod
    def validate_unique_categories(cls, v: list[UUID]) -> list[UUID]:
        if len(v) != len(set(v)):
            raise ValueError("Duplicate category IDs are not allowed")
        return v

    @field_validator("image_url", "video_url")
    @classmethod
    def validate_url_length(cls, v: HttpUrl | None) -> HttpUrl | None:
        if v and len(str(v)) > 500:
            raise ValueError("URL must not exceed 500 characters")
        return v


class ReviewUpdateRequest(BaseModel):
    """
    Update review request. At least one field must be supplied.
    Providing category_ids replaces all existing tags and triggers recalculation.
    """
    model_config = ConfigDict(extra="forbid")

    comment: str | None = Field(None, min_length=10, max_length=2000, description="Updated comment")
    category_ids: list[UUID] | None = Field(
        None,
        min_length=1,
        max_length=5,
        description="Updated tag list (1–5 UUIDs). Replaces existing tags.",
    )
    image_url: HttpUrl | None = Field(None, description="Updated image URL")
    video_url: HttpUrl | None = Field(None, description="Updated video URL")

    @field_validator("category_ids")
    @classmethod
    def validate_unique_categories(cls, v: list[UUID] | None) -> list[UUID] | None:
        if v is not None and len(v) != len(set(v)):
            raise ValueError("Duplicate category IDs are not allowed")
        return v

    @field_validator("image_url", "video_url")
    @classmethod
    def validate_url_length(cls, v: HttpUrl | None) -> HttpUrl | None:
        if v and len(str(v)) > 500:
            raise ValueError("URL must not exceed 500 characters")
        return v

    @model_validator(mode="after")
    def validate_not_empty(self) -> ReviewUpdateRequest:
        if not self.model_dump(exclude_none=True):
            raise ValueError("At least one field must be provided for update")
        return self


# ══════════════════════════════════════════════════════════════
#  Review Category Create / Update Requests
# ══════════════════════════════════════════════════════════════

class ReviewCategoryCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category_code: str = Field(..., min_length=1, max_length=50, description="Unique short code, e.g. INNOVATION")
    category_name: str = Field(..., min_length=1, max_length=100, description="Unique human-readable name")
    multiplier: float = Field(..., gt=0, description="Points multiplier (must be > 0)")
    description: str | None = Field(None, max_length=500, description="Optional description")

    @field_validator("category_code")
    @classmethod
    def uppercase_code(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("category_name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return v.strip()


class ReviewCategoryUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category_code: str | None = Field(None, min_length=1, max_length=50, description="Updated short code")
    category_name: str | None = Field(None, min_length=1, max_length=100, description="Updated human-readable name")
    multiplier: float | None = Field(None, gt=0, description="Updated multiplier (must be > 0)")
    description: str | None = Field(None, max_length=500, description="Updated description")
    is_active: bool | None = Field(None, description="Activate or deactivate the category")

    @field_validator("category_code")
    @classmethod
    def uppercase_code(cls, v: str | None) -> str | None:
        return v.strip().upper() if v else v

    @field_validator("category_name")
    @classmethod
    def strip_name(cls, v: str | None) -> str | None:
        return v.strip() if v else v

    @model_validator(mode="after")
    def validate_not_empty(self) -> ReviewCategoryUpdateRequest:
        if not self.model_dump(exclude_none=True):
            raise ValueError("At least one field must be provided for update")
        return self


# ══════════════════════════════════════════════════════════════
#  Category Response Schemas
# ══════════════════════════════════════════════════════════════

class ReviewCategoryResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "category_id": "770e8400-e29b-41d4-a716-446655440001",
                "category_code": "INNOVATION",
                "category_name": "Innovation",
                "multiplier": 1.4,
                "description": "Recognises creative problem-solving and novel ideas",
                "is_active": True,
            }
        },
    )

    category_id: UUID = Field(..., description="Unique category identifier")
    category_code: str = Field(..., description="Short code e.g. INNOVATION")
    category_name: str = Field(..., description="Human-readable name")
    multiplier: float = Field(..., description="Points multiplier for this category")
    description: str | None = Field(None)
    is_active: bool = Field(...)


class ReviewCategoryTagResponse(BaseModel):
    """Frozen multiplier snapshot from review_category_tags."""
    model_config = ConfigDict(from_attributes=True)

    category_id: UUID = Field(..., description="Category UUID")
    category_code: str = Field(..., description="Category code at write time")
    multiplier_snapshot: float = Field(..., description="Multiplier frozen at write time")


# ══════════════════════════════════════════════════════════════
#  Review Response Schemas
# ══════════════════════════════════════════════════════════════

class ReviewResponse(BaseModel):
    """Full review response model."""
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "review_id": "990e8400-e29b-41d4-a716-446655440004",
                "reviewer_id": "880e8400-e29b-41d4-a716-446655440000",
                "receiver_id": "550e8400-e29b-41d4-a716-446655440000",
                "comment": "Excellent work on the Q1 project.",
                "category_tags": [
                    {
                        "category_id": "770e8400-e29b-41d4-a716-446655440001",
                        "category_code": "INNOVATION",
                        "multiplier_snapshot": 1.4,
                    },
                    {
                        "category_id": "770e8400-e29b-41d4-a716-446655440002",
                        "category_code": "TEAMWORK",
                        "multiplier_snapshot": 1.2,
                    },
                ],
                "category_ids": [
                    "770e8400-e29b-41d4-a716-446655440001",
                    "770e8400-e29b-41d4-a716-446655440002",
                ],
                "category_codes": ["INNOVATION", "TEAMWORK"],
                "image_url": None,
                "video_url": None,
                "status_id": "aa0e8400-e29b-41d4-a716-446655440005",
                "review_at": "2026-02-06T10:30:00.000Z",
                "created_at": "2026-02-06T10:30:00.000Z",
                "created_by": "880e8400-e29b-41d4-a716-446655440000",
                "updated_at": "2026-02-06T10:30:00.000Z",
                "updated_by": "880e8400-e29b-41d4-a716-446655440000",
                "raw_points": 2.5,
            }
        },
    )

    review_id: UUID
    reviewer_id: UUID
    receiver_id: UUID
    reviewer_name: str | None = None
    receiver_name: str | None = None
    comment: str
    image_url: str | None = None
    video_url: str | None = None
    status_id: UUID
    review_at: datetime
    created_at: datetime
    created_by: UUID
    updated_at: datetime
    updated_by: UUID

    category_tags: list[ReviewCategoryTagResponse] | None = None
    category_ids: list[UUID] | None = None
    category_codes: list[str] | None = None
    raw_points: float | None = None


# ══════════════════════════════════════════════════════════════
#  Pagination Schemas
# ══════════════════════════════════════════════════════════════

class PaginationMeta(BaseModel):
    current_page: int
    per_page: int
    total: int
    total_pages: int
    has_next: bool
    has_previous: bool


class PaginatedReviewResponse(BaseModel):
    data: list[ReviewResponse]
    pagination: PaginationMeta


class PaginatedReviewCategoryResponse(BaseModel):
    data: list[ReviewCategoryResponse]
    pagination: PaginationMeta