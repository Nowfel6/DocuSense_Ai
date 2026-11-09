-- Stage 03 build. Canonical entry point: accompanying Alembic revision.
-- Standalone alternative: psql -X -v ON_ERROR_STOP=1 -f this-file.sql.
-- Requires verified auth revision 20260901_0001. Does NOT stamp Alembic.
BEGIN;
-- BEGIN DOCUMENT INGESTION UPGRADE
SET LOCAL search_path = pg_catalog, public;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';

DO $preflight$
DECLARE
    parent_name text;
    helper_body text;
BEGIN
    IF current_setting('server_version_num')::integer < 150000 THEN
        RAISE EXCEPTION 'Document ingestion requires PostgreSQL 15 or newer';
    END IF;
    IF to_regclass('public.alembic_version') IS NULL THEN
        RAISE EXCEPTION 'Verified Alembic predecessor is required; do not stamp blindly';
    END IF;
    IF (SELECT array_agg(version_num::text ORDER BY version_num)
        FROM public.alembic_version) IS DISTINCT FROM ARRAY['20260901_0001']::text[] THEN
        RAISE EXCEPTION 'Expected exactly auth revision 20260901_0001';
    END IF;
    FOREACH parent_name IN ARRAY ARRAY['companies', 'users'] LOOP
        IF NOT EXISTS (
            SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            JOIN pg_attribute a ON a.attrelid = c.oid AND a.attname = 'id'
            JOIN pg_constraint k ON k.conrelid = c.oid AND k.contype = 'p'
            WHERE n.nspname = 'public' AND c.relname = parent_name AND c.relkind = 'r'
              AND a.atttypid = 'uuid'::regtype AND a.attnotnull
              AND k.conkey = ARRAY[a.attnum]::smallint[]
        ) THEN
            RAISE EXCEPTION 'Auth parent relation or UUID primary key is incompatible';
        END IF;
        IF NOT has_table_privilege('public.' || parent_name, 'REFERENCES') THEN
            RAISE EXCEPTION 'REFERENCES privilege on auth parents is required';
        END IF;
    END LOOP;
    IF NOT EXISTS (
        SELECT 1 FROM pg_attribute a JOIN pg_constraint k
          ON k.conrelid = a.attrelid AND k.conkey = ARRAY[a.attnum]::smallint[]
        JOIN pg_attribute p ON p.attrelid = k.confrelid AND p.attname = 'id'
        WHERE a.attrelid = 'public.users'::regclass AND a.attname = 'company_id'
          AND a.atttypid = 'uuid'::regtype AND a.attnotnull
          AND k.contype = 'f' AND k.confrelid = 'public.companies'::regclass
          AND k.confkey = ARRAY[p.attnum]::smallint[] AND k.confdeltype = 'c'
          AND k.confupdtype = 'a' AND NOT k.condeferrable
    ) THEN
        RAISE EXCEPTION 'Auth user ownership relationship is incompatible';
    END IF;
    IF to_regprocedure('gen_random_uuid()') IS NULL
       OR NOT has_schema_privilege('public', 'CREATE') THEN
        RAISE EXCEPTION 'UUID generator and schema CREATE privilege are required';
    END IF;
    SELECT regexp_replace(lower(p.prosrc), '[[:space:]]', '', 'g') INTO helper_body
    FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
    JOIN pg_language l ON l.oid = p.prolang
    WHERE n.nspname = 'public' AND p.proname = 'update_updated_at_column'
      AND p.pronargs = 0 AND p.prorettype = 'trigger'::regtype
      AND l.lanname = 'plpgsql' AND NOT p.prosecdef;
    IF helper_body IS DISTINCT FROM 'beginnew.updated_at=now();returnnew;end;' THEN
        RAISE EXCEPTION 'Shared timestamp helper differs from verified auth migration';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relname = ANY (ARRAY[
            'documents', 'processing_jobs', 'pk_documents', 'pk_processing_jobs',
            'idx_documents_company_id', 'idx_documents_uploaded_by', 'idx_documents_status',
            'idx_documents_file_hash', 'idx_documents_company_created',
            'idx_documents_company_status_created', 'uq_processing_jobs_document_id',
            'idx_processing_jobs_dispatch', 'idx_processing_jobs_lease'])
    ) OR EXISTS (
        SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'public' AND p.proname = ANY (ARRAY[
            'validate_document_uploader_tenant', 'enforce_document_identity_immutable',
            'enforce_processing_job_identity_immutable'])
    ) OR EXISTS (
        SELECT 1 FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND t.tgname = ANY (ARRAY[
            'trg_documents_updated_at', 'trg_processing_jobs_updated_at',
            'trg_documents_uploader_tenant', 'trg_documents_identity_immutable',
            'trg_processing_jobs_identity_immutable'])
    ) THEN
        RAISE EXCEPTION 'Document ingestion object collision; reconcile instead of skipping DDL';
    END IF;
END;
$preflight$;

CREATE TABLE public.documents (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL,
    uploaded_by UUID,
    file_name VARCHAR(255) NOT NULL,
    s3_url TEXT NOT NULL,
    file_size_bytes INTEGER NOT NULL,
    file_hash VARCHAR(64) NOT NULL,
    mime_type VARCHAR(127) NOT NULL,
    doc_type VARCHAR(50) NOT NULL DEFAULT 'commercial_invoice',
    status VARCHAR(30) NOT NULL DEFAULT 'queued',
    overall_confidence NUMERIC(5,2),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT pk_documents PRIMARY KEY (id),
    CONSTRAINT fk_documents_company_id FOREIGN KEY (company_id)
        REFERENCES public.companies(id) ON DELETE CASCADE ON UPDATE NO ACTION,
    CONSTRAINT fk_documents_uploaded_by FOREIGN KEY (uploaded_by)
        REFERENCES public.users(id) ON DELETE SET NULL ON UPDATE NO ACTION,
    CONSTRAINT chk_documents_file_name CHECK (
        length(btrim(file_name)) > 0 AND file_name NOT IN ('.', '..')
        AND position('/' in file_name) = 0 AND position(chr(92) in file_name) = 0
        AND file_name !~ '[[:cntrl:]]'),
    CONSTRAINT chk_documents_s3_url CHECK (
        s3_url ~ ('^s3://[a-z0-9][a-z0-9.-]*/' || company_id::text || '/' || id::text || '/[^/?#]+$')
        AND s3_url !~ '[[:cntrl:]]' AND position(chr(92) in s3_url) = 0),
    CONSTRAINT chk_documents_file_size CHECK (file_size_bytes BETWEEN 1 AND 10485760),
    CONSTRAINT chk_documents_file_hash CHECK (file_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT chk_documents_mime_type CHECK (mime_type IN ('application/pdf', 'image/png', 'image/jpeg')),
    CONSTRAINT chk_documents_doc_type CHECK (doc_type IN ('commercial_invoice', 'purchase_order', 'packing_list')),
    CONSTRAINT chk_documents_status CHECK (status IN (
        'queued', 'partitioning', 'chunking', 'vectorizing', 'extracting',
        'pending_review', 'approved', 'rejected', 'failed')),
    CONSTRAINT chk_documents_confidence CHECK (
        overall_confidence IS NULL OR
        (overall_confidence <> 'NaN'::numeric AND overall_confidence BETWEEN 0.00 AND 100.00))
);

CREATE TABLE public.processing_jobs (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'queued',
    current_stage VARCHAR(30) NOT NULL DEFAULT 'upload',
    progress_percentage SMALLINT NOT NULL DEFAULT 0,
    attempt_count SMALLINT NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ,
    lease_expires_at TIMESTAMPTZ,
    error_code VARCHAR(100),
    error_message TEXT,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT pk_processing_jobs PRIMARY KEY (id),
    CONSTRAINT fk_processing_jobs_document_id FOREIGN KEY (document_id)
        REFERENCES public.documents(id) ON DELETE CASCADE ON UPDATE NO ACTION,
    CONSTRAINT uq_processing_jobs_document_id UNIQUE (document_id),
    CONSTRAINT chk_processing_jobs_status CHECK (status IN ('queued', 'processing', 'completed', 'failed')),
    CONSTRAINT chk_processing_jobs_stage CHECK (current_stage IN ('upload', 'partitioning', 'chunking', 'vectorizing', 'extracting')),
    CONSTRAINT chk_processing_jobs_progress CHECK (progress_percentage BETWEEN 0 AND 100),
    CONSTRAINT chk_processing_jobs_attempts CHECK (attempt_count BETWEEN 0 AND 4),
    CONSTRAINT chk_processing_jobs_completion CHECK (
        status <> 'completed' OR (progress_percentage = 100 AND finished_at IS NOT NULL)),
    CONSTRAINT chk_processing_jobs_failure CHECK (
        status <> 'failed' OR (finished_at IS NOT NULL AND error_code IS NOT NULL AND length(btrim(error_code)) > 0)),
    CONSTRAINT chk_processing_jobs_nonterminal_finish CHECK (
        status IN ('completed', 'failed') OR finished_at IS NULL),
    CONSTRAINT chk_processing_jobs_terminal_cleanup CHECK (
        status NOT IN ('completed', 'failed') OR (lease_expires_at IS NULL AND next_attempt_at IS NULL))
);

CREATE FUNCTION public.validate_document_uploader_tenant()
RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER
SET search_path = pg_catalog, public AS $function$
DECLARE uploader_company uuid;
BEGIN
    IF NEW.uploaded_by IS NULL THEN RETURN NEW; END IF;
    SELECT company_id INTO uploader_company FROM public.users
    WHERE id = NEW.uploaded_by FOR SHARE;
    IF FOUND AND uploader_company IS DISTINCT FROM NEW.company_id THEN
        RAISE EXCEPTION USING ERRCODE = '23514',
            CONSTRAINT = 'chk_documents_uploader_tenant',
            MESSAGE = 'Document uploader must belong to the document tenant';
    END IF;
    RETURN NEW;
END;
$function$;

CREATE FUNCTION public.enforce_document_identity_immutable()
RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER
SET search_path = pg_catalog, public AS $function$
BEGIN
    IF ROW(NEW.id, NEW.company_id, NEW.file_name, NEW.s3_url, NEW.file_size_bytes,
           NEW.file_hash, NEW.mime_type, NEW.doc_type, NEW.created_at)
       IS DISTINCT FROM
       ROW(OLD.id, OLD.company_id, OLD.file_name, OLD.s3_url, OLD.file_size_bytes,
           OLD.file_hash, OLD.mime_type, OLD.doc_type, OLD.created_at) THEN
        RAISE EXCEPTION USING ERRCODE = '23514',
            CONSTRAINT = 'chk_documents_identity_immutable',
            MESSAGE = 'Document identity and original file metadata are immutable';
    END IF;
    RETURN NEW;
END;
$function$;

CREATE FUNCTION public.enforce_processing_job_identity_immutable()
RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER
SET search_path = pg_catalog, public AS $function$
BEGIN
    IF ROW(NEW.id, NEW.document_id, NEW.created_at)
       IS DISTINCT FROM ROW(OLD.id, OLD.document_id, OLD.created_at) THEN
        RAISE EXCEPTION USING ERRCODE = '23514',
            CONSTRAINT = 'chk_processing_jobs_identity_immutable',
            MESSAGE = 'Processing job identity is immutable';
    END IF;
    RETURN NEW;
END;
$function$;

CREATE TRIGGER trg_documents_updated_at BEFORE UPDATE ON public.documents
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
CREATE TRIGGER trg_processing_jobs_updated_at BEFORE UPDATE ON public.processing_jobs
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
CREATE TRIGGER trg_documents_uploader_tenant
    BEFORE INSERT OR UPDATE OF uploaded_by, company_id ON public.documents
    FOR EACH ROW EXECUTE FUNCTION public.validate_document_uploader_tenant();
CREATE TRIGGER trg_documents_identity_immutable BEFORE UPDATE ON public.documents
    FOR EACH ROW EXECUTE FUNCTION public.enforce_document_identity_immutable();
CREATE TRIGGER trg_processing_jobs_identity_immutable BEFORE UPDATE ON public.processing_jobs
    FOR EACH ROW EXECUTE FUNCTION public.enforce_processing_job_identity_immutable();

CREATE INDEX idx_documents_company_id ON public.documents (company_id);
CREATE INDEX idx_documents_uploaded_by ON public.documents (uploaded_by);
CREATE INDEX idx_documents_status ON public.documents (status);
CREATE INDEX idx_documents_file_hash ON public.documents (company_id, file_hash);
CREATE INDEX idx_documents_company_created ON public.documents (company_id, created_at DESC, id DESC);
CREATE INDEX idx_documents_company_status_created ON public.documents (company_id, status, created_at DESC, id DESC);
CREATE INDEX idx_processing_jobs_dispatch ON public.processing_jobs (status, next_attempt_at ASC NULLS FIRST, created_at);
CREATE INDEX idx_processing_jobs_lease ON public.processing_jobs (status, lease_expires_at);

DO $verify$
BEGIN
    IF (SELECT count(*) FROM information_schema.columns WHERE table_schema = 'public'
        AND table_name IN ('documents', 'processing_jobs')) <> 27
       OR (SELECT count(*) FROM pg_indexes WHERE schemaname = 'public'
           AND tablename IN ('documents', 'processing_jobs')) <> 11
       OR (SELECT count(*) FROM pg_trigger WHERE tgrelid IN
           ('public.documents'::regclass, 'public.processing_jobs'::regclass) AND NOT tgisinternal) <> 5
       OR (SELECT count(*) FROM pg_constraint WHERE conrelid IN
           ('public.documents'::regclass, 'public.processing_jobs'::regclass)
           AND contype IN ('p', 'f', 'u', 'c')) <> 22 THEN
        RAISE EXCEPTION 'Document ingestion catalog verification failed';
    END IF;
END;
$verify$;
-- END DOCUMENT INGESTION UPGRADE
COMMIT;
