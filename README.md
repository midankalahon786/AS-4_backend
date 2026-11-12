# Employee Recognition & Rewards Platform (Backend)

## 📋 **Project Overview**
This is the backend service for the **Employee Recognition & Rewards Platform**, a system designed to boost organizational engagement through peer-to-peer recognition, automated celebrations, and measurable impact analytics.

The platform enables employees to send points-based appreciation, redeem rewards from a catalog, and integrates seamlessly with workplace tools like Slack and Microsoft Teams.

## 🛠 **Tech Stack**

### **Core Application**
**Framework:** FastAPI (Python 3.10+)
**ORM:** Prisma Client Python (Database Access)
**Database:** PostgreSQL (Transactional Data) 
**Caching & Rate Limiting:** Redis 
**Authentication:** OAuth2 / OIDC (Keycloak or Internal Auth)

### **Infrastructure & DevOps**
**Containerization:** Docker & Kubernetes (Helm) [cite: 53]
**Infrastructure as Code:** Terraform (AWS/Azure/GCP agnostic) [cite: 54]
**Background Workers:** Celery + RabbitMQ (for notifications/async tasks) [cite: 50]
**Storage:** AWS S3 (for image/video attachments) [cite: 51]
**CI/CD:** GitHub Actions [cite: 55]

## ✨ **Key Features**
1. **Recognition Engine:** Peer-to-peer recognition with point values, hashtags (e.g., #collaboration), and rich media attachments.
2. **Rewards Catalog:** Inventory management for gift cards, swag, and redemption workflows.
3. **Automations:** Scheduled milestone celebrations (birthdays, work anniversaries).
4. **Integrations:** Webhooks and APIs for Slack/Teams bots and HRIS synchronization.
5.  **Analytics:** Manager dashboards for tracking participation trends and budget usage.

## 🚀 **Getting Started**

### Prerequisites
* Python 3.10+
* Node.js (Required for Prisma CLI)
* Docker & Docker Compose (for local DB/Redis)

# 🛠️ Setup & Installation

## Application

```
PROJECT_NAME="Employee R&R API"
DEBUG=True
SECRET_KEY=change_this_secret_key
```

## **1. Clone the repository**

```
git clone https://github.com/LoneTerror/AS-4_backend.git
cd AS-4_backend
```

## **2. Create a virtual environment folder (venv)**

```
python -m venv venv
```

## **3. Activate the virtual environment**

```
.\venv\Scripts\activate
```

## **4. Install Dependencies using the following `pip` command (only after activating the venv)**

```
pip install -r requirements.txt
```

## **Database (Prisma)**
## **5. Initialize Prisma**

```
prisma init
```

## **6. Pull the schema from Database using Prisma**

```
prisma db pull
```

## **7. Generate the Prisma**

```
prisma generate
```

## **8. To work with microservices, switch to `/src`**

```
cd src
```

## **9. Create the database `.env` file in root directory**

```
DATABASE_URL="postgresql://user:pass@ep-cool-pooler.region.neon.tech/neondb?sslmode=require"
```

## **10. Start backend**

```
uvicorn main:app --reload
```

## Uvicorn Commands
- Refer to Uvicorn CLI Options at [Documentation](https://uvicorn.dev/#command-line-options)

## Caching (Optional)

```
REDIS_URL="redis://localhost:6379/0"
```

## External Services

```
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret
S3_BUCKET_NAME=rr-attachments
```

## Git Initialization Commands
* Now, open your terminal in the project folder and run these commands one by one to push everything to GitHub.

**Step 1: Initialize Git**

```
git init
```

# ***OR***
*(Cloning is recommend if you want to contribute and suggest changes to this repository)*

**Clone this repository**

```
git clone https://github.com/LoneTerror/AS-4_backend.git
```

**Step 2: Link to GitHub Repository (if you have ran the `git init` command)**

```
git remote add origin https://github.com/LoneTerror/AS-4_backend.git
```

**Step 3: Pull Recent Changes Before Pushing**

```
git pull
```

**Step 4: Create New Branch before push**

```
git branch -M <git_username>-patch-<patch_number>
```
*(Example: git branch -M loneTerror-patch-0)*

**Step 5: Add Files**

```
git add .
```

**Step 6: Commit**

```
git commit -m "Initial commit: Backend Configuration Done"
```

**Step 7: Push (on the new branch you created earlier)**

```
git git push -u origin <branchname>
```
*(Example: git push -u origin loneTerror-patch-0)*

**Step 8: Pull Request**

* Go To  [Pull Requests](https://github.com/LoneTerror/AS-4_backend/pulls)
* The CodeOwners will review your pull request, then they will approve/reject
* If your pull request is approved, then your created branch will be merged and deleted

---

## 📝 Recent Fixes & Change Log

### 1. Reward Catalog Redemption Fix
- **Issue**: Users could not redeem items from the reward catalog (`POST /aabhar/v1/rewards/redeem` failed with 500/422).
- **Fixes**:
  - Imported `Wallet` model into `src/rewards/models.py` and `src/rewards/repository.py` to eliminate SQLAlchemy `NoReferencedTableError` when mapping `RewardHistory.wallet_id`.
  - Added robust database fallbacks in `RewardService` for wallet lookups (`get_wallet_id_for_user`, `grant_reward`, `get_history`).
  - Allowed `points` to be optional in `RedeemRewardRequest`, defaulting seamlessly to `catalog_item.default_points`.
  - Added route `POST /aabhar/v1/rewards/catalog/{catalog_id}/redeem` allowing direct redemption from item view.
  - Made `CurrentUser.email` nullable (`str | None = ""`) in `src/common/dependencies.py` to prevent validation errors on tokens without emails.
  - Fixed `NotificationService` repository instantiation in `src/rewards/dependencies.py` and added auto-wrapping for `AsyncSession`.
  - Corrected `Transaction.status_master` relationship path in `src/wallet/models.py`.
- **Details**: Full documentation in `REWARD_REDEMPTION_FIX.md`.

### 2. Employee Activation Fix
- **Issue**: Admins could not activate deactivated employees (`PATCH /aabhar/v1/employees/{id}` failed to activate).
- **Fixes**:
  - Added `is_active: bool | None` to `UpdateEmployeeRequest`.
  - Added dedicated activation/deactivation methods in `src/employees/service.py` (`activate_employee`, `deactivate_employee`).
  - Added explicit routes `POST/PATCH /aabhar/v1/employees/{id}/activate` and `POST/PATCH /aabhar/v1/employees/{id}/deactivate`.
  - Standardized active employee status code check to include `"ACTIVE"`, `"EMP_ACTIVE"`, and `"GEN_ACTIVE"`.
- **Details**: Full documentation in `EMPLOYEE_ACTIVATION_FIX.md`.

### 3. Dashboard & Analytics Visibility Fix
- **Issue**: Dashboard/analytics data was not visible to both administrators and standard employees (HTTP 403 Forbidden on dashboard endpoints, empty reviews for admins, 422 unprocessable entity on inter-service stats aggregation).
- **Fixes**:
  - Normalized route key construction in `src/common/dependencies.py` to prevent route prefix stripping and duplication when sub-routers are mounted with prefixes like `/dashboard`.
  - Extended RBAC bypass in `check_route_permission` to include `"ADMIN"` alongside `"SUPER_ADMIN"`.
  - Updated `src/recognition/models.py` with `reviewer_employee` and `receiver_employee` relationships so usernames display on review cards.
  - Enabled platform-wide query modes on `/internal/reviews/recent`, `/internal/reviews/stats`, and `/internal/wallets/stats` when `employee_id` is omitted, returning organization-wide metrics and review histories for administrators while maintaining personal views for regular employees.
  - Added regression test suite in `src/analytics/tests/test_dashboard_analytics.py`.
- **Details**: Full documentation in `DASHBOARD_ANALYTICS_FIX.md`.

### 4. Rewards Control Panel Visibility & Access Control Fix
- **Issue**: Normal users (`EMPLOYEE`, `MANAGER`, etc.) could see the Control Panel link in the navbar and access the Rewards Control Panel card and management pages (`/control-panel` and `/rewards`).
- **Fixes**:
  - Refactored `D:\RNR-Frontend\components\layout\Navbar.tsx` so the "Control Panel" link is strictly hidden from standard users: filters out `SELF_SERVICE_ROUTES` and requires explicit write methods on admin prefixes or elevated admin roles (`isAdminUser()`).
  - Restricted `POST:/aabhar/v1/rewards/catalog/{catalog_id}/redeem` and `GET:/aabhar/v1/rewards/history` to admin roles (`SUPER_ADMIN`, `ADMIN`, `HR_ADMIN`), removing `EMPLOYEE` and `MANAGER` assignments.
  - Deactivated stale permissions in the `route_permissions` database table and ensured active permissions for the `ADMIN` role.
  - Added catalog redemption routes to `SELF_SERVICE_ROUTES` in `D:\RNR-Frontend\components\features\auth\ProtectedRoute.tsx` and `D:\RNR-Frontend\app\(dashboard)\control-panel\page.tsx`.
  - Added redirect guard in `control-panel/page.tsx` redirecting non-admin users directly to `/dashboard`.
  - Added automated test suite in `src/rewards/tests/test_permissions.py` (4/4 passed).
- **Details**: Full documentation in `REWARDS_CONTROL_PANEL_FIX.md`.
