"""Document ingestion, database-only build; parent 20260901_0001.

Keep the companion SQL file beside this revision when packaging migrations.
Online PostgreSQL/psycopg execution is required for catalog preflight checks.
"""
from pathlib import Path

from alembic import context, op

revision = "20260903_0002"
down_revision = "20260901_0001"
branch_labels = None
depends_on = None


def upgrade_sql() -> str:
    source = Path(__file__).with_name("20260903_create_document_ingestion.sql").read_text(encoding="utf-8")
    return source.split("-- BEGIN DOCUMENT INGESTION UPGRADE\n", 1)[1].split(
        "-- END DOCUMENT INGESTION UPGRADE", 1
    )[0]


def upgrade() -> None:
    if context.is_offline_mode():
        raise RuntimeError("Online PostgreSQL preflight is required; offline stamping is unsupported")
    # No nested BEGIN/COMMIT: Alembic owns the versioned transaction.
    op.get_bind().exec_driver_sql(upgrade_sql())


def downgrade() -> None:
    if context.is_offline_mode():
        raise RuntimeError("Disposable database checks require an online connection")
    op.get_bind().exec_driver_sql("""
        SET LOCAL lock_timeout = '5s';
        SET LOCAL statement_timeout = '60s';
        DO $guard$
        BEGIN
            IF current_database() !~ '^docusense_ingestion_test_[a-z0-9_]+$'
               OR current_setting('docusense.disposable_database', true)
                  IS DISTINCT FROM current_database() THEN
                RAISE EXCEPTION 'Rollback requires an explicitly acknowledged disposable test database';
            END IF;
        END;
        $guard$;
        LOCK TABLE public.documents, public.processing_jobs IN ACCESS EXCLUSIVE MODE;
        DO $empty$
        BEGIN
            IF EXISTS (SELECT 1 FROM public.documents)
               OR EXISTS (SELECT 1 FROM public.processing_jobs) THEN
                RAISE EXCEPTION 'Rollback refused: explicitly empty disposable feature fixtures first';
            END IF;
        END;
        $empty$;
        DROP TRIGGER trg_processing_jobs_updated_at ON public.processing_jobs;
        DROP TRIGGER trg_processing_jobs_identity_immutable ON public.processing_jobs;
        DROP TRIGGER trg_documents_updated_at ON public.documents;
        DROP TRIGGER trg_documents_uploader_tenant ON public.documents;
        DROP TRIGGER trg_documents_identity_immutable ON public.documents;
        DROP FUNCTION public.validate_document_uploader_tenant() RESTRICT;
        DROP FUNCTION public.enforce_document_identity_immutable() RESTRICT;
        DROP FUNCTION public.enforce_processing_job_identity_immutable() RESTRICT;
        DROP TABLE public.processing_jobs RESTRICT;
        DROP TABLE public.documents RESTRICT;
    """)
