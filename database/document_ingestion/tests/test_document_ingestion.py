"""Database-only acceptance tests. No application/worker implementation.

Offline checks always run. PostgreSQL cases require an EMPTY disposable database
and three explicit environment settings documented in this feature's README.
Each live test empties only records created by this suite, never an existing DB.
"""
from __future__ import annotations

import ast
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile
import threading
import time
import uuid

from alembic import command
from alembic.config import Config
import pglast
import psycopg
from psycopg import sql
import pytest
import sqlalchemy as sa

from seed_document_ingestion import A, B, ADMIN, OPERATOR, ROOT, disposable_name, fixture_payload, seed

AUTH = ROOT.parents[1] / "auth"
MIGRATIONS = ROOT.parent / "migrations"
TESTS = Path(__file__).resolve().parent
SQL_PATH = MIGRATIONS / "20260903_create_document_ingestion.sql"
REV_PATH = MIGRATIONS / "20260903_0002_document_ingestion_migration.py"
NEW_REVISION = "20260903_0002"
PARENT_REVISION = "20260901_0001"
D1 = "66666666-6666-4666-8666-000000000001"
J1 = "77777777-7777-4777-8777-000000000001"


def load_revision():
    spec = importlib.util.spec_from_file_location("ingestion_revision", REV_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_offline_python_syntax_and_revision_identity():
    for path in sorted([*ROOT.glob("*.py"), *MIGRATIONS.glob("*.py"), *TESTS.glob("*.py")]):
        ast.parse(path.read_text(encoding="utf-8"), filename=path.name)
    revision = load_revision()
    assert revision.revision == NEW_REVISION
    assert revision.down_revision == PARENT_REVISION
    assert "BEGIN;" not in revision.upgrade_sql().split("DO $preflight$")[0]
    assert "CREATE TABLE public.documents" in revision.upgrade_sql()


def test_offline_postgres_syntax_and_object_inventory():
    tree = json.loads(pglast.parser.parse_sql_json(SQL_PATH.read_text(encoding="utf-8")))
    statements = [item["stmt"] for item in tree["stmts"]]
    assert sum("CreateStmt" in item for item in statements) == 2
    assert sum("CreateTrigStmt" in item for item in statements) == 5
    assert sum("CreateFunctionStmt" in item for item in statements) == 3
    assert sum("IndexStmt" in item for item in statements) == 8
    assert sum("TransactionStmt" in item for item in statements) == 2
    tables = [item["CreateStmt"] for item in statements if "CreateStmt" in item]
    assert [sum("ColumnDef" in item for item in table["tableElts"]) for table in tables] == [13, 14]
    pglast.parse_sql((ROOT / "seed-document-ingestion.sql").read_text(encoding="utf-8"))
    assert len(pglast.parse_plpgsql(SQL_PATH.read_text(encoding="utf-8"))) == 5
    assert len(pglast.parse_plpgsql((ROOT / "seed-document-ingestion.sql").read_text(encoding="utf-8"))) == 1
    # Parsing PL/pgSQL syntax still does not prove live catalog or concurrency behavior.


def test_offline_real_fixture_bytes_and_matrix():
    payload = fixture_payload()
    assert len(payload["files"]) == 4
    assert len(payload["documents"]) == len(payload["jobs"]) == 6
    docs, jobs = payload["documents"], payload["jobs"]
    assert docs[0]["file_hash"] == docs[4]["file_hash"] == docs[5]["file_hash"]
    assert docs[0]["company_id"] == docs[4]["company_id"] != docs[5]["company_id"]
    assert {d["mime_type"] for d in docs} == {"application/pdf", "image/png", "image/jpeg"}
    assert {d["doc_type"] for d in docs} == {"commercial_invoice", "purchase_order", "packing_list"}
    assert [job["attempt_count"] for job in jobs] == [0, 1, 1, 4, 0, 0]
    assert docs[2]["overall_confidence"] == "82.50"


@pytest.mark.parametrize("dsn,ack", [
    ("", ""), ("host=localhost dbname=production", "production"),
    ("host=db.example.com dbname=docusense_ingestion_test_demo", "docusense_ingestion_test_demo"),
    ("host=localhost dbname=docusense_ingestion_test_demo", "wrong"),
])
def test_offline_seed_target_guards(dsn, ack):
    with pytest.raises(ValueError):
        disposable_name(dsn, ack)


def test_offline_manifest_tampering_rejected(tmp_path):
    fixture_dir = ROOT / "document-ingestion-fixtures"
    for path in fixture_dir.iterdir():
        shutil.copy2(path, tmp_path / path.name)
    # Test-owned temp data only, not committed fixtures.
    with (tmp_path / "synthetic-order.png").open("ab") as stream:
        stream.write(b"tampered")
    with pytest.raises(ValueError, match="checksum"):
        fixture_payload(tmp_path)


class Database:
    def __init__(self, dsn, name, scripts):
        self.dsn, self.name, self.scripts = dsn, name, scripts

    def connect(self, **kwargs):
        return psycopg.connect(self.dsn, autocommit=True, connect_timeout=5,
                               options="-c statement_timeout=10000 -c lock_timeout=2000", **kwargs)

    def migrate(self, target=NEW_REVISION, *, down=False):
        engine = sa.create_engine("postgresql+psycopg://", creator=lambda: self.connect())
        try:
            with engine.connect() as connection:
                # SQLAlchemy owns the transaction, including Alembic's version row.
                connection = connection.execution_options(isolation_level="READ COMMITTED")
                with connection.begin():
                    connection.execute(sa.text("SELECT set_config('docusense.disposable_database', :name, true)"), {"name": self.name})
                    connection.exec_driver_sql("SET LOCAL search_path = public")
                    config = Config()
                    config.set_main_option("script_location", str(self.scripts).replace("%", "%%"))
                    config.attributes["connection"] = connection
                    (command.downgrade if down else command.upgrade)(config, target)
        finally:
            engine.dispose()


@pytest.fixture(scope="session")
def database():
    dsn = os.environ.get("INGESTION_TEST_DSN")
    if not dsn:
        pytest.skip("No isolated PostgreSQL target supplied; live database validation NOT performed")
    name = disposable_name(dsn, os.environ.get("INGESTION_TEST_ACK", ""))
    if os.environ.get("INGESTION_TEST_NO_CONSUMERS") != "1":
        pytest.fail("Set INGESTION_TEST_NO_CONSUMERS=1 only for a database without active consumers")
    with tempfile.TemporaryDirectory(prefix="docusense-ingestion-alembic-") as directory:
        scripts = Path(directory)
        versions = scripts / "versions"
        versions.mkdir()
        shutil.copy2(TESTS / "alembic_env.py", scripts / "env.py")
        for source in [AUTH / "migrations" / "20260901_0001_auth_tenancy_migration.py", REV_PATH, SQL_PATH]:
            shutil.copy2(source, versions / source.name)
        db = Database(dsn, name, scripts)
        with db.connect() as conn:
            objects = conn.execute("""SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname NOT IN ('pg_catalog', 'information_schema') AND n.nspname NOT LIKE 'pg_toast%'
                  AND c.relkind IN ('r','p','v','m','S','f')""").fetchall()
            if objects:
                pytest.fail("Refusing a nonempty database. Supply a newly provisioned disposable database")
        db.migrate(PARENT_REVISION)
        with db.connect() as conn:
            conn.execute((AUTH / "seeds" / "seed_auth_tenancy.sql").read_text(encoding="utf-8"))
            parent_rows = {table: conn.execute(sql.SQL("SELECT jsonb_agg(to_jsonb(t) ORDER BY id) FROM public.{} t").format(
                sql.Identifier(table))).fetchone()[0] for table in ("companies", "users", "api_keys")}
            helper_before = conn.execute("SELECT pg_get_functiondef('public.update_updated_at_column()'::regprocedure)").fetchone()[0]
        db.migrate()
        with db.connect() as conn:
            for table, snapshot in parent_rows.items():
                assert conn.execute(sql.SQL("SELECT jsonb_agg(to_jsonb(t) ORDER BY id) FROM public.{} t").format(
                    sql.Identifier(table))).fetchone()[0] == snapshot
            assert conn.execute("SELECT pg_get_functiondef('public.update_updated_at_column()'::regprocedure)").fetchone()[0] == helper_before
        yield db
        # Keep the test database for inspection; never DROP DATABASE automatically.


@pytest.fixture
def db(database):
    with database.connect() as conn:
        # This database was proved empty before this suite created its tables.
        with conn.transaction():
            conn.execute("DELETE FROM public.documents")
            conn.execute("DELETE FROM public.companies")
        conn.execute((AUTH / "seeds" / "seed_auth_tenancy.sql").read_text(encoding="utf-8"))
        seed(conn, database.name, no_active_consumers=True)
    return database


def row(conn, table, identifier):
    return conn.execute(sql.SQL("SELECT to_jsonb(t) FROM public.{} t WHERE id=%s").format(
        sql.Identifier(table)), (identifier,)).fetchone()[0]


def insert_record(conn, table, record):
    columns = list(record)
    conn.execute(sql.SQL("INSERT INTO public.{} ({}) VALUES ({})").format(
        sql.Identifier(table), sql.SQL(",").join(map(sql.Identifier, columns)),
        sql.SQL(",").join(sql.Placeholder() for _ in columns)), tuple(record.values()))


def pair(tenant=A, uploader=None, *, file_hash=None):
    doc = dict(fixture_payload()["documents"][0])
    doc_id = str(uuid.uuid4())
    doc.update(id=doc_id, company_id=tenant, uploaded_by=uploader,
               file_hash=file_hash or hashlib.sha256(doc_id.encode()).hexdigest(),
               s3_url=f"s3://docusense-db-fixtures/{tenant}/{doc_id}/test.pdf")
    job = dict(fixture_payload()["jobs"][0], id=str(uuid.uuid4()), document_id=doc_id)
    return doc, job


def insert_pair(conn, document, job):
    insert_record(conn, "documents", document)
    insert_record(conn, "processing_jobs", job)


@contextmanager
def violation(conn, state="23514"):
    with pytest.raises(psycopg.Error) as error:
        with conn.transaction():
            yield
    assert error.value.sqlstate == state


def lock_pair(conn, doc_id, *, skip=False):
    clause = " SKIP LOCKED" if skip else ""
    parent = conn.execute("SELECT id FROM public.documents WHERE id=%s FOR UPDATE" + clause, (doc_id,)).fetchone()
    if not parent:
        return False
    return conn.execute("SELECT id FROM public.processing_jobs WHERE document_id=%s FOR UPDATE" + clause,
                        (doc_id,)).fetchone() is not None


def claim(conn, doc_id):
    # SQL-level protocol exercised by tests only, not a production dispatcher.
    with conn.transaction():
        if not lock_pair(conn, doc_id, skip=True):
            return None
        return conn.execute("""UPDATE public.processing_jobs SET status='processing',
            attempt_count=attempt_count+1, started_at=COALESCE(started_at, clock_timestamp()),
            lease_expires_at=clock_timestamp()+interval '60 seconds', next_attempt_at=NULL
            WHERE document_id=%s AND status='queued' AND attempt_count<4
              AND (next_attempt_at IS NULL OR next_attempt_at<=clock_timestamp())
            RETURNING attempt_count""", (doc_id,)).fetchone()


def checkpoint(conn, doc_id, attempt):
    with conn.transaction():
        lock_pair(conn, doc_id)
        return conn.execute("""UPDATE public.processing_jobs SET current_stage='chunking', progress_percentage=40
            WHERE document_id=%s AND status='processing' AND attempt_count=%s
              AND lease_expires_at > clock_timestamp()""", (doc_id, attempt)).rowcount


def renew(conn, doc_id, attempt):
    with conn.transaction():
        lock_pair(conn, doc_id)
        return conn.execute("""UPDATE public.processing_jobs SET lease_expires_at=clock_timestamp()+interval '60 seconds'
            WHERE document_id=%s AND status='processing' AND attempt_count=%s
              AND lease_expires_at>clock_timestamp()""", (doc_id, attempt)).rowcount


def finalize(conn, doc_id, attempt):
    with conn.transaction():
        lock_pair(conn, doc_id)
        changed = conn.execute("""UPDATE public.processing_jobs SET status='completed',current_stage='extracting',
            progress_percentage=100,finished_at=clock_timestamp(),lease_expires_at=NULL,next_attempt_at=NULL
            WHERE document_id=%s AND status='processing' AND attempt_count=%s
              AND lease_expires_at>clock_timestamp()""", (doc_id, attempt)).rowcount
        if changed:
            conn.execute("UPDATE public.documents SET status='pending_review' WHERE id=%s", (doc_id,))
        return changed


def advisory_key(tenant, file_hash):
    return int.from_bytes(hashlib.sha256(
        f"document-ingestion:{str(tenant).lower()}:{file_hash.lower()}".encode()).digest()[:8], "big", signed=True)


def accept(conn, document, job, *, deliberate=False, locked=None, release=None):
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (advisory_key(document["company_id"], document["file_hash"]),))
        if locked:
            locked.set()
        if release and not release.wait(5):
            raise TimeoutError("Test lock synchronization timed out")
        # Separate statement obtains a fresh READ COMMITTED snapshot after waiting.
        exists = conn.execute("SELECT id FROM public.documents WHERE company_id=%s AND file_hash=%s",
                              (document["company_id"], document["file_hash"])).fetchone()
        if exists and not deliberate:
            return False
        insert_pair(conn, document, job)
        return True


def test_db01_catalog_and_parent_preservation(db):
    with db.connect() as conn:
        columns = conn.execute("""SELECT table_name,column_name,data_type,is_nullable,column_default,
            character_maximum_length,numeric_precision,numeric_scale FROM information_schema.columns
            WHERE table_schema='public' AND table_name IN ('documents','processing_jobs')
            ORDER BY table_name,ordinal_position""").fetchall()
        assert len(columns) == 27
        assert sum(c[0] == "documents" for c in columns) == 13
        assert not any(c[0] == "processing_jobs" and c[1] == "company_id" for c in columns)
        confidence = next(c for c in columns if c[1] == "overall_confidence")
        assert confidence[2:4] == ("numeric", "YES") and confidence[6:] == (5, 2)
        assert all(c[2] == "timestamp with time zone" for c in columns if c[1].endswith("_at"))
        assert conn.execute("SELECT count(*) FROM public.companies").fetchone()[0] == 3
        assert conn.execute("SELECT count(*) FROM public.users").fetchone()[0] == 3
        assert conn.execute("SELECT count(*) FROM pg_trigger WHERE NOT tgisinternal AND tgrelid IN ('public.documents'::regclass,'public.processing_jobs'::regclass)").fetchone()[0] == 5
        expected_columns = {
            "documents": [
                ("id", "uuid", False), ("company_id", "uuid", False), ("uploaded_by", "uuid", True),
                ("file_name", "character varying(255)", False), ("s3_url", "text", False),
                ("file_size_bytes", "integer", False), ("file_hash", "character varying(64)", False),
                ("mime_type", "character varying(127)", False), ("doc_type", "character varying(50)", False),
                ("status", "character varying(30)", False), ("overall_confidence", "numeric(5,2)", True),
                ("created_at", "timestamp with time zone", False), ("updated_at", "timestamp with time zone", False)],
            "processing_jobs": [
                ("id", "uuid", False), ("document_id", "uuid", False), ("status", "character varying(20)", False),
                ("current_stage", "character varying(30)", False), ("progress_percentage", "smallint", False),
                ("attempt_count", "smallint", False), ("next_attempt_at", "timestamp with time zone", True),
                ("lease_expires_at", "timestamp with time zone", True), ("error_code", "character varying(100)", True),
                ("error_message", "text", True), ("started_at", "timestamp with time zone", True),
                ("finished_at", "timestamp with time zone", True), ("created_at", "timestamp with time zone", False),
                ("updated_at", "timestamp with time zone", False)],
        }
        for table, expected in expected_columns.items():
            actual = conn.execute("""SELECT a.attname,format_type(a.atttypid,a.atttypmod),NOT a.attnotnull
                FROM pg_attribute a WHERE a.attrelid=%s::regclass AND a.attnum>0 AND NOT a.attisdropped
                ORDER BY a.attnum""", ("public."+table,)).fetchall()
            assert actual == expected
        defaults = {(r[0], r[1]): r[4] for r in columns if r[4] is not None}
        assert defaults == {
            ("documents", "id"): "gen_random_uuid()", ("documents", "doc_type"): "'commercial_invoice'::character varying",
            ("documents", "status"): "'queued'::character varying", ("documents", "created_at"): "now()",
            ("documents", "updated_at"): "now()", ("processing_jobs", "id"): "gen_random_uuid()",
            ("processing_jobs", "status"): "'queued'::character varying", ("processing_jobs", "current_stage"): "'upload'::character varying",
            ("processing_jobs", "progress_percentage"): "0", ("processing_jobs", "attempt_count"): "0",
            ("processing_jobs", "created_at"): "now()", ("processing_jobs", "updated_at"): "now()",
        }
        foreign_keys = conn.execute("""SELECT conname,confdeltype,confupdtype,condeferrable
            FROM pg_constraint WHERE conrelid IN ('public.documents'::regclass,'public.processing_jobs'::regclass)
            AND contype='f' ORDER BY conname""").fetchall()
        assert foreign_keys == [("fk_documents_company_id", "c", "a", False),
                                ("fk_documents_uploaded_by", "n", "a", False),
                                ("fk_processing_jobs_document_id", "c", "a", False)]


def test_db02_repeat_revision_and_collision(db):
    with db.connect() as conn:
        before = row(conn, "documents", D1)
    db.migrate()
    with db.connect() as conn:
        assert row(conn, "documents", D1) == before
        # Unversioned replay must fail, never silently skip existing feature objects.
        with pytest.raises(psycopg.Error):
            with conn.transaction():
                conn.execute(load_revision().upgrade_sql())


@pytest.mark.parametrize("size,valid", [(0, False), (1, True), (10485760, True), (10485761, False)])
def test_db03_size_boundaries(db, size, valid):
    doc, _ = pair()
    doc["file_size_bytes"] = size
    with db.connect() as conn:
        if valid:
            insert_record(conn, "documents", doc)
        else:
            with violation(conn):
                insert_record(conn, "documents", doc)


@pytest.mark.parametrize("value,valid", [(None, True), ("0", True), ("100", True), ("82.555", True),
                                           ("-0.01", False), ("100.01", False), ("NaN", False)])
def test_db03_confidence_boundaries(db, value, valid):
    with db.connect() as conn:
        if valid:
            conn.execute("UPDATE public.documents SET overall_confidence=%s WHERE id=%s", (value, D1))
            if value == "82.555":
                assert conn.execute("SELECT overall_confidence FROM public.documents WHERE id=%s", (D1,)).fetchone()[0] == Decimal("82.56")
        else:
            with violation(conn):
                conn.execute("UPDATE public.documents SET overall_confidence=%s WHERE id=%s", (value, D1))


@pytest.mark.parametrize("field,value,state", [
    ("file_name", " ", "23514"), ("file_name", "..", "23514"), ("file_name", "a/b.pdf", "23514"),
    ("file_name", "a\\b.pdf", "23514"), ("file_name", "a\nb.pdf", "23514"), ("file_name", "x"*256, "22001"),
    ("file_hash", "ABC"*21+"A", "23514"), ("file_hash", "f"*63, "23514"),
    ("mime_type", "text/plain", "23514"), ("doc_type", "unknown", "23514"), ("status", "processing", "23514"),
    ("s3_url", "https://example.com/file.pdf?signature=x", "23514"),
    ("s3_url", f"s3://bucket/{B}/{D1}/x.pdf", "23514"), ("file_name", None, "23502"),
])
def test_db04_metadata_guards(db, field, value, state):
    doc, _ = pair()
    doc[field] = value
    with db.connect() as conn, violation(conn, state):
        insert_record(conn, "documents", doc)


def test_db05_foreign_keys_and_tenant_guard(db):
    with db.connect() as conn:
        for tenant, uploader, state in [(str(uuid.uuid4()), None, "23503"), (A, str(uuid.uuid4()), "23503"), (B, ADMIN, "23514")]:
            doc, _ = pair(tenant, uploader)
            with violation(conn, state):
                insert_record(conn, "documents", doc)
        doc, job = pair(B, None)
        insert_pair(conn, doc, job)
        job["id"], job["document_id"] = str(uuid.uuid4()), str(uuid.uuid4())
        with violation(conn, "23503"):
            insert_record(conn, "processing_jobs", job)


def test_db06_uploader_share_lock(db):
    doc, _ = pair(A, ADMIN)
    with db.connect() as first, db.connect() as second:
        with first.transaction():
            insert_record(first, "documents", doc)
            second.execute("SET lock_timeout='100ms'")
            with violation(second, "55P03"):
                second.execute("UPDATE public.users SET company_id=%s WHERE id=%s", (B, ADMIN))
        # Also prove an insert sees a concurrently committed changed tenant.
        with second.transaction():
            second.execute("UPDATE public.users SET company_id=%s WHERE id=%s", (B, OPERATOR))
        other, _ = pair(A, OPERATOR)
        with violation(first):
            insert_record(first, "documents", other)


def test_db07_deletion_actions(db):
    with db.connect() as conn:
        b_count = conn.execute("SELECT count(*) FROM public.documents WHERE company_id=%s", (B,)).fetchone()[0]
        conn.execute("DELETE FROM public.users WHERE id=%s", (ADMIN,))
        assert row(conn, "documents", D1)["uploaded_by"] is None
        conn.execute("DELETE FROM public.documents WHERE id=%s", (D1,))
        assert conn.execute("SELECT count(*) FROM public.processing_jobs WHERE id=%s", (J1,)).fetchone()[0] == 0
        conn.execute("DELETE FROM public.companies WHERE id=%s", (A,))
        assert conn.execute("SELECT count(*) FROM public.documents WHERE company_id=%s", (B,)).fetchone()[0] == b_count
        assert conn.execute("SELECT count(*) FROM public.processing_jobs").fetchone()[0] == b_count


def test_db08_identity_and_database_timestamps(db):
    with db.connect() as conn:
        before = row(conn, "documents", D1)
        for field, value in [("id", str(uuid.uuid4())), ("company_id", B), ("file_name", "changed.pdf"),
                             ("s3_url", "s3://changed/x"), ("file_size_bytes", 1), ("file_hash", "f"*64),
                             ("mime_type", "image/png"), ("doc_type", "packing_list"), ("created_at", "2020-01-01T00:00:00Z")]:
            with violation(conn):
                conn.execute(sql.SQL("UPDATE public.documents SET {}=%s WHERE id=%s").format(sql.Identifier(field)), (value, D1))
        for field, value in [("id", str(uuid.uuid4())), ("document_id", str(uuid.uuid4())), ("created_at", "2020-01-01T00:00:00Z")]:
            with violation(conn):
                conn.execute(sql.SQL("UPDATE public.processing_jobs SET {}=%s WHERE id=%s").format(sql.Identifier(field)), (value, J1))
        with conn.transaction():
            now = conn.execute("SELECT now()").fetchone()[0]
            conn.execute("UPDATE public.documents SET uploaded_by=%s, status='partitioning', updated_at='2000-01-01T00:00:00Z' WHERE id=%s", (OPERATOR, D1))
            assert conn.execute("SELECT updated_at FROM public.documents WHERE id=%s", (D1,)).fetchone()[0] == now
        assert row(conn, "documents", D1)["created_at"] == before["created_at"]


def test_db09_exact_indexes_and_one_job(db):
    with db.connect() as conn:
        indexes = dict(conn.execute("SELECT indexname,indexdef FROM pg_indexes WHERE schemaname='public' AND tablename IN ('documents','processing_jobs')").fetchall())
        assert set(indexes) == {"pk_documents", "pk_processing_jobs", "idx_documents_company_id",
            "idx_documents_uploaded_by", "idx_documents_status", "idx_documents_file_hash",
            "idx_documents_company_created", "idx_documents_company_status_created",
            "uq_processing_jobs_document_id", "idx_processing_jobs_dispatch", "idx_processing_jobs_lease"}
        assert "UNIQUE" not in indexes["idx_documents_file_hash"]
        assert "created_at DESC, id DESC" in indexes["idx_documents_company_created"]
        assert "next_attempt_at NULLS FIRST" in indexes["idx_processing_jobs_dispatch"]
        job = dict(fixture_payload()["jobs"][0], id=str(uuid.uuid4()))
        with violation(conn, "23505"):
            insert_record(conn, "processing_jobs", job)


def test_db10_pair_insert_rollback_and_schema_limit(db):
    doc, job = pair()
    job["attempt_count"] = 5
    with db.connect() as conn:
        with violation(conn):
            insert_pair(conn, doc, job)
        assert conn.execute("SELECT count(*) FROM public.documents WHERE id=%s", (doc["id"],)).fetchone()[0] == 0
        insert_record(conn, "documents", doc)
        assert conn.execute("SELECT count(*) FROM public.processing_jobs WHERE document_id=%s", (doc["id"],)).fetchone()[0] == 0


@pytest.mark.parametrize("changes", [
    {"status": "completed"}, {"status": "failed"}, {"status": "failed", "finished_at": "2026-09-03T12:01:00Z", "error_code": " "},
    {"finished_at": "2026-09-03T12:01:00Z"}, {"progress_percentage": -1}, {"progress_percentage": 101},
    {"attempt_count": -1}, {"attempt_count": 5}, {"status": "unknown"}, {"current_stage": "done"},
    {"status": "completed", "progress_percentage": 100, "finished_at": "2026-09-03T12:01:00Z", "lease_expires_at": "2026-09-03T12:05:00Z"},
])
def test_db11_terminal_and_range_checks(db, changes):
    doc, job = pair()
    job.update(changes)
    with db.connect() as conn, violation(conn):
        insert_pair(conn, doc, job)


def test_db12_terminal_pair_atomicity(db):
    with db.connect() as conn:
        before = row(conn, "documents", D1)
        with violation(conn):
            lock_pair(conn, D1)
            conn.execute("UPDATE public.documents SET status='pending_review' WHERE id=%s", (D1,))
            conn.execute("UPDATE public.processing_jobs SET status='completed',progress_percentage=99 WHERE id=%s", (J1,))
        assert row(conn, "documents", D1) == before
        with conn.transaction():
            lock_pair(conn, D1)
            conn.execute("UPDATE public.processing_jobs SET status='completed',current_stage='extracting',progress_percentage=100,finished_at=clock_timestamp() WHERE id=%s", (J1,))
            conn.execute("UPDATE public.documents SET status='pending_review' WHERE id=%s", (D1,))
        assert row(conn, "documents", D1)["status"] == "pending_review"


def test_db13_concurrent_deduplication_fresh_snapshot(db):
    doc1, job1 = pair()
    doc2, job2 = pair(file_hash=doc1["file_hash"])
    locked, release = threading.Event(), threading.Event()
    with db.connect() as first, db.connect() as second, ThreadPoolExecutor(2) as pool:
        a = pool.submit(accept, first, doc1, job1, locked=locked, release=release)
        assert locked.wait(3)
        b = pool.submit(accept, second, doc2, job2)
        release.set()
        assert a.result(5) is True and b.result(5) is False
        assert first.execute("SELECT count(*) FROM public.documents WHERE company_id=%s AND file_hash=%s", (A, doc1["file_hash"])).fetchone()[0] == 1


def test_db14_deliberate_and_cross_tenant_duplicates(db):
    file_hash = fixture_payload()["documents"][0]["file_hash"]
    with db.connect() as conn:
        doc, job = pair(file_hash=file_hash)
        assert accept(conn, doc, job, deliberate=True)
        shared_hash = hashlib.sha256(b"same-bytes-across-two-tenants").hexdigest()
        first, first_job = pair(A, file_hash=shared_hash)
        assert accept(conn, first, first_job)
        other, other_job = pair(B, file_hash=shared_hash)
        assert accept(conn, other, other_job)
        assert conn.execute("SELECT d.id FROM public.documents d JOIN public.processing_jobs j ON j.document_id=d.id WHERE d.company_id=%s AND d.id=%s", (A, other["id"])).fetchone() is None


def test_db15_advisory_release_and_empty_row_lock(db):
    key = advisory_key(A, "a"*64)
    assert key == advisory_key(A.upper(), ("a"*64).upper())
    with db.connect() as first, db.connect() as second:
        first.execute("BEGIN")
        first.execute("SELECT pg_advisory_xact_lock(%s)", (key,))
        with second.transaction():
            assert not second.execute("SELECT pg_try_advisory_xact_lock(%s)", (key,)).fetchone()[0]
        first.execute("ROLLBACK")
        with second.transaction():
            assert second.execute("SELECT pg_try_advisory_xact_lock(%s)", (key,)).fetchone()[0]
        first.execute("BEGIN")
        first.execute("SELECT pg_advisory_xact_lock(%s)", (key,))
        first.close()  # Simulates a lost connection; transaction locks must be released.
        with second.transaction():
            second.execute("SELECT pg_advisory_xact_lock(%s)", (key,))
    doc, job = pair()
    with db.connect() as first, db.connect() as second:
        with first.transaction():
            assert first.execute("SELECT id FROM public.documents WHERE company_id=%s AND file_hash=%s FOR UPDATE", (A, doc["file_hash"])).fetchone() is None
            with second.transaction():
                insert_pair(second, doc, job)  # Empty SELECT did not protect the absent key.


def test_db16_competing_claims_and_due_time(db):
    with db.connect() as first, db.connect() as second, ThreadPoolExecutor(2) as pool:
        a, b = pool.submit(claim, first, D1), pool.submit(claim, second, D1)
        assert sorted([a.result() is not None, b.result() is not None]) == [False, True]
        assert row(first, "processing_jobs", J1)["attempt_count"] == 1
        doc, job = pair()
        job["next_attempt_at"] = datetime.now(timezone.utc) + timedelta(hours=1)
        insert_pair(first, doc, job)
        assert claim(second, doc["id"]) is None


def test_db17_fencing_uses_wall_clock_and_recovery(db):
    with db.connect() as first, db.connect() as second:
        assert claim(first, D1) == (1,)
        assert checkpoint(first, D1, 99) == 0
        assert checkpoint(first, D1, 1) == 1
        # Start the transaction before its lease expires. NOW() would be unsafe.
        first.execute("BEGIN")
        first.execute("SELECT now()")
        second.execute("UPDATE public.processing_jobs SET lease_expires_at=clock_timestamp()+interval '100 milliseconds' WHERE id=%s", (J1,))
        first.execute("SELECT pg_sleep(0.15)")
        assert checkpoint(first, D1, 1) == 0
        first.execute("COMMIT")
        with second.transaction():
            lock_pair(second, D1)
            assert second.execute("""UPDATE public.processing_jobs SET status='queued',lease_expires_at=NULL
                WHERE id=%s AND status='processing' AND attempt_count=1 AND lease_expires_at<=clock_timestamp()""", (J1,)).rowcount == 1
        assert checkpoint(first, D1, 1) == 0
        assert claim(first, D1) == (2,)
        assert checkpoint(second, D1, 1) == 0


@pytest.mark.parametrize("operation", [checkpoint, renew, finalize])
def test_db17_all_writes_fenced(db, operation):
    with db.connect() as conn:
        assert operation(conn, D1, 0) == 0  # Not processing.
        assert claim(conn, D1) == (1,)
        assert operation(conn, D1, 2) == 0  # Wrong attempt.
        conn.execute("UPDATE public.processing_jobs SET lease_expires_at=clock_timestamp()-interval '1 second' WHERE id=%s", (J1,))
        assert operation(conn, D1, 1) == 0  # Expired; cannot revive or finalize.
        assert row(conn, "documents", D1)["status"] == "queued"


def test_db17_recovery_serializes_stale_finalization(db):
    locked, release = threading.Event(), threading.Event()
    with db.connect() as first, db.connect() as second, ThreadPoolExecutor(2) as pool:
        assert claim(first, D1) == (1,)
        first.execute("UPDATE public.processing_jobs SET lease_expires_at=clock_timestamp()-interval '1 second' WHERE id=%s", (J1,))

        def recover():
            with first.transaction():
                lock_pair(first, D1)
                count = first.execute("""UPDATE public.processing_jobs SET status='queued',lease_expires_at=NULL,
                    next_attempt_at=clock_timestamp()+interval '5 seconds'
                    WHERE id=%s AND status='processing' AND attempt_count=1 AND lease_expires_at<=clock_timestamp()""", (J1,)).rowcount
                locked.set()
                if not release.wait(5):
                    raise TimeoutError("Test recovery synchronization timed out")
                return count

        recovering = pool.submit(recover)
        assert locked.wait(3)
        stale = pool.submit(finalize, second, D1, 1)
        release.set()
        assert recovering.result(5) == 1 and stale.result(5) == 0
        assert row(first, "documents", D1)["status"] == "queued"


def test_db18_bounded_retry_checkpoint_and_terminal_failure(db):
    with db.connect() as conn:
        for attempt in range(1, 5):
            assert claim(conn, D1) == (attempt,)
            assert checkpoint(conn, D1, attempt) == 1
            with conn.transaction():
                lock_pair(conn, D1)
                if attempt < 4:
                    delay = (5, 10, 20)[attempt-1]
                    stamp = conn.execute("SELECT clock_timestamp()").fetchone()[0]
                    assert conn.execute("""UPDATE public.processing_jobs SET status='queued',lease_expires_at=NULL,
                        next_attempt_at=%s + %s * interval '1 second',error_code='PROCESSING_FAILED'
                        WHERE id=%s AND status='processing' AND attempt_count=%s AND lease_expires_at>clock_timestamp()""",
                        (stamp, delay, J1, attempt)).rowcount == 1
                    due = conn.execute("SELECT next_attempt_at FROM public.processing_jobs WHERE id=%s", (J1,)).fetchone()[0]
                    assert (due-stamp).total_seconds() == delay
                else:
                    assert conn.execute("""UPDATE public.processing_jobs SET status='failed',lease_expires_at=NULL,next_attempt_at=NULL,
                        finished_at=clock_timestamp(),error_code='PROCESSING_FAILED'
                        WHERE id=%s AND status='processing' AND attempt_count=%s AND lease_expires_at>clock_timestamp()""", (J1, attempt)).rowcount == 1
                    conn.execute("UPDATE public.documents SET status='failed' WHERE id=%s", (D1,))
            job = row(conn, "processing_jobs", J1)
            assert (job["current_stage"], job["progress_percentage"], job["attempt_count"]) == ("chunking", 40, attempt)
            if attempt < 4:
                assert claim(conn, D1) is None
                # Advance only this isolated test's retry eligibility; never reset attempts.
                conn.execute("UPDATE public.processing_jobs SET next_attempt_at=clock_timestamp()-interval '1 second' WHERE id=%s", (J1,))
        assert claim(conn, D1) is None
        assert row(conn, "documents", D1)["status"] == "failed"


def test_db19_tenant_snapshot(db):
    with db.connect() as first, db.connect() as second:
        first.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
        count = first.execute("SELECT count(*) FROM public.documents WHERE company_id=%s", (A,)).fetchone()[0]
        doc, job = pair()
        with second.transaction():
            insert_pair(second, doc, job)
        rows = first.execute("SELECT d.id,d.company_id FROM public.documents d JOIN public.processing_jobs j ON j.document_id=d.id WHERE d.company_id=%s ORDER BY d.created_at DESC,d.id DESC", (A,)).fetchall()
        assert len(rows) == count and all(str(r[1]) == A for r in rows)
        first.execute("COMMIT")
        assert first.execute("SELECT count(*) FROM public.documents WHERE company_id=%s", (A,)).fetchone()[0] == count+1


def test_db20_stable_ties_and_utc_half_open_dates(db):
    with db.connect() as conn:
        for stamp in ["2026-09-03T00:00:00Z", "2026-09-04T00:00:00Z"]:
            doc, job = pair()
            doc["created_at"] = stamp
            insert_pair(conn, doc, job)
        result = conn.execute("""SELECT id,created_at FROM public.documents WHERE company_id=%s
            AND created_at >= '2026-09-03T00:00:00Z'::timestamptz
            AND created_at < '2026-09-04T00:00:00Z'::timestamptz
            ORDER BY created_at DESC,id DESC""", (A,)).fetchall()
        assert len(result) == 5
        assert result == sorted(result, key=lambda r: (r[1], r[0]), reverse=True)
        assert all(r[1].day == 3 for r in result)


def test_db21_seed_repeat_mismatch_and_partial_pair(db):
    with db.connect() as conn:
        before = [row(conn, "documents", D1), row(conn, "processing_jobs", J1)]
        seed(conn, db.name, no_active_consumers=True)
        assert before == [row(conn, "documents", D1), row(conn, "processing_jobs", J1)]
        assert conn.execute("SELECT count(*) FROM public.documents").fetchone()[0] == 6
        conn.execute("UPDATE public.processing_jobs SET progress_percentage=20 WHERE id=%s", (J1,))
        with pytest.raises(psycopg.Error, match="mismatch"):
            seed(conn, db.name, no_active_consumers=True)
        assert row(conn, "processing_jobs", J1)["progress_percentage"] == 20
        conn.execute("DELETE FROM public.processing_jobs WHERE id=%s", (J1,))
        with pytest.raises(psycopg.Error, match="Partial"):
            seed(conn, db.name, no_active_consumers=True)
        assert conn.execute("SELECT count(*) FROM public.processing_jobs").fetchone()[0] == 5


def test_db21_seed_bad_bytes_and_missing_parent(db):
    with db.connect() as conn:
        payload = deepcopy(fixture_payload())
        payload["files"][0]["file_hash"] = "0"*64
        with pytest.raises(psycopg.Error, match="manifest"):
            seed(conn, db.name, no_active_consumers=True, payload=payload)
        conn.execute("DELETE FROM public.users WHERE id=%s", (OPERATOR,))
        with pytest.raises(psycopg.Error, match="prerequisite auth users"):
            seed(conn, db.name, no_active_consumers=True)
        assert conn.execute("SELECT count(*) FROM public.documents").fetchone()[0] == 6


def test_db22_lock_timeout_rolls_back_whole_pair(db):
    with db.connect() as first, db.connect() as second:
        before = row(first, "documents", D1)
        with first.transaction():
            first.execute("SELECT id FROM public.processing_jobs WHERE id=%s FOR UPDATE", (J1,))
            second.execute("SET lock_timeout='100ms'")
            with violation(second, "55P03"):
                second.execute("UPDATE public.documents SET status='partitioning' WHERE id=%s", (D1,))
                second.execute("UPDATE public.processing_jobs SET progress_percentage=20 WHERE id=%s", (J1,))
        assert row(second, "documents", D1) == before


def test_db22_serialization_failure_rolls_back_whole_pair(db):
    with db.connect() as first, db.connect() as second:
        before = row(second, "documents", D1)
        with violation(second, "40001"):
            second.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            second.execute("SELECT progress_percentage FROM public.processing_jobs WHERE id=%s", (J1,))
            first.execute("UPDATE public.processing_jobs SET progress_percentage=20 WHERE id=%s", (J1,))
            second.execute("UPDATE public.documents SET status='partitioning' WHERE id=%s", (D1,))
            second.execute("UPDATE public.processing_jobs SET progress_percentage=40 WHERE id=%s", (J1,))
        assert row(second, "documents", D1) == before


def test_db22_deadlock_rolls_back_losing_transaction(db):
    other_id = "66666666-6666-4666-8666-000000000005"
    barrier = threading.Barrier(2)

    def reversed_locks(first_id, second_id):
        with db.connect() as conn:
            conn.execute("SET lock_timeout='5s'")
            try:
                with conn.transaction():
                    conn.execute("UPDATE public.documents SET overall_confidence=10 WHERE id=%s", (first_id,))
                    barrier.wait(timeout=3)
                    conn.execute("UPDATE public.documents SET overall_confidence=20 WHERE id=%s", (second_id,))
                return "committed"
            except psycopg.Error as error:
                return error.sqlstate

    with ThreadPoolExecutor(2) as pool:
        a = pool.submit(reversed_locks, D1, other_id)
        b = pool.submit(reversed_locks, other_id, D1)
        assert sorted([a.result(8), b.result(8)]) == ["40P01", "committed"]
    with db.connect() as conn:
        values = conn.execute("SELECT overall_confidence FROM public.documents WHERE id IN (%s,%s)", (D1, other_id)).fetchall()
        assert sorted(v[0] for v in values) == [Decimal("10.00"), Decimal("20.00")]


def test_db23_nonempty_downgrade_refusal_empty_round_trip(db):
    with db.connect() as conn:
        parents = conn.execute("SELECT jsonb_agg(to_jsonb(t) ORDER BY id) FROM public.companies t").fetchone()[0]
    with pytest.raises(sa.exc.DBAPIError, match="Rollback refused"):
        db.migrate(PARENT_REVISION, down=True)
    with db.connect() as conn:
        assert conn.execute("SELECT version_num FROM public.alembic_version").fetchone()[0] == NEW_REVISION
        conn.execute("DELETE FROM public.documents")  # Explicitly empty only this suite's disposable fixture rows.
    db.migrate(PARENT_REVISION, down=True)
    with db.connect() as conn:
        assert conn.execute("SELECT to_regclass('public.documents')").fetchone()[0] is None
        assert conn.execute("SELECT jsonb_agg(to_jsonb(t) ORDER BY id) FROM public.companies t").fetchone()[0] == parents
        assert conn.execute("SELECT to_regprocedure('public.update_updated_at_column()')").fetchone()[0]
        with pytest.raises(psycopg.Error, match="collision"):
            with conn.transaction():
                # An incompatible unversioned relation must never be silently adopted.
                conn.execute("CREATE TABLE public.documents (id integer)")
                conn.execute(load_revision().upgrade_sql())
        assert conn.execute("SELECT to_regclass('public.documents')").fetchone()[0] is None
    db.migrate()


def test_db24_orm_handoff_gate():
    pytest.skip("ORM catalog parity pending: shared auth and ingestion mappings are absent; see final_project/issue_missing.md FP-ISSUE-001")
