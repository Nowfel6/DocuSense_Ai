"""Concurrent document search indexes; parent 20260907_0005."""
from pathlib import Path
import re

import sqlalchemy as sa
from alembic import context, op

revision = "20260907_0006"
down_revision = "20260907_0005"
branch_labels = None
depends_on = None

INDEXES = (
    ("idx_documents_company_search", "public.documents(company_id,status,doc_type,created_at,id)"),
    ("idx_invoices_date_document", "public.invoices(date_issued,document_id)"),
    ("idx_invoices_currency_date_document", "public.invoices(currency,date_issued,document_id)"),
    ("idx_invoices_total_document", "public.invoices(grand_total,document_id)"),
    (
        "idx_document_chunks_embedding_compat",
        "public.document_chunks(embedding_model,embedding_revision,document_id,ordinal) "
        "WHERE embedding_status='completed' AND embedding IS NOT NULL "
        "AND retrieval_role IN ('child','both')",
    ),
)


def source_sql() -> str:
    return Path(__file__).with_name(
        "20260907_create_document_search_export_indexes.sql"
    ).read_text(encoding="utf-8")


def _preflight_sql() -> str:
    text = source_sql()
    return text.split("DO $preflight$", 1)[0] + "DO $preflight$" + text.split(
        "DO $preflight$", 1
    )[1].split("$preflight$;", 1)[0] + "$preflight$;"


def _drop_invalid_canonical(bind) -> None:
    invalid = bind.execute(
        sa.text(
            """SELECT c.relname FROM pg_class c
               JOIN pg_namespace n ON n.oid=c.relnamespace
               JOIN pg_index i ON i.indexrelid=c.oid
               WHERE n.nspname='public' AND NOT i.indisvalid
                 AND c.relname=ANY(:names)"""
        ),
        {"names": [name for name, _ in INDEXES]},
    ).scalars().all()
    for name in invalid:
        bind.exec_driver_sql(f'DROP INDEX CONCURRENTLY public."{name}"')


def _compact(definition: str) -> str:
    return re.sub(r'[\s"();]+', "", definition.lower()).replace("usingbtree", "")


def _valid_exact_index_exists(bind, name: str, definition: str) -> bool:
    row = bind.execute(
        sa.text(
            """SELECT i.indisvalid,i.indisready,pg_get_indexdef(c.oid)
               FROM pg_class c
               JOIN pg_namespace n ON n.oid=c.relnamespace
               JOIN pg_index i ON i.indexrelid=c.oid
               WHERE n.nspname='public' AND c.relname=:name"""
        ),
        {"name": name},
    ).one_or_none()
    if row is None:
        return False
    if not row[0] or not row[1] or _compact("ON " + definition) not in _compact(row[2]):
        raise RuntimeError(f"Canonical index {name} has a different reviewed definition")
    return True


def upgrade() -> None:
    if context.is_offline_mode():
        raise RuntimeError("Concurrent indexes require an online PostgreSQL connection")
    migration_context = context.get_context()
    with migration_context.autocommit_block():
        bind = op.get_bind()
        # The preflight contains SQL LIKE patterns; protect their literal percent
        # characters from psycopg's percent-based placeholder parser.
        bind.exec_driver_sql(_preflight_sql().replace("%", "%%"))
        _drop_invalid_canonical(bind)
        for name, definition in INDEXES:
            if _valid_exact_index_exists(bind, name, definition):
                continue
            bind.exec_driver_sql("SET lock_timeout='5s'")
            bind.exec_driver_sql("SET statement_timeout='30min'")
            bind.exec_driver_sql(f"CREATE INDEX CONCURRENTLY {name} ON {definition}")


def downgrade() -> None:
    if context.is_offline_mode():
        raise RuntimeError("Disposable database checks require an online connection")
    migration_context = context.get_context()
    with migration_context.autocommit_block():
        bind = op.get_bind()
        guard = bind.execute(
            sa.text(
                """SELECT current_database(),
                          current_setting('docusense.disposable_database',true),
                          current_setting('docusense.no_active_consumers',true),
                          (SELECT array_agg(version_num::text ORDER BY version_num)
                           FROM public.alembic_version),
                          EXISTS(SELECT 1 FROM public.export_jobs),
                          EXISTS(SELECT 1 FROM public.export_job_documents)"""
            )
        ).one()
        if (
            not guard[0].startswith("docusense_export_test_")
            or guard[1] != guard[0]
            or guard[2] != "confirmed"
            or guard[3] != ["20260907_0006"]
            or guard[4]
            or guard[5]
        ):
            raise RuntimeError(
                "Online-index downgrade requires an acknowledged empty disposable export database"
            )
        for name, _ in reversed(INDEXES):
            bind.exec_driver_sql(f'DROP INDEX CONCURRENTLY public."{name}"')
