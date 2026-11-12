"""
src/rewards/dependencies.py
───────────────────────────
FastAPI dependency provider for RewardService.
"""
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.notifications.redis_client import get_redis
from src.notifications.repository import SQLAlchemyNotificationRepository
from src.notifications.service import NotificationService
from src.rewards.repository import SQLAlchemyRewardRepository
from src.rewards.service import RewardService


def get_reward_service(
    db: AsyncSession = Depends(get_db),
) -> RewardService:
    repo = SQLAlchemyRewardRepository(db)
    try:
        redis_conn = get_redis()
    except RuntimeError:
        redis_conn = None

    notif_repo = SQLAlchemyNotificationRepository(db)
    notif_service = NotificationService(notif_repo, redis=redis_conn)
    return RewardService(repo=repo, notif_service=notif_service)