"""
src/roles/dependencies.py
─────────────────────────
FastAPI dependency provider for RoleService.
"""
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.roles.repository import SQLAlchemyRoleRepository
from src.roles.service import RoleService


def get_role_service(
    db: AsyncSession = Depends(get_db),
) -> RoleService:
    repo = SQLAlchemyRoleRepository(db)
    return RoleService(repo=repo)