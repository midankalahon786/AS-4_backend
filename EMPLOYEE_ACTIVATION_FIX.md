# Bug Fix: Employee Activation and Status Management

**Date:** November 12, 2026  
**Scope:** `employees`, `notifications`, `digest`, `recognition`, `webhooks`  
**Database Frameworks:** SQLAlchemy 2.0 Async, Alembic, PostgreSQL  

---

## 1. Problem Summary
When an administrator attempted to activate an employee (via UI or API endpoints), the employee's active state remained `false`, or the request was not processed as an activation. Furthermore:
- All seeded employees showed `is_active: false` in list and detail responses despite having active status in the database.
- Filtering `GET /aabhar/v1/employees/list?is_active=true` returned 0 records.
- Deactivating an employee failed with HTTP 500 (`INACTIVE status not found`).
- Cross-service features (weekly digest manager lookups, notification active user queries, and recognition participation rates) were missing active employees.

---

## 2. Root Cause Analysis

1. **Status Code Inconsistency (`EMP_ACTIVE` vs `ACTIVE` & Missing `INACTIVE`)**:
   - `seed.py` seeded employee status records in `status_master` with `status_code = 'EMP_ACTIVE'` (`entity_type = 'employee'`) and `'EMP_INACTIVE'`.
   - The employee service and repository strictly compared `status_code == "ACTIVE"` when computing `is_active` and when applying SQL filters.
   - Because all seeded employees had `status_code = "EMP_ACTIVE"`, `(status_code == "ACTIVE")` always evaluated to `False`.
   - The deactivation flow queried `get_status_by_code("INACTIVE")`, but `status_master` only possessed `EMP_INACTIVE` and `GEN_INACTIVE`, resulting in a missing status error (`HTTP 500`).

2. **Missing `is_active` Attribute in Request Schema**:
   - `UpdateEmployeeRequest` did not declare an `is_active: bool | None` field.
   - When the admin client submitted `{"is_active": true}` in a `PUT` or `PATCH` payload, Pydantic stripped the unrecognized field during validation.

3. **No Direct `is_active` Column on Database Table**:
   - In PostgreSQL, the `employees` table does not contain a boolean `is_active` column. Active status is controlled via a foreign key `status_id` referencing `status_master`.
   - The service lacked translation logic to map a boolean `is_active` request to the corresponding active/inactive `status_id`.

4. **Hardcoded Unidirectional Deactivation on `PATCH /{employee_id}`**:
   - The `PATCH /{employee_id}` endpoint took no body parameter and unconditionally called `deactivate_employee`.
   - Sending a `PATCH` to update or activate an employee inadvertently triggered deactivation.
   - No explicit activation method (`activate_employee`) or dedicated `/activate` endpoints existed.

5. **Cross-Service Query Dependencies**:
   - Services such as `notifications`, `digest`, and `recognition` had SQL joins looking solely for `StatusMaster.status_code == "ACTIVE"`, ignoring employees marked as `EMP_ACTIVE`.

---

## 3. Changes Implemented

### A. Employee Service & Repository
- **`src/employees/schemas.py`**:
  - Added `is_active: bool | None = None` to `UpdateEmployeeRequest`.
- **`src/employees/service.py`**:
  - Updated `is_active` calculation in `get_employee_detail` and `create_employee` to check `status_code in ("ACTIVE", "EMP_ACTIVE", "GEN_ACTIVE")`.
  - Added `activate_employee(employee_id, updated_by_id, request)` to assign active employee status (`EMP_ACTIVE` / `ACTIVE`).
  - Updated `deactivate_employee(employee_id, updated_by_id, request)` to resolve `EMP_INACTIVE` / `INACTIVE` / `GEN_INACTIVE`.
  - Updated `update_employee` to intercept `is_active`, resolve the corresponding `status_id`, remove `is_active` from raw table update fields, and update `status_id`.
- **`src/employees/repository.py`**:
  - Updated `list_employees` to filter and map `is_active` using `("ACTIVE", "EMP_ACTIVE", "GEN_ACTIVE")`.
  - Enhanced `get_status_by_code` with fallback resolution across active/inactive status code aliases.
  - Updated `get_active_counts` to count active employee statuses correctly.

### B. Router & Permission Management
- **`src/employees/router.py`**:
  - Updated `PATCH /{employee_id}` to accept `payload: schemas.UpdateEmployeeRequest | None = None`.
    - If `payload.is_active is True`: calls `activate_employee`.
    - If `payload.is_active is False` or empty/no body: calls `deactivate_employee` (preserving backward compatibility for soft-delete calls).
    - If other fields are provided: calls `update_employee`.
  - Added dedicated endpoints:
    - `POST /aabhar/v1/employees/{employee_id}/activate` & `PATCH /aabhar/v1/employees/{employee_id}/activate`
    - `POST /aabhar/v1/employees/{employee_id}/deactivate` & `PATCH /aabhar/v1/employees/{employee_id}/deactivate`
- **`src/employees/main.py`**:
  - Registered the new activate and deactivate routes in `ROLE_OVERRIDES` (allowing `SUPER_ADMIN` and `HR_ADMIN`).
  - Added titles for new routes in `ROUTE_TITLES`.

### C. Database & Cross-Service Consistency
- **`src/digest/worker.py`**: Updated manager query to check `StatusMaster.status_code.in_(("ACTIVE", "EMP_ACTIVE", "GEN_ACTIVE"))`.
- **`src/notifications/repository.py`**: Updated active employee queries to accept `("ACTIVE", "EMP_ACTIVE", "GEN_ACTIVE")`.
- **`src/recognition/repository.py`**: Updated active employee participation rate query to match active statuses.
- **`src/webhooks/repository.py`**: Added fallback status code resolution for HRIS event webhooks.
- **`status_master` Table & `seed.py`**: Added `INACTIVE` (`entity_type = 'general'`) to `status_master` to ensure legacy strict checks never fail.

---

## 4. Verification and Testing

1. **Unit & Integration Tests** ([`src/employees/tests/test_activation.py`](src/employees/tests/test_activation.py)):
   - `test_service_get_detail_is_active_true_for_emp_active` — PASSED
   - `test_service_get_detail_is_active_false_for_emp_inactive` — PASSED
   - `test_service_activate_employee` — PASSED
   - `test_service_deactivate_employee` — PASSED
   - `test_service_update_employee_with_is_active_true` — PASSED
   - `test_router_patch_with_is_active_true` — PASSED
   - `test_router_patch_with_is_active_false` — PASSED
   - `test_router_patch_with_no_body` — PASSED
   - `test_router_post_activate` — PASSED
   - `test_router_post_deactivate` — PASSED

2. **Database Verification**:
   - Verified `list_employees` returns `is_active: True` for all active employees.
   - Tested deactivate -> activate cycle via `service.deactivate_employee` and `service.activate_employee`.
   - Tested `update_employee` with `UpdateEmployeeRequest(is_active=False)` and `UpdateEmployeeRequest(is_active=True)`.
