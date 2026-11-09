"""Human review and immutable audit database build; parent 20260904_0003."""
from pathlib import Path

from alembic import context, op

revision = "20260906_0004"
down_revision = "20260904_0003"
branch_labels = None
depends_on = None


def upgrade_sql() -> str:
    source = Path(__file__).with_name("20260906_create_human_review_audit.sql").read_text(
        encoding="utf-8"
    )
    return source.split("-- BEGIN HUMAN REVIEW AUDIT UPGRADE\n", 1)[1].split(
        "-- END HUMAN REVIEW AUDIT UPGRADE", 1
    )[0]


def upgrade() -> None:
    if context.is_offline_mode():
        raise RuntimeError("Online PostgreSQL predecessor preflight is required")
    # Preserve literal LIKE wildcards and PL/pgSQL %ROWTYPE tokens for psycopg.
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
          IF current_database() !~ '^docusense_(ingestion|rag|review)_test_[a-z0-9_]+$'
             OR current_setting('docusense.disposable_database',true)
                IS DISTINCT FROM current_database()
             OR current_setting('docusense.no_active_consumers',true)
                IS DISTINCT FROM 'confirmed' THEN
            RAISE EXCEPTION 'Rollback requires an acknowledged disposable test database without consumers';
          END IF;
        END $guard$;
        LOCK TABLE public.documents,public.line_items,public.review_audit_events,
          public.review_audit_changes,public.review_validation_runs,
          public.review_validation_results,public.review_idempotency_keys
          IN ACCESS EXCLUSIVE MODE;
        DO $empty$ BEGIN
          IF EXISTS(SELECT 1 FROM public.review_audit_events)
             OR EXISTS(SELECT 1 FROM public.review_audit_changes)
             OR EXISTS(SELECT 1 FROM public.review_validation_runs)
             OR EXISTS(SELECT 1 FROM public.review_validation_results)
             OR EXISTS(SELECT 1 FROM public.review_idempotency_keys)
             OR EXISTS(SELECT 1 FROM public.documents
                       WHERE review_revision<>0 OR last_reviewed_by IS NOT NULL
                          OR last_reviewed_at IS NOT NULL)
             OR EXISTS(SELECT 1 FROM public.line_items WHERE origin<>'extracted') THEN
            RAISE EXCEPTION 'Rollback refused: review state/history must be empty';
          END IF;
        END $empty$;

        DROP TRIGGER trg_review_validation_results_immutable ON public.review_validation_results;
        DROP TRIGGER trg_review_validation_runs_immutable ON public.review_validation_runs;
        DROP TRIGGER trg_review_audit_changes_immutable ON public.review_audit_changes;
        DROP TRIGGER trg_review_audit_events_immutable ON public.review_audit_events;
        DROP TRIGGER trg_review_idempotency_updated_at ON public.review_idempotency_keys;
        DROP TRIGGER trg_review_idempotency_owner ON public.review_idempotency_keys;
        DROP TRIGGER trg_review_validation_runs_commit ON public.review_validation_runs;
        DROP TRIGGER trg_review_audit_changes_payload ON public.review_audit_changes;
        DROP TRIGGER trg_review_audit_events_commit ON public.review_audit_events;
        DROP TRIGGER trg_review_audit_events_owner ON public.review_audit_events;
        DROP TRIGGER trg_line_items_review_mutation ON public.line_items;
        DROP TRIGGER trg_invoices_review_mutation ON public.invoices;
        DROP TRIGGER trg_documents_review_mutation ON public.documents;

        DROP FUNCTION public.enforce_review_history_immutable() RESTRICT;
        DROP FUNCTION public.validate_review_idempotency_owner() RESTRICT;
        DROP FUNCTION public.validate_review_validation_commit() RESTRICT;
        DROP FUNCTION public.validate_review_action_commit() RESTRICT;
        DROP FUNCTION public.validate_review_change_payload() RESTRICT;
        DROP FUNCTION public.validate_review_event_owner() RESTRICT;
        DROP FUNCTION public.enforce_line_item_review_mutation() RESTRICT;
        DROP FUNCTION public.enforce_invoice_review_mutation() RESTRICT;
        DROP FUNCTION public.require_review_mutation_context() RESTRICT;
        DROP FUNCTION public.validate_document_review_mutation() RESTRICT;
        DROP FUNCTION public.review_jsonb_depth(jsonb) RESTRICT;

        DROP TABLE public.review_idempotency_keys RESTRICT;
        DROP TABLE public.review_validation_results RESTRICT;
        DROP TABLE public.review_validation_runs RESTRICT;
        DROP TABLE public.review_audit_changes RESTRICT;
        DROP TABLE public.review_audit_events RESTRICT;

        ALTER TABLE public.line_items
          DROP CONSTRAINT chk_line_items_manual_source,
          DROP CONSTRAINT chk_line_items_origin,
          DROP COLUMN origin;
        ALTER TABLE public.documents
          DROP CONSTRAINT fk_documents_last_reviewed_by_users,
          DROP CONSTRAINT chk_documents_review_summary_pair,
          DROP CONSTRAINT chk_documents_review_revision,
          DROP COLUMN last_reviewed_at,
          DROP COLUMN last_reviewed_by,
          DROP COLUMN review_revision;

        CREATE FUNCTION public.enforce_invoice_initial_immutability() RETURNS trigger
        LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $fn$
        BEGIN
          IF pg_trigger_depth()>1 THEN
            IF TG_OP='DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
          END IF;
          RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='chk_invoices_immutable',
            MESSAGE='Initial extracted invoice is immutable';
        END $fn$;
        CREATE FUNCTION public.enforce_line_item_identity_immutability() RETURNS trigger
        LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $fn$
        BEGIN
          IF TG_OP='DELETE' THEN
            IF pg_trigger_depth()>1 THEN RETURN OLD; END IF;
            RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='chk_line_items_delete',
              MESSAGE='Direct line item deletion is not authorized';
          END IF;
          IF ROW(NEW.id,NEW.invoice_id,NEW.source_row_key,NEW.line_order,NEW.created_at)
             IS DISTINCT FROM ROW(OLD.id,OLD.invoice_id,OLD.source_row_key,OLD.line_order,OLD.created_at) THEN
            RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='chk_line_items_identity_immutable',
              MESSAGE='Line item identity is immutable';
          END IF;
          RETURN NEW;
        END $fn$;
        CREATE TRIGGER trg_invoices_immutable BEFORE UPDATE OR DELETE ON public.invoices
          FOR EACH ROW EXECUTE FUNCTION public.enforce_invoice_initial_immutability();
        CREATE TRIGGER trg_line_items_identity_immutable BEFORE UPDATE OR DELETE ON public.line_items
          FOR EACH ROW EXECUTE FUNCTION public.enforce_line_item_identity_immutability();
        """
    )
