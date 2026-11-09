"""Guarded deterministic seeder for human-review/audit database fixtures.

The loader never creates auth, ingestion, or RAG parents. It requires a matching
loopback disposable target, no active consumers, the exact migration head, and
three already-verified completed reviewable aggregates.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parent
TABLE_KEYS = {
    "review_audit_events": "events",
    "review_audit_changes": "changes",
    "review_validation_runs": "validation_runs",
    "review_validation_results": "validation_results",
    "review_idempotency_keys": "idempotency",
}


def load_fixture_module():
    path = ROOT / "generate_fixtures.py"
    spec = importlib.util.spec_from_file_location("human_review_audit_fixtures", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def disposable_name(dsn: str, acknowledgement: str) -> str:
    info = conninfo_to_dict(dsn)
    name = info.get("dbname", "")
    if (
        info.get("service")
        or info.get("host") not in {"127.0.0.1", "localhost", "::1"}
        or info.get("hostaddr", "127.0.0.1") not in {"127.0.0.1", "::1"}
    ):
        raise ValueError("Specify an explicit loopback test host; service/default targets are refused")
    if not re.fullmatch(r"docusense_review_test_[a-z0-9_]+", name) or acknowledgement != name:
        raise ValueError("Exact disposable review database acknowledgement is required")
    return name


def validate_payload(payload: dict) -> None:
    manifest = json.loads(
        (ROOT / "human-review-audit-fixtures" / "manifest.json").read_text(encoding="utf-8")
    )
    if payload.get("scope") != "DATABASE_ONLY" or payload.get("version") != 1:
        raise ValueError("Unsupported fixture payload")
    expected = manifest["counts"]
    actual = {table: len(payload[key]) for table, key in TABLE_KEYS.items()}
    actual["reviewer_added_line_items"] = len(payload["current_mutations"]["manual_lines"])
    if actual != expected or manifest.get("synthetic_only") is not True:
        raise ValueError("Fixture manifest/count mismatch")
    all_ids = [row["id"] for key in TABLE_KEYS.values() for row in payload[key]]
    if len(all_ids) != len(set(all_ids)):
        raise ValueError("Fixture IDs must be globally unique")


def _fixture_counts(conn: psycopg.Connection, payload: dict) -> dict[str, int]:
    counts = {}
    for table, key in TABLE_KEYS.items():
        ids = [row["id"] for row in payload[key]]
        counts[table] = conn.execute(
            f"SELECT count(*) FROM public.{table} WHERE id=ANY(%s::uuid[])", (ids,)
        ).fetchone()[0]
    return counts


def _verify_parents(conn: psycopg.Connection, payload: dict) -> None:
    for parent in sorted(payload["required_parents"], key=lambda row: row["document_id"]):
        row = conn.execute(
            """SELECT d.company_id::text,u.company_id::text,d.status,d.review_revision,
                      j.status,r.status,i.id::text
               FROM public.documents d
               JOIN public.processing_jobs j ON j.document_id=d.id
               JOIN public.extraction_runs r ON r.document_id=d.id
               JOIN public.invoices i ON i.document_id=d.id AND i.extraction_run_id=r.id
               JOIN public.users u ON u.id=%(actor_user_id)s
               WHERE d.id=%(document_id)s AND i.id=%(invoice_id)s
               FOR UPDATE OF d,i""",
            parent,
        ).fetchone()
        if row is None:
            raise ValueError("Required verified review parent graph is missing")
        if (
            row[0] != parent["company_id"]
            or row[1] != parent["company_id"]
            or row[2] != "pending_review"
            or row[3] != 0
            or row[4] != "completed"
            or row[5] != "completed"
            or row[6] != parent["invoice_id"]
        ):
            raise ValueError("Review parent graph is not completed, tenant-safe, and revision zero")


def seed(
    conn: psycopg.Connection,
    acknowledgement: str,
    *,
    no_active_consumers: bool,
    payload: dict | None = None,
) -> str:
    if not no_active_consumers:
        raise ValueError("Confirm that the disposable database has no active consumers")
    name = disposable_name(conn.info.dsn, acknowledgement)
    payload = payload or load_fixture_module().fixture_payload()
    validate_payload(payload)

    with conn.transaction():
        connected = conn.execute("SELECT current_database()").fetchone()[0]
        if connected != name:
            raise ValueError("Connected database differs from acknowledged target")
        conn.execute("SELECT set_config('docusense.disposable_database',%s,true)", (name,))
        conn.execute("SELECT set_config('docusense.no_active_consumers','confirmed',true)")
        conn.execute("SELECT pg_advisory_xact_lock(hashtextextended('human-review-audit-fixtures',0))")
        head = conn.execute("SELECT array_agg(version_num::text) FROM public.alembic_version").fetchone()[0]
        if head != ["20260906_0004"]:
            raise ValueError("Seeder requires canonical human review revision 20260906_0004")

        counts = _fixture_counts(conn, payload)
        expected = {table: len(payload[key]) for table, key in TABLE_KEYS.items()}
        if any(counts.values()):
            if counts != expected:
                raise ValueError("Conflicting or partial human-review fixture graph")
            for final in payload["document_final"]:
                actual = conn.execute(
                    """SELECT status,review_revision,last_reviewed_by::text,last_reviewed_at::text
                       FROM public.documents WHERE id=%(document_id)s""",
                    final,
                ).fetchone()
                if actual is None or actual[:3] != (
                    final["status"], final["review_revision"], final["last_reviewed_by"]
                ):
                    raise ValueError("Existing fixture current state differs")
            return "unchanged"

        _verify_parents(conn, payload)

        for event in payload["events"]:
            conn.execute(
                """INSERT INTO public.review_audit_events
                   (id,document_id,actor_user_id,action,from_status,to_status,review_revision,
                    reason,note,request_id,payload_hash,created_at)
                   VALUES (%(id)s,%(document_id)s,%(actor_user_id)s,%(action)s,%(from_status)s,
                    %(to_status)s,%(review_revision)s,%(reason)s,%(note)s,%(request_id)s,
                    %(payload_hash)s,%(created_at)s)""",
                event,
            )
        for change in payload["changes"]:
            conn.execute(
                """INSERT INTO public.review_audit_changes
                   (id,audit_event_id,field_path,change_kind,old_value,new_value,created_at)
                   VALUES (%(id)s,%(audit_event_id)s,%(field_path)s,%(change_kind)s,
                    %(old_value)s,%(new_value)s,%(created_at)s)""",
                {
                    **change,
                    "old_value": Jsonb(change["old_value"]) if change["old_value"] is not None else None,
                    "new_value": Jsonb(change["new_value"]) if change["new_value"] is not None else None,
                    "created_at": next(
                        e["created_at"] for e in payload["events"] if e["id"] == change["audit_event_id"]
                    ),
                },
            )

        for mutation in payload["current_mutations"]["invoice_updates"]:
            conn.execute("SELECT set_config('docusense.review_event_id',%s,true)", (mutation["event_id"],))
            if "supplier_name" in mutation:
                result = conn.execute(
                    "UPDATE public.invoices SET supplier_name=%s WHERE id=%s",
                    (mutation["supplier_name"], mutation["invoice_id"]),
                )
            elif "grand_total" in mutation:
                result = conn.execute(
                    "UPDATE public.invoices SET grand_total=%s WHERE id=%s",
                    (mutation["grand_total"], mutation["invoice_id"]),
                )
            else:
                result = conn.execute(
                    "UPDATE public.invoices SET currency=%s WHERE id=%s",
                    (mutation["currency"], mutation["invoice_id"]),
                )
            if result.rowcount != 1:
                raise ValueError("Expected fixture invoice was not updated")

        for line in payload["current_mutations"]["manual_lines"]:
            conn.execute("SELECT set_config('docusense.review_event_id',%s,true)", (line["event_id"],))
            conn.execute(
                """INSERT INTO public.line_items
                   (id,invoice_id,source_row_key,line_order,description,hs_code,quantity,
                    unit_price,tax_amount,total_price,created_at,updated_at,origin)
                   VALUES (%(id)s,%(invoice_id)s,%(source_row_key)s,%(line_order)s,%(description)s,
                    %(hs_code)s,%(quantity)s,%(unit_price)s,%(tax_amount)s,%(total_price)s,
                    %(created_at)s,%(updated_at)s,%(origin)s)""",
                line,
            )
        for run in payload["validation_runs"]:
            conn.execute(
                """INSERT INTO public.review_validation_runs
                   (id,audit_event_id,document_id,review_revision,validation_version,candidate_hash,
                    is_math_valid,approval_eligible,created_at)
                   VALUES (%(id)s,%(audit_event_id)s,%(document_id)s,%(review_revision)s,
                    %(validation_version)s,%(candidate_hash)s,%(is_math_valid)s,
                    %(approval_eligible)s,%(created_at)s)""",
                run,
            )
        for result in payload["validation_results"]:
            conn.execute(
                """INSERT INTO public.review_validation_results
                   (id,review_validation_run_id,rule_id,scope_key,status,observed_value,
                    expected_value,difference,epsilon,message_code,blocks_approval,created_at)
                   VALUES (%(id)s,%(review_validation_run_id)s,%(rule_id)s,%(scope_key)s,%(status)s,
                    %(observed_value)s,%(expected_value)s,%(difference)s,%(epsilon)s,%(message_code)s,
                    %(blocks_approval)s,%(created_at)s)""",
                {
                    **result,
                    "observed_value": Jsonb(result["observed_value"]) if result["observed_value"] is not None else None,
                    "expected_value": Jsonb(result["expected_value"]) if result["expected_value"] is not None else None,
                },
            )

        for event in sorted(
            payload["events"], key=lambda row: (row["document_id"], row["review_revision"])
        ):
            conn.execute(
                "SELECT set_config('docusense.review_event_id',%s,true)",
                (event["id"],),
            )
            if event["action"] in {"approved", "rejected"}:
                updated = conn.execute(
                    """UPDATE public.documents SET status=%(to_status)s,
                          review_revision=%(review_revision)s,last_reviewed_by=%(actor_user_id)s,
                          last_reviewed_at=%(created_at)s
                       WHERE id=%(document_id)s AND review_revision=%(prior_revision)s""",
                    {**event, "prior_revision": event["review_revision"] - 1},
                )
            else:
                updated = conn.execute(
                    """UPDATE public.documents SET status=%(to_status)s,
                          review_revision=%(review_revision)s
                       WHERE id=%(document_id)s AND review_revision=%(prior_revision)s""",
                    {**event, "prior_revision": event["review_revision"] - 1},
                )
            if updated.rowcount != 1:
                raise ValueError("Review fixture document revision conflict")

        for item in payload["idempotency"]:
            conn.execute(
                """INSERT INTO public.review_idempotency_keys
                   (id,company_id,actor_user_id,document_id,idempotency_key,request_hash,
                    audit_event_id,response_status,response_body,created_at,updated_at,expires_at)
                   VALUES (%(id)s,%(company_id)s,%(actor_user_id)s,%(document_id)s,
                    %(idempotency_key)s,%(request_hash)s,%(audit_event_id)s,%(response_status)s,
                    %(response_body)s,%(created_at)s,%(updated_at)s,%(expires_at)s)""",
                {**item, "response_body": Jsonb(item["response_body"])},
            )

        if _fixture_counts(conn, payload) != expected:
            raise RuntimeError("Human-review fixture count verification failed")
    return "inserted"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ack", required=True)
    parser.add_argument("--no-active-consumers", action="store_true")
    args = parser.parse_args()
    dsn = os.environ.get("HUMAN_REVIEW_TEST_DSN")
    if not dsn:
        raise SystemExit("HUMAN_REVIEW_TEST_DSN is required")
    with psycopg.connect(dsn) as connection:
        result = seed(connection, args.ack, no_active_consumers=args.no_active_consumers)
    print(f"Synthetic human-review fixtures: {result}")


if __name__ == "__main__":
    main()
