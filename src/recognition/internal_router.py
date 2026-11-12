"""
src/recognition/internal_router.py
──────────────────────────────────
Internal-only endpoints consumed by the Analytics microservice.
Routes are mounted as /internal/reviews/... without a prefix[cite: 22].
"""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from src.recognition.dependencies import get_recognition_service
from src.recognition.service import RecognitionService

router = APIRouter(tags=["Internal"])


@router.get("/internal/reviews/stats")
async def review_stats(
    employee_id: UUID | None = Query(None),
    service: RecognitionService = Depends(get_recognition_service),
):
    return await service.get_review_stats_internal(employee_id)


@router.get("/internal/reviews/stats/batch")
async def review_stats_batch(
    employee_ids: str = Query(...),
    service: RecognitionService = Depends(get_recognition_service),
):
    """
    Bulk review stats for a comma-separated list of employee_ids[cite: 22].
    Returns a dictionary keyed by employee_id[cite: 22].
    """
    ids = [UUID(eid.strip()) for eid in employee_ids.split(",") if eid.strip()]
    return await service.get_review_stats_batch_internal(ids)


@router.get("/internal/reviews/recent")
async def recent_reviews(
    employee_id: UUID | None = Query(None),
    limit: int = Query(5, ge=1, le=20),
    service: RecognitionService = Depends(get_recognition_service),
):
    return await service.get_recent_reviews_internal(employee_id, limit)


@router.get("/internal/reviews/trend")
async def recognition_trend(
    range: Literal["3m", "6m", "1y"] = Query("6m"),
    service: RecognitionService = Depends(get_recognition_service),
):
    return await service.get_recognition_trend_internal(range)


@router.get("/internal/reviews/by-user")
async def recognition_by_user(
    range: Literal["week", "month", "quarter", "year"] = Query("month"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    service: RecognitionService = Depends(get_recognition_service),
):
    return await service.get_recognition_by_user_internal(range, page, limit)


@router.get("/internal/reviews/by-team")
async def recognition_by_team(
    range: Literal["week", "month", "quarter", "year"] = Query("month"),
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    service: RecognitionService = Depends(get_recognition_service),
):
    return await service.get_recognition_by_team_internal(range, page, limit)


@router.get("/internal/reviews/participation")
async def participation(
    service: RecognitionService = Depends(get_recognition_service),
):
    return await service.get_participation_internal()