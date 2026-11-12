"""
src/auth/dependencies.py
─────────────────────────
FastAPI dependency provider for AuthService.
"""
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.repository import SQLAlchemyAuthRepository
from src.auth.service import AuthService
from src.core.database import get_db


def get_auth_service(
    db: AsyncSession = Depends(get_db),
) -> AuthService:
    repo = SQLAlchemyAuthRepository(db)
    return AuthService(repo=repo)