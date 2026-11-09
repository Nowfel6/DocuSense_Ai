-- Stage 03 build. Canonical entry point: accompanying Alembic revision.
-- Standalone alternative: psql -X -v ON_ERROR_STOP=1 -f this-file.sql.
-- Requires verified human-review revision 20260906_0004. Does NOT stamp Alembic.
BEGIN;
-- BEGIN DOCUMENT SEARCH EXPORT CORE UPGRADE
SET LOCAL search_path = pg_catalog, public;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '120s';

DO $preflight$
DECLARE
    heads text[];
    vector_type text;
BEGIN
    IF current_setting('server_version_num')::integer < 150000 THEN
        RAISE EXCEPTION 'Document search/export requires PostgreSQL 15 or newer';
    END IF;
    IF to_regclass('public.alembic_version') IS NULL THEN
        RAISE EXCEPTION 'Verified Alembic predecessor is required';
    END IF;
    SELECT array_agg(version_num::text ORDER BY version_num) INTO heads
    FROM public.alembic_version;
    IF heads IS DISTINCT FROM ARRAY['20260906_0004']::text[] THEN
        RAISE EXCEPTION 'Expected exactly human-review revision 20260906_0004';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname='vector') THEN
        RAISE EXCEPTION 'Verified pgvector extension is required';
    END IF;
    IF to_regclass('public.companies') IS NULL
       OR to_regclass('public.users') IS NULL
       OR to_regclass('public.documents') IS NULL
       OR to_regclass('public.processing_jobs') IS NULL
       OR to_regclass('public.document_chunks') IS NULL
       OR to_regclass('public.extraction_runs') IS NULL
       OR to_regclass('public.invoices') IS NULL
       OR to_regclass('public.line_items') IS NULL THEN
        RAISE EXCEPTION 'Verified auth, ingestion, RAG, and review parent tables are required';
    END IF;
    IF to_regprocedure('public.update_updated_at_column()') IS NULL THEN
        RAISE EXCEPTION 'Verified shared timestamp helper is required';
    END IF;
    SELECT format_type(a.atttypid,a.atttypmod) INTO vector_type
    FROM pg_attribute a
    WHERE a.attrelid='public.document_chunks'::regclass
      AND a.attname='embedding' AND NOT a.attisdropped;
    IF vector_type IS DISTINCT FROM 'vector(384)' THEN
        RAISE EXCEPTION 'Expected document_chunks.embedding vector(384), found %', vector_type;
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND c.relname = ANY (ARRAY[
          'export_jobs','export_job_documents','idx_export_jobs_company_created',
          'idx_export_jobs_requester_created','uq_export_jobs_idempotency',
          'idx_export_jobs_dispatch','idx_export_jobs_lease','idx_export_jobs_expiry',
          'idx_export_job_documents_document'])
    ) OR to_regprocedure('public.compute_export_source_value_hash(uuid)') IS NOT NULL
      OR to_regprocedure('public.validate_export_criteria_json(jsonb)') IS NOT NULL
      OR to_regprocedure('public.validate_export_job_owner()') IS NOT NULL
      OR to_regprocedure('public.validate_export_job_transition()') IS NOT NULL
      OR to_regprocedure('public.validate_export_job_document()') IS NOT NULL
      OR to_regprocedure('public.validate_export_membership_commit()') IS NOT NULL
      OR to_regprocedure('public.enforce_export_membership_immutable()') IS NOT NULL THEN
        RAISE EXCEPTION 'Document search/export object collision requires reconciliation';
    END IF;
    IF NOT EXISTS (
      SELECT 1 FROM information_schema.columns
      WHERE table_schema='public' AND table_name='documents'
        AND column_name='review_revision' AND data_type='bigint'
    ) THEN
      RAISE EXCEPTION 'Verified document review_revision is required';
    END IF;
END;
$preflight$;

CREATE FUNCTION public.validate_export_criteria_json(value jsonb) RETURNS boolean
LANGUAGE plpgsql IMMUTABLE SECURITY INVOKER
SET search_path = pg_catalog, public
AS $fn$
DECLARE
    key text;
    statuses jsonb;
BEGIN
    IF value IS NULL OR jsonb_typeof(value)<>'object'
       OR octet_length(value::text)>16384 THEN
        RETURN false;
    END IF;
    FOR key IN SELECT jsonb_object_keys(value) LOOP
        IF key <> ALL (ARRAY[
          'selection_type','sort_by','order','document_statuses','document_type',
          'supplier','currency','invoice_date_from','invoice_date_to',
          'uploaded_from','uploaded_to','min_total','max_total',
          'semantic_query_present','semantic_query_sha256','requested_document_count',
          'embedding_model','embedding_revision','schema_version']) THEN
            RETURN false;
        END IF;
    END LOOP;
    IF value ?| ARRAY['query','raw_query','document_ids','ids','company_id','requested_by_user_id'] THEN
        RETURN false;
    END IF;
    IF value ? 'selection_type'
       AND value->>'selection_type' NOT IN ('document_ids','criteria') THEN RETURN false; END IF;
    IF value ? 'sort_by'
       AND value->>'sort_by' NOT IN ('relevance','date_issued','grand_total','created_at') THEN RETURN false; END IF;
    IF value ? 'order' AND value->>'order' NOT IN ('asc','desc') THEN RETURN false; END IF;
    IF value ? 'document_type'
       AND value->>'document_type' NOT IN ('commercial_invoice','purchase_order','packing_list') THEN RETURN false; END IF;
    IF value ? 'supplier'
       AND (jsonb_typeof(value->'supplier')<>'string'
            OR length(btrim(value->>'supplier')) NOT BETWEEN 1 AND 255) THEN RETURN false; END IF;
    IF value ? 'currency'
       AND (jsonb_typeof(value->'currency')<>'string'
            OR value->>'currency' !~ '^[A-Z]{3}$') THEN RETURN false; END IF;
    IF value ? 'embedding_model'
       AND (jsonb_typeof(value->'embedding_model')<>'string'
            OR length(btrim(value->>'embedding_model')) NOT BETWEEN 1 AND 255) THEN RETURN false; END IF;
    IF value ? 'embedding_revision'
       AND (jsonb_typeof(value->'embedding_revision')<>'string'
            OR length(btrim(value->>'embedding_revision')) NOT BETWEEN 1 AND 255) THEN RETURN false; END IF;
    IF value ? 'schema_version'
       AND (jsonb_typeof(value->'schema_version')<>'string'
            OR value->>'schema_version'<>'docusense-approved-invoice-export-v1') THEN RETURN false; END IF;
    IF value ? 'document_statuses' THEN
        statuses := value->'document_statuses';
        IF jsonb_typeof(statuses)<>'array' OR jsonb_array_length(statuses) NOT BETWEEN 1 AND 3
           OR EXISTS (SELECT 1 FROM jsonb_array_elements_text(statuses) s(v)
                      WHERE v NOT IN ('pending_review','approved','rejected'))
           OR (SELECT count(*) FROM jsonb_array_elements_text(statuses)) <>
              (SELECT count(DISTINCT v) FROM jsonb_array_elements_text(statuses) s(v)) THEN
            RETURN false;
        END IF;
    END IF;
    IF value ? 'semantic_query_present'
       AND jsonb_typeof(value->'semantic_query_present')<>'boolean' THEN RETURN false; END IF;
    IF COALESCE((value->>'semantic_query_present')::boolean,false)
       <> (value ? 'semantic_query_sha256') THEN RETURN false; END IF;
    IF value ? 'semantic_query_sha256'
       AND value->>'semantic_query_sha256' !~ '^[0-9a-f]{64}$' THEN RETURN false; END IF;
    IF value ? 'requested_document_count'
       AND (jsonb_typeof(value->'requested_document_count')<>'number'
            OR (value->>'requested_document_count') !~ '^[0-9]+$'
            OR (value->>'requested_document_count')::numeric NOT BETWEEN 1 AND 50000) THEN RETURN false; END IF;
    IF value ? 'invoice_date_from' AND value->>'invoice_date_from' !~ '^\d{4}-\d{2}-\d{2}$' THEN RETURN false; END IF;
    IF value ? 'invoice_date_to' AND value->>'invoice_date_to' !~ '^\d{4}-\d{2}-\d{2}$' THEN RETURN false; END IF;
    IF value ? 'min_total' AND (jsonb_typeof(value->'min_total')<>'string' OR value->>'min_total' !~ '^(0|[1-9][0-9]{0,11})(\.[0-9]{2})$') THEN RETURN false; END IF;
    IF value ? 'max_total' AND (jsonb_typeof(value->'max_total')<>'string' OR value->>'max_total' !~ '^(0|[1-9][0-9]{0,11})(\.[0-9]{2})$') THEN RETURN false; END IF;
    IF value ? 'min_total' AND value ? 'max_total'
       AND (value->>'min_total')::numeric > (value->>'max_total')::numeric THEN RETURN false; END IF;
    IF value ? 'invoice_date_from' AND value ? 'invoice_date_to'
       AND (value->>'invoice_date_from')::date > (value->>'invoice_date_to')::date THEN RETURN false; END IF;
    IF value ? 'uploaded_from' THEN
      IF jsonb_typeof(value->'uploaded_from')<>'string' THEN RETURN false; END IF;
      PERFORM (value->>'uploaded_from')::timestamptz;
    END IF;
    IF value ? 'uploaded_to' THEN
      IF jsonb_typeof(value->'uploaded_to')<>'string' THEN RETURN false; END IF;
      PERFORM (value->>'uploaded_to')::timestamptz;
    END IF;
    IF value ? 'uploaded_from' AND value ? 'uploaded_to'
       AND (value->>'uploaded_from')::timestamptz > (value->>'uploaded_to')::timestamptz THEN RETURN false; END IF;
    IF value->>'sort_by'='relevance'
       AND NOT COALESCE((value->>'semantic_query_present')::boolean,false) THEN RETURN false; END IF;
    RETURN true;
EXCEPTION WHEN invalid_text_representation OR datetime_field_overflow OR numeric_value_out_of_range THEN
    RETURN false;
END;
$fn$;

CREATE FUNCTION public.compute_export_source_value_hash(p_document_id uuid) RETURNS char(64)
LANGUAGE sql STABLE SECURITY INVOKER
SET search_path = pg_catalog, public
AS $fn$
SELECT encode(sha256(convert_to(jsonb_build_object(
  'version','docusense-export-source-v1',
  'document',jsonb_build_object(
    'id',d.id::text,'status',d.status,'review_revision',d.review_revision),
  'invoice',jsonb_build_object(
    'id',i.id::text,'invoice_number',i.invoice_number,'supplier_name',i.supplier_name,
    'supplier_tax_id',i.supplier_tax_id,'buyer_name',i.buyer_name,
    'date_issued',CASE WHEN i.date_issued IS NULL THEN NULL ELSE to_char(i.date_issued,'YYYY-MM-DD') END,
    'due_date',CASE WHEN i.due_date IS NULL THEN NULL ELSE to_char(i.due_date,'YYYY-MM-DD') END,
    'currency',i.currency,
    'subtotal',CASE WHEN i.subtotal IS NULL THEN NULL ELSE to_char(i.subtotal,'FM9999999999990.00') END,
    'tax_amount',CASE WHEN i.tax_amount IS NULL THEN NULL ELSE to_char(i.tax_amount,'FM9999999999990.00') END,
    'discount_amount',CASE WHEN i.discount_amount IS NULL THEN NULL ELSE to_char(i.discount_amount,'FM9999999999990.00') END,
    'grand_total',CASE WHEN i.grand_total IS NULL THEN NULL ELSE to_char(i.grand_total,'FM9999999999990.00') END,
    'is_math_valid',i.is_math_valid),
  'lines',COALESCE((
    SELECT jsonb_agg(jsonb_build_object(
      'id',li.id::text,'source_row_key',li.source_row_key,'line_order',li.line_order,
      'origin',li.origin,'description',li.description,'hs_code',li.hs_code,
      'quantity',CASE WHEN li.quantity IS NULL THEN NULL ELSE to_char(li.quantity,'FM99999999999990.0000') END,
      'unit_price',CASE WHEN li.unit_price IS NULL THEN NULL ELSE to_char(li.unit_price,'FM9999999999990.0000') END,
      'tax_amount',CASE WHEN li.tax_amount IS NULL THEN NULL ELSE to_char(li.tax_amount,'FM9999999999990.00') END,
      'total_price',CASE WHEN li.total_price IS NULL THEN NULL ELSE to_char(li.total_price,'FM9999999999990.00') END
    ) ORDER BY li.line_order,li.id)
    FROM public.line_items li WHERE li.invoice_id=i.id
  ),'[]'::jsonb)
)::text,'UTF8')),'hex')::char(64)
FROM public.documents d
JOIN public.invoices i ON i.document_id=d.id
WHERE d.id=p_document_id;
$fn$;

CREATE TABLE public.export_jobs (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL,
    requested_by_user_id UUID NOT NULL,
    format VARCHAR(8) NOT NULL,
    mode VARCHAR(16) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'queued',
    current_stage VARCHAR(16) NOT NULL DEFAULT 'accepted',
    progress_percentage SMALLINT NOT NULL DEFAULT 0,
    selection_type VARCHAR(16) NOT NULL,
    schema_version VARCHAR(64) NOT NULL,
    criteria_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    criteria_hash CHAR(64) NOT NULL,
    request_hash CHAR(64) NOT NULL,
    idempotency_key_hash CHAR(64),
    selected_document_count INTEGER NOT NULL,
    exported_document_count INTEGER NOT NULL DEFAULT 0,
    row_count INTEGER NOT NULL DEFAULT 0,
    artifact_object_key TEXT,
    artifact_file_name VARCHAR(255),
    artifact_content_type VARCHAR(127),
    artifact_size_bytes BIGINT,
    artifact_sha256 CHAR(64),
    artifact_expires_at TIMESTAMPTZ,
    attempt_count SMALLINT NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ,
    lease_token UUID,
    lease_expires_at TIMESTAMPTZ,
    error_code VARCHAR(100),
    error_message VARCHAR(1000),
    request_id VARCHAR(128) NOT NULL,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    failed_at TIMESTAMPTZ,
    expired_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_export_jobs PRIMARY KEY (id),
    CONSTRAINT fk_export_jobs_company FOREIGN KEY (company_id)
      REFERENCES public.companies(id) ON DELETE RESTRICT ON UPDATE NO ACTION,
    CONSTRAINT fk_export_jobs_requested_by_user FOREIGN KEY (requested_by_user_id)
      REFERENCES public.users(id) ON DELETE RESTRICT ON UPDATE NO ACTION,
    CONSTRAINT chk_export_jobs_format CHECK (format IN ('csv','xlsx','json')),
    CONSTRAINT chk_export_jobs_mode CHECK (mode IN ('synchronous','asynchronous')),
    CONSTRAINT chk_export_jobs_status CHECK (status IN ('queued','processing','completed','failed','expired')),
    CONSTRAINT chk_export_jobs_stage CHECK (current_stage IN ('accepted','generating','packaging','storing','completed')),
    CONSTRAINT chk_export_jobs_selection_type CHECK (selection_type IN ('document_ids','criteria')),
    CONSTRAINT chk_export_jobs_schema_version CHECK (schema_version='docusense-approved-invoice-export-v1'),
    CONSTRAINT chk_export_jobs_criteria_object_size CHECK (
      public.validate_export_criteria_json(criteria_json)
      AND (NOT criteria_json ? 'selection_type' OR criteria_json->>'selection_type'=selection_type)),
    CONSTRAINT chk_export_jobs_hashes CHECK (
      criteria_hash ~ '^[0-9a-f]{64}$' AND request_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT chk_export_jobs_idempotency_hash CHECK (
      idempotency_key_hash IS NULL OR idempotency_key_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT chk_export_jobs_counts CHECK (
      selected_document_count BETWEEN 1 AND 50000
      AND exported_document_count BETWEEN 0 AND selected_document_count
      AND row_count BETWEEN 0 AND 1000000),
    CONSTRAINT chk_export_jobs_progress CHECK (progress_percentage BETWEEN 0 AND 100),
    CONSTRAINT chk_export_jobs_attempt_count CHECK (
      attempt_count BETWEEN 0 AND 4 AND (mode='asynchronous' OR attempt_count=0)),
    CONSTRAINT chk_export_jobs_artifact_hash CHECK (
      artifact_sha256 IS NULL OR artifact_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT chk_export_jobs_request_id CHECK (
      request_id=btrim(request_id) AND length(request_id) BETWEEN 1 AND 128
      AND request_id ~ '^[!-~]+$'),
    CONSTRAINT chk_export_jobs_artifact_file_name CHECK (
      artifact_file_name IS NULL OR (
        artifact_file_name=btrim(artifact_file_name) AND length(artifact_file_name)>0
        AND artifact_file_name NOT IN ('.','..')
        AND position('/' in artifact_file_name)=0
        AND position(E'\\' in artifact_file_name)=0
        AND artifact_file_name !~ '[[:cntrl:]]')),
    CONSTRAINT chk_export_jobs_content_type CHECK (
      artifact_content_type IS NULL OR artifact_content_type IN (
        'text/csv; charset=utf-8',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'application/json','application/zip')),
    CONSTRAINT chk_export_jobs_timestamps CHECK (
      updated_at>=created_at
      AND (started_at IS NULL OR started_at>=created_at)
      AND (completed_at IS NULL OR completed_at>=COALESCE(started_at,created_at))
      AND (failed_at IS NULL OR failed_at>=COALESCE(started_at,created_at))
      AND (artifact_expires_at IS NULL OR
           (completed_at IS NOT NULL AND artifact_expires_at>completed_at
            AND artifact_expires_at<=completed_at+INTERVAL '7 days'))
      AND (expired_at IS NULL OR
           (artifact_expires_at IS NOT NULL AND expired_at>=artifact_expires_at))),
    CONSTRAINT chk_export_jobs_state_shape CHECK (
      (
        status='queued' AND mode='asynchronous' AND current_stage='accepted'
        AND progress_percentage=0 AND exported_document_count=0 AND row_count=0
        AND completed_at IS NULL AND failed_at IS NULL AND expired_at IS NULL
        AND lease_token IS NULL AND lease_expires_at IS NULL
        AND artifact_object_key IS NULL AND artifact_file_name IS NULL
        AND artifact_content_type IS NULL AND artifact_size_bytes IS NULL
        AND artifact_sha256 IS NULL AND artifact_expires_at IS NULL
        AND ((attempt_count=0 AND started_at IS NULL AND next_attempt_at IS NULL
              AND error_code IS NULL AND error_message IS NULL)
          OR (attempt_count BETWEEN 1 AND 3 AND started_at IS NOT NULL
              AND next_attempt_at IS NOT NULL
              AND (error_code IS NULL)=(error_message IS NULL)
              AND (error_code IS NULL OR
                   (error_code=btrim(error_code) AND length(error_code)>0
                    AND error_message=btrim(error_message) AND length(error_message)>0))))
      ) OR (
        status='processing' AND started_at IS NOT NULL
        AND current_stage IN ('generating','packaging','storing')
        AND progress_percentage<100 AND exported_document_count<=selected_document_count
        AND completed_at IS NULL AND failed_at IS NULL AND expired_at IS NULL
        AND next_attempt_at IS NULL AND error_code IS NULL AND error_message IS NULL
        AND artifact_object_key IS NULL AND artifact_file_name IS NULL
        AND artifact_content_type IS NULL AND artifact_size_bytes IS NULL
        AND artifact_sha256 IS NULL AND artifact_expires_at IS NULL
        AND ((mode='synchronous' AND attempt_count=0 AND current_stage<>'packaging'
              AND lease_token IS NULL AND lease_expires_at IS NULL)
          OR (mode='asynchronous' AND attempt_count BETWEEN 1 AND 4
              AND lease_token IS NOT NULL AND lease_expires_at>updated_at))
      ) OR (
        status='completed' AND current_stage='completed' AND progress_percentage=100
        AND exported_document_count=selected_document_count AND row_count>0
        AND started_at IS NOT NULL AND completed_at IS NOT NULL
        AND artifact_object_key IS NOT NULL AND btrim(artifact_object_key)<>''
        AND artifact_file_name IS NOT NULL AND artifact_content_type IS NOT NULL
        AND artifact_size_bytes IS NOT NULL AND artifact_size_bytes>0 AND artifact_sha256 IS NOT NULL
        AND artifact_expires_at IS NOT NULL
        AND failed_at IS NULL AND expired_at IS NULL AND next_attempt_at IS NULL
        AND lease_token IS NULL AND lease_expires_at IS NULL
        AND error_code IS NULL AND error_message IS NULL
        AND ((mode='asynchronous' AND artifact_content_type='application/zip'
              AND artifact_file_name ~ '\.zip$' AND artifact_size_bytes<=2147483648)
          OR (mode='synchronous' AND artifact_size_bytes<=67108864
              AND ((format='csv' AND artifact_content_type='text/csv; charset=utf-8' AND artifact_file_name ~ '\.csv$')
                OR (format='xlsx' AND artifact_content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' AND artifact_file_name ~ '\.xlsx$')
                OR (format='json' AND artifact_content_type='application/json' AND artifact_file_name ~ '\.json$'))))
      ) OR (
        status='failed' AND current_stage<>'completed' AND progress_percentage<100
        AND exported_document_count=0 AND failed_at IS NOT NULL
        AND error_code IS NOT NULL AND error_message IS NOT NULL
        AND error_code=btrim(error_code) AND length(error_code)>0
        AND error_message=btrim(error_message) AND length(error_message)>0
        AND completed_at IS NULL AND expired_at IS NULL AND next_attempt_at IS NULL
        AND lease_token IS NULL AND lease_expires_at IS NULL
        AND artifact_object_key IS NULL AND artifact_file_name IS NULL
        AND artifact_content_type IS NULL AND artifact_size_bytes IS NULL
        AND artifact_sha256 IS NULL AND artifact_expires_at IS NULL
      ) OR (
        status='expired' AND current_stage='completed' AND progress_percentage=100
        AND exported_document_count=selected_document_count AND row_count>0
        AND started_at IS NOT NULL AND completed_at IS NOT NULL
        AND artifact_object_key IS NULL AND artifact_file_name IS NOT NULL
        AND artifact_content_type IS NOT NULL AND artifact_size_bytes IS NOT NULL AND artifact_size_bytes>0
        AND artifact_sha256 IS NOT NULL AND artifact_expires_at IS NOT NULL
        AND expired_at IS NOT NULL AND failed_at IS NULL AND next_attempt_at IS NULL
        AND lease_token IS NULL AND lease_expires_at IS NULL
        AND error_code IS NULL AND error_message IS NULL
        AND ((mode='asynchronous' AND artifact_content_type='application/zip'
              AND artifact_file_name ~ '\.zip$' AND artifact_size_bytes<=2147483648)
          OR (mode='synchronous' AND artifact_size_bytes<=67108864
              AND ((format='csv' AND artifact_content_type='text/csv; charset=utf-8' AND artifact_file_name ~ '\.csv$')
                OR (format='xlsx' AND artifact_content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' AND artifact_file_name ~ '\.xlsx$')
                OR (format='json' AND artifact_content_type='application/json' AND artifact_file_name ~ '\.json$'))))
      )
    )
);

CREATE TABLE public.export_job_documents (
    export_job_id UUID NOT NULL,
    document_id UUID NOT NULL,
    review_revision BIGINT NOT NULL,
    ordinal INTEGER NOT NULL,
    source_value_hash CHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_export_job_documents PRIMARY KEY (export_job_id,document_id),
    CONSTRAINT fk_export_job_documents_job FOREIGN KEY (export_job_id)
      REFERENCES public.export_jobs(id) ON DELETE CASCADE ON UPDATE NO ACTION,
    CONSTRAINT fk_export_job_documents_document FOREIGN KEY (document_id)
      REFERENCES public.documents(id) ON DELETE RESTRICT ON UPDATE NO ACTION,
    CONSTRAINT uq_export_job_documents_ordinal UNIQUE (export_job_id,ordinal),
    CONSTRAINT chk_export_job_documents_review_revision CHECK (review_revision>0),
    CONSTRAINT chk_export_job_documents_ordinal CHECK (ordinal>=0),
    CONSTRAINT chk_export_job_documents_source_hash CHECK (source_value_hash ~ '^[0-9a-f]{64}$')
);

CREATE INDEX idx_export_jobs_company_created
  ON public.export_jobs(company_id,created_at DESC,id DESC);
CREATE INDEX idx_export_jobs_requester_created
  ON public.export_jobs(requested_by_user_id,created_at DESC,id DESC);
CREATE UNIQUE INDEX uq_export_jobs_idempotency
  ON public.export_jobs(company_id,requested_by_user_id,idempotency_key_hash)
  WHERE idempotency_key_hash IS NOT NULL;
CREATE INDEX idx_export_jobs_dispatch
  ON public.export_jobs(next_attempt_at,created_at,id)
  WHERE status='queued' AND mode='asynchronous';
CREATE INDEX idx_export_jobs_lease
  ON public.export_jobs(lease_expires_at,id)
  WHERE status='processing' AND mode='asynchronous';
CREATE INDEX idx_export_jobs_expiry
  ON public.export_jobs(artifact_expires_at,id)
  WHERE status='completed';
CREATE INDEX idx_export_job_documents_document
  ON public.export_job_documents(document_id,export_job_id);

CREATE FUNCTION public.validate_export_job_owner() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $fn$
DECLARE owner_company uuid; owner_role text;
BEGIN
  SELECT u.company_id,u.role INTO owner_company,owner_role
  FROM public.users u WHERE u.id=NEW.requested_by_user_id FOR KEY SHARE;
  IF NOT FOUND OR owner_company IS DISTINCT FROM NEW.company_id
     OR owner_role NOT IN ('admin','operator') THEN
    RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='chk_export_jobs_owner',
      MESSAGE='Export requester must be a same-company admin or operator';
  END IF;
  RETURN NEW;
END;
$fn$;

CREATE FUNCTION public.validate_export_job_transition() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $fn$
DECLARE old_rank integer; new_rank integer;
BEGIN
  IF ROW(NEW.id,NEW.company_id,NEW.requested_by_user_id,NEW.format,NEW.mode,
         NEW.selection_type,NEW.schema_version,NEW.criteria_json,NEW.criteria_hash,
         NEW.request_hash,NEW.idempotency_key_hash,NEW.selected_document_count,
         NEW.request_id,NEW.created_at)
     IS DISTINCT FROM
     ROW(OLD.id,OLD.company_id,OLD.requested_by_user_id,OLD.format,OLD.mode,
         OLD.selection_type,OLD.schema_version,OLD.criteria_json,OLD.criteria_hash,
         OLD.request_hash,OLD.idempotency_key_hash,OLD.selected_document_count,
         OLD.request_id,OLD.created_at) THEN
    RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='chk_export_jobs_identity_immutable',
      MESSAGE='Accepted export identity and selection are immutable';
  END IF;
  IF OLD.status=NEW.status THEN
    IF NEW.status='processing' THEN
      old_rank := CASE OLD.current_stage WHEN 'generating' THEN 1 WHEN 'packaging' THEN 2 WHEN 'storing' THEN 3 ELSE 0 END;
      new_rank := CASE NEW.current_stage WHEN 'generating' THEN 1 WHEN 'packaging' THEN 2 WHEN 'storing' THEN 3 ELSE 0 END;
      IF new_rank<old_rank OR NEW.progress_percentage<OLD.progress_percentage
         OR NEW.exported_document_count<OLD.exported_document_count
         OR NEW.row_count<OLD.row_count OR NEW.attempt_count<>OLD.attempt_count
         OR NEW.started_at IS DISTINCT FROM OLD.started_at THEN
        RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='chk_export_jobs_monotonic_progress',
          MESSAGE='Processing updates must be monotonic and remain in the current attempt';
      END IF;
    ELSIF ROW(NEW.status,NEW.current_stage,NEW.progress_percentage,
              NEW.exported_document_count,NEW.row_count,NEW.artifact_object_key,
              NEW.artifact_file_name,NEW.artifact_content_type,NEW.artifact_size_bytes,
              NEW.artifact_sha256,NEW.artifact_expires_at,NEW.attempt_count,
              NEW.next_attempt_at,NEW.lease_token,NEW.lease_expires_at,
              NEW.error_code,NEW.error_message,NEW.started_at,NEW.completed_at,
              NEW.failed_at,NEW.expired_at)
          IS DISTINCT FROM
          ROW(OLD.status,OLD.current_stage,OLD.progress_percentage,
              OLD.exported_document_count,OLD.row_count,OLD.artifact_object_key,
              OLD.artifact_file_name,OLD.artifact_content_type,OLD.artifact_size_bytes,
              OLD.artifact_sha256,OLD.artifact_expires_at,OLD.attempt_count,
              OLD.next_attempt_at,OLD.lease_token,OLD.lease_expires_at,
              OLD.error_code,OLD.error_message,OLD.started_at,OLD.completed_at,
              OLD.failed_at,OLD.expired_at) THEN
      RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='chk_export_jobs_terminal_immutable',
        MESSAGE='Queued and terminal rows require a legal state transition';
    END IF;
  ELSIF NOT (
      (OLD.mode='synchronous' AND OLD.status='processing' AND NEW.status IN ('completed','failed'))
      OR (OLD.mode='asynchronous' AND OLD.status='queued' AND NEW.status IN ('processing','failed'))
      OR (OLD.mode='asynchronous' AND OLD.status='processing' AND NEW.status IN ('queued','completed','failed'))
      OR (OLD.status='completed' AND NEW.status='expired')
    ) THEN
    RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='chk_export_jobs_transition',
      MESSAGE='Illegal export job transition';
  END IF;
  IF OLD.status='queued' AND NEW.status='processing'
     AND NEW.attempt_count<>OLD.attempt_count+1 THEN
    RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='chk_export_jobs_claim_attempt',
      MESSAGE='Async claim must increment attempt exactly once';
  END IF;
  IF NOT (OLD.status='queued' AND NEW.status='processing')
     AND NEW.attempt_count<>OLD.attempt_count THEN
    RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='chk_export_jobs_attempt_transition',
      MESSAGE='Attempt changes are allowed only during claim';
  END IF;
  RETURN NEW;
END;
$fn$;

CREATE FUNCTION public.validate_export_job_document() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $fn$
DECLARE
  job_company uuid; job_status text; job_mode text;
  doc_company uuid; doc_status text; doc_type text; doc_revision bigint;
  process_status text; process_progress smallint; run_status text;
  current_hash char(64);
BEGIN
  SELECT company_id,status,mode INTO job_company,job_status,job_mode
  FROM public.export_jobs WHERE id=NEW.export_job_id FOR KEY SHARE;
  IF NOT FOUND OR NOT ((job_mode='asynchronous' AND job_status='queued')
                    OR (job_mode='synchronous' AND job_status='processing')) THEN
    RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='chk_export_job_documents_parent_state',
      MESSAGE='Membership can be accepted only with a new initial job';
  END IF;
  SELECT d.company_id,d.status,d.doc_type,d.review_revision,pj.status,
         pj.progress_percentage,er.status
    INTO doc_company,doc_status,doc_type,doc_revision,process_status,
         process_progress,run_status
  FROM public.documents d
  JOIN public.processing_jobs pj ON pj.document_id=d.id
  JOIN public.extraction_runs er ON er.document_id=d.id
  JOIN public.invoices i ON i.document_id=d.id AND i.extraction_run_id=er.id
  WHERE d.id=NEW.document_id
  FOR KEY SHARE OF d,pj,er,i;
  IF NOT FOUND OR doc_company IS DISTINCT FROM job_company
     OR doc_status<>'approved' OR doc_type<>'commercial_invoice'
     OR doc_revision<=0 OR doc_revision<>NEW.review_revision
     OR process_status<>'completed' OR process_progress<>100 OR run_status<>'completed' THEN
    RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='chk_export_job_documents_current_source',
      MESSAGE='Export member is not a current same-company approved invoice';
  END IF;
  current_hash := public.compute_export_source_value_hash(NEW.document_id);
  IF current_hash IS NULL OR current_hash IS DISTINCT FROM NEW.source_value_hash THEN
    RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='chk_export_job_documents_source_match',
      MESSAGE='Export member source hash does not match current approved values';
  END IF;
  RETURN NEW;
END;
$fn$;

CREATE FUNCTION public.validate_export_membership_commit() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $fn$
DECLARE job_id uuid; expected integer; actual integer; min_ord integer; max_ord integer; distinct_ord integer;
DECLARE parent_status text; parent_mode text; parent_stage text; parent_progress smallint;
BEGIN
  IF TG_TABLE_NAME='export_jobs' THEN
    job_id := NEW.id;
  ELSE
    job_id := NEW.export_job_id;
  END IF;
  SELECT selected_document_count,status,mode,current_stage,progress_percentage
    INTO expected,parent_status,parent_mode,parent_stage,parent_progress
  FROM public.export_jobs WHERE id=job_id FOR KEY SHARE;
  IF NOT FOUND THEN RETURN NULL; END IF;
  SELECT count(*)::integer,min(ordinal),max(ordinal),count(DISTINCT ordinal)::integer
    INTO actual,min_ord,max_ord,distinct_ord
  FROM public.export_job_documents WHERE export_job_id=job_id;
  IF actual<>expected OR min_ord<>0 OR max_ord<>expected-1 OR distinct_ord<>expected THEN
    RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='chk_export_membership_complete',
      MESSAGE='Export membership must exactly match the accepted contiguous count';
  END IF;
  IF NOT ((parent_mode='asynchronous' AND parent_status='queued'
           AND parent_stage='accepted' AND parent_progress=0)
       OR (parent_mode='synchronous' AND parent_status='processing'
           AND parent_stage IN ('generating','storing'))) THEN
    RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='chk_export_membership_initial_parent',
      MESSAGE='Export membership must commit with the initial parent state';
  END IF;
  RETURN NULL;
END;
$fn$;

CREATE FUNCTION public.enforce_export_membership_immutable() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $fn$
BEGIN
  RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='chk_export_membership_immutable',
    MESSAGE='Accepted export membership is immutable';
END;
$fn$;

CREATE TRIGGER trg_export_jobs_owner
  BEFORE INSERT OR UPDATE OF company_id,requested_by_user_id ON public.export_jobs
  FOR EACH ROW EXECUTE FUNCTION public.validate_export_job_owner();
CREATE TRIGGER trg_export_jobs_transition
  BEFORE UPDATE ON public.export_jobs
  FOR EACH ROW EXECUTE FUNCTION public.validate_export_job_transition();
CREATE TRIGGER trg_export_jobs_updated_at
  BEFORE UPDATE ON public.export_jobs
  FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
CREATE TRIGGER trg_export_job_documents_validate
  BEFORE INSERT ON public.export_job_documents
  FOR EACH ROW EXECUTE FUNCTION public.validate_export_job_document();
CREATE TRIGGER trg_export_job_documents_immutable
  BEFORE UPDATE OR DELETE ON public.export_job_documents
  FOR EACH ROW EXECUTE FUNCTION public.enforce_export_membership_immutable();
CREATE CONSTRAINT TRIGGER trg_export_jobs_membership_commit
  AFTER INSERT ON public.export_jobs DEFERRABLE INITIALLY DEFERRED
  FOR EACH ROW EXECUTE FUNCTION public.validate_export_membership_commit();
CREATE CONSTRAINT TRIGGER trg_export_job_documents_membership_commit
  AFTER INSERT ON public.export_job_documents DEFERRABLE INITIALLY DEFERRED
  FOR EACH ROW EXECUTE FUNCTION public.validate_export_membership_commit();

REVOKE ALL ON public.export_jobs,public.export_job_documents FROM PUBLIC;
REVOKE UPDATE, DELETE, TRUNCATE ON public.export_job_documents FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.compute_export_source_value_hash(uuid) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.validate_export_criteria_json(jsonb) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.validate_export_job_owner() FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.validate_export_job_transition() FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.validate_export_job_document() FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.validate_export_membership_commit() FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.enforce_export_membership_immutable() FROM PUBLIC;
-- END DOCUMENT SEARCH EXPORT CORE UPGRADE
COMMIT;
