"""Deterministic, synthetic database-only RAG fixtures."""
from __future__ import annotations

import hashlib
import math

MODEL = "sentence-transformers/all-MiniLM-L6-v2"
REVISION = "database-fixture-only-not-a-production-model-revision"
PIPELINE = "document-processing-rag-v1"
T0 = "2026-09-04T12:00:00Z"
COMPANY_A = "11111111-1111-1111-1111-111111111111"
COMPANY_B = "11111111-1111-1111-1111-222222222222"

DOC_E = "66666666-6666-4666-8666-000000000001"
JOB_E = "77777777-7777-4777-8777-000000000001"
DOC_A = "66666666-6666-4666-8666-000000000003"
JOB_A = "77777777-7777-4777-8777-000000000003"
DOC_B = "66666666-6666-4666-8666-000000000004"
JOB_B = "77777777-7777-4777-8777-000000000004"
DOC_C = "66666666-6666-4666-8666-000000000005"
JOB_C = "77777777-7777-4777-8777-000000000005"
DOC_D = "66666666-6666-4666-8666-000000000006"
JOB_D = "77777777-7777-4777-8777-000000000006"
RUN_A = "99999999-9999-4999-8999-000000000001"
RUN_B = "99999999-9999-4999-8999-000000000002"
RUN_C = "99999999-9999-4999-8999-000000000003"
RUN_D = "99999999-9999-4999-8999-000000000004"
RUN_E = "99999999-9999-4999-8999-000000000005"
INVOICE_A = "aaaaaaaa-aaaa-4aaa-8aaa-000000000001"
INVOICE_B = "aaaaaaaa-aaaa-4aaa-8aaa-000000000002"
INVOICE_C = "aaaaaaaa-aaaa-4aaa-8aaa-000000000003"
INVOICE_D = "aaaaaaaa-aaaa-4aaa-8aaa-000000000004"


def unit_vector(*components: tuple[int, float]) -> list[float]:
    vector = [0.0] * 384
    for index, value in components:
        vector[index] = value
    norm = math.sqrt(sum(value * value for value in vector))
    if not math.isfinite(norm) or norm == 0:
        raise ValueError("Fixture vector must have a finite non-zero norm")
    return [value / norm for value in vector]


def sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def fixture_payload() -> dict:
    chunks = [
        dict(id="88888888-8888-4888-8888-000000000001", document_id=DOC_A,
             parent_chunk_id=None, ordinal=0, page_start=1, page_end=2, chunk_type="table",
             retrieval_role="parent", raw_content="Synthetic invoice line-items table",
             embedding=None, embedding_status="not_required"),
        dict(id="88888888-8888-4888-8888-000000000002", document_id=DOC_A,
             parent_chunk_id="88888888-8888-4888-8888-000000000001", ordinal=1,
             page_start=1, page_end=1, chunk_type="table", retrieval_role="child",
             raw_content="Widget A quantity 2 unit price 50 total 100", embedding=unit_vector((0, 1.0)),
             embedding_status="completed"),
        dict(id="88888888-8888-4888-8888-000000000003", document_id=DOC_A,
             parent_chunk_id="88888888-8888-4888-8888-000000000001", ordinal=2,
             page_start=2, page_end=2, chunk_type="table", retrieval_role="child",
             raw_content="Widget B quantity 1 unit price 20 total 20", embedding=unit_vector((0, .8), (1, .6)),
             embedding_status="completed"),
        dict(id="88888888-8888-4888-8888-000000000004", document_id=DOC_B,
             parent_chunk_id=None, ordinal=0, page_start=1, page_end=1, chunk_type="text",
             retrieval_role="both", raw_content="Other tenant widget A quantity 2 total 100",
             embedding=unit_vector((0, 1.0)), embedding_status="completed"),
        dict(id="88888888-8888-4888-8888-000000000005", document_id=DOC_C,
             parent_chunk_id=None, ordinal=0, page_start=1, page_end=1, chunk_type="text",
             retrieval_role="both", raw_content="Synthetic rejected-review invoice",
             embedding=unit_vector((2, 1.0)), embedding_status="completed"),
        dict(id="88888888-8888-4888-8888-000000000006", document_id=DOC_D,
             parent_chunk_id=None, ordinal=0, page_start=1, page_end=1, chunk_type="text",
             retrieval_role="both", raw_content="Synthetic tenant B review invoice",
             embedding=unit_vector((3, 1.0)), embedding_status="completed"),
        dict(id="88888888-8888-4888-8888-000000000007", document_id=DOC_E,
             parent_chunk_id=None, ordinal=0, page_start=1, page_end=1, chunk_type="text",
             retrieval_role="both", raw_content="Synthetic export boundary invoice",
             embedding=unit_vector((4, 1.0)), embedding_status="completed"),
    ]
    for chunk in chunks:
        chunk.update(pipeline_version=PIPELINE, section="invoice", summary=None,
                     structured_content={"schema": "synthetic-v1"} if chunk["chunk_type"] == "table" else None,
                     token_count=max(1, len(chunk["raw_content"].split())), source_element_ids=[f"el-{chunk['ordinal']}"],
                     bounding_boxes=[], content_hash=sha(chunk["raw_content"]),
                     embedding_model=MODEL if chunk["embedding"] is not None else None,
                     embedding_revision=REVISION if chunk["embedding"] is not None else None,
                     created_at=T0, updated_at=T0)
    runs = [
        dict(id=RUN_A, document_id=DOC_A, job_id=JOB_A, status="completed", finished_at="2026-09-04T12:01:00Z",
             warning_codes=[], input_tokens=800, output_tokens=220, estimated_cost="0.012300"),
        dict(id=RUN_B, document_id=DOC_B, job_id=JOB_B, status="failed", finished_at="2026-09-04T12:01:30Z",
             warning_codes=["SYNTHETIC_PROVIDER_FAILURE"], input_tokens=100, output_tokens=0, estimated_cost="0.000000"),
        dict(id=RUN_C, document_id=DOC_C, job_id=JOB_C, status="completed", finished_at="2026-09-04T12:02:00Z",
             warning_codes=[], input_tokens=120, output_tokens=40, estimated_cost="0.001000"),
        dict(id=RUN_D, document_id=DOC_D, job_id=JOB_D, status="completed", finished_at="2026-09-04T12:02:30Z",
             warning_codes=[], input_tokens=120, output_tokens=40, estimated_cost="0.001000"),
        dict(id=RUN_E, document_id=DOC_E, job_id=JOB_E, status="completed", finished_at="2026-09-04T12:03:00Z",
             warning_codes=[], input_tokens=140, output_tokens=50, estimated_cost="0.001200"),
    ]
    for run in runs:
        run.update(pipeline_version=PIPELINE, configuration_hash=sha("fixture-config-v1"),
                   parser_name="docling", parser_version="fixture-parser-v1", ocr_policy_version="ocr-v1",
                   embedding_model=MODEL, embedding_revision=REVISION, embedding_dimension=384,
                   llm_provider="fixture-provider", llm_model="fixture-model", prompt_version="invoice-v1",
                   schema_version="commercial-invoice-v1", retrieval_config={"top_k": 5, "mode": "exact_cosine"},
                   started_at=T0, created_at=T0, updated_at=T0)
    tenants = {DOC_E: COMPANY_A, DOC_A: COMPANY_A, DOC_B: COMPANY_B,
               DOC_C: COMPANY_A, DOC_D: COMPANY_B}
    attempts = {DOC_E: 1, DOC_A: 1, DOC_B: 4, DOC_C: 1, DOC_D: 1}
    partitions = []
    for number, run in enumerate(runs, 1):
        canonical = {
            "document_id": run["document_id"],
            "pipeline_version": run["pipeline_version"],
            "parser_name": run["parser_name"],
            "parser_version": run["parser_version"],
            "ocr_policy_version": run["ocr_policy_version"],
            "warning_codes": [],
            "pages": [{
                "page_number": 1, "width": 612.0, "height": 792.0,
                "rotation": 0, "ocr_used": False, "ocr_language": None,
                "elements": [{
                    "source_id": f"partition-{number}-element-1",
                    "element_type": "paragraph",
                    "original_text": f"Synthetic canonical checkpoint {number}",
                    "normalized_text": None, "page_number": 1,
                    "bounding_box": None, "table": None, "section": "invoice",
                }],
            }],
        }
        partitions.append({
            "id": f"eeeeeeee-eeee-4eee-8eee-{number:012d}",
            "company_id": tenants[run["document_id"]],
            "document_id": run["document_id"], "job_id": run["job_id"],
            "created_attempt": attempts[run["document_id"]],
            "pipeline_version": run["pipeline_version"],
            "configuration_hash": run["configuration_hash"],
            "parser_name": run["parser_name"], "parser_version": run["parser_version"],
            "ocr_policy_version": run["ocr_policy_version"],
            "canonical_document": canonical, "created_at": T0,
        })
    invoices = [
        dict(id=INVOICE_A, document_id=DOC_A, extraction_run_id=RUN_A,
             invoice_number="SYN-2026-001", supplier_name="Synthetic Supplier", supplier_tax_id=None,
             buyer_name="Synthetic Buyer", date_issued="2026-09-04", due_date=None, currency="USD",
             subtotal="120.00", tax_amount="6.00", discount_amount="0.00", grand_total="126.00",
             is_math_valid=True, created_at=T0, updated_at=T0),
        dict(id=INVOICE_B, document_id=DOC_C, extraction_run_id=RUN_C,
             invoice_number=None, supplier_name="Synthetic Missing Number", supplier_tax_id=None,
             buyer_name="Synthetic Buyer", date_issued="2026-09-04", due_date=None, currency="USD",
             subtotal="0.00", tax_amount="0.00", discount_amount="0.00", grand_total="0.00",
             is_math_valid=True, created_at=T0, updated_at=T0),
        dict(id=INVOICE_C, document_id=DOC_D, extraction_run_id=RUN_D,
             invoice_number="SYN-2026-TB", supplier_name="Synthetic Tenant B Supplier", supplier_tax_id=None,
             buyer_name="Synthetic Tenant B Buyer", date_issued="2026-09-04", due_date=None, currency="BDT",
             subtotal="131.00", tax_amount="0.00", discount_amount="0.00", grand_total="131.00",
             is_math_valid=True, created_at=T0, updated_at=T0),
        dict(id=INVOICE_D, document_id=DOC_E, extraction_run_id=RUN_E,
             invoice_number="SYN-2026-EXPORT", supplier_name="Synthetic Export Supplier", supplier_tax_id=None,
             buyer_name="Synthetic Export Buyer", date_issued="2026-09-05", due_date=None, currency="USD",
             subtotal="500.00", tax_amount="25.00", discount_amount="0.00", grand_total="525.00",
             is_math_valid=True, created_at=T0, updated_at=T0),
    ]
    lines = [
        dict(id=f"bbbbbbbb-bbbb-4bbb-8bbb-{n:012d}", invoice_id=INVOICE_A,
             source_row_key=f"table-1-row-{n}", line_order=n, description=f"Widget {chr(64+n)}",
             hs_code=None, quantity=q, unit_price=p, tax_amount=t, total_price=total,
             created_at=T0, updated_at=T0)
        for n, q, p, t, total in [(1, "2.0000", "50.0000", "5.00", "105.00"),
                                  (2, "1.0000", "20.0000", "1.00", "21.00"),
                                  (3, None, None, None, None)]
    ]
    lines.append(
        dict(id="bbbbbbbb-bbbb-4bbb-8bbb-000000000004", invoice_id=INVOICE_C,
             source_row_key="table-1-row-1", line_order=1, description="Tenant B service",
             hs_code=None, quantity="1.0000", unit_price="131.0000", tax_amount="0.00",
             total_price="131.00", created_at=T0, updated_at=T0)
    )
    lines.append(
        dict(id="bbbbbbbb-bbbb-4bbb-8bbb-000000000005", invoice_id=INVOICE_D,
             source_row_key="table-1-row-1", line_order=1, description="Export boundary item",
             hs_code=None, quantity="5.0000", unit_price="100.0000", tax_amount="25.00",
             total_price="525.00", created_at=T0, updated_at=T0)
    )
    evidence = [
        dict(id="cccccccc-cccc-4ccc-8ccc-000000000001", extraction_run_id=RUN_A,
             field_path="invoice.invoice_number", source_value="SYN-2026-001",
             normalized_value="SYN-2026-001", primary_chunk_id="88888888-8888-4888-8888-000000000002",
             source_page=1, bounding_box={"v": 1, "x": 0.1, "y": 0.1, "w": 0.2, "h": 0.05},
             evidence_excerpt="Invoice SYN-2026-001", retrieval_rank=1, retrieval_score="1.000000",
             exact_match=True, confidence_score="99.00", reason_codes=[], validation_state="valid", created_at=T0),
        dict(id="cccccccc-cccc-4ccc-8ccc-000000000002", extraction_run_id=RUN_A,
             field_path="invoice.supplier_tax_id", source_value=None, normalized_value=None,
             primary_chunk_id=None, source_page=None, bounding_box=None, evidence_excerpt=None,
             retrieval_rank=None, retrieval_score=None, exact_match=False, confidence_score="0.00",
             reason_codes=["NOT_PRESENT"], validation_state="missing", created_at=T0),
    ]
    validations = [
        dict(id="dddddddd-dddd-4ddd-8ddd-000000000001", extraction_run_id=RUN_A,
             rule_id="BR-03-TOTAL", scope_key="document", status="passed",
             observed_value="126.00", expected_value="126.00", difference="0.000000",
             epsilon="0.050000", message_code="TOTAL_RECONCILED", created_at=T0),
        dict(id="dddddddd-dddd-4ddd-8ddd-000000000002", extraction_run_id=RUN_A,
             rule_id="BR-02-TAX-ID", scope_key="invoice.supplier_tax_id", status="missing",
             observed_value=None, expected_value=None, difference=None, epsilon=None,
             message_code="FIELD_NOT_PRESENT", created_at=T0),
    ]
    return {"scope": "DATABASE_ONLY", "version": 2, "partitions": partitions,
            "chunks": chunks, "runs": runs,
            "invoices": invoices, "line_items": lines, "field_evidence": evidence,
            "validation_results": validations}
