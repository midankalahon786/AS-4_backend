# Rewards Control Panel Access & Visibility Fix

## Overview
Normal users (`EMPLOYEE`, `MANAGER`, etc.) previously had visibility into the Admin Control Panel navbar link and were able to see and access the **Rewards Control Panel** (`/control-panel` Rewards card and `/rewards` admin management view).

This issue has been completely resolved. Normal users are strictly prohibited from viewing or accessing the Control Panel and Rewards management at any point, while elevated administrators (`SUPER_ADMIN`, `ADMIN`, `HR_ADMIN`) retain full management capabilities over the reward catalog, stock, and categories.

---

## Root Causes Identified

1. **Frontend `Navbar.tsx` Missing Write Method & Self-Service Filtering:**
   - In `D:\RNR-Frontend\components\layout\Navbar.tsx`, the Control Panel link visibility check tested whether any route key from `GET /aabhar/v1/roles/my-permissions` matched `CONTROL_PANEL_PREFIXES = ['/aabhar/v1/rewards', '/aabhar/v1/employees', ...]`.
   - It did **not** filter out `SELF_SERVICE_ROUTES` and did **not** verify that the permission had an HTTP write method (`POST`, `PUT`, `PATCH`, `DELETE`).
   - Because standard employees have self-service routes (such as `GET:/aabhar/v1/rewards/catalog` or `POST:/aabhar/v1/rewards/redeem`), the check evaluated to `true`, rendering the "Control Panel" link in the navbar for all normal employees.

2. **Backend Route Registration of `POST:/aabhar/v1/rewards/catalog/{catalog_id}/redeem`:**
   - In `src/rewards/main.py` and the database `route_permissions` table, `POST:/aabhar/v1/rewards/catalog/{catalog_id}/redeem` was assigned to `["SUPER_ADMIN", "HR_ADMIN", "MANAGER", "EMPLOYEE"]`.
   - In `control-panel/page.tsx` and `ProtectedRoute.tsx`, the Rewards card and page are gated by `pathPrefix: '/aabhar/v1/rewards/catalog'`, requiring at least one write method starting with that prefix.
   - The frontend's `SELF_SERVICE_ROUTES` set only contained `'POST:/aabhar/v1/rewards/redeem'`, not the catalog-nested redeem route.
   - As a result, the frontend treated normal employees as having write permissions on the catalog, displaying the "Rewards" card in `/control-panel` and permitting access to `/rewards`.

3. **Improper Global History Permission Assigned to Employees:**
   - In `src/rewards/main.py`, `"GET:/aabhar/v1/rewards/history"` (Admin Global Redemption History) was mistakenly assigned to `EMPLOYEE` and `MANAGER` instead of strictly admin roles.

4. **Missing `ADMIN` Role in Rewards Management Overrides:**
   - In `src/rewards/main.py`, admin routes only listed `SUPER_ADMIN` and `HR_ADMIN`, leaving standard `ADMIN` users without rewards permissions.

---

## Changes Implemented

### 1. Backend Route Overrides & Database Permissions (`src/rewards/main.py`)
- **Restricted Admin Routes:**
  - Removed `EMPLOYEE` and `MANAGER` from `GET:/aabhar/v1/rewards/history` and `POST:/aabhar/v1/rewards/catalog/{catalog_id}/redeem`.
  - Added `ADMIN` to all admin routes alongside `SUPER_ADMIN` and `HR_ADMIN`.
- **Default Lifespan Registration:**
  - Updated `register_app_routes(app, default_roles=["SUPER_ADMIN", "ADMIN", "HR_ADMIN"], ...)` in `src/rewards/main.py`.
- **Database Cleanup:**
  - Deactivated stale `route_permissions` for `EMPLOYEE` and `MANAGER` on `GET:/aabhar/v1/rewards/history` and `POST:/aabhar/v1/rewards/catalog/{catalog_id}/redeem`.
  - Ensured active `route_permissions` for the `ADMIN` role.

### 2. Frontend Navbar Visibility (`D:\RNR-Frontend\components\layout\Navbar.tsx`)
- Imported `isAdminUser` from `@/lib/role-utils`.
- Defined `WRITE_METHODS`, `SELF_SERVICE_ROUTES`, and `CONTROL_PANEL_WRITE_PREFIXES`.
- Refactored `hasControlPanelAccess` logic:
  - If `isAdminUser()` is true, access is granted immediately.
  - For other users, strips `SELF_SERVICE_ROUTES` from permissions.
  - Only grants access if the user has an explicit admin write route (`POST`, `PUT`, `PATCH`, `DELETE`) matching control panel prefixes (or GET access to `/organizations/audit-logs`).
  - Standard employees evaluate to `false` and never see "Control Panel" in the navbar.

### 3. Frontend Control Panel Hub & Page Protection
- **`D:\RNR-Frontend\app\(dashboard)\control-panel\page.tsx`:**
  - Added `'POST:/aabhar/v1/rewards/catalog/{catalog_id}/redeem'` and `'POST:/aabhar/v1/rewards/catalog/{id}/redeem'` to `SELF_SERVICE_ROUTES`.
  - Added redirect safeguard: If `!isAdminUser()` or no accessible cards exist, user is immediately redirected to `/dashboard`.
- **`D:\RNR-Frontend\components\features\auth\ProtectedRoute.tsx`:**
  - Added catalog redeem variants to `SELF_SERVICE_ROUTES`.
  - Ensures normal employees cannot bypass `<ProtectedRoute adminOnly>` or `<ProtectedRoute adminOnly pathPrefix="/aabhar/v1/rewards/catalog">`.

---

## Verification & Automated Testing

1. **Automated Unit & Integration Tests (`src/rewards/tests/test_permissions.py`):**
   - `test_role_overrides_rewards_admin_isolation`: Verifies `EMPLOYEE` and `MANAGER` are strictly excluded from admin routes in `ROLE_OVERRIDES`.
   - `test_employee_self_service_routes_accessible`: Verifies employees retain access to catalog browsing (`GET /catalog`), categories (`GET /categories`), personal history (`GET /history/me`), and redemption (`POST /redeem`).
   - `test_database_route_permissions_isolation`: Verifies DB query on `route_permissions` confirms no active admin routes for `EMPLOYEE`.
   - `test_frontend_gating_simulation`: Simulates exact frontend card and navbar gating logic, confirming `hasRewardsCard === false` and `hasControlPanelAccess === false` for employees.
   - Result: **4/4 passed (100%)**.

2. **Redemption Tests (`src/rewards/tests/test_redemption.py`):**
   - Result: **7/7 passed (100%)**.

3. **Frontend Production Build:**
   - Ran `npm run build` in `D:\RNR-Frontend`.
   - Result: **Success**, zero compile or lint errors across all routes (`/control-panel`, `/rewards`, `/reward-categories`, etc.).
