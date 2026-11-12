import asyncio
from logging.config import fileConfig
import os

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import inspect, pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# 1. Load environment variables from .env
load_dotenv()

# 2. Alembic Config object
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 3. Import Base AND all model modules explicitly
from src.core.database import Base

import src.organization.models
import src.roles.models
import src.employees.models
import src.auth.models
import src.recognition.models
import src.rewards.models
import src.wallet.models
import src.analytics.models

# 4. Bind target_metadata AFTER all model imports
target_metadata = Base.metadata


def get_database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if not url:
        ini_url = config.get_main_option("sqlalchemy.url")
        if ini_url and not ini_url.startswith("driver://"):
            url = ini_url
    if not url:
        raise ValueError("DATABASE_URL is not set.")
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


def do_run_migrations(connection: Connection) -> None:
    print(f"\n[ALEMBIC] Connecting to DB: {connection.engine.url.database}")
    print(f"[ALEMBIC] Detected {len(target_metadata.tables)} models in Base.metadata")

    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_database_url()

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


def run_migrations_offline() -> None:
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()