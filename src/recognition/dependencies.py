"""
src/recognition/dependencies.py
────────────────────────────────
FastAPI dependency provider for RecognitionService.
"""
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.recognition.repository import SQLAlchemyRecognitionRepository
from src.recognition.service import RecognitionService


def get_recognition_service(
    db: AsyncSession = Depends(get_db),
) -> RecognitionService:
    repo = SQLAlchemyRecognitionRepository(db)
    return RecognitionService(repo=repo)