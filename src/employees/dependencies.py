"""
src/employees/dependencies.py
──────────────────────────────
FastAPI dependency provider for EmployeeService.
"""
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.employees.repository import SQLAlchemyEmployeeRepository
from src.employees.service import EmployeeService


def get_employee_service(
    db: AsyncSession = Depends(get_db),
) -> EmployeeService:
    repo = SQLAlchemyEmployeeRepository(db)
    return EmployeeService(repo=repo)