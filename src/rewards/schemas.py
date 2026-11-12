"""
src/rewards/schemas.py
──────────────────────
Pydantic v2 schemas for Reward Categories, Catalog, Stock, and Redemptions.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    field_validator,
    model_validator,
)


# ══════════════════════════════════════════════════════════════
#  Shared Metadata Schemas
# ══════════════════════════════════════════════════════════════

class PaginationMeta(BaseModel):
    current_page: int
    per_page: int
    total: int
    total_pages: int
    has_next: bool
    has_previous: bool


class ErrorResponse(BaseModel):
    success: bool = False
    error_code: str  # e.g., "INSUFFICIENT_FUNDS", "OUT_OF_STOCK"
    message: str
    details: Any | None = None


# ══════════════════════════════════════════════════════════════
#  Category Schemas (reward_categories)
# ══════════════════════════════════════════════════════════════

class CreateCategoryRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "category_name": "Top Performer",
                    "category_code": "TOP_PERFORMER_01",
                    "description": "Awarded for exceptional quarterly performance.",
                }
            ]
        },
    )

    category_name: str = Field(
        ...,
        min_length=3,
        max_length=100,
        pattern=r"^[a-zA-Z0-9\s\-_&.,()]+$",
        description="Name of the category. Alphanumeric and basic punctuation only.",
    )
    category_code: str = Field(
        ...,
        min_length=3,
        max_length=50,
        pattern=r"^[A-Z0-9_-]+$",
        description="Unique code (Uppercase alphanumeric, dashes, underscores only) e.g. 'CAT-GIFT'",
    )
    description: str | None = Field(
        None,
        pattern=r"^[^<>]*$",
        description="Optional description. HTML tags are not allowed.",
    )

    @field_validator("category_name", "category_code")
    @classmethod
    def check_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Field cannot be empty or just whitespace")
        return v.strip().upper() if v == "category_code" else v.strip()


class UpdateCategoryRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "category_name": "Updated Category Name",
                    "description": "Updated description without HTML tags.",
                    "is_active": False,
                }
            ]
        },
    )

    category_name: str | None = Field(
        None,
        min_length=3,
        max_length=100,
        pattern=r"^[a-zA-Z0-9\s\-_&.,()]+$",
        description="Name of the category. Alphanumeric and basic punctuation only.",
    )
    description: str | None = Field(
        None,
        pattern=r"^[^<>]*$",
        description="Optional description. HTML tags are not allowed.",
    )
    is_active: StrictBool | None = Field(
        None,
        description="Must be a pure boolean (true/false). Strings like 'true' are rejected.",
    )

    @field_validator("category_name")
    @classmethod
    def check_not_empty(cls, v: str | None) -> str | None:
        if v is not None:
            if not v or not v.strip():
                raise ValueError("Category name cannot be empty or just whitespace")
            return v.strip()
        return v

    @model_validator(mode="before")
    @classmethod
    def prevent_system_field_updates(cls, data: Any) -> Any:
        if isinstance(data, dict):
            allowed_fields = {"category_name", "description", "is_active"}
            extra_fields = [key for key in data.keys() if key not in allowed_fields]
            if extra_fields:
                raise ValueError(
                    f"Internal system fields cannot be modified. Invalid fields detected: {', '.join(extra_fields)}"
                )
        return data


class MinimalCategoryInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    category_id: UUID
    category_name: str
    category_code: str


class CategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    category_id: UUID
    category_name: str
    category_code: str
    description: str | None = None
    is_active: bool
    created_at: datetime


# ══════════════════════════════════════════════════════════════
#  Catalog Schemas (reward_catalog)
# ══════════════════════════════════════════════════════════════

class CreateRewardRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "reward_name": "Amazon $50 Gift Card",
                    "reward_code": "AMZ_50_GC",
                    "description": "A $50 digital gift card for Amazon.com purchases.",
                    "category_id": "cc0e8400-e29b-41d4-a716-446655440003",
                    "default_points": 500,
                    "min_points": 500,
                    "max_points": 500,
                    "available_stock": 100,
                }
            ]
        },
    )

    reward_name: str = Field(
        ...,
        min_length=3,
        max_length=200,
        pattern=r"^[a-zA-Z0-9\s\-_&.,()$₹€£]+$",
        description="Name of the reward. Alphanumeric, basic punctuation, and currency symbols only.",
    )
    reward_code: str = Field(
        ...,
        min_length=3,
        max_length=50,
        pattern=r"^[A-Z0-9_-]+$",
        description="Unique SKU e.g. 'REW-AMZ-50'",
    )
    description: str | None = Field(
        None,
        pattern=r"^[^<>]*$",
        description="Optional description. HTML tags are not allowed.",
    )
    category_id: UUID
    default_points: StrictInt = Field(..., gt=0)
    min_points: StrictInt = Field(..., gt=0)
    max_points: StrictInt = Field(..., gt=0)
    available_stock: StrictInt = Field(default=0, ge=0, description="Initial stock count")

    @field_validator("reward_name", "reward_code")
    @classmethod
    def check_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Field cannot be empty or just whitespace")
        return v.strip().upper() if v == "reward_code" else v.strip()

    @field_validator("description")
    @classmethod
    def check_desc_not_empty(cls, v: str | None) -> str | None:
        if v is not None:
            if not v.strip():
                raise ValueError("Description cannot be just whitespace")
            return v.strip()
        return v

    @model_validator(mode="after")
    def check_points_logic(self) -> CreateRewardRequest:
        if self.max_points < self.min_points:
            raise ValueError("max_points must be greater than or equal to min_points")
        if not (self.min_points <= self.default_points <= self.max_points):
            raise ValueError(
                f"default_points ({self.default_points}) must be between "
                f"min_points ({self.min_points}) and max_points ({self.max_points})"
            )
        return self


class UpdateRewardRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "reward_name": "Updated Amazon $50 Gift Card",
                    "description": "Updated description without HTML tags.",
                    "default_points": 550,
                    "min_points": 500,
                    "max_points": 600,
                    "is_active": False,
                }
            ]
        },
    )

    reward_name: str | None = Field(
        None,
        min_length=1,
        max_length=200,
        pattern=r"^[a-zA-Z0-9\s\-_&.,()$₹€£]+$",
        description="Name of the reward. Alphanumeric and basic punctuation only.",
    )
    description: str | None = Field(
        None,
        pattern=r"^[^<>]*$",
        description="Optional description. HTML tags are not allowed.",
    )
    default_points: StrictInt | None = Field(None, gt=0)
    min_points: StrictInt | None = Field(None, gt=0)
    max_points: StrictInt | None = Field(None, gt=0)
    is_active: StrictBool | None = Field(
        None,
        description="Must be a pure boolean (true/false). Strings like 'true' are rejected.",
    )
    category_id: UUID | None = None

    @field_validator("reward_name")
    @classmethod
    def check_not_empty(cls, v: str | None) -> str | None:
        if v is not None:
            if not v or not v.strip():
                raise ValueError("Reward name cannot be empty or just whitespace")
            return v.strip()
        return v

    @field_validator("description")
    @classmethod
    def check_desc_not_empty(cls, v: str | None) -> str | None:
        if v is not None:
            if not v.strip():
                raise ValueError("Description cannot be just whitespace")
            return v.strip()
        return v

    @model_validator(mode="before")
    @classmethod
    def prevent_system_field_updates(cls, data: Any) -> Any:
        if isinstance(data, dict):
            allowed_fields = {
                "reward_name",
                "description",
                "default_points",
                "min_points",
                "max_points",
                "is_active",
                "category_id",
            }
            extra_fields = [key for key in data.keys() if key not in allowed_fields]
            if extra_fields:
                raise ValueError(
                    f"Internal system fields or immutable fields (like reward_code) cannot be modified. Invalid fields detected: {', '.join(extra_fields)}"
                )
        return data


class RewardItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    catalog_id: UUID
    reward_name: str
    reward_code: str
    description: str | None = None
    default_points: int
    min_points: int
    max_points: int
    is_active: bool
    created_at: datetime
    stock_status: str
    available_stock: int
    category: MinimalCategoryInfo | None = None


class AddStockRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{"amount": 50}]},
    )

    amount: StrictInt = Field(..., gt=0, description="Amount of new stock to add")

    @field_validator("amount")
    @classmethod
    def check_reasonable_amount(cls, v: int) -> int:
        max_restock_limit = 10000
        if v > max_restock_limit:
            raise ValueError(f"Cannot add more than {max_restock_limit} items in a single transaction.")
        return v


# ══════════════════════════════════════════════════════════════
#  History & Redemption Schemas (reward_history)
# ══════════════════════════════════════════════════════════════

class RedeemRewardRequest(BaseModel):
    catalog_id: UUID
    points: int | None = Field(default=None, strict=True, gt=0, description="Actual points redeemed (defaults to catalog item default_points)")
    comment: str | None = None


class RedeemRewardRequestOptionalCatalog(BaseModel):
    catalog_id: UUID | None = None
    points: int | None = Field(default=None, strict=True, gt=0, description="Actual points redeemed (defaults to catalog item default_points)")
    comment: str | None = None


class MinimalCatalogInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    reward_name: str
    reward_code: str


class MinimalEmployeeInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    username: str
    email: str | None = None


class RewardHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    history_id: UUID
    points: int
    comment: str | None = None
    granted_at: datetime
    reward_catalog: MinimalCatalogInfo | None = None
    granted_by: MinimalEmployeeInfo | None = Field(
        None,
        alias="employees_reward_history_granted_byToemployees",
    )


class RedemptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    history_id: UUID
    points: int
    granted_at: datetime
    status: str
    new_stock_level: int | None = None
    new_balance: int | None = None


class PaginatedHistoryResponse(BaseModel):
    data: list[RewardHistoryResponse]
    total_items: int
    page: int
    size: int


class PaginatedCatalogResponse(BaseModel):
    data: list[RewardItemResponse]
    pagination: PaginationMeta