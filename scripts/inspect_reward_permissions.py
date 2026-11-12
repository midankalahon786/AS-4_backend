import asyncio
from src.core.database import async_session_factory
from sqlalchemy import text

async def check():
    async with async_session_factory() as session:
        res = await session.execute(text("""
            SELECT r.role_code, rp.route_key, rp.is_active
            FROM route_permissions rp
            JOIN roles r ON rp.role_id = r.role_id
            WHERE rp.route_key LIKE '%rewards%'
            ORDER BY r.role_code, rp.route_key
        """))
        for row in res.fetchall():
            print(f"{row[0]}: {row[1]} (active: {row[2]})")

if __name__ == "__main__":
    asyncio.run(check())
