"""Guarded, idempotent loader for synthetic RAG persistence fixtures."""
from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path

import psycopg
from pgvector.psycopg import register_vector
from psycopg.conninfo import conninfo_to_dict
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parent


def _fixtures():
    spec = importlib.util.spec_from_file_location("rag_fixtures", ROOT / "generate_fixtures.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.fixture_payload()


def disposable_name(dsn: str, acknowledgement: str) -> str:
    info = conninfo_to_dict(dsn)
    name = info.get("dbname", "")
    if info.get("service") or info.get("host") not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("Specify an explicit loopback test host")
    prefixes = ("docusense_ingestion_test_", "docusense_rag_test_", "docusense_export_test_")
    if not name.startswith(prefixes) or not name.replace("_", "").isalnum() or acknowledgement != name:
        raise ValueError("Matching disposable database acknowledgement is required")
    return name


def seed(conn: psycopg.Connection, acknowledgement: str, *, no_active_consumers: bool) -> str:
    name = disposable_name(conn.info.dsn, acknowledgement)
    if not no_active_consumers:
        raise ValueError("Explicit no-active-consumers assertion is required")
    register_vector(conn)
    payload = _fixtures()
    with conn.transaction():
        conn.execute("SELECT set_config('docusense.disposable_database', %s, true)", (name,))
        if conn.execute("SELECT version_num FROM public.alembic_version").fetchone()[0] != "20260904_0003":
            raise ValueError("Expected RAG migration revision 20260904_0003")
        conn.execute("SELECT pg_advisory_xact_lock(hashtextextended('docusense-rag-fixtures-v1',0))")
        parent_document_ids = sorted({run["document_id"] for run in payload["runs"]})
        parents = conn.execute(
            "SELECT d.id::text,j.id::text FROM public.documents d JOIN public.processing_jobs j ON j.document_id=d.id WHERE d.id=ANY(%s::uuid[])",
            (parent_document_ids,),
        ).fetchall()
        if len(parents) != len(parent_document_ids):
            raise ValueError("Expected verified ingestion fixture parents")
        expected = {
            "document_partitions": len(payload["partitions"]),
            "document_chunks": len(payload["chunks"]),
            "extraction_runs": len(payload["runs"]),
            "invoices": len(payload["invoices"]),
            "line_items": len(payload["line_items"]),
            "field_evidence": len(payload["field_evidence"]),
            "validation_results": len(payload["validation_results"]),
        }
        existing = {table: conn.execute(f"SELECT count(*) FROM public.{table}").fetchone()[0] for table in expected}
        if any(existing.values()):
            if existing != expected:
                raise ValueError("Conflicting or partial RAG fixture graph")
            hashes = conn.execute("SELECT array_agg(content_hash::text ORDER BY id) FROM public.document_chunks").fetchone()[0]
            if hashes != [chunk["content_hash"] for chunk in sorted(payload["chunks"], key=lambda item: item["id"])]:
                raise ValueError("Existing RAG fixture content differs")
            canonical = conn.execute(
                "SELECT canonical_document FROM public.document_partitions ORDER BY id"
            ).fetchall()
            if [row[0] for row in canonical] != [
                item["canonical_document"] for item in sorted(payload["partitions"], key=lambda item: item["id"])
            ]:
                raise ValueError("Existing canonical partition fixtures differ")
            return "unchanged"
        for run in sorted(payload["runs"], key=lambda item: item["document_id"]):
            conn.execute(
                """SELECT d.id FROM public.documents d
                   JOIN public.processing_jobs j ON j.document_id=d.id
                   WHERE d.id=%s FOR UPDATE OF d,j""",
                (run["document_id"],),
            ).fetchone()
            conn.execute(
                """UPDATE public.processing_jobs
                   SET status='processing',current_stage='partitioning',progress_percentage=20,
                       attempt_count=GREATEST(attempt_count,1),next_attempt_at=NULL,
                       lease_expires_at=clock_timestamp()+interval '5 minutes',error_code=NULL,error_message=NULL,
                       started_at=COALESCE(started_at,%s),finished_at=NULL
                   WHERE id=%s""",
                (run["started_at"], run["job_id"]),
            )
            conn.execute(
                """UPDATE public.documents
                   SET status='partitioning',overall_confidence=NULL
                   WHERE id=%s""",
                (run["document_id"],),
            )
        for partition in payload["partitions"]:
            conn.execute("""INSERT INTO public.document_partitions
              (id,company_id,document_id,job_id,created_attempt,pipeline_version,configuration_hash,
               parser_name,parser_version,ocr_policy_version,canonical_document,created_at)
              VALUES (%(id)s,%(company_id)s,%(document_id)s,%(job_id)s,%(created_attempt)s,%(pipeline_version)s,
               %(configuration_hash)s,%(parser_name)s,%(parser_version)s,%(ocr_policy_version)s,
               %(canonical_document)s,%(created_at)s)""",
              {**partition, "canonical_document": Jsonb(partition["canonical_document"])})
        for c in payload["chunks"]:
            conn.execute("""INSERT INTO public.document_chunks
              (id,document_id,parent_chunk_id,pipeline_version,ordinal,page_start,page_end,section,chunk_type,retrieval_role,
               raw_content,structured_content,summary,token_count,source_element_ids,bounding_boxes,content_hash,embedding,
               embedding_model,embedding_revision,embedding_status,created_at,updated_at)
              VALUES (%(id)s,%(document_id)s,%(parent_chunk_id)s,%(pipeline_version)s,%(ordinal)s,%(page_start)s,%(page_end)s,
               %(section)s,%(chunk_type)s,%(retrieval_role)s,%(raw_content)s,%(structured_content)s,%(summary)s,%(token_count)s,
               %(source_element_ids)s,%(bounding_boxes)s,%(content_hash)s,%(embedding)s,%(embedding_model)s,
               %(embedding_revision)s,%(embedding_status)s,%(created_at)s,%(updated_at)s)""",
              {**c, "structured_content": Jsonb(c["structured_content"]) if c["structured_content"] is not None else None,
               "source_element_ids": Jsonb(c["source_element_ids"]), "bounding_boxes": Jsonb(c["bounding_boxes"])})
        for r in payload["runs"]:
            conn.execute("""INSERT INTO public.extraction_runs
              (id,document_id,job_id,status,pipeline_version,configuration_hash,parser_name,parser_version,ocr_policy_version,
               embedding_model,embedding_revision,embedding_dimension,llm_provider,llm_model,prompt_version,schema_version,
               retrieval_config,warning_codes,input_tokens,output_tokens,estimated_cost,started_at,finished_at,created_at,updated_at)
              VALUES (%(id)s,%(document_id)s,%(job_id)s,%(status)s,%(pipeline_version)s,%(configuration_hash)s,%(parser_name)s,
               %(parser_version)s,%(ocr_policy_version)s,%(embedding_model)s,%(embedding_revision)s,%(embedding_dimension)s,
               %(llm_provider)s,%(llm_model)s,%(prompt_version)s,%(schema_version)s,%(retrieval_config)s,%(warning_codes)s,
               %(input_tokens)s,%(output_tokens)s,%(estimated_cost)s,%(started_at)s,%(finished_at)s,%(created_at)s,%(updated_at)s)""",
              {**r, "retrieval_config": Jsonb(r["retrieval_config"]), "warning_codes": Jsonb(r["warning_codes"])})
        for invoice in payload["invoices"]:
            conn.execute("""INSERT INTO public.invoices VALUES
              (%(id)s,%(document_id)s,%(extraction_run_id)s,%(invoice_number)s,%(supplier_name)s,%(supplier_tax_id)s,%(buyer_name)s,
               %(date_issued)s,%(due_date)s,%(currency)s,%(subtotal)s,%(tax_amount)s,%(discount_amount)s,%(grand_total)s,
               %(is_math_valid)s,%(created_at)s,%(updated_at)s)""", invoice)
        for item in payload["line_items"]:
            conn.execute("""INSERT INTO public.line_items VALUES
              (%(id)s,%(invoice_id)s,%(source_row_key)s,%(line_order)s,%(description)s,%(hs_code)s,%(quantity)s,
               %(unit_price)s,%(tax_amount)s,%(total_price)s,%(created_at)s,%(updated_at)s)""", item)
        for e in payload["field_evidence"]:
            conn.execute("""INSERT INTO public.field_evidence VALUES
              (%(id)s,%(extraction_run_id)s,%(field_path)s,%(source_value)s,%(normalized_value)s,%(primary_chunk_id)s,
               %(source_page)s,%(bounding_box)s,%(evidence_excerpt)s,%(retrieval_rank)s,%(retrieval_score)s,%(exact_match)s,
               %(confidence_score)s,%(reason_codes)s,%(validation_state)s,%(created_at)s)""",
              {**e, "normalized_value": Jsonb(e["normalized_value"]) if e["normalized_value"] is not None else None,
               "bounding_box": Jsonb(e["bounding_box"]) if e["bounding_box"] is not None else None,
               "reason_codes": Jsonb(e["reason_codes"])})
        for v in payload["validation_results"]:
            conn.execute("""INSERT INTO public.validation_results VALUES
              (%(id)s,%(extraction_run_id)s,%(rule_id)s,%(scope_key)s,%(status)s,%(observed_value)s,%(expected_value)s,
               %(difference)s,%(epsilon)s,%(message_code)s,%(created_at)s)""",
              {**v, "observed_value": Jsonb(v["observed_value"]) if v["observed_value"] is not None else None,
               "expected_value": Jsonb(v["expected_value"]) if v["expected_value"] is not None else None})
        for run in sorted(payload["runs"], key=lambda item: item["document_id"]):
            if run["status"] == "completed":
                conn.execute(
                    """UPDATE public.processing_jobs
                       SET status='completed',current_stage='extracting',progress_percentage=100,
                           next_attempt_at=NULL,lease_expires_at=NULL,error_code=NULL,error_message=NULL,
                           finished_at=%s WHERE id=%s""",
                    (run["finished_at"], run["job_id"]),
                )
                conn.execute(
                    """UPDATE public.documents SET status='pending_review',
                       overall_confidence=COALESCE(overall_confidence,90.00) WHERE id=%s""",
                    (run["document_id"],),
                )
            else:
                conn.execute(
                    """UPDATE public.processing_jobs
                       SET status='failed',current_stage='extracting',progress_percentage=80,
                           next_attempt_at=NULL,lease_expires_at=NULL,error_code='PROCESSING_FAILED',
                           error_message='Synthetic processing failure',finished_at=%s WHERE id=%s""",
                    (run["finished_at"], run["job_id"]),
                )
                conn.execute(
                    "UPDATE public.documents SET status='failed',overall_confidence=NULL WHERE id=%s",
                    (run["document_id"],),
                )
        actual = {table: conn.execute(f"SELECT count(*) FROM public.{table}").fetchone()[0] for table in expected}
        if actual != expected:
            raise RuntimeError("RAG fixture count verification failed")
    return "inserted"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ack", required=True)
    parser.add_argument("--no-active-consumers", action="store_true")
    args = parser.parse_args()
    dsn = os.environ.get("RAG_TEST_DSN") or os.environ.get("INGESTION_TEST_DSN")
    if not dsn:
        raise SystemExit("RAG_TEST_DSN or INGESTION_TEST_DSN is required")
    with psycopg.connect(dsn) as conn:
        result = seed(conn, args.ack, no_active_consumers=args.no_active_consumers)
    print(f"Synthetic RAG fixtures: {result}")


if __name__ == "__main__":
    main()
