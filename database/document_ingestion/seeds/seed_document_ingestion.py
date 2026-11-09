"""Safe fixture loader for an explicitly disposable PostgreSQL database.

No auth fixture creation, object upload, event dispatch, job reset, or deletion.
Credentials come from INGESTION_TEST_DSN, never from a committed literal.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
import re
from pathlib import Path

import psycopg
from psycopg.conninfo import conninfo_to_dict

ROOT = Path(__file__).resolve().parent
A = "11111111-1111-1111-1111-111111111111"
B = "11111111-1111-1111-1111-222222222222"
ADMIN = "22222222-2222-2222-2222-222222222222"
OPERATOR = "33333333-3333-3333-3333-333333333333"
T0 = "2026-09-03T12:00:00Z"


def disposable_name(dsn: str, acknowledgement: str) -> str:
    info = conninfo_to_dict(dsn)
    name = info.get("dbname", "")
    # Never accept inherited host/db defaults, external targets or service files.
    if (info.get("service") or info.get("host") not in {"127.0.0.1", "localhost", "::1"}
            or info.get("hostaddr", "127.0.0.1") not in {"127.0.0.1", "::1"}):
        raise ValueError("Specify an explicit loopback test host; service/default targets are refused")
    if not re.fullmatch(r"docusense_ingestion_test_[a-z0-9_]+", name) or acknowledgement != name:
        raise ValueError("Explicit matching disposable test database acknowledgement is required")
    return name


def fixture_payload(directory: Path | None = None) -> dict:
    from PIL import Image
    from pypdf import PdfReader

    directory = (directory or ROOT / "document-ingestion-fixtures").resolve()
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("scope") != "DATABASE_ONLY" or manifest.get("version") != 1:
        raise ValueError("Unsupported fixture manifest")
    files = {}
    for entry in manifest["files"]:
        path = (directory / entry["path"]).resolve()
        if path.parent != directory or entry["key"] in files:
            raise ValueError("Fixture paths must be unique basenames inside the fixture directory")
        data = path.read_bytes()
        if len(data) != entry["file_size_bytes"] or hashlib.sha256(data).hexdigest() != entry["file_hash"]:
            raise ValueError("Fixture checksum/size mismatch")
        mime = entry["mime_type"]
        if mime == "application/pdf":
            if not data.startswith(b"%PDF-") or len(PdfReader(io.BytesIO(data), strict=True).pages) != 1:
                raise ValueError("Invalid synthetic PDF fixture")
        elif mime in {"image/png", "image/jpeg"}:
            with Image.open(io.BytesIO(data)) as picture:
                if picture.format != {"image/png": "PNG", "image/jpeg": "JPEG"}[mime]:
                    raise ValueError("Fixture MIME/signature mismatch")
                picture.verify()
        else:
            raise ValueError("Unsupported fixture MIME type")
        files[entry["key"]] = dict(entry, bytes_base64=base64.b64encode(data).decode("ascii"))
    if set(files) != {"F1", "F2", "F3", "F4"}:
        raise ValueError("Expected exactly F1 through F4")

    documents, jobs = [], []
    cases = [(A, ADMIN, "F1", "commercial_invoice"), (A, OPERATOR, "F2", "purchase_order"),
             (A, ADMIN, "F3", "packing_list"), (B, None, "F4", "commercial_invoice"),
             (A, ADMIN, "F1", "commercial_invoice"), (B, None, "F1", "commercial_invoice")]
    for n, (tenant, uploader, key, doc_type) in enumerate(cases, 1):
        asset = files[key]
        doc_id = f"66666666-6666-4666-8666-{n:012d}"
        doc = dict(id=doc_id, company_id=tenant, uploaded_by=uploader, file_name=asset["path"],
                   s3_url=f"s3://docusense-db-fixtures/{tenant}/{doc_id}/{asset['path']}",
                   file_size_bytes=asset["file_size_bytes"], file_hash=asset["file_hash"],
                   mime_type=asset["mime_type"], doc_type=doc_type, status="queued",
                   overall_confidence=None, created_at=T0, updated_at=T0)
        job = dict(id=f"77777777-7777-4777-8777-{n:012d}", document_id=doc_id,
                   status="queued", current_stage="upload", progress_percentage=0, attempt_count=0,
                   next_attempt_at=None, lease_expires_at=None, error_code=None, error_message=None,
                   started_at=None, finished_at=None, created_at=T0, updated_at=T0)
        if n == 2:
            doc.update(status="vectorizing")
            job.update(status="processing", current_stage="vectorizing", progress_percentage=60,
                       attempt_count=1, started_at=T0, lease_expires_at="2026-09-03T12:05:00Z")
        elif n == 3:
            doc.update(status="pending_review", overall_confidence="82.50")
            job.update(status="completed", current_stage="extracting", progress_percentage=100,
                       attempt_count=1, started_at=T0, finished_at="2026-09-03T12:01:00Z")
        elif n == 4:
            doc.update(status="failed")
            job.update(status="failed", current_stage="partitioning", progress_percentage=20,
                       attempt_count=4, started_at=T0, finished_at="2026-09-03T12:01:00Z",
                       error_code="PROCESSING_FAILED", error_message="Synthetic processing failure")
        documents.append(doc)
        jobs.append(job)
    return dict(scope="DATABASE_ONLY", files=list(files.values()), documents=documents, jobs=jobs)


def seed(conn: psycopg.Connection, acknowledgement: str, *, no_active_consumers: bool,
         payload: dict | None = None) -> None:
    if not no_active_consumers:
        raise ValueError("Confirm that this disposable database has no active consumers")
    name = disposable_name(conn.info.dsn, acknowledgement)
    # Validate bytes before opening a write transaction.
    payload = fixture_payload() if payload is None else payload
    with conn.transaction():
        if conn.execute("SELECT current_database()").fetchone()[0] != name:
            raise ValueError("Connected database differs from the acknowledged target")
        conn.execute("SELECT set_config('docusense.disposable_database', %s, true)", (name,))
        conn.execute("SELECT set_config('docusense.no_active_consumers', 'confirmed', true)")
        conn.execute("SELECT set_config('docusense.ingestion_seed_payload', %s, true)", (json.dumps(payload),))
        conn.execute((ROOT / "seed-document-ingestion.sql").read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acknowledge-disposable", required=True)
    parser.add_argument("--no-active-consumers", action="store_true", required=True)
    args = parser.parse_args()
    dsn = os.environ.get("INGESTION_TEST_DSN", "")
    disposable_name(dsn, args.acknowledge_disposable)
    with psycopg.connect(dsn, autocommit=True, connect_timeout=5) as conn:
        seed(conn, args.acknowledge_disposable, no_active_consumers=args.no_active_consumers)
    print("Six document/job fixture pairs validated; absent pairs inserted, exact pairs unchanged.")


if __name__ == "__main__":
    main()
