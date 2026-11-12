"""
src/digest/router.py
────────────────────
FastAPI router for weekly recognition digests (preview and email dispatch)[cite: 35].
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.common.dependencies import CurrentUser, check_route_permission
from src.core.database import get_db
from src.digest.schemas import DigestEmailRequest, DigestResponse, WeeklyDigestData
from src.digest.service import DigestService
from src.notifications.email_sender import EmailSender, SMTPConfig

router = APIRouter(prefix="/digest", tags=["Weekly Digest"])

_ADMIN_ROLES = {"SUPER_ADMIN", "HR_ADMIN"}


def get_email_sender() -> EmailSender:
    return EmailSender(SMTPConfig.from_env())


def get_digest_service(
    session: AsyncSession = Depends(get_db),
    sender: EmailSender = Depends(get_email_sender),
) -> DigestService:
    return DigestService(session, sender)


@router.get("", response_model=WeeklyDigestData, summary="Get Weekly Digest Preview")
async def get_weekly_digest(
    week_start: datetime | None = Query(
        default=None,
        description="Monday of the desired week in ISO 8601. Defaults to last completed week[cite: 35].",
    ),
    manager_id: UUID | None = Query(
        default=None,
        description="Scope digest to direct reports of this manager UUID[cite: 35].",
    ),
    current_user: CurrentUser = Depends(check_route_permission),
    svc: DigestService = Depends(get_digest_service),
):
    """
    Returns weekly digest recognition summary JSON for dashboard views[cite: 35].
    """
    effective_manager_id: UUID | None = None
    if manager_id:
        effective_manager_id = manager_id
    elif any(r in _ADMIN_ROLES for r in current_user.roles):
        effective_manager_id = None
    else:
        effective_manager_id = UUID(str(current_user.id))

    return await svc.get_digest_data(
        week_start=week_start,
        manager_id=effective_manager_id,
    )


@router.post(
    "/send",
    response_model=DigestResponse,
    status_code=status.HTTP_200_OK,
    summary="Dispatch Weekly Digest Email",
)
async def send_weekly_digest(
    payload: DigestEmailRequest,
    current_user: CurrentUser = Depends(check_route_permission),
    svc: DigestService = Depends(get_digest_service),
):
    """
    Generates a team-scoped weekly digest and delivers it to the manager's email[cite: 35].
    """
    if payload.week_start is not None:
        now_utc = datetime.now(tz=timezone.utc)
        ws = payload.week_start if payload.week_start.tzinfo else payload.week_start.replace(tzinfo=timezone.utc)
        if ws > now_utc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="week_start must not be in the future.",
            )

    return await svc.send_digest_email(
        manager_email=payload.manager_email,
        manager_id=payload.manager_id,
        week_start=payload.week_start,
    )