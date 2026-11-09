"""Document search/export core database build; parent 20260906_0004."""
from pathlib import Path

from alembic import context, op

revision = "20260907_0005"
down_revision = "20260906_0004"
branch_labels = None
depends_on = None


def upgrade_sql() -> str:
    source = Path(__file__).with_name(
        "20260907_create_document_search_export.sql"
    ).read_text(encoding="utf-8")
    return source.split("-- BEGIN DOCUMENT SEARCH EXPORT CORE UPGRADE\n", 1)[1].split(
        "-- END DOCUMENT SEARCH EXPORT CORE UPGRADE", 1
    )[0]


def upgrade() -> None:
    if context.is_offline_mode():
        raise RuntimeError("Online PostgreSQL predecessor preflight is required")
    # psycopg uses percent-based DBAPI placeholders even for driver SQL. Escape
    # literal PostgreSQL RAISE/LIKE percent tokens before handing the script off.
    op.get_bind().exec_driver_sql(upgrade_sql().replace("%", "%%"))


def downgrade() -> None:
    if context.is_offline_mode():
        raise RuntimeError("Disposable database checks require an online connection")
    op.get_bind().exec_driver_sql(
        """
        SET LOCAL search_path=pg_catalog,public;
        SET LOCAL lock_timeout='5s';
        SET LOCAL statement_timeout='120s';
        DO $guard$ BEGIN
          IF current_database() !~ '^docusense_export_test_[a-z0-9_]+$'
             OR current_setting('docusense.disposable_database',true)
                IS DISTINCT FROM current_database()
             OR current_setting('docusense.no_active_consumers',true)
                IS DISTINCT FROM 'confirmed' THEN
            RAISE EXCEPTION 'Rollback requires an acknowledged disposable export test database without consumers';
          END IF;
          IF (SELECT array_agg(version_num::text ORDER BY version_num)
              FROM public.alembic_version)
             IS DISTINCT FROM ARRAY['20260907_0005']::text[] THEN
            RAISE EXCEPTION 'Core downgrade requires exact revision 20260907_0005';
          END IF;
          IF EXISTS(SELECT 1 FROM public.export_jobs)
             OR EXISTS(SELECT 1 FROM public.export_job_documents) THEN
            RAISE EXCEPTION 'Rollback refused: export provenance must be empty';
          END IF;
        END $guard$;
        LOCK TABLE public.export_job_documents,public.export_jobs IN ACCESS EXCLUSIVE MODE;

        DROP TRIGGER trg_export_job_documents_membership_commit ON public.export_job_documents;
        DROP TRIGGER trg_export_jobs_membership_commit ON public.export_jobs;
        DROP TRIGGER trg_export_job_documents_immutable ON public.export_job_documents;
        DROP TRIGGER trg_export_job_documents_validate ON public.export_job_documents;
        DROP TRIGGER trg_export_jobs_updated_at ON public.export_jobs;
        DROP TRIGGER trg_export_jobs_transition ON public.export_jobs;
        DROP TRIGGER trg_export_jobs_owner ON public.export_jobs;

        DROP TABLE public.export_job_documents RESTRICT;
        DROP TABLE public.export_jobs RESTRICT;

        DROP FUNCTION public.enforce_export_membership_immutable() RESTRICT;
        DROP FUNCTION public.validate_export_membership_commit() RESTRICT;
        DROP FUNCTION public.validate_export_job_document() RESTRICT;
        DROP FUNCTION public.validate_export_job_transition() RESTRICT;
        DROP FUNCTION public.validate_export_job_owner() RESTRICT;
        DROP FUNCTION public.compute_export_source_value_hash(uuid) RESTRICT;
        DROP FUNCTION public.validate_export_criteria_json(jsonb) RESTRICT;
        """
    )
