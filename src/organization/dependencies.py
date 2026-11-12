"""
src/organization/dependencies.py
─────────────────────────────────
FastAPI dependency provider for OrganizationService.
"""
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.organization.repository import SQLAlchemyOrganizationRepository
from src.organization.service import OrganizationService


def get_organization_service(
    db: AsyncSession = Depends(get_db),
) -> OrganizationService:
    repo = SQLAlchemyOrganizationRepository(db)
    return OrganizationService(repo=repo)