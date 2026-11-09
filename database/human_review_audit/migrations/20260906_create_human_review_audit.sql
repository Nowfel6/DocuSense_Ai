-- Stage 03 build. Canonical entry point: accompanying Alembic revision.
-- Standalone alternative: psql -X -v ON_ERROR_STOP=1 -f this-file.sql.
-- Requires verified RAG revision 20260904_0003. Does NOT stamp Alembic.
BEGIN;
-- BEGIN HUMAN REVIEW AUDIT UPGRADE
SET LOCAL search_path = pg_catalog, public;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '120s';

DO $preflight$
DECLARE
    heads text[];
BEGIN
    IF current_setting('server_version_num')::integer < 150000 THEN
        RAISE EXCEPTION 'Human review audit requires PostgreSQL 15 or newer';
    END IF;
    IF to_regclass('public.alembic_version') IS NULL THEN
        RAISE EXCEPTION 'Verified Alembic predecessor is required';
    END IF;
    SELECT array_agg(version_num::text ORDER BY version_num) INTO heads
    FROM public.alembic_version;
    IF heads IS DISTINCT FROM ARRAY['20260904_0003']::text[] THEN
        RAISE EXCEPTION 'Expected exactly RAG revision 20260904_0003';
    END IF;
    IF to_regclass('public.companies') IS NULL
       OR to_regclass('public.users') IS NULL
       OR to_regclass('public.documents') IS NULL
       OR to_regclass('public.processing_jobs') IS NULL
       OR to_regclass('public.extraction_runs') IS NULL
       OR to_regclass('public.invoices') IS NULL
       OR to_regclass('public.line_items') IS NULL
       OR to_regclass('public.field_evidence') IS NULL
       OR to_regclass('public.validation_results') IS NULL THEN
        RAISE EXCEPTION 'Verified auth, ingestion, and RAG parent tables are required';
    END IF;
    IF to_regclass('public.audit_logs') IS NOT NULL THEN
        RAISE EXCEPTION 'Legacy audit_logs requires explicit reconciliation';
    END IF;
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public'
          AND ((table_name='documents' AND column_name IN
                ('review_revision','last_reviewed_by','last_reviewed_at'))
            OR (table_name='line_items' AND column_name='origin'))
    ) THEN
        RAISE EXCEPTION 'Human review extension column collision';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND c.relname = ANY (ARRAY[
          'review_audit_events','review_audit_changes','review_validation_runs',
          'review_validation_results','review_idempotency_keys',
          'idx_documents_company_review_state','idx_documents_last_reviewed_by',
          'idx_review_audit_document_created','idx_review_audit_actor_created',
          'idx_review_audit_document_action','idx_review_idempotency_actor',
          'idx_review_idempotency_document','idx_review_idempotency_expiry'])
    ) THEN
        RAISE EXCEPTION 'Human review relation/index collision';
    END IF;
    IF EXISTS (SELECT 1 FROM public.line_items WHERE source_row_key LIKE 'manual:%') THEN
        RAISE EXCEPTION 'Reserved manual source-row prefix already exists';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger
                   WHERE tgrelid='public.invoices'::regclass
                     AND tgname='trg_invoices_immutable' AND NOT tgisinternal)
       OR NOT EXISTS (SELECT 1 FROM pg_trigger
                      WHERE tgrelid='public.line_items'::regclass
                        AND tgname='trg_line_items_identity_immutable' AND NOT tgisinternal) THEN
        RAISE EXCEPTION 'Expected exact RAG review handoff guards';
    END IF;
    IF to_regprocedure('public.update_updated_at_column()') IS NULL THEN
        RAISE EXCEPTION 'Verified shared timestamp helper is required';
    END IF;
END;
$preflight$;

ALTER TABLE public.documents
  ADD COLUMN review_revision BIGINT NOT NULL DEFAULT 0,
  ADD COLUMN last_reviewed_by UUID,
  ADD COLUMN last_reviewed_at TIMESTAMPTZ,
  ADD CONSTRAINT chk_documents_review_revision CHECK (review_revision >= 0),
  ADD CONSTRAINT chk_documents_review_summary_pair CHECK (
    (last_reviewed_by IS NULL) = (last_reviewed_at IS NULL)),
  ADD CONSTRAINT fk_documents_last_reviewed_by_users FOREIGN KEY (last_reviewed_by)
    REFERENCES public.users(id) ON DELETE SET NULL ON UPDATE NO ACTION;

ALTER TABLE public.line_items
  ADD COLUMN origin VARCHAR(20) NOT NULL DEFAULT 'extracted',
  ADD CONSTRAINT chk_line_items_origin CHECK (origin IN ('extracted','reviewer_added')),
  ADD CONSTRAINT chk_line_items_manual_source CHECK (
    (origin='reviewer_added' AND source_row_key='manual:'||id::text)
    OR (origin='extracted' AND source_row_key NOT LIKE 'manual:%'));

CREATE TABLE public.review_audit_events (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL,
    actor_user_id UUID NOT NULL,
    action VARCHAR(20) NOT NULL,
    from_status VARCHAR(30) NOT NULL,
    to_status VARCHAR(30) NOT NULL,
    review_revision BIGINT NOT NULL,
    reason VARCHAR(1000),
    note VARCHAR(1000),
    request_id VARCHAR(128) NOT NULL,
    payload_hash CHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT pk_review_audit_events PRIMARY KEY (id),
    CONSTRAINT fk_review_audit_events_document FOREIGN KEY (document_id)
      REFERENCES public.documents(id) ON DELETE RESTRICT ON UPDATE NO ACTION,
    CONSTRAINT fk_review_audit_events_actor FOREIGN KEY (actor_user_id)
      REFERENCES public.users(id) ON DELETE RESTRICT ON UPDATE NO ACTION,
    CONSTRAINT uq_review_audit_event_revision UNIQUE (document_id,review_revision),
    CONSTRAINT chk_review_audit_events_action CHECK (
      action IN ('field_edited','approved','rejected','reopened')),
    CONSTRAINT chk_review_audit_events_revision CHECK (review_revision > 0),
    CONSTRAINT chk_review_audit_events_hash CHECK (payload_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT chk_review_audit_events_request_id CHECK (
      request_id=btrim(request_id) AND request_id ~ '^[!-~]+$'),
    CONSTRAINT chk_review_audit_events_reason_note CHECK (
      (action='field_edited' AND from_status='pending_review' AND to_status='pending_review'
       AND reason IS NULL AND (note IS NULL OR (note=btrim(note) AND length(note)>0)))
      OR (action='approved' AND from_status='pending_review' AND to_status='approved'
       AND reason IS NULL AND (note IS NULL OR (note=btrim(note) AND length(note)>0)))
      OR (action='rejected' AND from_status='pending_review' AND to_status='rejected'
       AND reason=btrim(reason) AND length(reason)>0 AND note IS NULL)
      OR (action='reopened' AND from_status='approved' AND to_status='pending_review'
       AND reason=btrim(reason) AND length(reason)>0 AND note IS NULL))
);

CREATE TABLE public.review_audit_changes (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    audit_event_id UUID NOT NULL,
    field_path VARCHAR(255) NOT NULL,
    change_kind VARCHAR(10) NOT NULL,
    old_value JSONB,
    new_value JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT pk_review_audit_changes PRIMARY KEY (id),
    CONSTRAINT fk_review_audit_changes_event FOREIGN KEY (audit_event_id)
      REFERENCES public.review_audit_events(id) ON DELETE CASCADE ON UPDATE NO ACTION,
    CONSTRAINT uq_review_audit_change_path UNIQUE (audit_event_id,field_path),
    CONSTRAINT chk_review_audit_changes_kind CHECK (change_kind IN ('set','add','remove','reorder')),
    CONSTRAINT chk_review_audit_changes_path CHECK (
      field_path ~ '^(invoice\.(invoice_number|supplier_name|supplier_tax_id|buyer_name|date_issued|due_date|currency|subtotal|tax_amount|discount_amount|grand_total)|line_items\.[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}(\.(description|hs_code|quantity|unit_price|tax_amount|total_price|line_order))?|document\.status)$'),
    CONSTRAINT chk_review_audit_changes_values CHECK (
      (change_kind='set' AND old_value IS DISTINCT FROM new_value)
      OR (change_kind='add' AND old_value IS NULL AND new_value IS NOT NULL)
      OR (change_kind='remove' AND old_value IS NOT NULL AND new_value IS NULL)
      OR (change_kind='reorder' AND jsonb_typeof(old_value)='array'
          AND jsonb_typeof(new_value)='array' AND old_value IS DISTINCT FROM new_value)),
    CONSTRAINT chk_review_audit_changes_size CHECK (
      (old_value IS NULL OR octet_length(old_value::text)<=65536)
      AND (new_value IS NULL OR octet_length(new_value::text)<=65536))
);

CREATE TABLE public.review_validation_runs (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    audit_event_id UUID NOT NULL,
    document_id UUID NOT NULL,
    review_revision BIGINT NOT NULL,
    validation_version VARCHAR(64) NOT NULL,
    candidate_hash CHAR(64) NOT NULL,
    is_math_valid BOOLEAN NOT NULL,
    approval_eligible BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT pk_review_validation_runs PRIMARY KEY (id),
    CONSTRAINT fk_review_validation_runs_event FOREIGN KEY (audit_event_id)
      REFERENCES public.review_audit_events(id) ON DELETE CASCADE ON UPDATE NO ACTION,
    CONSTRAINT fk_review_validation_runs_document FOREIGN KEY (document_id)
      REFERENCES public.documents(id) ON DELETE RESTRICT ON UPDATE NO ACTION,
    CONSTRAINT uq_review_validation_event UNIQUE (audit_event_id),
    CONSTRAINT uq_review_validation_revision UNIQUE (document_id,review_revision),
    CONSTRAINT chk_review_validation_runs_revision CHECK (review_revision>0),
    CONSTRAINT chk_review_validation_runs_version CHECK (
      validation_version=btrim(validation_version) AND length(validation_version)>0),
    CONSTRAINT chk_review_validation_runs_hash CHECK (candidate_hash ~ '^[0-9a-f]{64}$')
);

CREATE TABLE public.review_validation_results (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    review_validation_run_id UUID NOT NULL,
    rule_id VARCHAR(64) NOT NULL,
    scope_key VARCHAR(255) NOT NULL DEFAULT 'document',
    status VARCHAR(16) NOT NULL,
    observed_value JSONB,
    expected_value JSONB,
    difference NUMERIC(18,6),
    epsilon NUMERIC(8,6),
    message_code VARCHAR(100) NOT NULL,
    blocks_approval BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT pk_review_validation_results PRIMARY KEY (id),
    CONSTRAINT fk_review_validation_results_run FOREIGN KEY (review_validation_run_id)
      REFERENCES public.review_validation_runs(id) ON DELETE CASCADE ON UPDATE NO ACTION,
    CONSTRAINT uq_review_validation_rule UNIQUE (review_validation_run_id,rule_id,scope_key),
    CONSTRAINT chk_review_validation_results_strings CHECK (
      rule_id=btrim(rule_id) AND length(rule_id)>0
      AND scope_key=btrim(scope_key) AND length(scope_key)>0
      AND message_code=btrim(message_code) AND length(message_code)>0),
    CONSTRAINT chk_review_validation_results_status CHECK (
      status IN ('passed','failed','missing','not_applicable')),
    CONSTRAINT chk_review_validation_results_nonnegative CHECK (
      (difference IS NULL OR (difference<>'NaN'::numeric AND difference>=0))
      AND (epsilon IS NULL OR (epsilon<>'NaN'::numeric AND epsilon>=0))),
    CONSTRAINT chk_review_validation_results_financial_epsilon CHECK (
      rule_id NOT LIKE 'BR-03%'
      OR status IN ('missing','not_applicable')
      OR epsilon=0.050000),
    CONSTRAINT chk_review_validation_results_comparison CHECK (
      (status IN ('missing','not_applicable') AND difference IS NULL AND epsilon IS NULL)
      OR status NOT IN ('missing','not_applicable')),
    CONSTRAINT chk_review_validation_results_pass_fail CHECK (
      difference IS NULL OR epsilon IS NULL OR status NOT IN ('passed','failed')
      OR (status='passed' AND difference<=epsilon)
      OR (status='failed' AND difference>epsilon))
);

CREATE TABLE public.review_idempotency_keys (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL,
    actor_user_id UUID NOT NULL,
    document_id UUID NOT NULL,
    idempotency_key VARCHAR(128) NOT NULL,
    request_hash CHAR(64) NOT NULL,
    audit_event_id UUID,
    response_status SMALLINT,
    response_body JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT pk_review_idempotency_keys PRIMARY KEY (id),
    CONSTRAINT fk_review_idempotency_company FOREIGN KEY (company_id)
      REFERENCES public.companies(id) ON DELETE RESTRICT ON UPDATE NO ACTION,
    CONSTRAINT fk_review_idempotency_actor FOREIGN KEY (actor_user_id)
      REFERENCES public.users(id) ON DELETE RESTRICT ON UPDATE NO ACTION,
    CONSTRAINT fk_review_idempotency_document FOREIGN KEY (document_id)
      REFERENCES public.documents(id) ON DELETE RESTRICT ON UPDATE NO ACTION,
    CONSTRAINT fk_review_idempotency_event FOREIGN KEY (audit_event_id)
      REFERENCES public.review_audit_events(id) ON DELETE RESTRICT ON UPDATE NO ACTION,
    CONSTRAINT uq_review_idempotency_scope UNIQUE
      (company_id,actor_user_id,document_id,idempotency_key),
    CONSTRAINT uq_review_idempotency_audit_event UNIQUE (audit_event_id),
    CONSTRAINT chk_review_idempotency_key CHECK (
      idempotency_key=btrim(idempotency_key) AND idempotency_key ~ '^[!-~]+$'),
    CONSTRAINT chk_review_idempotency_hash CHECK (request_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT chk_review_idempotency_expiry CHECK (
      expires_at>=created_at+INTERVAL '24 hours'),
    CONSTRAINT chk_review_idempotency_response CHECK (
      (audit_event_id IS NULL AND response_status IS NULL AND response_body IS NULL)
      OR (audit_event_id IS NOT NULL AND response_status BETWEEN 200 AND 299
          AND jsonb_typeof(response_body)='object'
          AND octet_length(response_body::text)<=65536))
);

CREATE INDEX idx_documents_company_review_state
  ON public.documents(company_id,status,review_revision,updated_at,id);
CREATE INDEX idx_documents_last_reviewed_by ON public.documents(last_reviewed_by);
CREATE INDEX idx_review_audit_document_created
  ON public.review_audit_events(document_id,created_at DESC,id DESC);
CREATE INDEX idx_review_audit_actor_created
  ON public.review_audit_events(actor_user_id,created_at DESC,id DESC);
CREATE INDEX idx_review_audit_document_action
  ON public.review_audit_events(document_id,action,created_at DESC,id DESC);
CREATE INDEX idx_review_idempotency_actor
  ON public.review_idempotency_keys(actor_user_id,created_at DESC);
CREATE INDEX idx_review_idempotency_document
  ON public.review_idempotency_keys(document_id,created_at DESC);
CREATE INDEX idx_review_idempotency_expiry
  ON public.review_idempotency_keys(expires_at,id);

CREATE FUNCTION public.review_jsonb_depth(value JSONB) RETURNS INTEGER
LANGUAGE plpgsql IMMUTABLE STRICT SECURITY INVOKER SET search_path=pg_catalog,public AS $fn$
DECLARE
    child JSONB;
    maximum INTEGER := 0;
BEGIN
    IF jsonb_typeof(value) NOT IN ('array','object') THEN RETURN 1; END IF;
    IF jsonb_typeof(value)='array' THEN
        FOR child IN SELECT v FROM jsonb_array_elements(value) AS a(v) LOOP
            maximum := greatest(maximum, public.review_jsonb_depth(child));
        END LOOP;
    ELSE
        FOR child IN SELECT v FROM jsonb_each(value) AS o(k,v) LOOP
            maximum := greatest(maximum, public.review_jsonb_depth(child));
        END LOOP;
    END IF;
    RETURN maximum+1;
END;
$fn$;

CREATE FUNCTION public.validate_document_review_mutation() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $fn$
DECLARE
    actor_company UUID;
    event_text TEXT;
    event_document UUID;
    event_revision BIGINT;
    event_status VARCHAR(30);
BEGIN
    IF NEW.last_reviewed_by IS NOT NULL THEN
        SELECT company_id INTO actor_company FROM public.users
        WHERE id=NEW.last_reviewed_by FOR SHARE;
        IF actor_company IS DISTINCT FROM NEW.company_id THEN
            RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='chk_documents_review_tenant',
              MESSAGE='Review summary actor must belong to document tenant';
        END IF;
    END IF;
    IF OLD.review_revision=0 AND NEW.review_revision=0
       AND OLD.last_reviewed_by IS NULL AND NEW.last_reviewed_by IS NULL
       AND OLD.last_reviewed_at IS NULL AND NEW.last_reviewed_at IS NULL THEN
        RETURN NEW;
    END IF;
    event_text := current_setting('docusense.review_event_id',true);
    IF event_text IS NULL OR event_text !~
      '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
       OR NEW.review_revision<>OLD.review_revision+1 THEN
        RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='chk_documents_review_mutation',
          MESSAGE='Document review state requires one correlated next revision';
    END IF;
    SELECT document_id,review_revision,to_status
      INTO event_document,event_revision,event_status
      FROM public.review_audit_events WHERE id=event_text::UUID;
    IF event_document IS DISTINCT FROM NEW.id OR event_revision IS DISTINCT FROM NEW.review_revision
       OR event_status IS DISTINCT FROM NEW.status THEN
        RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='chk_documents_review_event',
          MESSAGE='Document review mutation must match its uncommitted event';
    END IF;
    RETURN NEW;
END;
$fn$;

CREATE FUNCTION public.require_review_mutation_context() RETURNS UUID
LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path=pg_catalog,public AS $fn$
DECLARE
    event_text TEXT;
    event_id UUID;
BEGIN
    event_text := current_setting('docusense.review_event_id',true);
    IF event_text IS NULL OR event_text !~
      '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$' THEN
        RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='chk_review_mutation_context',
          MESSAGE='Correlated review transaction is required';
    END IF;
    event_id := event_text::UUID;
    IF NOT EXISTS (SELECT 1 FROM public.review_audit_events WHERE id=event_id) THEN
        RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='chk_review_mutation_event',
          MESSAGE='Review event must be staged before current-value mutation';
    END IF;
    RETURN event_id;
END;
$fn$;

CREATE FUNCTION public.enforce_invoice_review_mutation() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $fn$
DECLARE
    event_id UUID;
    event_document UUID;
BEGIN
    IF TG_OP='DELETE' THEN
        IF pg_trigger_depth()>1 THEN RETURN OLD; END IF;
        RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='chk_invoices_review_delete',
          MESSAGE='Review does not authorize invoice deletion';
    END IF;
    IF ROW(NEW.id,NEW.document_id,NEW.extraction_run_id,NEW.created_at)
       IS DISTINCT FROM ROW(OLD.id,OLD.document_id,OLD.extraction_run_id,OLD.created_at) THEN
        RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='chk_invoices_review_identity',
          MESSAGE='Invoice identity and provenance are immutable';
    END IF;
    event_id := public.require_review_mutation_context();
    SELECT document_id INTO event_document FROM public.review_audit_events WHERE id=event_id;
    IF event_document IS DISTINCT FROM NEW.document_id
       OR (OLD.invoice_number IS DISTINCT FROM NEW.invoice_number AND NOT EXISTS
          (SELECT 1 FROM public.review_audit_changes WHERE audit_event_id=event_id AND field_path='invoice.invoice_number'))
       OR (OLD.supplier_name IS DISTINCT FROM NEW.supplier_name AND NOT EXISTS
          (SELECT 1 FROM public.review_audit_changes WHERE audit_event_id=event_id AND field_path='invoice.supplier_name'))
       OR (OLD.supplier_tax_id IS DISTINCT FROM NEW.supplier_tax_id AND NOT EXISTS
          (SELECT 1 FROM public.review_audit_changes WHERE audit_event_id=event_id AND field_path='invoice.supplier_tax_id'))
       OR (OLD.buyer_name IS DISTINCT FROM NEW.buyer_name AND NOT EXISTS
          (SELECT 1 FROM public.review_audit_changes WHERE audit_event_id=event_id AND field_path='invoice.buyer_name'))
       OR (OLD.date_issued IS DISTINCT FROM NEW.date_issued AND NOT EXISTS
          (SELECT 1 FROM public.review_audit_changes WHERE audit_event_id=event_id AND field_path='invoice.date_issued'))
       OR (OLD.due_date IS DISTINCT FROM NEW.due_date AND NOT EXISTS
          (SELECT 1 FROM public.review_audit_changes WHERE audit_event_id=event_id AND field_path='invoice.due_date'))
       OR (OLD.currency IS DISTINCT FROM NEW.currency AND NOT EXISTS
          (SELECT 1 FROM public.review_audit_changes WHERE audit_event_id=event_id AND field_path='invoice.currency'))
       OR (OLD.subtotal IS DISTINCT FROM NEW.subtotal AND NOT EXISTS
          (SELECT 1 FROM public.review_audit_changes WHERE audit_event_id=event_id AND field_path='invoice.subtotal'))
       OR (OLD.tax_amount IS DISTINCT FROM NEW.tax_amount AND NOT EXISTS
          (SELECT 1 FROM public.review_audit_changes WHERE audit_event_id=event_id AND field_path='invoice.tax_amount'))
       OR (OLD.discount_amount IS DISTINCT FROM NEW.discount_amount AND NOT EXISTS
          (SELECT 1 FROM public.review_audit_changes WHERE audit_event_id=event_id AND field_path='invoice.discount_amount'))
       OR (OLD.grand_total IS DISTINCT FROM NEW.grand_total AND NOT EXISTS
          (SELECT 1 FROM public.review_audit_changes WHERE audit_event_id=event_id AND field_path='invoice.grand_total')) THEN
        RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='chk_invoice_review_audit_paths',
          MESSAGE='Invoice mutation must match staged audit paths and document';
    END IF;
    RETURN NEW;
END;
$fn$;

CREATE FUNCTION public.enforce_line_item_review_mutation() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $fn$
DECLARE
    event_id UUID;
    event_document UUID;
    line_document UUID;
BEGIN
    IF TG_OP='INSERT' THEN
        IF NEW.origin='reviewer_added' THEN
            event_id := public.require_review_mutation_context();
            SELECT e.document_id,i.document_id INTO event_document,line_document
            FROM public.review_audit_events e CROSS JOIN public.invoices i
            WHERE e.id=event_id AND i.id=NEW.invoice_id;
            IF event_document IS DISTINCT FROM line_document OR NOT EXISTS
              (SELECT 1 FROM public.review_audit_changes WHERE audit_event_id=event_id
               AND field_path='line_items.'||NEW.id::text AND change_kind='add') THEN
                RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='chk_line_item_review_add',
                  MESSAGE='Reviewer-added line must match a staged audit addition';
            END IF;
        END IF;
        RETURN NEW;
    END IF;
    IF TG_OP='DELETE' THEN
        IF pg_trigger_depth()>1 THEN RETURN OLD; END IF;
        event_id := public.require_review_mutation_context();
        IF NOT EXISTS (SELECT 1 FROM public.review_audit_changes WHERE audit_event_id=event_id
                       AND field_path='line_items.'||OLD.id::text AND change_kind='remove') THEN
            RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='chk_line_item_review_remove',
              MESSAGE='Removed line must match a staged audit removal';
        END IF;
        RETURN OLD;
    END IF;
    IF ROW(NEW.id,NEW.invoice_id,NEW.source_row_key,NEW.origin,NEW.created_at)
       IS DISTINCT FROM ROW(OLD.id,OLD.invoice_id,OLD.source_row_key,OLD.origin,OLD.created_at) THEN
        RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='chk_line_items_review_identity',
          MESSAGE='Line item identity, origin, and provenance are immutable';
    END IF;
    event_id := public.require_review_mutation_context();
    SELECT e.document_id,i.document_id INTO event_document,line_document
      FROM public.review_audit_events e CROSS JOIN public.invoices i
      WHERE e.id=event_id AND i.id=NEW.invoice_id;
    IF event_document IS DISTINCT FROM line_document
       OR (OLD.description IS DISTINCT FROM NEW.description AND NOT EXISTS
          (SELECT 1 FROM public.review_audit_changes WHERE audit_event_id=event_id AND field_path='line_items.'||NEW.id::text||'.description'))
       OR (OLD.hs_code IS DISTINCT FROM NEW.hs_code AND NOT EXISTS
          (SELECT 1 FROM public.review_audit_changes WHERE audit_event_id=event_id AND field_path='line_items.'||NEW.id::text||'.hs_code'))
       OR (OLD.quantity IS DISTINCT FROM NEW.quantity AND NOT EXISTS
          (SELECT 1 FROM public.review_audit_changes WHERE audit_event_id=event_id AND field_path='line_items.'||NEW.id::text||'.quantity'))
       OR (OLD.unit_price IS DISTINCT FROM NEW.unit_price AND NOT EXISTS
          (SELECT 1 FROM public.review_audit_changes WHERE audit_event_id=event_id AND field_path='line_items.'||NEW.id::text||'.unit_price'))
       OR (OLD.tax_amount IS DISTINCT FROM NEW.tax_amount AND NOT EXISTS
          (SELECT 1 FROM public.review_audit_changes WHERE audit_event_id=event_id AND field_path='line_items.'||NEW.id::text||'.tax_amount'))
       OR (OLD.total_price IS DISTINCT FROM NEW.total_price AND NOT EXISTS
          (SELECT 1 FROM public.review_audit_changes WHERE audit_event_id=event_id AND field_path='line_items.'||NEW.id::text||'.total_price'))
       OR (OLD.line_order IS DISTINCT FROM NEW.line_order AND NOT EXISTS
          (SELECT 1 FROM public.review_audit_changes WHERE audit_event_id=event_id AND field_path='line_items.'||NEW.id::text||'.line_order')) THEN
        RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='chk_line_item_review_audit_paths',
          MESSAGE='Line mutation must match staged audit paths and document';
    END IF;
    RETURN NEW;
END;
$fn$;

CREATE FUNCTION public.validate_review_event_owner() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $fn$
DECLARE
    document_company UUID;
    actor_company UUID;
BEGIN
    SELECT company_id INTO document_company FROM public.documents
      WHERE id=NEW.document_id FOR SHARE;
    SELECT company_id INTO actor_company FROM public.users
      WHERE id=NEW.actor_user_id FOR SHARE;
    IF document_company IS NULL OR actor_company IS DISTINCT FROM document_company THEN
        RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='chk_review_audit_event_tenant',
          MESSAGE='Review actor and document tenant must match';
    END IF;
    RETURN NEW;
END;
$fn$;

CREATE FUNCTION public.validate_review_change_payload() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $fn$
DECLARE
    old_count INTEGER;
    new_count INTEGER;
BEGIN
    IF coalesce(public.review_jsonb_depth(NEW.old_value),0)>8
       OR coalesce(public.review_jsonb_depth(NEW.new_value),0)>8 THEN
        RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='chk_review_change_depth',
          MESSAGE='Review change JSON exceeds maximum depth';
    END IF;
    IF NEW.change_kind='reorder' THEN
        IF jsonb_array_length(NEW.old_value)>500 OR jsonb_array_length(NEW.new_value)>500 THEN
            RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='chk_review_change_reorder_size',
              MESSAGE='Review reorder exceeds maximum line count';
        END IF;
        SELECT count(DISTINCT value),count(*) INTO old_count,new_count
          FROM jsonb_array_elements_text(NEW.old_value);
        IF old_count<>new_count THEN
            RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='chk_review_change_reorder_unique',
              MESSAGE='Old review order contains duplicate line IDs';
        END IF;
        SELECT count(DISTINCT value),count(*) INTO old_count,new_count
          FROM jsonb_array_elements_text(NEW.new_value);
        IF old_count<>new_count OR NOT (NEW.old_value <@ NEW.new_value AND NEW.new_value <@ NEW.old_value) THEN
            RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='chk_review_change_reorder_members',
              MESSAGE='Review reorder must contain the same unique line IDs';
        END IF;
    END IF;
    RETURN NEW;
END;
$fn$;

CREATE FUNCTION public.validate_review_action_commit() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $fn$
DECLARE
    document_row public.documents%ROWTYPE;
    previous_event public.review_audit_events%ROWTYPE;
    next_event public.review_audit_events%ROWTYPE;
    decision_event public.review_audit_events%ROWTYPE;
    change_count INTEGER;
    validation_count INTEGER;
    eligible BOOLEAN;
    math_valid BOOLEAN;
    valid_line_count INTEGER;
BEGIN
    SELECT * INTO STRICT document_row FROM public.documents WHERE id=NEW.document_id;
    SELECT * INTO previous_event FROM public.review_audit_events
      WHERE document_id=NEW.document_id AND review_revision=NEW.review_revision-1;
    SELECT * INTO next_event FROM public.review_audit_events
      WHERE document_id=NEW.document_id AND review_revision=NEW.review_revision+1;
    IF NEW.review_revision=1 THEN
        IF FOUND AND previous_event.id IS NOT NULL THEN
          RAISE EXCEPTION 'Unexpected review revision zero event'; END IF;
    ELSIF previous_event.id IS NULL OR previous_event.to_status<>NEW.from_status THEN
        RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='chk_review_event_revision_chain',
          MESSAGE='Review event revision/status chain is incomplete';
    END IF;
    IF next_event.id IS NULL THEN
        IF document_row.review_revision<>NEW.review_revision OR document_row.status<>NEW.to_status THEN
            RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='chk_review_event_current_state',
              MESSAGE='Latest review event must match current document state';
        END IF;
    ELSIF next_event.from_status<>NEW.to_status THEN
        RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='chk_review_event_next_state',
          MESSAGE='Review event next state is inconsistent';
    END IF;
    SELECT count(*) INTO change_count FROM public.review_audit_changes
      WHERE audit_event_id=NEW.id;
    IF change_count>1000 OR (NEW.action='field_edited' AND change_count=0)
       OR (NEW.action IN ('rejected','reopened') AND change_count<>0) THEN
        RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='chk_review_event_change_count',
          MESSAGE='Review action has an invalid change count';
    END IF;
    SELECT count(*),bool_or(approval_eligible),bool_or(is_math_valid)
      INTO validation_count,eligible,math_valid
      FROM public.review_validation_runs WHERE audit_event_id=NEW.id;
    IF (NEW.action IN ('field_edited','approved') AND validation_count<>1)
       OR (NEW.action IN ('rejected','reopened') AND validation_count<>0)
       OR (NEW.action='approved' AND (eligible IS DISTINCT FROM TRUE OR math_valid IS DISTINCT FROM TRUE)) THEN
        RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='chk_review_event_validation',
          MESSAGE='Review action has an invalid validation snapshot';
    END IF;
    IF NEW.action='approved' THEN
        SELECT count(*) INTO valid_line_count
        FROM public.invoices i JOIN public.line_items l ON l.invoice_id=i.id
        WHERE i.document_id=NEW.document_id
          AND l.description IS NOT NULL AND length(btrim(l.description))>0
          AND l.quantity IS NOT NULL AND l.unit_price IS NOT NULL
          AND l.total_price IS NOT NULL;
        IF valid_line_count=0 THEN
            RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='chk_review_approval_line',
              MESSAGE='Approval requires at least one valid current line item';
        END IF;
    END IF;
    IF next_event.id IS NULL THEN
        SELECT * INTO decision_event FROM public.review_audit_events
          WHERE document_id=NEW.document_id AND action IN ('approved','rejected')
          ORDER BY review_revision DESC LIMIT 1;
        IF decision_event.id IS NULL THEN
            IF document_row.last_reviewed_by IS NOT NULL OR document_row.last_reviewed_at IS NOT NULL THEN
                RAISE EXCEPTION 'Review decision summary exists without a decision';
            END IF;
        ELSIF document_row.last_reviewed_by IS DISTINCT FROM decision_event.actor_user_id
           OR document_row.last_reviewed_at IS DISTINCT FROM decision_event.created_at THEN
            RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='chk_review_event_decision_summary',
              MESSAGE='Document review summary must match latest decision event';
        END IF;
    END IF;
    RETURN NULL;
END;
$fn$;

CREATE FUNCTION public.validate_review_validation_commit() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $fn$
DECLARE
    event_row public.review_audit_events%ROWTYPE;
    blocking_count INTEGER;
    math_failure_count INTEGER;
    result_count INTEGER;
BEGIN
    SELECT * INTO STRICT event_row FROM public.review_audit_events WHERE id=NEW.audit_event_id;
    IF event_row.document_id<>NEW.document_id
       OR event_row.review_revision<>NEW.review_revision
       OR event_row.action NOT IN ('field_edited','approved') THEN
        RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='chk_review_validation_owner',
          MESSAGE='Review validation must match a save or approve event';
    END IF;
    SELECT count(*),
           count(*) FILTER (WHERE blocks_approval AND status IN ('failed','missing')),
           count(*) FILTER (WHERE rule_id LIKE 'BR-03%' AND status IN ('failed','missing'))
      INTO result_count,blocking_count,math_failure_count
      FROM public.review_validation_results WHERE review_validation_run_id=NEW.id;
    IF result_count=0 OR (NEW.approval_eligible AND blocking_count>0)
       OR (NEW.is_math_valid AND math_failure_count>0)
       OR (event_row.action='approved' AND
          (NEW.approval_eligible IS DISTINCT FROM TRUE OR NEW.is_math_valid IS DISTINCT FROM TRUE)) THEN
        RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='chk_review_validation_derived',
          MESSAGE='Review validation summary conflicts with rule results';
    END IF;
    RETURN NULL;
END;
$fn$;

CREATE FUNCTION public.validate_review_idempotency_owner() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $fn$
DECLARE
    actor_company UUID;
    document_company UUID;
    event_document UUID;
    event_actor UUID;
BEGIN
    SELECT company_id INTO actor_company FROM public.users WHERE id=NEW.actor_user_id FOR SHARE;
    SELECT company_id INTO document_company FROM public.documents WHERE id=NEW.document_id FOR SHARE;
    IF actor_company IS DISTINCT FROM NEW.company_id OR document_company IS DISTINCT FROM NEW.company_id THEN
        RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='chk_review_idempotency_tenant',
          MESSAGE='Idempotency scope owners must share one tenant';
    END IF;
    IF NEW.audit_event_id IS NOT NULL THEN
        SELECT document_id,actor_user_id INTO event_document,event_actor
        FROM public.review_audit_events WHERE id=NEW.audit_event_id FOR SHARE;
        IF event_document IS DISTINCT FROM NEW.document_id OR event_actor IS DISTINCT FROM NEW.actor_user_id THEN
            RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='chk_review_idempotency_event_owner',
              MESSAGE='Idempotency result event must match scope';
        END IF;
    END IF;
    RETURN NEW;
END;
$fn$;

CREATE FUNCTION public.enforce_review_history_immutable() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $fn$
BEGIN
    IF TG_OP='DELETE' AND pg_trigger_depth()>1 THEN RETURN OLD; END IF;
    RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='chk_review_history_immutable',
      MESSAGE='Review history is append-only';
END;
$fn$;

DROP TRIGGER trg_invoices_immutable ON public.invoices;
DROP FUNCTION public.enforce_invoice_initial_immutability() RESTRICT;
DROP TRIGGER trg_line_items_identity_immutable ON public.line_items;
DROP FUNCTION public.enforce_line_item_identity_immutability() RESTRICT;

CREATE TRIGGER trg_documents_review_mutation
  BEFORE UPDATE OF review_revision,status,last_reviewed_by,last_reviewed_at ON public.documents
  FOR EACH ROW EXECUTE FUNCTION public.validate_document_review_mutation();
CREATE TRIGGER trg_invoices_review_mutation
  BEFORE UPDATE OR DELETE ON public.invoices
  FOR EACH ROW EXECUTE FUNCTION public.enforce_invoice_review_mutation();
CREATE TRIGGER trg_line_items_review_mutation
  BEFORE INSERT OR UPDATE OR DELETE ON public.line_items
  FOR EACH ROW EXECUTE FUNCTION public.enforce_line_item_review_mutation();
CREATE TRIGGER trg_review_audit_events_owner
  BEFORE INSERT ON public.review_audit_events
  FOR EACH ROW EXECUTE FUNCTION public.validate_review_event_owner();
CREATE CONSTRAINT TRIGGER trg_review_audit_events_commit
  AFTER INSERT ON public.review_audit_events DEFERRABLE INITIALLY DEFERRED
  FOR EACH ROW EXECUTE FUNCTION public.validate_review_action_commit();
CREATE TRIGGER trg_review_audit_changes_payload
  BEFORE INSERT ON public.review_audit_changes
  FOR EACH ROW EXECUTE FUNCTION public.validate_review_change_payload();
CREATE CONSTRAINT TRIGGER trg_review_validation_runs_commit
  AFTER INSERT ON public.review_validation_runs DEFERRABLE INITIALLY DEFERRED
  FOR EACH ROW EXECUTE FUNCTION public.validate_review_validation_commit();
CREATE TRIGGER trg_review_idempotency_owner
  BEFORE INSERT OR UPDATE ON public.review_idempotency_keys
  FOR EACH ROW EXECUTE FUNCTION public.validate_review_idempotency_owner();
CREATE TRIGGER trg_review_idempotency_updated_at
  BEFORE UPDATE ON public.review_idempotency_keys
  FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
CREATE TRIGGER trg_review_audit_events_immutable
  BEFORE UPDATE OR DELETE ON public.review_audit_events
  FOR EACH ROW EXECUTE FUNCTION public.enforce_review_history_immutable();
CREATE TRIGGER trg_review_audit_changes_immutable
  BEFORE UPDATE OR DELETE ON public.review_audit_changes
  FOR EACH ROW EXECUTE FUNCTION public.enforce_review_history_immutable();
CREATE TRIGGER trg_review_validation_runs_immutable
  BEFORE UPDATE OR DELETE ON public.review_validation_runs
  FOR EACH ROW EXECUTE FUNCTION public.enforce_review_history_immutable();
CREATE TRIGGER trg_review_validation_results_immutable
  BEFORE UPDATE OR DELETE ON public.review_validation_results
  FOR EACH ROW EXECUTE FUNCTION public.enforce_review_history_immutable();

REVOKE UPDATE, DELETE, TRUNCATE ON public.review_audit_events,
  public.review_audit_changes,public.review_validation_runs,
  public.review_validation_results FROM PUBLIC;

DO $verify$
BEGIN
    IF (SELECT count(*) FROM information_schema.columns
        WHERE table_schema='public' AND table_name IN
          ('review_audit_events','review_audit_changes','review_validation_runs',
           'review_validation_results','review_idempotency_keys')) <> 52 THEN
        RAISE EXCEPTION 'Human review table column inventory verification failed';
    END IF;
    IF (SELECT count(*) FROM information_schema.columns
        WHERE table_schema='public' AND table_name='documents'
          AND column_name IN ('review_revision','last_reviewed_by','last_reviewed_at'))<>3
       OR (SELECT count(*) FROM information_schema.columns
           WHERE table_schema='public' AND table_name='line_items' AND column_name='origin')<>1 THEN
        RAISE EXCEPTION 'Human review extension column verification failed';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname='public'
               AND tablename LIKE 'review_%' AND indexdef ~* 'using gin') THEN
        RAISE EXCEPTION 'Unapproved review JSON index detected';
    END IF;
END;
$verify$;
-- END HUMAN REVIEW AUDIT UPGRADE
COMMIT;
