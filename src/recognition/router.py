"""
src/recognition/router.py
─────────────────────────
Public and Admin-protected routes for Reviews and Review Categories.
Powered by RecognitionService and SQLAlchemy 2.0 async sessions.
"""
from __future__ import annotations

import math
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, status

from src.common.dependencies import CurrentUser, check_route_permission
from src.recognition.dependencies import get_recognition_service
from src.recognition.schemas import (
    PaginatedReviewCategoryResponse,
    PaginatedReviewResponse,
    PaginationMeta,
    ReviewCategoryCreateRequest,
    ReviewCategoryResponse,
    ReviewCategoryUpdateRequest,
    ReviewCreateRequest,
    ReviewResponse,
    ReviewUpdateRequest,
)
from src.recognition.service import RecognitionService

router = APIRouter(prefix="/reviews", tags=["Reviews"])
categories_router = APIRouter(prefix="/review-categories", tags=["Review Categories"])


# ══════════════════════════════════════════════════════════════
#  REVIEW CATEGORIES
# ══════════════════════════════════════════════════════════════

@categories_router.get(
    "",
    response_model=PaginatedReviewCategoryResponse,
    response_model_exclude_none=True,
    summary="List Review Categories",
    description=(
        "Returns all active review categories with their points multipliers.\n\n"
        "Call this first to get valid category_ids UUIDs before creating a review[cite: 23]."
    ),
)
async def list_review_categories_route(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    active_only: bool = Query(True, description="Return only active categories"),
    current_user: CurrentUser = Depends(check_route_permission),
    service: RecognitionService = Depends(get_recognition_service),
):
    return await service.list_review_categories(
        page=page, limit=page_size, active_only=active_only
    )


@categories_router.post(
    "",
    response_model=ReviewCategoryResponse,
    status_code=status.HTTP_201_CREATED,
    response_model_exclude_none=True,
    summary="Create Review Category",
    description="Create a new review category with code, name, and multiplier[cite: 23].",
)
async def create_review_category_route(
    payload: ReviewCategoryCreateRequest,
    current_user: CurrentUser = Depends(check_route_permission),
    service: RecognitionService = Depends(get_recognition_service),
):
    return await service.create_review_category(
        body=payload, current_user_id=UUID(str(current_user.id))
    )


@categories_router.put(
    "/{id}",
    response_model=ReviewCategoryResponse,
    response_model_exclude_none=True,
    summary="Update Review Category",
    description="Update an existing review category[cite: 23].",
)
async def update_review_category_route(
    payload: ReviewCategoryUpdateRequest,
    id: UUID = Path(..., description="Unique review category identifier"),
    current_user: CurrentUser = Depends(check_route_permission),
    service: RecognitionService = Depends(get_recognition_service),
):
    return await service.update_review_category(
        category_id=id, body=payload, current_user_id=UUID(str(current_user.id))
    )


# ══════════════════════════════════════════════════════════════
#  REVIEWS
# ══════════════════════════════════════════════════════════════

@router.get(
    "",
    response_model=PaginatedReviewResponse,
    response_model_exclude_none=True,
    summary="List Reviews",
)
async def list_reviews_route(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: CurrentUser = Depends(check_route_permission),
    service: RecognitionService = Depends(get_recognition_service),
):
    """
    - EMPLOYEE / MANAGER: only reviews they gave or received.
    - HR_ADMIN / SUPER_ADMIN: all reviews.
    """
    user_id = UUID(str(current_user.id))
    is_admin = any(r in current_user.roles for r in ("HR_ADMIN", "SUPER_ADMIN"))

    if is_admin:
        return await service.list_reviews(page=page, limit=page_size)

    # Employees/managers see only reviews where they are reviewer or receiver
    as_reviewer = await service.list_reviews(page=1, limit=1000, reviewer_id=user_id)
    as_receiver = await service.list_reviews(page=1, limit=1000, receiver_id=user_id)

    seen: set[UUID] = set()
    merged: list[ReviewResponse] = []
    combined = sorted(
        as_reviewer.data + as_receiver.data,
        key=lambda r: r.review_at,
        reverse=True,
    )
    for rev in combined:
        if rev.review_id not in seen:
            seen.add(rev.review_id)
            merged.append(rev)

    total = len(merged)
    start = (page - 1) * page_size
    page_items = merged[start : start + page_size]

    return PaginatedReviewResponse(
        data=page_items,
        pagination=PaginationMeta(
            current_page=page,
            per_page=page_size,
            total=total,
            total_pages=math.ceil(total / page_size) if total else 0,
            has_next=(page * page_size) < total,
            has_previous=page > 1,
        ),
    )


@router.get(
    "/{id}",
    response_model=ReviewResponse,
    response_model_exclude_none=True,
    summary="Get Review",
)
async def get_review_route(
    id: UUID = Path(..., description="Unique review identifier"),
    current_user: CurrentUser = Depends(check_route_permission),
    service: RecognitionService = Depends(get_recognition_service),
):
    return await service.get_review(id)


@router.post(
    "",
    response_model=ReviewResponse,
    status_code=status.HTTP_201_CREATED,
    response_model_exclude_none=True,
    summary="Create Review",
    description="Create a new performance review with 1–5 category tags.",
)
async def create_review_route(
    payload: ReviewCreateRequest,
    current_user: CurrentUser = Depends(check_route_permission),
    service: RecognitionService = Depends(get_recognition_service),
):
    return await service.create_review(
        body=payload,
        reviewer_id=UUID(str(current_user.id)),
    )


@router.put(
    "/{id}",
    response_model=ReviewResponse,
    response_model_exclude_none=True,
    summary="Update Review",
    description="Update an existing review comment, URLs, or category tags",
)
async def update_review_route(
    payload: ReviewUpdateRequest,
    id: UUID = Path(..., description="Unique review identifier"),
    current_user: CurrentUser = Depends(check_route_permission),
    service: RecognitionService = Depends(get_recognition_service),
):
    return await service.update_review(
        review_id=id,
        body=payload,
        current_user_id=UUID(str(current_user.id)),
    )