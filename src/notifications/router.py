"""
src/notifications/router.py
───────────────────────────
FastAPI routes for notifications and announcements.
Powered by NotificationService with SQLAlchemy 2.0 async sessions[cite: 42].
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.common.dependencies import CurrentUser, get_current_user
from src.notifications import schemas
from src.notifications.dependencies import get_notification_service
from src.notifications.service import NotificationService

router = APIRouter(prefix="/notifications", tags=["Notifications"])


def _assert_valid_user_id(user_id: str) -> UUID:
    try:
        return UUID(str(user_id))
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user identity in token — please re-authenticate",
        )


# ══════════════════════════════════════════════════════════════
#  Read Routes
# ══════════════════════════════════════════════════════════════

@router.get("", response_model=schemas.NotificationListResponse)
async def list_notifications(
    limit: int = Query(default=50, ge=1, le=200),
    unread_only: bool = Query(default=False),
    current_user: CurrentUser = Depends(get_current_user),
    svc: NotificationService = Depends(get_notification_service),
):
    uid = _assert_valid_user_id(current_user.id)
    items = await svc.get_notifications(
        employee_id=uid,
        limit=limit,
        unread_only=unread_only,
    )
    return schemas.NotificationListResponse(notifications=items, total=len(items))


@router.get("/unread-count")
async def unread_count(
    current_user: CurrentUser = Depends(get_current_user),
    svc: NotificationService = Depends(get_notification_service),
):
    uid = _assert_valid_user_id(current_user.id)
    count = await svc.get_unread_count(employee_id=uid)
    return {"unread_count": count}


# ══════════════════════════════════════════════════════════════
#  Mark-Read Routes
# ══════════════════════════════════════════════════════════════

@router.put("/read-all", status_code=status.HTTP_200_OK)
async def mark_all_read(
    current_user: CurrentUser = Depends(get_current_user),
    svc: NotificationService = Depends(get_notification_service),
):
    uid = _assert_valid_user_id(current_user.id)
    updated = await svc.mark_all_as_read(employee_id=uid)
    return {"marked_read": updated}


@router.put("/{notification_id}/read", response_model=schemas.NotificationResponse)
async def mark_one_read(
    notification_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    svc: NotificationService = Depends(get_notification_service),
):
    uid = _assert_valid_user_id(current_user.id)
    updated = await svc.mark_as_read(
        notification_id=notification_id,
        employee_id=uid,
    )
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found.",
        )
    return updated


# ══════════════════════════════════════════════════════════════
#  Send Routes (Admin)
# ══════════════════════════════════════════════════════════════

@router.post("", status_code=status.HTTP_201_CREATED)
async def send_custom_notification(
    payload: schemas.NotificationCreateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    svc: NotificationService = Depends(get_notification_service),
):
    _assert_valid_user_id(current_user.id)
    created = await svc.create_bulk_notifications(
        employee_ids=payload.employee_ids,
        title=payload.title,
        message=payload.message,
        type=payload.type,
    )
    return {"created": len(created), "notifications": created}


@router.post(
    "/announcements",
    status_code=status.HTTP_201_CREATED,
    response_model=schemas.AnnouncementResponse,
)
async def send_announcement(
    payload: schemas.AnnouncementCreateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    svc: NotificationService = Depends(get_notification_service),
):
    _assert_valid_user_id(current_user.id)

    if not payload.employee_ids and not payload.department_ids:
        recipient_ids = await svc.get_all_active_employee_ids()
        if not recipient_ids:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No active employees found.",
            )
    else:
        id_set: set[str] = set()

        if payload.department_ids:
            dept_ids = await svc.get_active_employee_ids_by_department(payload.department_ids)
            if not dept_ids:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No active employees found in the specified department(s).",
                )
            id_set.update(dept_ids)

        if payload.employee_ids:
            id_set.update(str(eid) for eid in payload.employee_ids)

        recipient_ids = list(id_set)

    await svc.create_bulk_notifications(
        employee_ids=recipient_ids,
        title=payload.title,
        message=payload.message,
        type=schemas.NotificationType.ANNOUNCEMENT,
    )

    return schemas.AnnouncementResponse(
        created=len(recipient_ids),
        recipient_count=len(recipient_ids),
        title=payload.title,
        message=payload.message,
    )