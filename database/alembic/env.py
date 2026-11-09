"""Production Alembic environment for the feature-owned DocuSense migrations."""

from __future__ import annotations

from pathlib import Path

from alembic import context
from dotenv import dotenv_values
from sqlalchemy import engine_from_config, pool


config = context.config
project_root = Path(__file__).resolve().parents[2]
values = dotenv_values(project_root / ".env")
database_url = values.get("DATABASE_URL")
if not database_url:
    raise RuntimeError("DATABASE_URL must be configured in final_project/.env")
if database_url.startswith("postgresql://"):
    database_url = "postgresql+psycopg://" + database_url.removeprefix("postgresql://")
config.set_main_option("sqlalchemy.url", database_url)


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=None, version_table_schema="public")
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    raise RuntimeError("DocuSense migrations require an online PostgreSQL connection")
run_migrations_online()
