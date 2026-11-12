"""
src/notifications/dependencies.py
─────────────────────────────────
FastAPI dependency provider for NotificationService.
"""
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.notifications.repository import SQLAlchemyNotificationRepository
from src.notifications.service import NotificationService


def get_notification_service(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> NotificationService:
    repo = SQLAlchemyNotificationRepository(db)
    redis_conn = getattr(request.app.state, "redis", None)
    return NotificationService(repo=repo, redis=redis_conn)