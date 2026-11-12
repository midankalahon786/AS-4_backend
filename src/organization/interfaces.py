"""
src/organization/interfaces.py
───────────────────────────────
Abstract repository contract for organization management.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Protocol

from src.organization import schemas
from src.employees.models import Designation, StatusMaster
from src.organization.models import (
    Department,
    DepartmentType
)


class IOrganizationRepository(Protocol):
    # ── Department Types ─────────────────────────────────────
    async def list_department_types(self) -> list[DepartmentType]: ...

    async def get_department_type_by_id(
        self, department_type_id: uuid.UUID
    ) -> DepartmentType | None: ...

    # ── Departments ──────────────────────────────────────────
    async def list_departments(
        self,
        page: int,
        limit: int,
        is_active: bool | None,
        search: str | None,
    ) -> schemas.DepartmentListResponse: ...

    async def get_department_detail(
        self, department_id: uuid.UUID
    ) -> schemas.DepartmentDetailResponse | None: ...

    async def get_department_by_name_or_code(
        self, name: str, code: str
    ) -> Department | None: ...

    async def create_department(
        self,
        data: schemas.CreateDepartmentRequest,
        created_by_id: uuid.UUID,
    ) -> Department: ...

    async def update_department(
        self,
        department_id: uuid.UUID,
        update_data: dict[str, Any],
        updated_by_id: uuid.UUID,
    ) -> Department | None: ...

    # ── Designations ─────────────────────────────────────────
    async def list_designations(
        self,
        page: int,
        limit: int,
        is_active: bool | None,
    ) -> schemas.DesignationListResponse: ...

    async def get_designation_detail(
        self, designation_id: uuid.UUID
    ) -> schemas.DesignationDetailResponse | None: ...

    async def get_designation_by_name_or_code(
        self, name: str, code: str
    ) -> Designation | None: ...

    async def check_designation_code_conflict(
        self, code: str, exclude_id: uuid.UUID
    ) -> bool: ...

    async def create_designation(
        self,
        data: schemas.CreateDesignationRequest,
        created_by_id: uuid.UUID,
    ) -> Designation: ...

    async def update_designation(
        self,
        designation_id: uuid.UUID,
        update_data: dict[str, Any],
        updated_by_id: uuid.UUID,
    ) -> Designation | None: ...

    # ── Status Master ────────────────────────────────────────
    async def list_statuses(
        self, entity_type: str | None = None
    ) -> list[StatusMaster]: ...

    async def get_status_by_id(self, status_id: uuid.UUID) -> StatusMaster | None: ...

    async def get_status_by_code(self, status_code: str) -> StatusMaster | None: ...

    async def create_status(
        self,
        data: schemas.CreateStatusRequest,
        created_by_id: uuid.UUID,
    ) -> StatusMaster: ...

    async def update_status(
        self,
        status_id: uuid.UUID,
        update_data: dict[str, Any],
        updated_by_id: uuid.UUID,
    ) -> StatusMaster | None: ...

    # ── Audit Logs (Viewer) ──────────────────────────────────
    async def list_audit_logs(
        self,
        page: int,
        limit: int,
        table_name: str | None,
        record_id: uuid.UUID | None,
        operation_type: str | None,
        performed_by: uuid.UUID | None,
        start_date: datetime | None,
        end_date: datetime | None,
    ) -> schemas.AuditLogListResponse: ...

    async def get_audit_log(
        self, audit_id: uuid.UUID
    ) -> schemas.AuditLogResponse | None: ...