"""Async SQLAlchemy runtime over the integrated, shared final-project models."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
import sys
from types import ModuleType
from typing import AsyncIterator

from psycopg.conninfo import conninfo_to_dict
from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import (
    AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine,
)

from ..auth import models as auth_models
from ..document_ingestion import models as ingestion_models
from ..document_processing_rag import models as rag_models
from ..document_search_export import models as export_models
from ..human_review_audit import models as review_models

if sys.platform == "win32" and hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    # Psycopg async connections require selector-based readiness on Windows.
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

EXPECTED_HEAD = "20260907_0006"
EXPECTED_TABLES = frozenset({
    "companies", "users", "api_keys", "documents", "processing_jobs",
    "document_partitions", "document_chunks", "extraction_runs", "invoices", "line_items",
    "field_evidence", "validation_results", "review_audit_events",
    "review_audit_changes", "review_validation_runs", "review_validation_results",
    "review_idempotency_keys", "export_jobs", "export_job_documents",
})


def _sqlalchemy_url(value: str) -> str | URL:
    value = value.strip()
    if value.startswith("postgresql+psycopg://"):
        return value
    if value.startswith("postgresql://"):
        return "postgresql+psycopg://" + value.removeprefix("postgresql://")
    info = conninfo_to_dict(value)
    if not info.get("dbname"):
        raise ValueError("DATABASE_URL must name an explicit PostgreSQL database")
    return URL.create(
        "postgresql+psycopg", username=info.get("user"),
        password=info.get("password"), host=info.get("host"),
        port=int(info["port"]) if info.get("port") else None,
        database=info["dbname"],
    )


class DatabaseRuntime:
    def __init__(self, database_url: str, *, echo: bool = False) -> None:
        self.engine: AsyncEngine = create_async_engine(
            _sqlalchemy_url(database_url), echo=echo, pool_pre_ping=True,
            pool_recycle=900,
        )
        self.sessions = async_sessionmaker(
            self.engine, expire_on_commit=False, autoflush=False,
        )

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.sessions() as session:
            yield session

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[AsyncSession]:
        async with self.sessions() as session:
            async with session.begin():
                yield session

    async def verify_schema(self) -> None:
        async with self.engine.connect() as connection:
            head = (await connection.execute(text(
                "SELECT version_num FROM public.alembic_version"
            ))).scalar_one()
            rows = await connection.execute(text(
                "SELECT tablename FROM pg_tables WHERE schemaname='public'"
            ))
            tables = {row[0] for row in rows}
        if head != EXPECTED_HEAD:
            raise RuntimeError(f"Expected verified database head {EXPECTED_HEAD}")
        missing = EXPECTED_TABLES - tables
        if missing:
            raise RuntimeError(
                "Verified database tables are incomplete: " + ", ".join(sorted(missing))
            )

    async def close(self) -> None:
        await self.engine.dispose()


def load_verified_models(_output_directory: Path) -> dict[str, ModuleType]:
    """Validate the final project's package-native shared model registry."""
    modules = {
        "models": auth_models,
        "document_ingestion_models": ingestion_models,
        "document_processing_rag_models": rag_models,
        "human_review_audit_models": review_models,
        "document_search_export_models": export_models,
    }
    base = auth_models.Base
    if any(getattr(module, "Base", base) is not base for module in modules.values()):
        raise RuntimeError("Verified database mappings do not share one SQLAlchemy Base")
    if not EXPECTED_TABLES <= set(base.metadata.tables):
        raise RuntimeError("Verified database model metadata is incomplete")
    return modules


__all__ = ["DatabaseRuntime", "EXPECTED_HEAD", "EXPECTED_TABLES", "load_verified_models"]
