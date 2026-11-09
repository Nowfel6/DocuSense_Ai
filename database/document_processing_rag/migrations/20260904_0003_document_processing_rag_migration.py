"""Document processing/RAG database build; parent 20260903_0002."""
from pathlib import Path

from alembic import context, op

revision = "20260904_0003"
down_revision = "20260903_0002"
branch_labels = None
depends_on = None


def upgrade_sql() -> str:
    source = Path(__file__).with_name("20260904_create_document_processing_rag.sql").read_text(encoding="utf-8")
    return source.split("-- BEGIN DOCUMENT PROCESSING RAG UPGRADE\n", 1)[1].split(
        "-- END DOCUMENT PROCESSING RAG UPGRADE", 1
    )[0]


def upgrade() -> None:
    if context.is_offline_mode():
        raise RuntimeError("Online PostgreSQL/pgvector preflight is required")
    # psycopg uses ``%`` for client-side placeholders even when Alembic passes
    # no application parameters. Preserve literal SQL LIKE wildcards.
    op.get_bind().exec_driver_sql(upgrade_sql().replace("%", "%%"))


def downgrade() -> None:
    if context.is_offline_mode():
        raise RuntimeError("Disposable database checks require an online connection")
    op.get_bind().exec_driver_sql("""
      SET LOCAL lock_timeout='5s'; SET LOCAL statement_timeout='120s';
      DO $guard$ BEGIN
        IF current_database() !~ '^docusense_(ingestion|rag|export)_test_[a-z0-9_]+$'
           OR current_setting('docusense.disposable_database',true) IS DISTINCT FROM current_database() THEN
          RAISE EXCEPTION 'Rollback requires an explicitly acknowledged disposable test database';
        END IF;
      END $guard$;
      LOCK TABLE public.document_partitions,public.document_chunks,public.extraction_runs,public.invoices,public.line_items,
        public.field_evidence,public.validation_results IN ACCESS EXCLUSIVE MODE;
      DO $empty$ BEGIN
        IF EXISTS(SELECT 1 FROM public.document_partitions) OR EXISTS(SELECT 1 FROM public.document_chunks) OR EXISTS(SELECT 1 FROM public.extraction_runs)
          OR EXISTS(SELECT 1 FROM public.invoices) OR EXISTS(SELECT 1 FROM public.line_items)
          OR EXISTS(SELECT 1 FROM public.field_evidence) OR EXISTS(SELECT 1 FROM public.validation_results) THEN
          RAISE EXCEPTION 'Rollback refused: explicitly empty disposable feature fixtures first';
        END IF;
      END $empty$;
      DROP TABLE public.validation_results RESTRICT;
      DROP TABLE public.field_evidence RESTRICT;
      DROP TABLE public.line_items RESTRICT;
      DROP TABLE public.invoices RESTRICT;
      DROP TABLE public.extraction_runs RESTRICT;
      DROP TABLE public.document_chunks RESTRICT;
      DROP TABLE public.document_partitions RESTRICT;
      DROP FUNCTION public.enforce_document_partition_immutability() RESTRICT;
      DROP FUNCTION public.validate_document_partition_owner_fence() RESTRICT;
      DROP FUNCTION public.enforce_result_immutability() RESTRICT;
      DROP FUNCTION public.validate_field_evidence_owner() RESTRICT;
      DROP FUNCTION public.enforce_line_item_identity_immutability() RESTRICT;
      DROP FUNCTION public.enforce_invoice_initial_immutability() RESTRICT;
      DROP FUNCTION public.validate_invoice_run_pair() RESTRICT;
      DROP FUNCTION public.enforce_extraction_run_immutability() RESTRICT;
      DROP FUNCTION public.validate_extraction_run_pair() RESTRICT;
      DROP FUNCTION public.enforce_document_chunk_immutability() RESTRICT;
      DROP FUNCTION public.validate_document_chunk_hierarchy() RESTRICT;
    """)
