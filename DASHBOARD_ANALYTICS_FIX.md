# Dashboard & Analytics Microservice Fix

## 1. Overview & Problem Description
When logging into the Employee Rewards and Recognition platform, dashboard and analytics data was not displaying for either administrators (`SUPER_ADMIN`, `ADMIN`, `HR_ADMIN`) or regular employees (`EMPLOYEE`, `MANAGER`).

### Symptoms
1. **HTTP 403 Forbidden for Regular Employees**:
   - Calling `/aabhar/v1/analytics/dashboard/recent-reviews`, `/leaderboard`, or `/platform-stats` failed with `403 Forbidden: "No permissions configured for GET:/aabhar/v1/analytics/..."`.
2. **Empty or Missing Data for Admins**:
   - `recent-reviews` returned `[]` because the database query strictly filtered by `receiver_id == current_user.id`. In standard workflows, administrators give recognitions rather than receive them.
   - `platform-stats` returned single-user stats (0 reviews received) rather than organization-wide aggregates.
3. **HTTP 422 Unprocessable Entity on Inter-Service Calls**:
   - Internal queries to `/internal/reviews/recent` and `/internal/wallets/stats` required `employee_id` query parameters, causing failure when Analytics requested platform-wide statistics.
4. **Missing Reviewer & Receiver Display Names**:
   - Recognition reviews displayed `"Unknown"` or `None` instead of employee usernames because relationships were not loaded on the `Review` model.

---

## 2. Root Cause Analysis

1. **FastAPI Route Key Path Truncation and Duplication**:
   - Starlette and FastAPI store the sub-router's relative path in `request.scope["route"].path` (e.g. `/recent-reviews`).
   - The permission check dependency `_build_route_key(request)` previously miscalculated prefixes when combined with `root_path`, leading to duplicated paths (e.g., `GET:/aabhar/v1/analytics/aabhar/v1/analytics/dashboard/recent-reviews`) or stripped prefixes (`GET:/aabhar/v1/analytics/recent-reviews`).
   - The database table `route_permissions` stored `GET:/aabhar/v1/analytics/dashboard/recent-reviews`, causing permission lookup failure for non-superadmin roles.
2. **Permission Check Bypass Scope**:
   - `check_route_permission` strictly checked `"SUPER_ADMIN" in current_user.roles`, failing to bypass the standard `"ADMIN"` role.
3. **Single-Employee Filtering on Internal Endpoints**:
   - `RecognitionRepository.get_recent_reviews_internal` strictly filtered `where Review.receiver_id == employee_id`.
   - `WalletRepository.get_wallet_stats` strictly required an `employee_id`.
4. **ORM Relationship Missing on Recognition Model**:
   - `Review` in `src/recognition/models.py` lacked explicit SQLAlchemy relationships to `Employee` for `reviewer_id` and `receiver_id`, preventing the service from populating `reviewer_name` and `receiver_name`.

---

## 3. Changes Applied

### A. Route Key Generation & Permission Checks (`src/common/dependencies.py`)
- **`_build_route_key(request)`**:
  - Normalized `scope_path` relative to `root_path`.
  - Preserved sub-router prefixes (e.g., `/dashboard/`) when forming the route key.
  - Eliminated duplicate `root_path` prefixing.
- **`check_route_permission(request, current_user)`**:
  - Updated admin bypass to include `ADMIN` alongside `SUPER_ADMIN`:
    ```python
    if any(r in current_user.roles for r in ("SUPER_ADMIN", "ADMIN")):
        return current_user
    ```
  - Added multi-key fallback check in database lookup to test both prefixed (`/dashboard/...`) and base route keys.

### B. Recognition Service (`src/recognition/`)
- **Model Relationships (`src/recognition/models.py`)**:
  - Added `reviewer_employee` and `receiver_employee` relationships on `Review` mapped to `Employee`.
- **Serialization & Schemas (`src/recognition/schemas.py`, `src/recognition/service.py`)**:
  - Added `reviewer_name: str | None` and `receiver_name: str | None` to `ReviewResponse`.
  - Serialized names from employee relationship records instead of hardcoded placeholders.
- **Platform-Wide Queries (`src/recognition/repository.py`, `src/recognition/internal_router.py`)**:
  - Made `employee_id: UUID | None = None` optional on:
    - `/internal/reviews/recent`
    - `/internal/reviews/stats`
  - When `employee_id is None`:
    - Queries recent reviews platform-wide with eager-loaded `reviewer_employee` and `receiver_employee`.
    - Computes platform-wide review metrics across all employees.

### C. Wallet Service (`src/wallet/`)
- **Platform-Wide Wallet Aggregation (`src/wallet/repository.py`, `src/wallet/internal_router.py`)**:
  - Made `employee_id: UUID | None = None` optional on `/internal/wallets/stats`.
  - When `employee_id is None`:
    - Aggregates platform-wide available points and total earned points across all wallets.
    - Aggregates platform-wide monthly point credits and reward redemptions.

### D. Analytics Service (`src/analytics/`)
- **Router (`src/analytics/router.py`)**:
  - Enabled optional `employee_id` query parameter on:
    - `/recent-reviews`
    - `/platform-stats`
  - Automatically routes admins to organization-wide aggregates while routing regular employees to personal statistics.
- **Service (`src/analytics/service.py`)**:
  - Updated `_key_reviews` and `_key_platform` cache keys to support platform-wide caching (`dashboard:reviews:all`, `dashboard:platform:all`).
  - Added graceful fallback for category tags and reviewer usernames.
- **Registration (`src/analytics/main.py`)**:
  - Updated `ROLE_OVERRIDES` to include `ALL_ROLES` for employee dashboard routes (`/leaderboard`, `/recent-reviews`, `/platform-stats`).
  - Registered all routes in PostgreSQL `route_permissions` table.

---

## 4. Verification & Testing

### Automated Regression Tests
Ran targeted pytest suite `src/analytics/tests/test_dashboard_analytics.py`:
- `test_build_route_key_with_dashboard_prefix`: PASSED
- `test_build_route_key_without_prefix`: PASSED
- `test_analytics_service_recent_reviews_admin_and_employee`: PASSED
- `test_analytics_service_platform_stats`: PASSED
- `test_analytics_service_leaderboard`: PASSED
- `test_check_route_permission_admin_bypass`: PASSED
- **Result: 6/6 tests passed.**

### Live Service Verification (HTTP on Port 8008)
Tested with live JWT tokens for `admin.user` (`SUPER_ADMIN`, `ADMIN`) and `shubrajit.deb` (`EMPLOYEE`):
1. **Admin Endpoints**:
   - `GET /aabhar/v1/analytics/dashboard/recent-reviews` -> **200 OK** (Returns 5 recent reviews with reviewer usernames and category tags).
   - `GET /aabhar/v1/analytics/dashboard/leaderboard` -> **200 OK** (Returns ranked employee leaderboard).
   - `GET /aabhar/v1/analytics/dashboard/platform-stats` -> **200 OK** (Returns platform totals: 1,074,799 points, 14 rewards redeemed, 14 active users).
   - `GET /aabhar/v1/analytics/dashboard/teams` -> **200 OK** (Returns department breakdown with member counts and performance scores).
   - `GET /aabhar/v1/analytics/dashboard/participation` -> **200 OK** (Returns 64.3% active participation rate).
   - `GET /aabhar/v1/analytics/dashboard/recognition-trend?range=6m` -> **200 OK** (Returns 6-month monthly trends).
   - `GET /aabhar/v1/analytics/dashboard/recognition/teams` -> **200 OK** (Returns recognition per department).
   - `GET /aabhar/v1/analytics/dashboard/recognition/users` -> **200 OK** (Returns recognition per user).
2. **Employee Endpoints**:
   - `GET /aabhar/v1/analytics/dashboard/recent-reviews` -> **200 OK** (Returns employee's received reviews from peers/admins).
   - `GET /aabhar/v1/analytics/dashboard/leaderboard` -> **200 OK** (Returns leaderboard).
   - `GET /aabhar/v1/analytics/dashboard/platform-stats` -> **200 OK** (Returns employee's personal earned points and reviews).
   - `GET /aabhar/v1/analytics/dashboard/teams` -> **403 Forbidden** (Verified strict RBAC preventing non-admin access).
