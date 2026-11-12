"""
src/webhooks/dependencies.py
────────────────────────────
FastAPI dependency provider for WebhookService.
"""
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.webhooks.repository import SQLAlchemyWebhookRepository
from src.webhooks.service import WebhookService


def get_webhook_service(
    db: AsyncSession = Depends(get_db),
) -> WebhookService:
    repo = SQLAlchemyWebhookRepository(db)
    return WebhookService(repo=repo)