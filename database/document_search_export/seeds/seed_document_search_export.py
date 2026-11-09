"""Guarded deterministic seeder for document-search-export fixtures.

The loader never creates or repairs auth, ingestion, RAG, or review parents. It
requires a loopback disposable target, explicit acknowledgement/no-consumer
confirmation, exact Feature 05 head, and all required approved source aggregates.
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


def load_fixture_module():
    path = ROOT / "generate_fixtures.py"
    spec = importlib.util.spec_from_file_location("document_search_export_fixtures", path)
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
    if not re.fullmatch(r"docusense_export_test_[a-z0-9_]+", name) or acknowledgement != name:
        raise ValueError("Exact disposable export database acknowledgement is required")
    return name


def validate_payload(payload: dict) -> None:
    manifest = json.loads(
        (ROOT / "document-search-export-fixtures" / "manifest.json").read_text(encoding="utf-8")
    )
    if payload.get("scope") != "DATABASE_ONLY" or payload.get("version") != 1:
        raise ValueError("Unsupported fixture payload")
    if payload.get("synthetic_only") is not True or manifest.get("synthetic_only") is not True:
        raise ValueError("Only synthetic database fixtures are permitted")
    if len(payload["jobs"]) != manifest["counts"]["export_jobs"]:
        raise ValueError("Export job manifest count mismatch")
    if len(payload["memberships"]) != manifest["counts"]["export_job_documents"]:
        raise ValueError("Membership manifest count mismatch")
    ids = [row["id"] for row in payload["jobs"]]
    if len(ids) != len(set(ids)) or {m["export_job_id"] for m in payload["memberships"]} != set(ids):
        raise ValueError("Fixture IDs/membership references are not exact")
    if any(m["source_value_hash"] != "DATABASE_COMPUTED" for m in payload["memberships"]):
        raise ValueError("Fixture source hashes must use the reviewed database-canonical policy")


def _verify_parents(conn: psycopg.Connection, payload: dict) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for parent in sorted(payload["required_parents"], key=lambda row: row["document_id"]):
        row = conn.execute(
            """SELECT d.company_id::text,u.company_id::text,u.role,d.doc_type,d.status,
                      d.review_revision,pj.status,pj.progress_percentage,er.status,
                      public.compute_export_source_value_hash(d.id)::text
               FROM public.documents d
               JOIN public.processing_jobs pj ON pj.document_id=d.id
               JOIN public.extraction_runs er ON er.document_id=d.id
               JOIN public.invoices i ON i.document_id=d.id AND i.extraction_run_id=er.id
               JOIN public.users u ON u.id=%(actor_user_id)s
               WHERE d.id=%(document_id)s
               FOR KEY SHARE OF d,pj,er,i,u""",
            parent,
        ).fetchone()
        if row is None or row[:9] != (
            parent["company_id"], parent["company_id"], row[2], "commercial_invoice",
            "approved", parent["review_revision"], "completed", 100, "completed"
        ) or row[2] not in {"admin", "operator"} or row[9] is None:
            raise ValueError("Required approved tenant-safe export parent graph is missing")
        hashes[parent["document_id"]] = row[9]
    return hashes


def _existing_fixture_state(conn: psycopg.Connection, payload: dict) -> str | None:
    ids = [row["id"] for row in payload["jobs"]]
    rows = conn.execute(
        """SELECT id::text,request_hash::text FROM public.export_jobs
           WHERE id=ANY(%s::uuid[]) ORDER BY id""",
        (ids,),
    ).fetchall()
    if not rows:
        return None
    expected = sorted((row["id"], row["request_hash"]) for row in payload["jobs"])
    actual = sorted(rows)
    members = conn.execute(
        "SELECT count(*) FROM public.export_job_documents WHERE export_job_id=ANY(%s::uuid[])",
        (ids,),
    ).fetchone()[0]
    if actual != expected or members != len(payload["memberships"]):
        raise ValueError("Conflicting or partial document-search-export fixture graph")
    return "unchanged"


def _insert_acceptance(conn: psycopg.Connection, job: dict, source_hash: str) -> None:
    sync = job["mode"] == "synchronous"
    conn.execute(
        """INSERT INTO public.export_jobs
           (id,company_id,requested_by_user_id,format,mode,status,current_stage,
            progress_percentage,selection_type,schema_version,criteria_json,criteria_hash,
            request_hash,idempotency_key_hash,selected_document_count,request_id,
            started_at,created_at,updated_at)
           VALUES (%(id)s,%(company_id)s,%(requested_by_user_id)s,%(format)s,%(mode)s,
            %(status)s,%(stage)s,0,%(selection_type)s,%(schema_version)s,%(criteria_json)s,
            %(criteria_hash)s,%(request_hash)s,%(idempotency_key_hash)s,1,%(request_id)s,
            %(started_at)s,%(created_at)s,%(created_at)s)""",
        {
            **job,
            "status": "processing" if sync else "queued",
            "stage": "generating" if sync else "accepted",
            "started_at": job["created_at"] if sync else None,
            "criteria_json": Jsonb(job["criteria_json"]),
        },
    )
    conn.execute(
        """INSERT INTO public.export_job_documents
           (export_job_id,document_id,review_revision,ordinal,source_value_hash,created_at)
           VALUES (%s,%s,%s,0,%s,%s)""",
        (job["id"], job["document_id"], job["review_revision"], source_hash, job["created_at"]),
    )


def _claim(conn: psycopg.Connection, job: dict) -> None:
    conn.execute(
        """UPDATE public.export_jobs SET status='processing',current_stage='generating',
             progress_percentage=10,attempt_count=attempt_count+1,next_attempt_at=NULL,
             lease_token=gen_random_uuid(),lease_expires_at=CURRENT_TIMESTAMP+INTERVAL '15 minutes',
             started_at=COALESCE(started_at,CURRENT_TIMESTAMP),error_code=NULL,error_message=NULL
           WHERE id=%s""",
        (job["id"],),
    )


def _complete(conn: psycopg.Connection, job: dict) -> None:
    extension = "zip" if job["mode"] == "asynchronous" else job["format"]
    content_type = {
        "zip": "application/zip",
        "csv": "text/csv; charset=utf-8",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "json": "application/json",
    }[extension]
    conn.execute(
        """UPDATE public.export_jobs SET status='completed',current_stage='completed',
             progress_percentage=100,exported_document_count=selected_document_count,row_count=2,
             artifact_object_key=%s,artifact_file_name=%s,artifact_content_type=%s,
             artifact_size_bytes=128,artifact_sha256=%s,
             completed_at=CURRENT_TIMESTAMP,artifact_expires_at=CURRENT_TIMESTAMP+INTERVAL '7 days',
             lease_token=NULL,lease_expires_at=NULL
           WHERE id=%s""",
        (
            f"database-fixtures/{job['id']}/export.{extension}",
            f"synthetic-export-{job['id'][-4:]}.{extension}",
            content_type,
            load_fixture_module().canonical_sha({"fixture": job["id"]}),
            job["id"],
        ),
    )


def _advance_target(conn: psycopg.Connection, job: dict) -> None:
    target = job["target_state"]
    if job["mode"] == "asynchronous" and target != "queued":
        _claim(conn, job)
    if target == "completed":
        _complete(conn, job)
    elif target == "processing" or target == "queued":
        return
    elif target == "failed_source_changed":
        conn.execute(
            """UPDATE public.export_jobs SET status='failed',current_stage='generating',
                 progress_percentage=10,exported_document_count=0,row_count=0,
                 failed_at=CURRENT_TIMESTAMP,error_code='EXPORT_SOURCE_CHANGED',
                 error_message='Accepted source changed before generation',
                 lease_token=NULL,lease_expires_at=NULL WHERE id=%s""",
            (job["id"],),
        )
    elif target == "retry":
        conn.execute(
            """UPDATE public.export_jobs SET status='queued',current_stage='accepted',
                 progress_percentage=0,exported_document_count=0,row_count=0,
                 next_attempt_at=CURRENT_TIMESTAMP+INTERVAL '10 minutes',
                 error_code='EXPORT_STORAGE_UNAVAILABLE',
                 error_message='Synthetic recoverable storage failure',
                 lease_token=NULL,lease_expires_at=NULL WHERE id=%s""",
            (job["id"],),
        )
    elif target == "expired":
        _complete(conn, job)
        conn.execute(
            """UPDATE public.export_jobs SET status='expired',artifact_object_key=NULL,
                 expired_at=artifact_expires_at WHERE id=%s""",
            (job["id"],),
        )
    else:
        raise ValueError(f"Unsupported fixture target state: {target}")


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
        if conn.execute("SELECT current_database()").fetchone()[0] != name:
            raise ValueError("Connected database differs from acknowledged target")
        conn.execute("SELECT set_config('docusense.disposable_database',%s,true)", (name,))
        conn.execute("SELECT set_config('docusense.no_active_consumers','confirmed',true)")
        conn.execute("SELECT pg_advisory_xact_lock(hashtextextended('document-search-export-fixtures',0))")
        head = conn.execute(
            "SELECT array_agg(version_num::text ORDER BY version_num) FROM public.alembic_version"
        ).fetchone()[0]
        if head != ["20260907_0006"]:
            raise ValueError("Seeder requires canonical Feature 05 head 20260907_0006")
        existing = _existing_fixture_state(conn, payload)
        if existing:
            return existing
        hashes = _verify_parents(conn, payload)
        for job in payload["jobs"]:
            _insert_acceptance(conn, job, hashes[job["document_id"]])
        conn.execute("SET CONSTRAINTS trg_export_jobs_membership_commit, trg_export_job_documents_membership_commit IMMEDIATE")
        for job in payload["jobs"]:
            _advance_target(conn, job)
    return "inserted"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", default=os.getenv("DOCUSENSE_TEST_DATABASE_URL"))
    parser.add_argument("--acknowledge-database", required=True)
    parser.add_argument("--no-active-consumers", action="store_true")
    args = parser.parse_args()
    if not args.dsn:
        parser.error("--dsn or DOCUSENSE_TEST_DATABASE_URL is required")
    with psycopg.connect(args.dsn) as conn:
        print(seed(conn, args.acknowledge_database, no_active_consumers=args.no_active_consumers))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
