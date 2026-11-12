"""
src/common/responses.py
───────────────────────
Standard API response envelopes and pagination containers.
"""
from __future__ import annotations

from typing import Generic, TypeVar
from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class MetaInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    page: int
    size: int
    total: int
    total_pages: int
    has_next: bool
    has_prev: bool


class ApiResponse(BaseModel, Generic[T]):
    model_config = ConfigDict(from_attributes=True)

    success: bool = True
    message: str | None = None
    data: T | None = None


class PaginatedResponse(BaseModel, Generic[T]):
    model_config = ConfigDict(from_attributes=True)

    success: bool = True
    data: list[T]
    meta: MetaInfo