-- Execute within the Python loader's transaction. Not an unguarded psql seed.
-- The loader validates real assets and supplies transaction-local JSON payload.
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';
DO $seed$
DECLARE
    payload jsonb := current_setting('docusense.ingestion_seed_payload', true)::jsonb;
    asset jsonb;
    expected_doc public.documents%ROWTYPE;
    expected_job public.processing_jobs%ROWTYPE;
    actual_doc public.documents%ROWTYPE;
    actual_job public.processing_jobs%ROWTYPE;
    doc_exists boolean;
    job_exists boolean;
BEGIN
    IF current_database() !~ '^docusense_ingestion_test_[a-z0-9_]+$'
       OR current_setting('docusense.disposable_database', true) IS DISTINCT FROM current_database()
       OR current_setting('docusense.no_active_consumers', true) IS DISTINCT FROM 'confirmed' THEN
        RAISE EXCEPTION 'Seeder requires a confirmed disposable database without active consumers';
    END IF;
    IF (SELECT array_agg(version_num::text) FROM public.alembic_version)
       IS DISTINCT FROM ARRAY['20260903_0002']::text[] THEN
        RAISE EXCEPTION 'Seeder requires canonical document ingestion revision 20260903_0002';
    END IF;
    IF payload IS NULL OR payload->>'scope' IS DISTINCT FROM 'DATABASE_ONLY'
       OR jsonb_array_length(payload->'documents') IS DISTINCT FROM 6
       OR jsonb_array_length(payload->'jobs') IS DISTINCT FROM 6
       OR jsonb_array_length(payload->'files') IS DISTINCT FROM 4 THEN
        RAISE EXCEPTION 'Missing or invalid validated fixture payload';
    END IF;
    FOR asset IN SELECT value FROM jsonb_array_elements(payload->'files') LOOP
        IF encode(public.digest(decode(asset->>'bytes_base64', 'base64'), 'sha256'), 'hex')
             IS DISTINCT FROM asset->>'file_hash'
           OR octet_length(decode(asset->>'bytes_base64', 'base64'))
             IS DISTINCT FROM (asset->>'file_size_bytes')::integer THEN
            RAISE EXCEPTION 'Fixture bytes do not match the manifest';
        END IF;
    END LOOP;
    -- Serialize seeders; block dispatchers and changes for this small fixture transaction.
    LOCK TABLE public.documents, public.processing_jobs IN SHARE ROW EXCLUSIVE MODE;
    PERFORM id FROM public.companies WHERE id IN
        ('11111111-1111-1111-1111-111111111111', '11111111-1111-1111-1111-222222222222')
        ORDER BY id FOR SHARE;
    IF (SELECT count(*) FROM public.companies WHERE id IN
        ('11111111-1111-1111-1111-111111111111', '11111111-1111-1111-1111-222222222222')) <> 2 THEN
        RAISE EXCEPTION 'Missing prerequisite auth companies; seed auth separately';
    END IF;
    PERFORM id FROM public.users WHERE id IN
        ('22222222-2222-2222-2222-222222222222', '33333333-3333-3333-3333-333333333333')
        ORDER BY id FOR SHARE;
    IF (SELECT count(*) FROM public.users WHERE company_id = '11111111-1111-1111-1111-111111111111'
        AND id IN ('22222222-2222-2222-2222-222222222222', '33333333-3333-3333-3333-333333333333')) <> 2 THEN
        RAISE EXCEPTION 'Missing or mismatched prerequisite auth users';
    END IF;
    -- Validate every pair first. No write occurs until this entire pass succeeds.
    IF (SELECT count(DISTINCT value->>'id') FROM jsonb_array_elements(payload->'documents')) <> 6
       OR (SELECT count(DISTINCT value->>'id') FROM jsonb_array_elements(payload->'jobs')) <> 6
       OR (SELECT count(DISTINCT value->>'document_id') FROM jsonb_array_elements(payload->'jobs')) <> 6 THEN
        RAISE EXCEPTION 'Fixture IDs must be unique';
    END IF;
    FOR expected_doc IN SELECT * FROM jsonb_populate_recordset(NULL::public.documents, payload->'documents') ORDER BY id LOOP
        SELECT * INTO STRICT expected_job FROM jsonb_populate_recordset(NULL::public.processing_jobs, payload->'jobs')
            WHERE document_id = expected_doc.id;
        IF NOT EXISTS (SELECT 1 FROM jsonb_array_elements(payload->'files') f
            WHERE f->>'file_hash' = expected_doc.file_hash
              AND f->>'mime_type' = expected_doc.mime_type
              AND f->>'path' = expected_doc.file_name
              AND (f->>'file_size_bytes')::integer = expected_doc.file_size_bytes) THEN
            RAISE EXCEPTION 'Document fixture does not match validated file metadata';
        END IF;
        SELECT * INTO actual_doc FROM public.documents WHERE id = expected_doc.id FOR UPDATE;
        doc_exists := FOUND;
        SELECT * INTO actual_job FROM public.processing_jobs
            WHERE id = expected_job.id OR document_id = expected_doc.id FOR UPDATE;
        job_exists := FOUND;
        IF doc_exists IS DISTINCT FROM job_exists THEN
            RAISE EXCEPTION 'Partial fixture pair detected; refusing implicit repair';
        END IF;
        IF doc_exists AND (to_jsonb(actual_doc) IS DISTINCT FROM to_jsonb(expected_doc)
                           OR to_jsonb(actual_job) IS DISTINCT FROM to_jsonb(expected_job)) THEN
            RAISE EXCEPTION 'Fixture mismatch; refusing to reset existing data or job state';
        END IF;
    END LOOP;
    FOR expected_doc IN SELECT * FROM jsonb_populate_recordset(NULL::public.documents, payload->'documents') ORDER BY id LOOP
        IF NOT EXISTS (SELECT 1 FROM public.documents WHERE id = expected_doc.id) THEN
            SELECT * INTO STRICT expected_job FROM jsonb_populate_recordset(NULL::public.processing_jobs, payload->'jobs')
                WHERE document_id = expected_doc.id;
            INSERT INTO public.documents SELECT expected_doc.*;
            INSERT INTO public.processing_jobs SELECT expected_job.*;
        END IF;
    END LOOP;
END;
$seed$;
