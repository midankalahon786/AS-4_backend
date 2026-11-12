from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.analytics.repository import (
    HttpAnalyticsDataProvider,
    SQLAlchemyAnalyticsRepository,
)
from src.analytics.service import AnalyticsService

# Singleton provider instance
_data_provider = HttpAnalyticsDataProvider()


def get_analytics_service(
    db: AsyncSession = Depends(get_db),
) -> AnalyticsService:
    repo = SQLAlchemyAnalyticsRepository(db)
    return AnalyticsService(provider=_data_provider, repo=repo)