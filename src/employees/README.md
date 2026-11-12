# Employee Microservice (`src/employees`)

## Overview
The **Employee Microservice** handles employee directory management, profile details, manager-subordinate hierarchies, and status lifecycle operations (activation, deactivation, and updates).

## Key Architecture & Database Model
- **ORM / Database:** SQLAlchemy 2.0 Async with PostgreSQL.
- **Table:** `employees`
  - References `designations` via `designation_id`.
  - References `departments` via `department_id`.
  - Self-references `employees` via `manager_id`.
  - References `status_master` via `status_id`.
  - **Note:** The `employees` table does **not** store a boolean `is_active` column directly. Active status is resolved dynamically through joined `status_master` records (`status_code` in `("ACTIVE", "EMP_ACTIVE", "GEN_ACTIVE")`).

---

## Status Management & Lifecycle

### Supported Status Codes in `status_master`
- `EMP_ACTIVE` / `ACTIVE`: Active employee state (`is_active = True`).
- `EMP_INACTIVE` / `INACTIVE`: Inactive employee state (`is_active = False`).
- `EMP_ON_LEAVE`, `EMP_TERMINATED`, `EMP_PROBATION`: Specialized lifecycle states.

---

## API Endpoints

### 1. List Employees
- **Method / URL:** `GET /aabhar/v1/employees/list`
- **Query Parameters:** `page`, `limit`, `department_id`, `designation_id`, `status_id`, `manager_id`, `is_active`, `search`, `sort_by`, `sort_order`
- **Response:** `EmployeeListResponse`

### 2. Get Employee Details
- **Method / URL:** `GET /aabhar/v1/employees/{employee_id}`
- **Response:** `EmployeeDetailResponse`

### 3. Create Employee
- **Method / URL:** `POST /aabhar/v1/employees/create`
- **Request Body:** `CreateEmployeeRequest`
- **Response:** `EmployeeCreatedResponse` (Status 201)

### 4. Update Employee
- **Method / URL:** `PUT /aabhar/v1/employees/{employee_id}`
- **Request Body:** `UpdateEmployeeRequest` (supports `username`, `email`, `department_id`, `designation_id`, `manager_id`, `status_id`, `date_of_birth`, `is_active`)
- **Activation / Deactivation:** Setting `{"is_active": true}` automatically transitions the employee to `EMP_ACTIVE`. Setting `{"is_active": false}` transitions the employee to `EMP_INACTIVE`.

### 5. Partially Update / Toggle Active State
- **Method / URL:** `PATCH /aabhar/v1/employees/{employee_id}`
- **Request Body (Optional):** `UpdateEmployeeRequest`
  - Body `{"is_active": true}`: Activates employee.
  - Body `{"is_active": false}`: Deactivates employee.
  - Empty / No body: Deactivates employee (soft-delete backwards compatibility).
- **Response:** 204 No Content

### 6. Explicit Activation
- **Method / URL:** `POST /aabhar/v1/employees/{employee_id}/activate` or `PATCH /aabhar/v1/employees/{employee_id}/activate`
- **Role Required:** `SUPER_ADMIN`, `HR_ADMIN`
- **Response:** 204 No Content

### 7. Explicit Deactivation
- **Method / URL:** `POST /aabhar/v1/employees/{employee_id}/deactivate` or `PATCH /aabhar/v1/employees/{employee_id}/deactivate`
- **Role Required:** `SUPER_ADMIN`, `HR_ADMIN`
- **Response:** 204 No Content

---

## Testing & Verification
Tests for activation, deactivation, status translation, and router endpoints are located in:
- `src/employees/tests/test_activation.py`
- `src/employees/tests/test_schemas.py`
