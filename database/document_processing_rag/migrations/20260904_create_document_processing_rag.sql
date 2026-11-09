-- Stage 03 build. Canonical entry point: accompanying Alembic revision.
-- Standalone alternative: psql -X -v ON_ERROR_STOP=1 -f this-file.sql.
-- Requires verified ingestion revision 20260903_0002. Does NOT stamp Alembic.
BEGIN;
-- BEGIN DOCUMENT PROCESSING RAG UPGRADE
SET LOCAL search_path = pg_catalog, public;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '120s';

DO $preflight$
DECLARE helper_body text;
BEGIN
    IF current_setting('server_version_num')::integer < 150000 THEN
        RAISE EXCEPTION 'Document processing RAG requires PostgreSQL 15 or newer';
    END IF;
    IF to_regclass('public.alembic_version') IS NULL OR
       (SELECT array_agg(version_num::text ORDER BY version_num) FROM public.alembic_version)
          IS DISTINCT FROM ARRAY['20260903_0002']::text[] THEN
        RAISE EXCEPTION 'Expected exactly ingestion revision 20260903_0002';
    END IF;
    IF to_regclass('public.documents') IS NULL OR to_regclass('public.processing_jobs') IS NULL THEN
        RAISE EXCEPTION 'Verified ingestion parent tables are required';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.processing_jobs'::regclass
          AND contype = 'u' AND conname = 'uq_processing_jobs_document_id'
    ) THEN
        RAISE EXCEPTION 'Expected one-job-per-document predecessor constraint';
    END IF;
    SELECT regexp_replace(lower(p.prosrc), '[[:space:]]', '', 'g') INTO helper_body
    FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
    JOIN pg_language l ON l.oid=p.prolang
    WHERE n.nspname='public' AND p.proname='update_updated_at_column'
      AND p.pronargs=0 AND p.prorettype='trigger'::regtype
      AND l.lanname='plpgsql' AND NOT p.prosecdef;
    IF helper_body IS DISTINCT FROM 'beginnew.updated_at=now();returnnew;end;' THEN
        RAISE EXCEPTION 'Shared timestamp helper differs from verified predecessor';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND c.relname = ANY (ARRAY[
          'document_partitions','document_chunks','extraction_runs','invoices','line_items','field_evidence','validation_results',
          'idx_document_partitions_company_id',
          'idx_document_chunks_document_type_page','idx_document_chunks_parent',
          'idx_document_chunks_embedding_ready','idx_invoices_number',
          'idx_field_evidence_primary_chunk','idx_field_evidence_state'])
    ) THEN RAISE EXCEPTION 'RAG relation/index collision; reconcile instead of adopting'; END IF;
END;
$preflight$;

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE public.document_partitions (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL,
    document_id UUID NOT NULL,
    job_id UUID NOT NULL,
    created_attempt SMALLINT NOT NULL,
    pipeline_version VARCHAR(64) NOT NULL,
    configuration_hash CHAR(64) NOT NULL,
    parser_name VARCHAR(100) NOT NULL DEFAULT 'docling',
    parser_version VARCHAR(100) NOT NULL,
    ocr_policy_version VARCHAR(64) NOT NULL,
    canonical_document JSONB NOT NULL,
    content_hash CHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT pk_document_partitions PRIMARY KEY (id),
    CONSTRAINT fk_document_partitions_company_id FOREIGN KEY (company_id)
      REFERENCES public.companies(id) ON DELETE CASCADE ON UPDATE NO ACTION,
    CONSTRAINT fk_document_partitions_document_id FOREIGN KEY (document_id)
      REFERENCES public.documents(id) ON DELETE CASCADE ON UPDATE NO ACTION,
    CONSTRAINT fk_document_partitions_job_id FOREIGN KEY (job_id)
      REFERENCES public.processing_jobs(id) ON DELETE CASCADE ON UPDATE NO ACTION,
    CONSTRAINT uq_document_partitions_document_id UNIQUE (document_id),
    CONSTRAINT uq_document_partitions_job_id UNIQUE (job_id),
    CONSTRAINT chk_document_partitions_attempt CHECK (created_attempt BETWEEN 1 AND 4),
    CONSTRAINT chk_document_partitions_versions CHECK (
      length(btrim(pipeline_version))>0 AND parser_name='docling'
      AND length(btrim(parser_version))>0 AND length(btrim(ocr_policy_version))>0),
    CONSTRAINT chk_document_partitions_configuration_hash CHECK (configuration_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT chk_document_partitions_content_hash CHECK (content_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT chk_document_partitions_size CHECK (octet_length(canonical_document::text)<=16777216),
    CONSTRAINT chk_document_partitions_shape CHECK (
      jsonb_typeof(canonical_document)='object'
      AND canonical_document->>'document_id'=document_id::text
      AND canonical_document->>'pipeline_version'=pipeline_version
      AND canonical_document->>'parser_name'=parser_name
      AND canonical_document->>'parser_version'=parser_version
      AND canonical_document->>'ocr_policy_version'=ocr_policy_version
      AND CASE WHEN jsonb_typeof(canonical_document->'pages')='array'
        THEN jsonb_array_length(canonical_document->'pages') BETWEEN 1 AND 500 ELSE FALSE END
      AND jsonb_typeof(canonical_document->'warning_codes')='array')
);

CREATE TABLE public.document_chunks (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL,
    parent_chunk_id UUID,
    pipeline_version VARCHAR(64) NOT NULL,
    ordinal INTEGER NOT NULL,
    page_start INTEGER NOT NULL,
    page_end INTEGER NOT NULL,
    section VARCHAR(255),
    chunk_type VARCHAR(20) NOT NULL,
    retrieval_role VARCHAR(10) NOT NULL,
    raw_content TEXT NOT NULL,
    structured_content JSONB,
    summary TEXT,
    token_count INTEGER NOT NULL,
    source_element_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    bounding_boxes JSONB NOT NULL DEFAULT '[]'::jsonb,
    content_hash CHAR(64) NOT NULL,
    embedding VECTOR(384),
    embedding_model VARCHAR(255),
    embedding_revision VARCHAR(255),
    embedding_status VARCHAR(12) NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT pk_document_chunks PRIMARY KEY (id),
    CONSTRAINT fk_document_chunks_document_id FOREIGN KEY (document_id)
      REFERENCES public.documents(id) ON DELETE CASCADE ON UPDATE NO ACTION,
    CONSTRAINT uq_document_chunks_version_ordinal UNIQUE (document_id,pipeline_version,ordinal),
    CONSTRAINT uq_document_chunks_identity_owner UNIQUE (id,document_id,pipeline_version),
    CONSTRAINT fk_document_chunks_parent_owner FOREIGN KEY (parent_chunk_id,document_id,pipeline_version)
      REFERENCES public.document_chunks(id,document_id,pipeline_version) ON DELETE CASCADE ON UPDATE NO ACTION,
    CONSTRAINT chk_document_chunks_pipeline_version CHECK (length(btrim(pipeline_version)) > 0),
    CONSTRAINT chk_document_chunks_ordinal CHECK (ordinal >= 0),
    CONSTRAINT chk_document_chunks_pages CHECK (page_start >= 1 AND page_end >= page_start),
    CONSTRAINT chk_document_chunks_type CHECK (chunk_type IN ('text','table','header','list','image','unknown')),
    CONSTRAINT chk_document_chunks_retrieval_role CHECK (retrieval_role IN ('parent','child','both')),
    CONSTRAINT chk_document_chunks_content CHECK (length(btrim(raw_content)) > 0),
    CONSTRAINT chk_document_chunks_token_count CHECK (token_count > 0),
    CONSTRAINT chk_document_chunks_source_ids_array CHECK (jsonb_typeof(source_element_ids)='array'),
    CONSTRAINT chk_document_chunks_boxes_array CHECK (jsonb_typeof(bounding_boxes)='array'),
    CONSTRAINT chk_document_chunks_content_hash CHECK (content_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT chk_document_chunks_embedding_status CHECK (embedding_status IN ('pending','completed','failed','not_required')),
    CONSTRAINT chk_document_chunks_embedding_consistency CHECK (
      (embedding_status='completed' AND embedding IS NOT NULL
       AND embedding_model='sentence-transformers/all-MiniLM-L6-v2'
       AND embedding_revision IS NOT NULL AND length(btrim(embedding_revision)) > 0
       AND abs(vector_norm(embedding)-1.0) <= 0.0001)
      OR (embedding_status IN ('pending','failed') AND embedding IS NULL
          AND embedding_model IS NULL AND embedding_revision IS NULL)
      OR (embedding_status='not_required' AND retrieval_role='parent' AND embedding IS NULL
          AND embedding_model IS NULL AND embedding_revision IS NULL)),
    CONSTRAINT chk_document_chunks_parent_not_self CHECK (parent_chunk_id IS NULL OR parent_chunk_id <> id)
);

CREATE TABLE public.extraction_runs (
    id UUID NOT NULL DEFAULT gen_random_uuid(), document_id UUID NOT NULL, job_id UUID NOT NULL,
    status VARCHAR(12) NOT NULL DEFAULT 'running', pipeline_version VARCHAR(64) NOT NULL,
    configuration_hash CHAR(64) NOT NULL, parser_name VARCHAR(100) NOT NULL DEFAULT 'docling',
    parser_version VARCHAR(100) NOT NULL, ocr_policy_version VARCHAR(64) NOT NULL,
    embedding_model VARCHAR(255) NOT NULL DEFAULT 'sentence-transformers/all-MiniLM-L6-v2',
    embedding_revision VARCHAR(255) NOT NULL, embedding_dimension SMALLINT NOT NULL DEFAULT 384,
    llm_provider VARCHAR(100) NOT NULL, llm_model VARCHAR(255) NOT NULL,
    prompt_version VARCHAR(64) NOT NULL,
    schema_version VARCHAR(64) NOT NULL DEFAULT 'commercial-invoice-v1',
    retrieval_config JSONB NOT NULL, warning_codes JSONB NOT NULL DEFAULT '[]'::jsonb,
    input_tokens INTEGER, output_tokens INTEGER, estimated_cost NUMERIC(14,6),
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), finished_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT pk_extraction_runs PRIMARY KEY(id),
    CONSTRAINT fk_extraction_runs_document_id FOREIGN KEY(document_id) REFERENCES public.documents(id) ON DELETE CASCADE ON UPDATE NO ACTION,
    CONSTRAINT fk_extraction_runs_job_id FOREIGN KEY(job_id) REFERENCES public.processing_jobs(id) ON DELETE CASCADE ON UPDATE NO ACTION,
    CONSTRAINT uq_extraction_runs_document_id UNIQUE(document_id),
    CONSTRAINT uq_extraction_runs_job_id UNIQUE(job_id),
    CONSTRAINT chk_extraction_runs_status CHECK(status IN ('running','completed','failed')),
    CONSTRAINT chk_extraction_runs_terminal_time CHECK(
      (status='running' AND finished_at IS NULL) OR
      (status IN ('completed','failed') AND finished_at IS NOT NULL AND finished_at >= started_at)),
    CONSTRAINT chk_extraction_runs_configuration_hash CHECK(configuration_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT chk_extraction_runs_embedding CHECK(
      embedding_model='sentence-transformers/all-MiniLM-L6-v2' AND embedding_dimension=384
      AND length(btrim(embedding_revision)) > 0),
    CONSTRAINT chk_extraction_runs_versions CHECK(
      parser_name='docling' AND schema_version='commercial-invoice-v1'
      AND length(btrim(pipeline_version))>0 AND length(btrim(parser_version))>0
      AND length(btrim(ocr_policy_version))>0 AND length(btrim(llm_provider))>0
      AND length(btrim(llm_model))>0 AND length(btrim(prompt_version))>0),
    CONSTRAINT chk_extraction_runs_retrieval_config CHECK(jsonb_typeof(retrieval_config)='object'),
    CONSTRAINT chk_extraction_runs_warning_codes CHECK(jsonb_typeof(warning_codes)='array'),
    CONSTRAINT chk_extraction_runs_usage CHECK(
      (input_tokens IS NULL OR input_tokens>=0) AND (output_tokens IS NULL OR output_tokens>=0)
      AND (estimated_cost IS NULL OR (estimated_cost <> 'NaN'::numeric AND estimated_cost>=0)))
);

CREATE TABLE public.invoices (
    id UUID NOT NULL DEFAULT gen_random_uuid(), document_id UUID NOT NULL, extraction_run_id UUID NOT NULL,
    invoice_number VARCHAR(100), supplier_name VARCHAR(255), supplier_tax_id VARCHAR(100),
    buyer_name VARCHAR(255), date_issued DATE, due_date DATE, currency CHAR(3),
    subtotal NUMERIC(14,2), tax_amount NUMERIC(14,2), discount_amount NUMERIC(14,2),
    grand_total NUMERIC(14,2), is_math_valid BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT pk_invoices PRIMARY KEY(id),
    CONSTRAINT fk_invoices_document_id FOREIGN KEY(document_id) REFERENCES public.documents(id) ON DELETE CASCADE ON UPDATE NO ACTION,
    CONSTRAINT fk_invoices_extraction_run_id FOREIGN KEY(extraction_run_id) REFERENCES public.extraction_runs(id) ON DELETE CASCADE ON UPDATE NO ACTION,
    CONSTRAINT uq_invoices_document_id UNIQUE(document_id), CONSTRAINT uq_invoices_extraction_run_id UNIQUE(extraction_run_id),
    CONSTRAINT chk_invoices_normalized_strings CHECK(
      (invoice_number IS NULL OR (length(btrim(invoice_number))>0 AND lower(btrim(invoice_number)) NOT IN ('n/a','none','null')))
      AND (supplier_name IS NULL OR length(btrim(supplier_name))>0)
      AND (supplier_tax_id IS NULL OR length(btrim(supplier_tax_id))>0)
      AND (buyer_name IS NULL OR length(btrim(buyer_name))>0)),
    CONSTRAINT chk_invoices_currency CHECK(currency IS NULL OR currency ~ '^[A-Z]{3}$'),
    CONSTRAINT chk_invoices_nonnegative_amounts CHECK(
      (subtotal IS NULL OR (subtotal <> 'NaN'::numeric AND subtotal>=0))
      AND (tax_amount IS NULL OR (tax_amount <> 'NaN'::numeric AND tax_amount>=0))
      AND (discount_amount IS NULL OR (discount_amount <> 'NaN'::numeric AND discount_amount>=0))
      AND (grand_total IS NULL OR (grand_total <> 'NaN'::numeric AND grand_total>=0)))
);

CREATE TABLE public.line_items (
    id UUID NOT NULL DEFAULT gen_random_uuid(), invoice_id UUID NOT NULL,
    source_row_key VARCHAR(128) NOT NULL, line_order INTEGER NOT NULL,
    description TEXT, hs_code VARCHAR(50), quantity NUMERIC(18,4), unit_price NUMERIC(14,4),
    tax_amount NUMERIC(14,2), total_price NUMERIC(14,2),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT pk_line_items PRIMARY KEY(id),
    CONSTRAINT fk_line_items_invoice_id FOREIGN KEY(invoice_id) REFERENCES public.invoices(id) ON DELETE CASCADE ON UPDATE NO ACTION,
    CONSTRAINT uq_line_items_invoice_source UNIQUE(invoice_id,source_row_key),
    CONSTRAINT uq_line_items_invoice_order UNIQUE(invoice_id,line_order),
    CONSTRAINT chk_line_items_source CHECK(length(btrim(source_row_key))>0),
    CONSTRAINT chk_line_items_order CHECK(line_order>0),
    CONSTRAINT chk_line_items_strings CHECK(
      (description IS NULL OR length(btrim(description))>0) AND (hs_code IS NULL OR length(btrim(hs_code))>0)),
    CONSTRAINT chk_line_items_nonnegative CHECK(
      (quantity IS NULL OR (quantity <> 'NaN'::numeric AND quantity>=0))
      AND (unit_price IS NULL OR (unit_price <> 'NaN'::numeric AND unit_price>=0))
      AND (tax_amount IS NULL OR (tax_amount <> 'NaN'::numeric AND tax_amount>=0))
      AND (total_price IS NULL OR (total_price <> 'NaN'::numeric AND total_price>=0)))
);

CREATE TABLE public.field_evidence (
    id UUID NOT NULL DEFAULT gen_random_uuid(), extraction_run_id UUID NOT NULL,
    field_path VARCHAR(255) NOT NULL, source_value TEXT, normalized_value JSONB,
    primary_chunk_id UUID, source_page INTEGER, bounding_box JSONB,
    evidence_excerpt VARCHAR(1000), retrieval_rank SMALLINT, retrieval_score NUMERIC(8,6),
    exact_match BOOLEAN NOT NULL DEFAULT FALSE, confidence_score NUMERIC(5,2) NOT NULL DEFAULT 0.00,
    reason_codes JSONB NOT NULL DEFAULT '[]'::jsonb, validation_state VARCHAR(16) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT pk_field_evidence PRIMARY KEY(id),
    CONSTRAINT fk_field_evidence_extraction_run_id FOREIGN KEY(extraction_run_id) REFERENCES public.extraction_runs(id) ON DELETE CASCADE ON UPDATE NO ACTION,
    CONSTRAINT fk_field_evidence_primary_chunk_id FOREIGN KEY(primary_chunk_id) REFERENCES public.document_chunks(id) ON DELETE SET NULL ON UPDATE NO ACTION,
    CONSTRAINT uq_field_evidence_run_path UNIQUE(extraction_run_id,field_path),
    CONSTRAINT chk_field_evidence_path CHECK(length(btrim(field_path))>0),
    CONSTRAINT chk_field_evidence_positions CHECK((source_page IS NULL OR source_page>0) AND (retrieval_rank IS NULL OR retrieval_rank>0)),
    CONSTRAINT chk_field_evidence_confidence CHECK(confidence_score <> 'NaN'::numeric AND confidence_score BETWEEN 0 AND 100),
    CONSTRAINT chk_field_evidence_retrieval CHECK(retrieval_score IS NULL OR (retrieval_score <> 'NaN'::numeric AND retrieval_score BETWEEN -1 AND 1)),
    CONSTRAINT chk_field_evidence_box CHECK(bounding_box IS NULL OR jsonb_typeof(bounding_box)='object'),
    CONSTRAINT chk_field_evidence_reason_codes CHECK(jsonb_typeof(reason_codes)='array'),
    CONSTRAINT chk_field_evidence_state CHECK(validation_state IN ('valid','invalid','missing','ambiguous','unsupported')),
    CONSTRAINT chk_field_evidence_state_consistency CHECK(
      (validation_state='valid' AND primary_chunk_id IS NOT NULL)
      OR (validation_state IN ('missing','unsupported') AND source_value IS NULL AND normalized_value IS NULL
          AND primary_chunk_id IS NULL AND source_page IS NULL AND bounding_box IS NULL
          AND evidence_excerpt IS NULL AND exact_match=FALSE AND confidence_score=0)
      OR validation_state IN ('invalid','ambiguous'))
);

CREATE TABLE public.validation_results (
    id UUID NOT NULL DEFAULT gen_random_uuid(), extraction_run_id UUID NOT NULL,
    rule_id VARCHAR(64) NOT NULL, scope_key VARCHAR(255) NOT NULL DEFAULT 'document',
    status VARCHAR(16) NOT NULL, observed_value JSONB, expected_value JSONB,
    difference NUMERIC(18,6), epsilon NUMERIC(8,6), message_code VARCHAR(100) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT pk_validation_results PRIMARY KEY(id),
    CONSTRAINT fk_validation_results_extraction_run_id FOREIGN KEY(extraction_run_id) REFERENCES public.extraction_runs(id) ON DELETE CASCADE ON UPDATE NO ACTION,
    CONSTRAINT uq_validation_results_run_rule_scope UNIQUE(extraction_run_id,rule_id,scope_key),
    CONSTRAINT chk_validation_results_strings CHECK(length(btrim(rule_id))>0 AND length(btrim(scope_key))>0 AND length(btrim(message_code))>0),
    CONSTRAINT chk_validation_results_status CHECK(status IN ('passed','failed','missing','not_applicable')),
    CONSTRAINT chk_validation_results_nonnegative CHECK(
      (difference IS NULL OR (difference <> 'NaN'::numeric AND difference>=0))
      AND (epsilon IS NULL OR (epsilon <> 'NaN'::numeric AND epsilon>=0))),
    CONSTRAINT chk_validation_results_financial_epsilon CHECK(rule_id NOT LIKE 'BR-03%' OR epsilon=0.050000),
    CONSTRAINT chk_validation_results_comparison CHECK(
      difference IS NULL OR epsilon IS NULL OR status NOT IN ('passed','failed')
      OR (status='passed' AND difference<=epsilon) OR (status='failed' AND difference>epsilon))
);

CREATE FUNCTION public.validate_document_partition_owner_fence() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $fn$
DECLARE
  document_company uuid; job_document uuid; job_status text; job_stage text;
  job_attempt smallint; job_lease timestamptz;
BEGIN
  SELECT company_id INTO document_company FROM public.documents
    WHERE id=NEW.document_id FOR SHARE;
  SELECT document_id,status,current_stage,attempt_count,lease_expires_at
    INTO job_document,job_status,job_stage,job_attempt,job_lease
    FROM public.processing_jobs WHERE id=NEW.job_id FOR SHARE;
  IF document_company IS DISTINCT FROM NEW.company_id
     OR job_document IS DISTINCT FROM NEW.document_id THEN
    RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='chk_document_partitions_owner',
      MESSAGE='Partition company, document, and job ownership must match';
  END IF;
  IF job_status IS DISTINCT FROM 'processing' OR job_stage IS DISTINCT FROM 'partitioning'
     OR job_attempt IS DISTINCT FROM NEW.created_attempt
     OR job_lease IS NULL OR job_lease<=clock_timestamp() THEN
    RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='chk_document_partitions_fence',
      MESSAGE='Partition write requires the current unexpired partitioning attempt';
  END IF;
  NEW.content_hash := encode(public.digest(convert_to(NEW.canonical_document::text,'UTF8'),'sha256'),'hex');
  RETURN NEW;
END $fn$;

CREATE FUNCTION public.enforce_document_partition_immutability() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $fn$
BEGIN
  IF TG_OP='DELETE' THEN
    IF pg_trigger_depth()>1 THEN RETURN OLD; END IF;
    RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='chk_document_partitions_delete',
      MESSAGE='Direct canonical partition deletion is not authorized';
  END IF;
  IF ROW(NEW.id,NEW.company_id,NEW.document_id,NEW.job_id,NEW.created_attempt,
         NEW.pipeline_version,NEW.configuration_hash,NEW.parser_name,NEW.parser_version,
         NEW.ocr_policy_version,NEW.canonical_document,NEW.content_hash,NEW.created_at)
     IS DISTINCT FROM
     ROW(OLD.id,OLD.company_id,OLD.document_id,OLD.job_id,OLD.created_attempt,
         OLD.pipeline_version,OLD.configuration_hash,OLD.parser_name,OLD.parser_version,
         OLD.ocr_policy_version,OLD.canonical_document,OLD.content_hash,OLD.created_at) THEN
    RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='chk_document_partitions_immutable',
      MESSAGE='Canonical partition facts are immutable';
  END IF;
  RETURN OLD;
END $fn$;

CREATE FUNCTION public.validate_document_chunk_hierarchy() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $fn$
BEGIN
  PERFORM pg_advisory_xact_lock(hashtextextended('rag-chunk-hierarchy:'||NEW.document_id::text,0));
  IF NEW.parent_chunk_id IS NULL THEN RETURN NEW; END IF;
  IF EXISTS (
    WITH RECURSIVE ancestors(id,parent_chunk_id) AS (
      SELECT id,parent_chunk_id FROM public.document_chunks WHERE id=NEW.parent_chunk_id
      UNION ALL SELECT c.id,c.parent_chunk_id FROM public.document_chunks c JOIN ancestors a ON c.id=a.parent_chunk_id)
    SELECT 1 FROM ancestors WHERE id=NEW.id
  ) THEN RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='chk_document_chunks_hierarchy', MESSAGE='Chunk hierarchy must be acyclic'; END IF;
  RETURN NEW;
END $fn$;

CREATE FUNCTION public.enforce_document_chunk_immutability() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $fn$
BEGIN
  IF OLD.embedding_status='completed' THEN
    RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='chk_document_chunks_completed_immutable',
      MESSAGE='Completed document chunks are immutable';
  END IF;
  IF ROW(NEW.id,NEW.document_id,NEW.parent_chunk_id,NEW.pipeline_version,NEW.ordinal,
         NEW.page_start,NEW.page_end,NEW.section,NEW.chunk_type,NEW.retrieval_role,
         NEW.raw_content,NEW.structured_content,NEW.summary,NEW.token_count,
         NEW.source_element_ids,NEW.bounding_boxes,NEW.content_hash,NEW.created_at)
     IS DISTINCT FROM
     ROW(OLD.id,OLD.document_id,OLD.parent_chunk_id,OLD.pipeline_version,OLD.ordinal,
         OLD.page_start,OLD.page_end,OLD.section,OLD.chunk_type,OLD.retrieval_role,
         OLD.raw_content,OLD.structured_content,OLD.summary,OLD.token_count,
         OLD.source_element_ids,OLD.bounding_boxes,OLD.content_hash,OLD.created_at) THEN
    RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='chk_document_chunks_source_immutable',
      MESSAGE='Document chunk identity and source content are immutable';
  END IF;
  RETURN NEW;
END $fn$;

CREATE FUNCTION public.validate_extraction_run_pair() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $fn$
DECLARE job_document uuid;
BEGIN
  PERFORM 1 FROM public.documents WHERE id=NEW.document_id FOR SHARE;
  SELECT document_id INTO job_document FROM public.processing_jobs WHERE id=NEW.job_id FOR SHARE;
  IF FOUND AND job_document IS DISTINCT FROM NEW.document_id THEN
    RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='chk_extraction_runs_job_document', MESSAGE='Run job must belong to run document';
  END IF;
  RETURN NEW;
END $fn$;

CREATE FUNCTION public.enforce_extraction_run_immutability() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $fn$
BEGIN
  IF OLD.status IN ('completed','failed') OR ROW(NEW.id,NEW.document_id,NEW.job_id,NEW.pipeline_version,
      NEW.configuration_hash,NEW.parser_name,NEW.parser_version,NEW.ocr_policy_version,NEW.embedding_model,
      NEW.embedding_revision,NEW.embedding_dimension,NEW.llm_provider,NEW.llm_model,NEW.prompt_version,
      NEW.schema_version,NEW.retrieval_config,NEW.started_at,NEW.created_at)
    IS DISTINCT FROM ROW(OLD.id,OLD.document_id,OLD.job_id,OLD.pipeline_version,
      OLD.configuration_hash,OLD.parser_name,OLD.parser_version,OLD.ocr_policy_version,OLD.embedding_model,
      OLD.embedding_revision,OLD.embedding_dimension,OLD.llm_provider,OLD.llm_model,OLD.prompt_version,
      OLD.schema_version,OLD.retrieval_config,OLD.started_at,OLD.created_at) THEN
    RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='chk_extraction_runs_immutable', MESSAGE='Run identity and provenance are immutable';
  END IF;
  RETURN NEW;
END $fn$;

CREATE FUNCTION public.validate_invoice_run_pair() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $fn$
DECLARE run_document uuid;
BEGIN
  SELECT document_id INTO run_document FROM public.extraction_runs WHERE id=NEW.extraction_run_id FOR SHARE;
  IF FOUND AND run_document IS DISTINCT FROM NEW.document_id THEN
    RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='chk_invoices_run_document', MESSAGE='Invoice run must belong to invoice document';
  END IF;
  RETURN NEW;
END $fn$;

CREATE FUNCTION public.enforce_invoice_initial_immutability() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $fn$
BEGIN
  IF pg_trigger_depth()>1 THEN
    IF TG_OP='DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
  END IF;
  RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='chk_invoices_immutable', MESSAGE='Initial extracted invoice is immutable';
END $fn$;

CREATE FUNCTION public.enforce_line_item_identity_immutability() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $fn$
BEGIN
  IF TG_OP='DELETE' THEN
    IF pg_trigger_depth()>1 THEN RETURN OLD; END IF;
    RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='chk_line_items_delete', MESSAGE='Direct line item deletion is not authorized';
  END IF;
  IF ROW(NEW.id,NEW.invoice_id,NEW.source_row_key,NEW.line_order,NEW.created_at)
     IS DISTINCT FROM ROW(OLD.id,OLD.invoice_id,OLD.source_row_key,OLD.line_order,OLD.created_at) THEN
    RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='chk_line_items_identity_immutable', MESSAGE='Line item identity is immutable';
  END IF;
  RETURN NEW;
END $fn$;

CREATE FUNCTION public.validate_field_evidence_owner() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $fn$
DECLARE run_document uuid; run_version text; chunk_document uuid; chunk_version text;
BEGIN
  IF NEW.primary_chunk_id IS NULL THEN RETURN NEW; END IF;
  SELECT document_id,pipeline_version INTO run_document,run_version FROM public.extraction_runs WHERE id=NEW.extraction_run_id FOR SHARE;
  SELECT document_id,pipeline_version INTO chunk_document,chunk_version FROM public.document_chunks WHERE id=NEW.primary_chunk_id FOR SHARE;
  IF run_document IS DISTINCT FROM chunk_document OR run_version IS DISTINCT FROM chunk_version THEN
    RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='chk_field_evidence_owner', MESSAGE='Evidence chunk must match run document and pipeline';
  END IF;
  RETURN NEW;
END $fn$;

CREATE FUNCTION public.enforce_result_immutability() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $fn$
BEGIN
  IF pg_trigger_depth()>1 THEN
    IF TG_OP='DELETE' THEN
      RETURN OLD;
    END IF;
    IF TG_TABLE_NAME='field_evidence'
       AND TG_OP='UPDATE'
       AND OLD.primary_chunk_id IS NOT NULL
       AND NEW.primary_chunk_id IS NULL THEN
      NEW.source_value=NULL;
      NEW.normalized_value=NULL;
      NEW.source_page=NULL;
      NEW.bounding_box=NULL;
      NEW.evidence_excerpt=NULL;
      NEW.retrieval_rank=NULL;
      NEW.retrieval_score=NULL;
      NEW.exact_match=FALSE;
      NEW.confidence_score=0;
      NEW.reason_codes='["PRIMARY_CHUNK_DELETED"]'::jsonb;
      NEW.validation_state='missing';
    END IF;
    RETURN NEW;
  END IF;
  RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='chk_result_immutable', MESSAGE='Extraction result fact is immutable';
END $fn$;

CREATE TRIGGER trg_document_partitions_owner_fence BEFORE INSERT ON public.document_partitions FOR EACH ROW EXECUTE FUNCTION public.validate_document_partition_owner_fence();
CREATE TRIGGER trg_document_partitions_immutable BEFORE UPDATE OR DELETE ON public.document_partitions FOR EACH ROW EXECUTE FUNCTION public.enforce_document_partition_immutability();
CREATE TRIGGER trg_document_chunks_hierarchy BEFORE INSERT OR UPDATE OF parent_chunk_id,document_id,pipeline_version ON public.document_chunks FOR EACH ROW EXECUTE FUNCTION public.validate_document_chunk_hierarchy();
CREATE TRIGGER trg_document_chunks_immutable BEFORE UPDATE ON public.document_chunks FOR EACH ROW EXECUTE FUNCTION public.enforce_document_chunk_immutability();
CREATE TRIGGER trg_document_chunks_updated_at BEFORE UPDATE ON public.document_chunks FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
CREATE TRIGGER trg_extraction_runs_pair BEFORE INSERT OR UPDATE OF document_id,job_id ON public.extraction_runs FOR EACH ROW EXECUTE FUNCTION public.validate_extraction_run_pair();
CREATE TRIGGER trg_extraction_runs_immutable BEFORE UPDATE ON public.extraction_runs FOR EACH ROW EXECUTE FUNCTION public.enforce_extraction_run_immutability();
CREATE TRIGGER trg_extraction_runs_updated_at BEFORE UPDATE ON public.extraction_runs FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
CREATE TRIGGER trg_invoices_run_pair BEFORE INSERT OR UPDATE OF document_id,extraction_run_id ON public.invoices FOR EACH ROW EXECUTE FUNCTION public.validate_invoice_run_pair();
CREATE TRIGGER trg_invoices_immutable BEFORE UPDATE OR DELETE ON public.invoices FOR EACH ROW EXECUTE FUNCTION public.enforce_invoice_initial_immutability();
CREATE TRIGGER trg_invoices_updated_at BEFORE UPDATE ON public.invoices FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
CREATE TRIGGER trg_line_items_identity_immutable BEFORE UPDATE OR DELETE ON public.line_items FOR EACH ROW EXECUTE FUNCTION public.enforce_line_item_identity_immutability();
CREATE TRIGGER trg_line_items_updated_at BEFORE UPDATE ON public.line_items FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
CREATE TRIGGER trg_field_evidence_owner BEFORE INSERT OR UPDATE OF extraction_run_id,primary_chunk_id ON public.field_evidence FOR EACH ROW EXECUTE FUNCTION public.validate_field_evidence_owner();
CREATE TRIGGER trg_field_evidence_immutable BEFORE UPDATE OR DELETE ON public.field_evidence FOR EACH ROW EXECUTE FUNCTION public.enforce_result_immutability();
CREATE TRIGGER trg_validation_results_immutable BEFORE UPDATE OR DELETE ON public.validation_results FOR EACH ROW EXECUTE FUNCTION public.enforce_result_immutability();

CREATE INDEX idx_document_partitions_company_id ON public.document_partitions(company_id);
CREATE INDEX idx_document_chunks_document_type_page ON public.document_chunks(document_id,chunk_type,page_start,ordinal);
CREATE INDEX idx_document_chunks_parent ON public.document_chunks(parent_chunk_id,ordinal);
CREATE INDEX idx_document_chunks_embedding_ready ON public.document_chunks(document_id,ordinal)
  WHERE embedding_status='completed' AND embedding IS NOT NULL;
CREATE INDEX idx_invoices_number ON public.invoices(invoice_number) WHERE invoice_number IS NOT NULL;
CREATE INDEX idx_field_evidence_primary_chunk ON public.field_evidence(primary_chunk_id) WHERE primary_chunk_id IS NOT NULL;
CREATE INDEX idx_field_evidence_state ON public.field_evidence(extraction_run_id,validation_state,confidence_score);

DO $verify$
BEGIN
  IF (SELECT count(*) FROM information_schema.columns WHERE table_schema='public' AND table_name IN
      ('document_partitions','document_chunks','extraction_runs','invoices','line_items','field_evidence','validation_results')) <> 117 THEN
    RAISE EXCEPTION 'RAG column inventory verification failed';
  END IF;
  IF format_type((SELECT atttypid FROM pg_attribute WHERE attrelid='public.document_chunks'::regclass AND attname='embedding'),
                 (SELECT atttypmod FROM pg_attribute WHERE attrelid='public.document_chunks'::regclass AND attname='embedding')) <> 'vector(384)' THEN
    RAISE EXCEPTION 'RAG vector dimension verification failed';
  END IF;
  IF (SELECT count(*) FROM pg_trigger WHERE tgrelid IN (
      'public.document_partitions'::regclass,'public.document_chunks'::regclass,'public.extraction_runs'::regclass,'public.invoices'::regclass,
      'public.line_items'::regclass,'public.field_evidence'::regclass,'public.validation_results'::regclass)
      AND NOT tgisinternal) <> 16 THEN RAISE EXCEPTION 'RAG trigger inventory verification failed'; END IF;
  IF EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname='public' AND tablename='document_chunks'
             AND indexdef ~* 'using (hnsw|ivfflat|gin)') THEN RAISE EXCEPTION 'Unapproved RAG index detected'; END IF;
END $verify$;
-- END DOCUMENT PROCESSING RAG UPGRADE
COMMIT;
