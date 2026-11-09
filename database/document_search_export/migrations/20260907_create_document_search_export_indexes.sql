-- Stage 03 online-index build. Canonical entry point: accompanying Alembic revision.
-- Every CREATE INDEX CONCURRENTLY must run outside a transaction block.
-- Requires exact core revision 20260907_0005. Does NOT stamp Alembic.

SET search_path = pg_catalog, public;
SET lock_timeout = '5s';
SET statement_timeout = '30min';

DO $preflight$
DECLARE heads text[];
BEGIN
  SELECT array_agg(version_num::text ORDER BY version_num) INTO heads
  FROM public.alembic_version;
  IF heads IS DISTINCT FROM ARRAY['20260907_0005']::text[] THEN
    RAISE EXCEPTION 'Expected exactly document-search-export core revision 20260907_0005';
  END IF;
  IF to_regclass('public.export_jobs') IS NULL
     OR to_regclass('public.export_job_documents') IS NULL THEN
    RAISE EXCEPTION 'Verified Feature 05 core catalog is required';
  END IF;
  -- The Alembic runner compares any canonical named index with its exact
  -- reviewed definition and resumes past a valid one after an interrupted run.
  -- A differently named equivalent remains a reconciliation failure here.
  IF EXISTS (
    SELECT 1 FROM pg_indexes
    WHERE schemaname='public' AND indexname<>ALL(ARRAY[
      'idx_documents_company_search','idx_invoices_date_document',
      'idx_invoices_currency_date_document','idx_invoices_total_document',
      'idx_document_chunks_embedding_compat'])
      AND (
        regexp_replace(indexdef,'\s+',' ','g') LIKE '% ON public.documents USING btree (company_id, status, doc_type, created_at, id)%'
        OR regexp_replace(indexdef,'\s+',' ','g') LIKE '% ON public.invoices USING btree (date_issued, document_id)%'
        OR regexp_replace(indexdef,'\s+',' ','g') LIKE '% ON public.invoices USING btree (currency, date_issued, document_id)%'
        OR regexp_replace(indexdef,'\s+',' ','g') LIKE '% ON public.invoices USING btree (grand_total, document_id)%'
        OR regexp_replace(indexdef,'\s+',' ','g') LIKE '% ON public.document_chunks USING btree (embedding_model, embedding_revision, document_id, ordinal) WHERE%'
      )
  ) THEN
    RAISE EXCEPTION 'Equivalent existing index requires reviewed reconciliation';
  END IF;
END;
$preflight$;

CREATE INDEX CONCURRENTLY idx_documents_company_search
  ON public.documents(company_id,status,doc_type,created_at,id);
CREATE INDEX CONCURRENTLY idx_invoices_date_document
  ON public.invoices(date_issued,document_id);
CREATE INDEX CONCURRENTLY idx_invoices_currency_date_document
  ON public.invoices(currency,date_issued,document_id);
CREATE INDEX CONCURRENTLY idx_invoices_total_document
  ON public.invoices(grand_total,document_id);
CREATE INDEX CONCURRENTLY idx_document_chunks_embedding_compat
  ON public.document_chunks(embedding_model,embedding_revision,document_id,ordinal)
  WHERE embedding_status='completed' AND embedding IS NOT NULL
    AND retrieval_role IN ('child','both');
