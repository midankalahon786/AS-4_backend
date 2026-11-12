"""
seed.py
Full seed script for rnr_db / aabhar_test.
Native SQLAlchemy 2.0 Async implementation.

Run with:
    uv run python seed.py
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
import bcrypt
from dotenv import load_dotenv

# Load environment variables before importing application modules
load_dotenv()

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from src.core.database import async_session_factory

# Employee domain
from src.employees.models import Employee, StatusMaster
try:
    from src.employees.models import Designation
except ImportError:
    from src.organization.models import Designation

# Organization domain
from src.organization.models import Department
try:
    from src.organization.models import DepartmentType
except ImportError:
    from src.employees.models import DepartmentType

# Roles domain
from src.roles.models import EmployeeRole, Role

# Wallet domain
from src.wallet.models import TransactionType, Wallet
try:
    from src.wallet.models import PointTransaction
except ImportError:
    from src.wallet.models import Transaction as PointTransaction

# Recognition domain
from src.recognition.models import Review, ReviewCategory, ReviewCategoryTag

# Rewards domain
from src.rewards.models import RewardCatalog, RewardCategory, RewardHistory

# Notifications domain
from src.notifications.models import Notification

HASH = bcrypt.hashpw(b"Password@123", bcrypt.gensalt()).decode()
NOW = datetime.now(timezone.utc)


def model_dict(model, data: dict) -> dict:
    """Filter dictionary to only keys that match columns defined on the model."""
    valid_cols = {c.name for c in model.__table__.columns}
    return {k: v for k, v in data.items() if k in valid_cols}


async def main():
    print("Seeding database via SQLAlchemy 2.0 Async...")

    async with async_session_factory() as session:
        # =========================================================================
        # 1. STATUS MASTER
        # =========================================================================
        print("  -> status_master")
        statuses = [
            {"code": "EMP_ACTIVE",     "name": "Active",      "entity": "employee",    "desc": "Employee is active"},
            {"code": "EMP_INACTIVE",   "name": "Inactive",    "entity": "employee",    "desc": "Employee is inactive"},
            {"code": "EMP_ON_LEAVE",   "name": "On Leave",    "entity": "employee",    "desc": "Employee is on leave"},
            {"code": "EMP_TERMINATED", "name": "Terminated",  "entity": "employee",    "desc": "Employee has been terminated"},
            {"code": "EMP_PROBATION",  "name": "Probation",   "entity": "employee",    "desc": "Employee is on probation"},
            {"code": "REV_PENDING",    "name": "Pending",     "entity": "review",      "desc": "Review is pending approval"},
            {"code": "REV_APPROVED",   "name": "Approved",    "entity": "review",      "desc": "Review has been approved"},
            {"code": "REV_REJECTED",   "name": "Rejected",    "entity": "review",      "desc": "Review has been rejected"},
            {"code": "REV_DRAFT",      "name": "Draft",       "entity": "review",      "desc": "Review is in draft state"},
            {"code": "REV_WITHDRAWN",  "name": "Withdrawn",   "entity": "review",      "desc": "Review has been withdrawn"},
            {"code": "TXN_PENDING",    "name": "Pending",     "entity": "transaction", "desc": "Transaction is pending"},
            {"code": "TXN_COMPLETED",  "name": "Completed",   "entity": "transaction", "desc": "Transaction completed"},
            {"code": "TXN_FAILED",     "name": "Failed",      "entity": "transaction", "desc": "Transaction failed"},
            {"code": "TXN_REVERSED",   "name": "Reversed",    "entity": "transaction", "desc": "Transaction reversed"},
            {"code": "TXN_PROCESSING", "name": "Processing",  "entity": "transaction", "desc": "Transaction is processing"},
            {"code": "RWD_AVAILABLE",  "name": "Available",   "entity": "reward",      "desc": "Reward is available"},
            {"code": "RWD_REDEEMED",   "name": "Redeemed",    "entity": "reward",      "desc": "Reward has been redeemed"},
            {"code": "RWD_EXPIRED",    "name": "Expired",     "entity": "reward",      "desc": "Reward has expired"},
            {"code": "RWD_RESERVED",   "name": "Reserved",    "entity": "reward",      "desc": "Reward is reserved"},
            {"code": "RWD_CANCELLED",  "name": "Cancelled",   "entity": "reward",      "desc": "Reward was cancelled"},
            {"code": "ROLE_ACTIVE",    "name": "Active",      "entity": "role",        "desc": "Role is active"},
            {"code": "ROLE_INACTIVE",  "name": "Inactive",    "entity": "role",        "desc": "Role is inactive"},
            {"code": "GEN_ACTIVE",     "name": "Active",      "entity": "general",     "desc": "Record is active"},
            {"code": "GEN_INACTIVE",   "name": "Inactive",    "entity": "general",     "desc": "Record is inactive"},
            {"code": "GEN_ARCHIVED",   "name": "Archived",    "entity": "general",     "desc": "Record has been archived"},
            {"code": "GEN_DELETED",    "name": "Deleted",     "entity": "general",     "desc": "Record has been soft deleted"},
            {"code": "GEN_DRAFT",      "name": "Draft",       "entity": "general",     "desc": "Record is in draft"},
            {"code": "GEN_PUBLISHED",  "name": "Published",   "entity": "general",     "desc": "Record has been published"},
            {"code": "GEN_SUSPENDED",  "name": "Suspended",   "entity": "general",     "desc": "Record is suspended"},
            {"code": "GEN_PENDING",    "name": "Pending",     "entity": "general",     "desc": "Record is pending"},
            {"code": "ACTIVE",         "name": "Active",      "entity": "general",     "desc": "General active status"},
            {"code": "INACTIVE",       "name": "Inactive",    "entity": "general",     "desc": "General inactive status"},
            {"code": "APPROVED",       "name": "Approved",    "entity": "general",     "desc": "General approved status"},
            {"code": "SUCCESS",        "name": "Success",     "entity": "TRANSACTION", "desc": "Transaction successful"},
            {"code": "REVIEW_ACTIVE",  "name": "Review Active","entity": "REVIEW",      "desc": "Review approved and active"},
        ]

        for s in statuses:
            stmt = insert(StatusMaster).values(
                **model_dict(StatusMaster, {
                    "status_code": s["code"],
                    "status_name": s["name"],
                    "entity_type": s["entity"],
                    "description": s["desc"],
                    "created_at": NOW,
                    "updated_at": NOW,
                })
            ).on_conflict_do_nothing(index_elements=["status_code"])
            await session.execute(stmt)
        await session.commit()

        status_rows = (await session.execute(select(StatusMaster))).scalars().all()
        status_map = {s.status_code: s.status_id for s in status_rows}

        emp_active_id = status_map.get("EMP_ACTIVE", status_map.get("ACTIVE"))
        rev_approved_id = status_map.get("REV_APPROVED", status_map.get("APPROVED", emp_active_id))
        txn_completed_id = status_map.get("TXN_COMPLETED", status_map.get("SUCCESS", emp_active_id))

        # =========================================================================
        # 2. DEPARTMENT TYPES
        # =========================================================================
        print("  -> department_types")
        dept_type_data = [
            {"name": "Engineering",    "code": "ENG"},
            {"name": "Business",       "code": "BIZ"},
            {"name": "Operations",     "code": "OPS"},
            {"name": "Support",        "code": "SUP"},
            {"name": "Executive",      "code": "EXEC"},
            {"name": "Research",       "code": "RES"},
            {"name": "Creative",       "code": "CRE"},
            {"name": "Compliance",     "code": "COMP"},
            {"name": "Infrastructure", "code": "INFRA"},
            {"name": "Analytics",      "code": "ANLT"},
        ]

        for dt in dept_type_data:
            stmt = insert(DepartmentType).values(
                **model_dict(DepartmentType, {
                    "type_name": dt["name"],
                    "type_code": dt["code"],
                    "created_at": NOW,
                    "updated_at": NOW,
                })
            ).on_conflict_do_nothing(index_elements=["type_code"])
            await session.execute(stmt)
        await session.commit()

        dt_rows = (await session.execute(select(DepartmentType))).scalars().all()
        dt_map = {d.type_code: d.department_type_id for d in dt_rows}

        # =========================================================================
        # 3. DEPARTMENTS
        # =========================================================================
        print("  -> departments")
        dept_data = [
            {"name": "Backend Engineering",      "code": "BE",     "type_code": "ENG"},
            {"name": "Frontend Engineering",     "code": "FE",     "type_code": "ENG"},
            {"name": "DevOps & Infrastructure",  "code": "DEVOPS", "type_code": "INFRA"},
            {"name": "Product Management",       "code": "PM",     "type_code": "BIZ"},
            {"name": "Human Resources",          "code": "HR",     "type_code": "OPS"},
            {"name": "Finance & Accounting",     "code": "FIN",    "type_code": "BIZ"},
            {"name": "Quality Assurance",        "code": "QA",     "type_code": "ENG"},
            {"name": "Customer Success",         "code": "CS",     "type_code": "SUP"},
            {"name": "Data & Analytics",         "code": "DA",     "type_code": "ANLT"},
            {"name": "Executive Leadership",     "code": "EL",     "type_code": "EXEC"},
            {"name": "Security",                 "code": "SEC",    "type_code": "COMP"},
            {"name": "Mobile Engineering",       "code": "MOB",    "type_code": "ENG"},
            {"name": "Design & UX",              "code": "DES",    "type_code": "CRE"},
            {"name": "Research & Development",   "code": "RD",     "type_code": "RES"},
            {"name": "Marketing",                "code": "MKT",    "type_code": "BIZ"},
            {"name": "Legal & Compliance",       "code": "LEG",    "type_code": "COMP"},
            {"name": "Sales",                    "code": "SAL",    "type_code": "BIZ"},
            {"name": "IT Support",               "code": "ITS",    "type_code": "SUP"},
            {"name": "Business Intelligence",    "code": "BI",     "type_code": "ANLT"},
            {"name": "Platform Engineering",     "code": "PLE",    "type_code": "ENG"},
        ]

        for d in dept_data:
            stmt = insert(Department).values(
                **model_dict(Department, {
                    "department_name": d["name"],
                    "department_code": d["code"],
                    "department_type_id": dt_map.get(d["type_code"]),
                    "is_active": True,
                    "created_at": NOW,
                    "updated_at": NOW,
                })
            ).on_conflict_do_nothing(index_elements=["department_code"])
            await session.execute(stmt)
        await session.commit()

        dept_rows = (await session.execute(select(Department))).scalars().all()
        dept_map = {d.department_code: d.department_id for d in dept_rows}

        # =========================================================================
        # 4. DESIGNATIONS
        # =========================================================================
        print("  -> designations")
        designation_data = [
            {"name": "Chief Executive Officer",  "code": "CEO",    "level": 1},
            {"name": "Chief Technology Officer", "code": "CTO",    "level": 2},
            {"name": "Chief Financial Officer",  "code": "CFO",    "level": 2},
            {"name": "Vice President",           "code": "VP",     "level": 3},
            {"name": "Senior Director",          "code": "SDIR",   "level": 4},
            {"name": "Director",                 "code": "DIR",    "level": 5},
            {"name": "Senior Manager",           "code": "SMGR",   "level": 6},
            {"name": "Manager",                  "code": "MGR",    "level": 7},
            {"name": "Senior Engineer",          "code": "SENG",   "level": 8},
            {"name": "Engineer",                 "code": "ENG",    "level": 9},
            {"name": "Junior Engineer",          "code": "JENG",   "level": 10},
            {"name": "Lead Engineer",            "code": "LENG",   "level": 7},
            {"name": "Staff Engineer",           "code": "STENG",  "level": 6},
            {"name": "Senior Analyst",           "code": "SANA",   "level": 8},
            {"name": "Senior Consultant",        "code": "SCON",   "level": 7},
            {"name": "Team Lead",                "code": "TL",     "level": 7},
            {"name": "Product Manager",          "code": "PMGR",   "level": 7},
        ]

        for d in designation_data:
            stmt = insert(Designation).values(
                **model_dict(Designation, {
                    "designation_name": d["name"],
                    "designation_code": d["code"],
                    "level": d["level"],
                    "hierarchy_level": d["level"],
                    "is_active": True,
                    "created_at": NOW,
                    "updated_at": NOW,
                })
            ).on_conflict_do_nothing(index_elements=["designation_code"])
            await session.execute(stmt)
        await session.commit()

        desig_rows = (await session.execute(select(Designation))).scalars().all()
        desig_map = {d.designation_code: d.designation_id for d in desig_rows}

        # =========================================================================
        # 5. ROLES
        # =========================================================================
        print("  -> roles")
        role_data = [
            {"name": "Super Admin",      "code": "SUPER_ADMIN",   "desc": "Full system access",       "weight": 2.0},
            {"name": "Admin",            "code": "ADMIN",         "desc": "Administrative access",    "weight": 1.8},
            {"name": "HR Admin",         "code": "HR_ADMIN",      "desc": "HR administration access", "weight": 1.5},
            {"name": "HR Manager",       "code": "HR_MANAGER",    "desc": "HR management access",     "weight": 1.5},
            {"name": "Manager",          "code": "MANAGER",       "desc": "Team manager access",      "weight": 1.4},
            {"name": "Senior Employee",  "code": "SENIOR_EMP",    "desc": "Senior employee access",   "weight": 1.2},
            {"name": "Employee",         "code": "EMPLOYEE",      "desc": "Standard employee access", "weight": 1.0},
            {"name": "Finance",          "code": "FINANCE",       "desc": "Finance team access",      "weight": 1.2},
            {"name": "Department Head",  "code": "DEPT_HEAD",     "desc": "Department head access",   "weight": 1.6},
            {"name": "Team Lead",        "code": "TEAM_LEAD",     "desc": "Technical lead access",    "weight": 1.3},
            {"name": "Tech Lead",        "code": "TECH_LEAD",     "desc": "Technical leadership",     "weight": 1.4},
            {"name": "Legal Counsel",    "code": "LEGAL",         "desc": "Legal and compliance",     "weight": 1.2},
        ]

        for r in role_data:
            stmt = insert(Role).values(
                **model_dict(Role, {
                    "role_name": r["name"],
                    "role_code": r["code"],
                    "description": r["desc"],
                    "reviewer_weight": r["weight"],
                    "created_at": NOW,
                    "updated_at": NOW,
                })
            ).on_conflict_do_nothing(index_elements=["role_code"])
            await session.execute(stmt)
        await session.commit()

        role_rows = (await session.execute(select(Role))).scalars().all()
        role_map = {r.role_code: r.role_id for r in role_rows}

        # =========================================================================
        # 6. TRANSACTION TYPES
        # =========================================================================
        print("  -> transaction_types")
        txn_types = [
            {"name": "Points Earned",        "code": "POINTS_EARNED",    "is_credit": True,  "desc": "Points credited from review"},
            {"name": "Points Redeemed",      "code": "POINTS_REDEEMED",  "is_credit": False, "desc": "Points used for reward redemption"},
            {"name": "Points Adjustment",    "code": "POINTS_ADJ",       "is_credit": True,  "desc": "Manual adjustment by admin"},
            {"name": "Points Deduction",     "code": "POINTS_DED",       "is_credit": False, "desc": "Manual deduction by admin"},
            {"name": "Bonus Points",         "code": "BONUS",            "is_credit": True,  "desc": "Bonus points awarded"},
            {"name": "Credit",               "code": "CREDIT",           "is_credit": True,  "desc": "Standard credit"},
            {"name": "Debit",                "code": "DEBIT",            "is_credit": False, "desc": "Standard debit"},
            {"name": "Review Credit",        "code": "REVIEW_CREDIT",    "is_credit": True,  "desc": "Review credit"},
            {"name": "Reward Redemption",    "code": "REWARD_REDEMPTION","is_credit": False, "desc": "Reward debit"},
            {"name": "Welcome Bonus",        "code": "WELCOME_BONUS",    "is_credit": True,  "desc": "One-time welcome bonus"},
            {"name": "Peer Recognition",     "code": "PEER_RECOG",       "is_credit": True,  "desc": "Peer-to-peer recognition"},
        ]

        for t in txn_types:
            stmt = insert(TransactionType).values(
                **model_dict(TransactionType, {
                    "type_name": t["name"],
                    "type_code": t["code"],
                    "is_credit": t["is_credit"],
                    "description": t["desc"],
                    "created_at": NOW,
                    "updated_at": NOW,
                })
            ).on_conflict_do_nothing(index_elements=["type_code"])
            await session.execute(stmt)
        await session.commit()

        txn_type_records = (await session.execute(select(TransactionType))).scalars().all()
        txn_type_map = {t.type_code: t.type_id for t in txn_type_records}

        # =========================================================================
        # 7. REWARD CATEGORIES
        # =========================================================================
        print("  -> reward_categories")
        reward_cat_data = [
            {"name": "Gift Cards",           "code": "GIFT_CARD",   "desc": "Digital and physical gift cards"},
            {"name": "Electronics",          "code": "ELECTRONICS", "desc": "Gadgets and electronics"},
            {"name": "Travel & Experiences", "code": "TRAVEL",      "desc": "Travel vouchers and experiences"},
            {"name": "Wellness",             "code": "WELLNESS",    "desc": "Health and wellness rewards"},
            {"name": "Food & Dining",        "code": "FOOD",        "desc": "Restaurant and food vouchers"},
            {"name": "Company Merchandise",  "code": "MERCH",       "desc": "Company branded items"},
            {"name": "Entertainment",        "code": "ENTERTAIN",   "desc": "Movies, games, streaming"},
        ]

        for rc in reward_cat_data:
            stmt = insert(RewardCategory).values(
                **model_dict(RewardCategory, {
                    "category_name": rc["name"],
                    "category_code": rc["code"],
                    "description": rc["desc"],
                    "is_active": True,
                    "created_at": NOW,
                    "updated_at": NOW,
                })
            ).on_conflict_do_nothing(index_elements=["category_code"])
            await session.execute(stmt)
        await session.commit()

        reward_cats = (await session.execute(select(RewardCategory))).scalars().all()
        reward_cat_map = {r.category_code: r.category_id for r in reward_cats}

        # =========================================================================
        # 8. REWARD CATALOG
        # =========================================================================
        print("  -> reward_catalog")
        catalog_data = [
            {"name": "Amazon Gift Card Rs500",  "code": "AMZ_500",     "cat": "GIFT_CARD",   "def_pts": 500,   "min": 400,  "max": 600,   "stock": 100},
            {"name": "Amazon Gift Card Rs1000", "code": "AMZ_1000",    "cat": "GIFT_CARD",   "def_pts": 1000,  "min": 900,  "max": 1100,  "stock": 50},
            {"name": "Apple AirPods",           "code": "AIRPODS",     "cat": "ELECTRONICS", "def_pts": 8000,  "min": 7500, "max": 9000,  "stock": 10},
            {"name": "Kindle eReader",          "code": "KINDLE",      "cat": "ELECTRONICS", "def_pts": 5000,  "min": 4500, "max": 5500,  "stock": 15},
            {"name": "Swiggy Voucher Rs500",    "code": "SWIGGY_500",  "cat": "FOOD",        "def_pts": 500,   "min": 400,  "max": 600,   "stock": 150},
            {"name": "Netflix 3 Months",        "code": "NETFLIX_3M",  "cat": "ENTERTAIN",   "def_pts": 1200,  "min": 1000, "max": 1400,  "stock": 80},
            {"name": "Company T-Shirt",         "code": "TSHIRT",      "cat": "MERCH",       "def_pts": 300,   "min": 200,  "max": 400,   "stock": 200},
            {"name": "Company Hoodie",          "code": "HOODIE",      "cat": "MERCH",       "def_pts": 600,   "min": 500,  "max": 700,   "stock": 100},
        ]

        for c in catalog_data:
            stmt = insert(RewardCatalog).values(
                **model_dict(RewardCatalog, {
                    "reward_name": c["name"],
                    "reward_code": c["code"],
                    "category_id": reward_cat_map[c["cat"]],
                    "default_points": c["def_pts"],
                    "min_points": c["min"],
                    "max_points": c["max"],
                    "available_stock": c["stock"],
                    "is_active": True,
                    "created_at": NOW,
                    "updated_at": NOW,
                })
            ).on_conflict_do_nothing(index_elements=["reward_code"])
            await session.execute(stmt)
        await session.commit()

        catalog_items = (await session.execute(select(RewardCatalog))).scalars().all()
        catalog_map = {c.reward_code: c.catalog_id for c in catalog_items}

        # =========================================================================
        # 9. REVIEW CATEGORIES
        # =========================================================================
        print("  -> review_categories")
        review_cat_data = [
            {"code": "INNOVATION",    "name": "Innovation",            "multiplier": 1.5, "desc": "Creative contributions"},
            {"code": "TEAMWORK",      "name": "Teamwork",              "multiplier": 1.2, "desc": "Collaboration and support"},
            {"code": "LEADERSHIP",    "name": "Leadership",            "multiplier": 1.8, "desc": "Mentoring and guidance"},
            {"code": "DELIVERY",      "name": "Delivery Excellence",   "multiplier": 1.3, "desc": "Quality execution"},
            {"code": "CUSTOMER",      "name": "Customer Focus",        "multiplier": 1.4, "desc": "Customer impact"},
            {"code": "TECHNICAL",     "name": "Technical Excellence",  "multiplier": 1.5, "desc": "Deep technical work"},
            {"code": "QUALITY",       "name": "Quality",               "multiplier": 1.4, "desc": "Quality standards"},
            {"code": "STRATEGIC",     "name": "Strategic Thinking",    "multiplier": 1.7, "desc": "Long-term planning"},
        ]

        for rc in review_cat_data:
            stmt = insert(ReviewCategory).values(
                **model_dict(ReviewCategory, {
                    "category_code": rc["code"],
                    "category_name": rc["name"],
                    "multiplier": rc["multiplier"],
                    "description": rc["desc"],
                    "is_active": True,
                    "created_at": NOW,
                    "updated_at": NOW,
                })
            ).on_conflict_do_nothing(index_elements=["category_code"])
            await session.execute(stmt)
        await session.commit()

        review_cats = (await session.execute(select(ReviewCategory))).scalars().all()
        review_cat_map = {r.category_code: r for r in review_cats}

        # =========================================================================
        # 10. EMPLOYEES
        # =========================================================================
        print("  -> employees")
        admin_stmt = select(Employee).where(Employee.username == "admin.user")
        admin_emp = (await session.execute(admin_stmt)).scalar_one_or_none()

        if not admin_emp:
            admin_emp = Employee(
                **model_dict(Employee, {
                    "username": "admin.user",
                    "email": "admin@company.com",
                    "password_hash": HASH,
                    "designation_id": desig_map["CEO"],
                    "department_id": dept_map["EL"],
                    "status_id": emp_active_id,
                    "date_of_joining": date(2020, 1, 1),
                    "date_of_birth": date(1985, 3, 15),
                    "created_at": NOW,
                    "updated_at": NOW,
                })
            )
            session.add(admin_emp)
            await session.commit()
            await session.refresh(admin_emp)

        all_employees_to_seed = [
            {"username": "jane.smith",          "email": "jane.smith@company.com",       "desig": "VP",    "dept": "HR",     "doj": "2020-03-10", "dob": "1988-07-22"},
            {"username": "shubrajit.deb",       "email": "shubrajitdeb180603@gmail.com", "desig": "SENG",  "dept": "BE",     "doj": "2022-06-18", "dob": "2003-06-18"},
            {"username": "prasun.chakraborty",  "email": "nothingshere21@gmail.com",     "desig": "ENG",   "dept": "BE",     "doj": "2023-01-15", "dob": "2002-09-21"},
            {"username": "midanka.lahon",       "email": "midankalahon@gmail.com",       "desig": "ENG",   "dept": "FE",     "doj": "2023-02-20", "dob": "2001-11-05"},
            {"username": "swarup.das",          "email": "swarup1to3@gmail.com",         "desig": "SENG",  "dept": "BE",     "doj": "2021-08-01", "dob": "1998-03-30"},
            {"username": "mrinmoy.kashyap",     "email": "mrinmoykashyap.mk@gmail.com",  "desig": "ENG",   "dept": "QA",     "doj": "2022-11-14", "dob": "2000-05-14"},
            {"username": "rishav.bora",         "email": "rishavbora550@gmail.com",      "desig": "ENG",   "dept": "FE",     "doj": "2023-04-03", "dob": "2001-08-12"},
            {"username": "alice.wong",          "email": "alice.wong@company.com",      "desig": "SDIR",  "dept": "FIN",    "doj": "2019-06-01", "dob": "1986-04-10"},
            {"username": "bob.sharma",          "email": "bob.sharma@company.com",      "desig": "MGR",   "dept": "PM",     "doj": "2020-08-15", "dob": "1990-09-25"},
            {"username": "frank.das",           "email": "frank.das@company.com",       "desig": "TL",    "dept": "BE",     "doj": "2021-07-07", "dob": "1994-03-22"},
            {"username": "grace.hopper",        "email": "grace.hopper@company.com",    "desig": "DIR",   "dept": "PLE",    "doj": "2018-03-19", "dob": "1984-12-09"},
            {"username": "james.bond",          "email": "james.bond@company.com",      "desig": "SCON",  "dept": "LEG",    "doj": "2020-10-10", "dob": "1989-10-07"},
            {"username": "neil.gupta",          "email": "neil.gupta@company.com",      "desig": "LENG",  "dept": "BE",     "doj": "2021-06-21", "dob": "1993-06-21"},
        ]

        emp_map = {"admin.user": admin_emp.employee_id}

        for e in all_employees_to_seed:
            existing = (await session.execute(select(Employee).where(Employee.username == e["username"]))).scalar_one_or_none()
            if existing:
                emp_map[e["username"]] = existing.employee_id
            else:
                new_emp = Employee(
                    **model_dict(Employee, {
                        "username": e["username"],
                        "email": e["email"],
                        "password_hash": HASH,
                        "designation_id": desig_map[e["desig"]],
                        "department_id": dept_map[e["dept"]],
                        "manager_id": admin_emp.employee_id,
                        "status_id": emp_active_id,
                        "date_of_joining": date.fromisoformat(e["doj"]),
                        "date_of_birth": date.fromisoformat(e["dob"]),
                        "created_by": admin_emp.employee_id,
                        "updated_by": admin_emp.employee_id,
                        "created_at": NOW,
                        "updated_at": NOW,
                    })
                )
                session.add(new_emp)
                await session.flush()
                emp_map[e["username"]] = new_emp.employee_id
        await session.commit()

       # =========================================================================
        # 11. EMPLOYEE ROLES
        # =========================================================================
        print("  -> employee_roles")
        emp_role_assignments = [
            {"username": "admin.user",         "role_code": "SUPER_ADMIN"},
            {"username": "admin.user",         "role_code": "HR_ADMIN"},
            {"username": "jane.smith",         "role_code": "MANAGER"},
            {"username": "shubrajit.deb",      "role_code": "EMPLOYEE"},
            {"username": "prasun.chakraborty", "role_code": "EMPLOYEE"},
            {"username": "midanka.lahon",      "role_code": "EMPLOYEE"},
            {"username": "swarup.das",         "role_code": "SENIOR_EMP"},
            {"username": "mrinmoy.kashyap",    "role_code": "EMPLOYEE"},
            {"username": "rishav.bora",        "role_code": "EMPLOYEE"},
            {"username": "alice.wong",         "role_code": "FINANCE"},
            {"username": "bob.sharma",         "role_code": "MANAGER"},
            {"username": "frank.das",          "role_code": "TECH_LEAD"},
            {"username": "grace.hopper",       "role_code": "DEPT_HEAD"},
            {"username": "james.bond",         "role_code": "LEGAL"},
            {"username": "neil.gupta",         "role_code": "TEAM_LEAD"},
        ]

        for ra in emp_role_assignments:
            emp_id = emp_map.get(ra["username"])
            role_id = role_map.get(ra["role_code"])
            if not emp_id or not role_id:
                continue

            existing_er = (
                await session.execute(
                    select(EmployeeRole).where(
                        EmployeeRole.employee_id == emp_id,
                        EmployeeRole.role_id == role_id,
                    )
                )
            ).scalar_one_or_none()

            if not existing_er:
                session.add(
                    EmployeeRole(
                        **model_dict(EmployeeRole, {
                            "employee_id": emp_id,
                            "role_id": role_id,
                            "assigned_by": admin_emp.employee_id,
                            "is_active": True,
                            "created_by": admin_emp.employee_id,
                            "updated_by": admin_emp.employee_id,  # <-- Added missing NOT NULL field
                            "created_at": NOW,
                            "updated_at": NOW,
                        })
                    )
                )
        await session.commit()

        # =========================================================================
        # 12. WALLETS
        # =========================================================================
        print("  -> wallets")
        wallet_points = {
            "admin.user":         {"avail": 999999, "redeemed": 0,    "total": 999999},
            "jane.smith":         {"avail": 8500,   "redeemed": 500,  "total": 9000},
            "shubrajit.deb":      {"avail": 3200,   "redeemed": 300,  "total": 3500},
            "prasun.chakraborty": {"avail": 2800,   "redeemed": 200,  "total": 3000},
            "midanka.lahon":      {"avail": 2500,   "redeemed": 0,    "total": 2500},
            "swarup.das":         {"avail": 4500,   "redeemed": 500,  "total": 5000},
            "mrinmoy.kashyap":    {"avail": 2100,   "redeemed": 400,  "total": 2500},
            "rishav.bora":        {"avail": 1800,   "redeemed": 200,  "total": 2000},
            "alice.wong":         {"avail": 13000,  "redeemed": 1000, "total": 14000},
            "bob.sharma":         {"avail": 5500,   "redeemed": 500,  "total": 6000},
            "frank.das":          {"avail": 6200,   "redeemed": 800,  "total": 7000},
            "grace.hopper":       {"avail": 5800,   "redeemed": 1500, "total": 7300},
            "james.bond":         {"avail": 6400,   "redeemed": 600,  "total": 7000},
            "neil.gupta":         {"avail": 5100,   "redeemed": 900,  "total": 6000},
        }

        wallet_map = {}
        for username, pts in wallet_points.items():
            emp_id = emp_map.get(username)
            if not emp_id:
                continue

            existing_wallet = (
                await session.execute(select(Wallet).where(Wallet.employee_id == emp_id))
            ).scalar_one_or_none()

            if existing_wallet:
                wallet_map[username] = existing_wallet.wallet_id
            else:
                new_w = Wallet(
                    **model_dict(Wallet, {
                        "employee_id": emp_id,
                        "available_points": pts["avail"],
                        "redeemed_points": pts["redeemed"],
                        "total_earned_points": pts["total"],
                        "version": 1,
                        "created_by": admin_emp.employee_id,
                        "updated_by": admin_emp.employee_id,
                        "created_at": NOW,
                        "updated_at": NOW,
                    })
                )
                session.add(new_w)
                await session.flush()
                wallet_map[username] = new_w.wallet_id
        await session.commit()

        # =========================================================================
        # 13. TRANSACTIONS
        # =========================================================================
        print("  -> transactions")
        txn_earned_id = txn_type_map.get("POINTS_EARNED", txn_type_map.get("CREDIT"))
        txn_counter = 1

        for username, wallet_id in wallet_map.items():
            pts = wallet_points.get(username, {}).get("total", 0)
            if pts == 0:
                continue
            ref = f"TXN-SEED-{str(txn_counter).zfill(5)}"
            txn_counter += 1

            existing_tx = (
                await session.execute(
                    select(PointTransaction).where(PointTransaction.reference_number == ref)
                )
            ).scalar_one_or_none()

            if not existing_tx:
                session.add(
                    PointTransaction(
                        **model_dict(PointTransaction, {
                            "wallet_id": wallet_id,
                            "amount": pts,
                            "transaction_type_id": txn_earned_id,
                            "status_id": txn_completed_id,
                            "reference_number": ref,
                            "description": f"Seed initial points for {username}",
                            "transaction_at": NOW,
                            "created_by": admin_emp.employee_id,
                            "updated_by": admin_emp.employee_id,
                            "created_at": NOW,
                            "updated_at": NOW,
                        })
                    )
                )
        await session.commit()

        # =========================================================================
        # 14. REVIEWS & CATEGORY TAGS
        # =========================================================================
        print("  -> reviews")
        review_pairs = [
            {"reviewer": "admin.user",  "receiver": "shubrajit.deb",      "comment": "Outstanding backend work.",         "pts": 1200, "cats": ["TECHNICAL", "DELIVERY"]},
            {"reviewer": "jane.smith",  "receiver": "prasun.chakraborty",  "comment": "Great initiative on API redesign.",  "pts": 900,  "cats": ["INITIATIVE", "INNOVATION"]},
            {"reviewer": "alice.wong",  "receiver": "swarup.das",          "comment": "Consistently delivers quality code.","pts": 1000, "cats": ["QUALITY", "DELIVERY"]},
            {"reviewer": "admin.user",  "receiver": "midanka.lahon",       "comment": "Pixel-perfect UI implementation.",   "pts": 850,  "cats": ["QUALITY", "INNOVATION"]},
            {"reviewer": "frank.das",   "receiver": "mrinmoy.kashyap",     "comment": "Diligent testing & quality focus.",   "pts": 700,  "cats": ["QUALITY", "TEAMWORK"]},
        ]

        for r in review_pairs:
            reviewer_id = emp_map.get(r["reviewer"])
            receiver_id = emp_map.get(r["receiver"])
            if not reviewer_id or not receiver_id:
                continue

            existing_rev = (
                await session.execute(
                    select(Review).where(
                        Review.reviewer_id == reviewer_id,
                        Review.receiver_id == receiver_id,
                    )
                )
            ).scalar_one_or_none()

            if not existing_rev:
                new_rev = Review(
                    **model_dict(Review, {
                        "reviewer_id": reviewer_id,
                        "receiver_id": receiver_id,
                        "comment": r["comment"],
                        "status_id": rev_approved_id,
                        "raw_points": r["pts"],
                        "review_at": NOW,
                        "created_by": reviewer_id,
                        "updated_by": reviewer_id,
                        "created_at": NOW,
                        "updated_at": NOW,
                    })
                )
                session.add(new_rev)
                await session.flush()

                for cat_code in r["cats"]:
                    rc = review_cat_map.get(cat_code)
                    if not rc:
                        continue
                    session.add(
                        ReviewCategoryTag(
                            **model_dict(ReviewCategoryTag, {
                                "review_id": new_rev.review_id,
                                "category_id": rc.category_id,
                                "multiplier_snapshot": rc.multiplier,
                                "category_code_snapshot": rc.category_code,
                            })
                        )
                    )
        await session.commit()

        # =========================================================================
        # 15. REWARD HISTORY
        # =========================================================================
        print("  -> reward_history")
        reward_history_data = [
            {"username": "jane.smith",    "catalog_code": "NETFLIX_3M", "pts": 1200, "comment": "Monthly Netflix reward"},
            {"username": "alice.wong",    "catalog_code": "AMZ_1000",   "pts": 1000, "comment": "Amazon gift card reward"},
            {"username": "swarup.das",    "catalog_code": "TSHIRT",     "pts": 300,  "comment": "Company t-shirt redemption"},
            {"username": "midanka.lahon", "catalog_code": "SWIGGY_500", "pts": 500,  "comment": "Swiggy food voucher"},
        ]

        for rh in reward_history_data:
            wallet_id = wallet_map.get(rh["username"])
            catalog_id = catalog_map.get(rh["catalog_code"])
            if not wallet_id or not catalog_id:
                continue

            existing_rh = (
                await session.execute(
                    select(RewardHistory).where(
                        RewardHistory.wallet_id == wallet_id,
                        RewardHistory.catalog_id == catalog_id,
                        RewardHistory.points == rh["pts"],
                    )
                )
            ).scalar_one_or_none()

            if not existing_rh:
                session.add(
                    RewardHistory(
                        **model_dict(RewardHistory, {
                            "wallet_id": wallet_id,
                            "catalog_id": catalog_id,
                            "granted_by": admin_emp.employee_id,
                            "points": rh["pts"],
                            "comment": rh["comment"],
                            "created_by": admin_emp.employee_id,
                            "updated_by": admin_emp.employee_id,
                            "granted_at": NOW,
                            "created_at": NOW,
                            "updated_at": NOW,
                        })
                    )
                )
        await session.commit()

        # =========================================================================
        # 16. NOTIFICATIONS
        # =========================================================================
        print("  -> notifications")
        notif_data = [
            {"username": "shubrajit.deb",      "title": "You received a review!", "message": "admin.user recognized you.", "type": "REVIEW"},
            {"username": "midanka.lahon",      "title": "Welcome to Aabhar!",     "message": "Your profile is active.",    "type": "SYSTEM"},
            {"username": "prasun.chakraborty", "title": "New review received",     "message": "jane.smith left a review.",  "type": "REVIEW"},
        ]

        for n in notif_data:
            emp_id = emp_map.get(n["username"])
            if not emp_id:
                continue

            existing_id = (
                await session.execute(
                    select(Notification.notification_id).where(
                        Notification.employee_id == emp_id,
                        Notification.title == n["title"],
                    )
                )
            ).scalar_one_or_none()

            if not existing_id:
                session.add(
                    Notification(
                        **model_dict(Notification, {
                            "employee_id": emp_id,
                            "title": n["title"],
                            "message": n["message"],
                            "type": n["type"],
                            "is_read": False,
                            "email_sent": False,
                            "send_attempts": 0,
                            "created_at": NOW,
                            "updated_at": NOW,
                        })
                    )
                )
        await session.commit()

        # =========================================================================
        # 17. ROUTE PERMISSIONS
        # =========================================================================
        print("  -> route_permissions")
        from src.common.route_registry import register_app_routes

        from src.auth.main import app as auth_app, ROLE_OVERRIDES as auth_overrides, ROUTE_TITLES as auth_titles, ALWAYS_PUBLIC_ROUTES as auth_public
        from src.roles.main import app as roles_app, ROLE_OVERRIDES as roles_overrides, ROUTE_TITLES as roles_titles
        from src.employees.main import app as emp_app, ROLE_OVERRIDES as emp_overrides, ROUTE_TITLES as emp_titles
        from src.wallet.main import app as wallet_app, ROLE_OVERRIDES as wallet_overrides, ROUTE_TITLES as wallet_titles
        from src.recognition.main import app as rec_app, ROLE_OVERRIDES as rec_overrides, ROUTE_TITLES as rec_titles
        from src.rewards.main import app as rwd_app, ROLE_OVERRIDES as rwd_overrides, ROUTE_TITLES as rwd_titles
        from src.organization.main import app as org_app, ROLE_OVERRIDES as org_overrides, ROUTE_TITLES as org_titles
        from src.analytics.main import app as anl_app, ROLE_OVERRIDES as anl_overrides, ROUTE_TITLES as anl_titles

        services_to_register = [
            ("auth",          auth_app,   ["SUPER_ADMIN"],             auth_overrides,   auth_titles,  auth_public),
            ("roles",         roles_app,  ["SUPER_ADMIN"],             roles_overrides,  roles_titles, None),
            ("employees",     emp_app,    ["SUPER_ADMIN", "HR_ADMIN"], emp_overrides,    emp_titles,   None),
            ("wallets",       wallet_app, ["SUPER_ADMIN", "HR_ADMIN"], wallet_overrides, wallet_titles,None),
            ("recognitions",  rec_app,    ["SUPER_ADMIN", "HR_ADMIN"], rec_overrides,    rec_titles,   None),
            ("rewards",       rwd_app,    ["SUPER_ADMIN", "HR_ADMIN"], rwd_overrides,    rwd_titles,   None),
            ("organizations", org_app,    ["SUPER_ADMIN", "HR_ADMIN"], org_overrides,    org_titles,   None),
            ("analytics",     anl_app,    ["SUPER_ADMIN", "HR_ADMIN"], anl_overrides,    anl_titles,   None),
        ]

        for svc_name, svc_app, def_roles, overrides, titles, pub_routes in services_to_register:
            await register_app_routes(
                svc_app,
                default_roles=def_roles,
                role_overrides=overrides,
                route_titles=titles,
                always_public_routes=pub_routes,
                apply_jitter=False,
            )

    print("Seed complete ✅")


if __name__ == "__main__":
    asyncio.run(main())