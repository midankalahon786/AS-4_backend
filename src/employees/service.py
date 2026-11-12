"""
src/employees/service.py
────────────────────────
Employee Service layer decoupled via IEmployeeRepository.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import HTTPException, Request, status
from passlib.context import CryptContext

from src.common.audit import audit_ctx
from src.common.cache import cache_delete, invalidate_pattern
from src.employees import schemas
from src.employees.interfaces import IEmployeeRepository
from src.notifications.schemas import NotificationType
from src.common import internal_client

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


class EmployeeService:
    def __init__(self, repo: IEmployeeRepository) -> None:
        self.repo = repo

    @staticmethod
    async def invalidate_employee_caches(employee_id: uuid.UUID) -> None:
        eid_str = str(employee_id)
        await cache_delete(f"wallets:employee:{eid_str}")
        await cache_delete(f"dashboard:platform:{eid_str}")
        await cache_delete(f"dashboard:reviews:{eid_str}")
        await cache_delete("roles:employees")
        await cache_delete("dashboard:leaderboard")
        await invalidate_pattern("dashboard:team:*")
        await cache_delete("dashboard:teams")
        logger.debug("Cache invalidated for employee=%s", eid_str)

    # ─────────────────────────────────────────────────────────────────────────
    # Read Methods
    # ─────────────────────────────────────────────────────────────────────────

    async def list_employees(
        self,
        page: int,
        limit: int,
        department_id: uuid.UUID | None = None,
        designation_id: uuid.UUID | None = None,
        status_id: uuid.UUID | None = None,
        manager_id: uuid.UUID | None = None,
        is_active: bool | None = None,
        search: str | None = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> schemas.EmployeeListResponse:
        return await self.repo.list_employees(
            page=page,
            limit=limit,
            department_id=department_id,
            designation_id=designation_id,
            status_id=status_id,
            manager_id=manager_id,
            is_active=is_active,
            search=search,
            sort_by=sort_by,
            sort_order=sort_order,
        )

    async def get_employee_detail(
        self, employee_id: uuid.UUID
    ) -> schemas.EmployeeDetailResponse:
        emp = await self.repo.get_employee_by_id(employee_id)
        if not emp:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found"
            )

        # 1. Fetch active roles via internal_client (or roles repo/endpoint)
        roles_list: list[schemas.RoleResponse] = []
        try:
            roles_data = await internal_client.get_employee_roles(str(employee_id))
            for r in roles_data or []:
                roles_list.append(
                    schemas.RoleResponse(
                        role_id=r["role_id"],
                        role_name=r["role_name"],
                        role_code=r["role_code"],
                    )
                )
        except Exception as exc:
            logger.warning(
                "Could not fetch roles for employee %s: %s", employee_id, exc
            )

        # 2. Fetch department using emp.department_id
        dept_resp = None
        if emp.department_id:
            try:
                dept_data = await internal_client.get_department_by_id(
                    str(emp.department_id)
                )
                if dept_data:
                    dept_type_data = dept_data.get("department_type")
                    dept_type_resp = (
                        schemas.DepartmentTypeResponse(
                            type_name=dept_type_data["type_name"],
                            type_code=dept_type_data["type_code"],
                        )
                        if dept_type_data
                        else None
                    )
                    dept_resp = schemas.DepartmentResponse(
                        department_id=dept_data["department_id"],
                        department_name=dept_data["department_name"],
                        department_code=dept_data["department_code"],
                        department_type=dept_type_resp,
                    )
            except Exception as exc:
                logger.warning(
                    "Could not fetch department %s: %s", emp.department_id, exc
                )

        # 3. Fetch wallet using emp.employee_id
        wallet_resp = None
        try:
            wallet_data = await internal_client.get_wallet_by_employee(str(employee_id))
            if wallet_data:
                wallet_resp = schemas.WalletResponse.model_validate(wallet_data)
        except Exception as exc:
            logger.warning(
                "Could not fetch wallet for employee %s: %s", employee_id, exc
            )

        is_active = (
            emp.status.status_code in ("ACTIVE", "EMP_ACTIVE", "GEN_ACTIVE")
        ) if emp.status else False

        return schemas.EmployeeDetailResponse(
            employee_id=emp.employee_id,
            username=emp.username,
            email=emp.email,
            date_of_joining=emp.date_of_joining,
            date_of_birth=emp.date_of_birth,
            is_active=is_active,
            designation=(
                schemas.DesignationResponse.model_validate(emp.designation)
                if emp.designation
                else None
            ),
            department=dept_resp,
            manager=(
                schemas.ManagerResponse.model_validate(emp.manager)
                if emp.manager
                else None
            ),
            status=(
                schemas.StatusResponse.model_validate(emp.status)
                if emp.status
                else None
            ),
            wallet=wallet_resp,
            roles=roles_list,
            created_at=emp.created_at,
            created_by=emp.created_by,
            updated_at=emp.updated_at,
            updated_by=emp.updated_by,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Write Methods
    # ─────────────────────────────────────────────────────────────────────────

    async def create_employee(
        self,
        data: schemas.CreateEmployeeRequest,
        created_by_id: uuid.UUID,
        request: Request | None = None,
    ) -> schemas.EmployeeCreatedResponse:
        existing = await self.repo.get_by_username_or_email(data.username, data.email)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username or Email already exists",
            )

        default_role_id = await self.repo.get_role_by_code("EMPLOYEE")
        if not default_role_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Default 'EMPLOYEE' role not found",
            )

        hashed_pwd = get_password_hash(data.password)
        new_emp = None

        async with audit_ctx(
            user_id=str(created_by_id),
            request=request,
            table_name="employees",
            record_id=lambda: str(new_emp.employee_id) if new_emp else "UNKNOWN",
            operation="INSERT",
            new_values=lambda: {
                "username": new_emp.username,
                "email": new_emp.email,
                "department_id": str(new_emp.department_id),
                "designation_id": str(new_emp.designation_id),
                "status_id": str(new_emp.status_id),
            },
        ):
            new_emp = await self.repo.create_employee_with_wallet_and_role(
                data=data,
                hashed_password=hashed_pwd,
                default_role_id=default_role_id,
                created_by_id=created_by_id,
            )

        is_active = (
            (new_emp.status.status_code in ("ACTIVE", "EMP_ACTIVE", "GEN_ACTIVE"))
            if new_emp.status
            else False
        )

        response = schemas.EmployeeCreatedResponse(
            employee_id=new_emp.employee_id,
            username=new_emp.username,
            email=new_emp.email,
            designation_id=new_emp.designation_id,
            department_id=new_emp.department_id,
            manager_id=new_emp.manager_id,
            date_of_joining=new_emp.date_of_joining,
            date_of_birth=new_emp.date_of_birth,
            status_id=new_emp.status_id,
            is_active=is_active,
            created_at=new_emp.created_at,
            created_by=new_emp.created_by,
            wallet=(
                schemas.WalletResponse.model_validate(new_emp.wallet)
                if new_emp.wallet
                else None
            ),
        )

        await self.invalidate_employee_caches(new_emp.employee_id)

        try:
            from src.common.event_publisher import publish

            await publish(
                "events:employee.created",
                {
                    "employee_id": str(new_emp.employee_id),
                    "created_by": str(created_by_id),
                },
            )
        except Exception:
            logger.exception(
                "Event publish failed for employee %s", new_emp.employee_id
            )

        return response

    async def update_employee(
        self,
        employee_id: uuid.UUID,
        data: schemas.UpdateEmployeeRequest,
        updated_by_id: uuid.UUID,
        request: Request | None = None,
    ) -> schemas.EmployeeDetailResponse:
        existing = await self.repo.get_employee_by_id(employee_id)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found"
            )

        update_data = {k: v for k, v in data.model_dump(exclude_unset=True).items()}
        if not update_data:
            return await self.get_employee_detail(employee_id)

        # Handle is_active translation to status_id
        if "is_active" in update_data:
            is_active_flag = update_data.pop("is_active")
            if is_active_flag is not None:
                if is_active_flag:
                    target_status_id = (
                        await self.repo.get_status_by_code("EMP_ACTIVE")
                        or await self.repo.get_status_by_code("ACTIVE")
                    )
                else:
                    target_status_id = (
                        await self.repo.get_status_by_code("EMP_INACTIVE")
                        or await self.repo.get_status_by_code("INACTIVE")
                    )
                if not target_status_id:
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=f"{'ACTIVE' if is_active_flag else 'INACTIVE'} status not found",
                    )
                update_data["status_id"] = target_status_id

        if not update_data:
            return await self.get_employee_detail(employee_id)

        old_snapshot = {
            "username": existing.username,
            "email": existing.email,
            "department_id": str(existing.department_id),
            "designation_id": str(existing.designation_id),
            "status_id": str(existing.status_id),
            "manager_id": str(existing.manager_id) if existing.manager_id else None,
        }

        async with audit_ctx(
            user_id=str(updated_by_id),
            request=request,
            table_name="employees",
            record_id=str(employee_id),
            operation="UPDATE",
            old_values=old_snapshot,
            new_values=lambda: {
                k: str(v) if isinstance(v, uuid.UUID) else v
                for k, v in update_data.items()
            },
        ):
            await self.repo.update_employee(
                employee_id=employee_id,
                update_fields=update_data,
                updated_by_id=updated_by_id,
            )

        await self.invalidate_employee_caches(employee_id)
        return await self.get_employee_detail(employee_id)

    async def activate_employee(
        self,
        employee_id: uuid.UUID,
        updated_by_id: uuid.UUID,
        request: Request | None = None,
    ) -> bool:
        active_status_id = (
            await self.repo.get_status_by_code("EMP_ACTIVE")
            or await self.repo.get_status_by_code("ACTIVE")
        )
        if not active_status_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="ACTIVE status not found",
            )

        existing = await self.repo.get_employee_by_id(employee_id)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found"
            )

        async with audit_ctx(
            user_id=str(updated_by_id),
            request=request,
            table_name="employees",
            record_id=str(employee_id),
            operation="ACTIVATE",
            old_values={"status_id": str(existing.status_id)},
            new_values={
                "status_id": str(active_status_id),
                "status_code": "ACTIVE",
            },
        ):
            await self.repo.update_status(
                employee_id=employee_id,
                status_id=active_status_id,
                updated_by_id=updated_by_id,
            )

        await self.invalidate_employee_caches(employee_id)
        return True

    async def deactivate_employee(
        self,
        employee_id: uuid.UUID,
        updated_by_id: uuid.UUID,
        request: Request | None = None,
    ) -> bool:
        inactive_status_id = (
            await self.repo.get_status_by_code("EMP_INACTIVE")
            or await self.repo.get_status_by_code("INACTIVE")
        )
        if not inactive_status_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="INACTIVE status not found",
            )

        existing = await self.repo.get_employee_by_id(employee_id)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found"
            )

        async with audit_ctx(
            user_id=str(updated_by_id),
            request=request,
            table_name="employees",
            record_id=str(employee_id),
            operation="DEACTIVATE",
            old_values={"status_id": str(existing.status_id)},
            new_values={
                "status_id": str(inactive_status_id),
                "status_code": "INACTIVE",
            },
        ):
            await self.repo.update_status(
                employee_id=employee_id,
                status_id=inactive_status_id,
                updated_by_id=updated_by_id,
            )

        await self.invalidate_employee_caches(employee_id)
        return True

    async def get_active_counts(self) -> dict[str, int]:
        return await self.repo.get_active_counts()

    async def get_manager_email(self, employee_id: uuid.UUID) -> str:
        email = await self.repo.get_manager_email(employee_id)
        if not email:
            raise HTTPException(status_code=404, detail="Manager or employee not found")
        return email

    async def get_departments_with_members(self) -> list[dict[str, Any]]:
        return await self.repo.get_departments_with_members()
