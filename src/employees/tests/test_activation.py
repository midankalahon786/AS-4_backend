import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from src.employees import schemas
from src.employees.models import Employee, StatusMaster
from src.employees.repository import SQLAlchemyEmployeeRepository
from src.employees.service import EmployeeService


def make_uuid() -> uuid.UUID:
    return uuid.uuid4()


def fake_status(status_code: str, status_id: uuid.UUID | None = None) -> StatusMaster:
    return StatusMaster(
        status_id=status_id or make_uuid(),
        status_code=status_code,
        status_name="Active" if "ACTIVE" in status_code else "Inactive",
        entity_type="employee",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def fake_employee(status_code: str = "EMP_ACTIVE") -> Employee:
    st = fake_status(status_code)
    emp_id = make_uuid()
    return Employee(
        employee_id=emp_id,
        username="john.doe",
        email="john.doe@company.com",
        designation_id=make_uuid(),
        password_hash="hashed_pw",
        department_id=make_uuid(),
        date_of_joining=date(2023, 1, 1),
        status_id=st.status_id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        status=st,
    )


@pytest.mark.asyncio
async def test_service_get_detail_is_active_true_for_emp_active():
    emp = fake_employee("EMP_ACTIVE")
    mock_repo = MagicMock()
    mock_repo.get_employee_by_id = AsyncMock(return_value=emp)

    service = EmployeeService(mock_repo)
    with patch("src.common.internal_client.get_employee_roles", new_callable=AsyncMock, return_value=[]), \
         patch("src.common.internal_client.get_department_by_id", new_callable=AsyncMock, return_value=None), \
         patch("src.common.internal_client.get_wallet_by_employee", new_callable=AsyncMock, return_value=None):
        res = await service.get_employee_detail(emp.employee_id)

    assert res.is_active is True
    assert res.username == "john.doe"


@pytest.mark.asyncio
async def test_service_get_detail_is_active_false_for_emp_inactive():
    emp = fake_employee("EMP_INACTIVE")
    mock_repo = MagicMock()
    mock_repo.get_employee_by_id = AsyncMock(return_value=emp)

    service = EmployeeService(mock_repo)
    with patch("src.common.internal_client.get_employee_roles", new_callable=AsyncMock, return_value=[]), \
         patch("src.common.internal_client.get_department_by_id", new_callable=AsyncMock, return_value=None), \
         patch("src.common.internal_client.get_wallet_by_employee", new_callable=AsyncMock, return_value=None):
        res = await service.get_employee_detail(emp.employee_id)

    assert res.is_active is False


@pytest.mark.asyncio
async def test_service_activate_employee():
    emp = fake_employee("EMP_INACTIVE")
    active_status_id = make_uuid()

    mock_repo = MagicMock()
    mock_repo.get_employee_by_id = AsyncMock(return_value=emp)
    mock_repo.get_status_by_code = AsyncMock(return_value=active_status_id)
    mock_repo.update_status = AsyncMock(return_value=True)

    service = EmployeeService(mock_repo)
    with patch.object(service, "invalidate_employee_caches", new_callable=AsyncMock):
        success = await service.activate_employee(emp.employee_id, make_uuid())

    assert success is True
    mock_repo.update_status.assert_called_once_with(
        employee_id=emp.employee_id,
        status_id=active_status_id,
        updated_by_id=mock_repo.update_status.call_args.kwargs["updated_by_id"],
    )


@pytest.mark.asyncio
async def test_service_deactivate_employee():
    emp = fake_employee("EMP_ACTIVE")
    inactive_status_id = make_uuid()

    mock_repo = MagicMock()
    mock_repo.get_employee_by_id = AsyncMock(return_value=emp)
    mock_repo.get_status_by_code = AsyncMock(return_value=inactive_status_id)
    mock_repo.update_status = AsyncMock(return_value=True)

    service = EmployeeService(mock_repo)
    with patch.object(service, "invalidate_employee_caches", new_callable=AsyncMock):
        success = await service.deactivate_employee(emp.employee_id, make_uuid())

    assert success is True
    mock_repo.update_status.assert_called_once_with(
        employee_id=emp.employee_id,
        status_id=inactive_status_id,
        updated_by_id=mock_repo.update_status.call_args.kwargs["updated_by_id"],
    )


@pytest.mark.asyncio
async def test_service_update_employee_with_is_active_true():
    emp_inactive = fake_employee("EMP_INACTIVE")
    active_status_id = make_uuid()

    mock_repo = MagicMock()
    mock_repo.get_employee_by_id = AsyncMock(return_value=emp_inactive)
    mock_repo.get_status_by_code = AsyncMock(return_value=active_status_id)
    mock_repo.update_employee = AsyncMock(return_value=emp_inactive)

    service = EmployeeService(mock_repo)
    with patch.object(service, "get_employee_detail", new_callable=AsyncMock) as mock_get_detail, \
         patch.object(service, "invalidate_employee_caches", new_callable=AsyncMock):
        mock_get_detail.return_value = MagicMock(is_active=True)
        await service.update_employee(
            emp_inactive.employee_id,
            schemas.UpdateEmployeeRequest(is_active=True),
            make_uuid(),
        )

    # Verify update_fields contains status_id and does NOT contain is_active
    call_kwargs = mock_repo.update_employee.call_args.kwargs
    assert call_kwargs["update_fields"]["status_id"] == active_status_id
    assert "is_active" not in call_kwargs["update_fields"]


from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.employees.router import router as emp_router
from src.employees.dependencies import get_employee_service
from src.common.dependencies import check_route_permission, CurrentUser


def _build_test_client(mock_service):
    app = FastAPI()
    app.include_router(emp_router)
    dummy_user = CurrentUser(id=str(make_uuid()), email="admin@company.com", roles=["SUPER_ADMIN"])
    app.dependency_overrides[check_route_permission] = lambda: dummy_user
    app.dependency_overrides[get_employee_service] = lambda: mock_service
    return TestClient(app)


def test_router_patch_with_is_active_true():
    mock_service = MagicMock()
    mock_service.activate_employee = AsyncMock(return_value=True)
    client = _build_test_client(mock_service)

    emp_id = make_uuid()
    res = client.patch(f"/{emp_id}", json={"is_active": True})
    assert res.status_code == 204
    mock_service.activate_employee.assert_called_once()


def test_router_patch_with_is_active_false():
    mock_service = MagicMock()
    mock_service.deactivate_employee = AsyncMock(return_value=True)
    client = _build_test_client(mock_service)

    emp_id = make_uuid()
    res = client.patch(f"/{emp_id}", json={"is_active": False})
    assert res.status_code == 204
    mock_service.deactivate_employee.assert_called_once()


def test_router_patch_with_no_body():
    mock_service = MagicMock()
    mock_service.deactivate_employee = AsyncMock(return_value=True)
    client = _build_test_client(mock_service)

    emp_id = make_uuid()
    res = client.patch(f"/{emp_id}")
    assert res.status_code == 204
    mock_service.deactivate_employee.assert_called_once()


def test_router_post_activate():
    mock_service = MagicMock()
    mock_service.activate_employee = AsyncMock(return_value=True)
    client = _build_test_client(mock_service)

    emp_id = make_uuid()
    res = client.post(f"/{emp_id}/activate")
    assert res.status_code == 204
    mock_service.activate_employee.assert_called_once()


def test_router_post_deactivate():
    mock_service = MagicMock()
    mock_service.deactivate_employee = AsyncMock(return_value=True)
    client = _build_test_client(mock_service)

    emp_id = make_uuid()
    res = client.post(f"/{emp_id}/deactivate")
    assert res.status_code == 204
    mock_service.deactivate_employee.assert_called_once()

