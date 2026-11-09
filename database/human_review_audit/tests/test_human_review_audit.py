"""Final-project database verification for human-review-audit.

Offline checks always run. Live checks require an explicitly acknowledged,
loopback-only disposable database already verified at RAG revision 20260904_0003.
"""
from __future__ import annotations

import ast
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

from alembic import command
from alembic.config import Config
import pglast
import psycopg
import pytest
import sqlalchemy as sa

TEST_ROOT = Path(__file__).resolve().parent
FEATURE_ROOT = TEST_ROOT.parent
PROJECT_ROOT = FEATURE_ROOT.parents[1]
MIGRATIONS = FEATURE_ROOT / "migrations"
SEEDS = FEATURE_ROOT / "seeds"
BACKEND_ROOT = PROJECT_ROOT / "backend"
SQL_PATH = MIGRATIONS / "20260906_create_human_review_audit.sql"
REV_PATH = MIGRATIONS / "20260906_0004_human_review_audit_migration.py"
if str(SEEDS) not in sys.path:
    sys.path.insert(0, str(SEEDS))
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from seed_human_review_audit import disposable_name, seed
NEW_REVISION = "20260906_0004"
PARENT_REVISION = "20260904_0003"
TABLES = (
    "review_audit_events",
    "review_audit_changes",
    "review_validation_runs",
    "review_validation_results",
    "review_idempotency_keys",
)


def load_file(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_offline_python_sql_and_revision_identity():
    for path in (
        REV_PATH,
        BACKEND_ROOT / "app" / "human_review_audit" / "models.py",
        SEEDS / "generate_fixtures.py",
        SEEDS / "seed_human_review_audit.py",
    ):
        ast.parse(path.read_text(encoding="utf-8"), filename=path.name)
    parsed = json.loads(pglast.parser.parse_sql_json(SQL_PATH.read_text(encoding="utf-8")))
    statements = [entry["stmt"] for entry in parsed["stmts"]]
    assert sum("CreateStmt" in item for item in statements) == 5
    assert sum("CreateTrigStmt" in item for item in statements) == 13
    assert sum("CreateFunctionStmt" in item for item in statements) == 11
    assert sum("IndexStmt" in item for item in statements) == 8
    assert len(pglast.parse_plpgsql(SQL_PATH.read_text(encoding="utf-8"))) == 13
    revision = load_file("human_review_revision", REV_PATH)
    assert (revision.revision, revision.down_revision) == (NEW_REVISION, PARENT_REVISION)
    assert "BEGIN;" not in revision.upgrade_sql().split("DO $preflight$", 1)[0]


def test_offline_fixture_manifest_and_serial_history():
    fixture = load_file(
        "human_review_fixture_test", SEEDS / "generate_fixtures.py"
    ).fixture_payload()
    manifest = json.loads(
        (SEEDS / "human-review-audit-fixtures" / "manifest.json").read_text(encoding="utf-8")
    )
    assert fixture["scope"] == "DATABASE_ONLY" and manifest["synthetic_only"] is True
    actual = {
        "review_audit_events": len(fixture["events"]),
        "review_audit_changes": len(fixture["changes"]),
        "review_validation_runs": len(fixture["validation_runs"]),
        "review_validation_results": len(fixture["validation_results"]),
        "review_idempotency_keys": len(fixture["idempotency"]),
        "reviewer_added_line_items": len(fixture["current_mutations"]["manual_lines"]),
    }
    assert actual == manifest["counts"]
    assert {event["action"] for event in fixture["events"]} == {
        "field_edited", "approved", "rejected", "reopened"
    }
    assert {result["status"] for result in fixture["validation_results"]} == {
        "passed", "failed", "missing", "not_applicable"
    }
    assert len({parent["company_id"] for parent in fixture["required_parents"]}) == 2
    for document in {event["document_id"] for event in fixture["events"]}:
        revisions = sorted(
            event["review_revision"] for event in fixture["events"]
            if event["document_id"] == document
        )
        assert revisions == list(range(1, len(revisions) + 1))
    ids = [row["id"] for key in ("events", "changes", "validation_runs", "validation_results", "idempotency") for row in fixture[key]]
    assert len(ids) == len(set(ids))


def load_models():
    from app.auth import models as auth
    from app.document_ingestion import models as ingestion
    from app.document_processing_rag import models as rag
    from app.human_review_audit import models as review

    return auth, ingestion, rag, review


def test_offline_single_shared_metadata_and_model_contract():
    auth, ingestion, rag, review = load_models()
    sa.orm.configure_mappers()
    assert auth.Base is ingestion.Base is rag.Base is review.Base
    assert set(TABLES) <= set(review.Base.metadata.tables)
    assert {"review_revision", "last_reviewed_by", "last_reviewed_at"} <= set(
        ingestion.Document.__table__.columns.keys()
    )
    assert "origin" in rag.LineItem.__table__.columns
    assert len(review.ReviewAuditEvent.__table__.columns) == 12
    assert len(review.ReviewAuditChange.__table__.columns) == 7
    assert len(review.ReviewValidationRun.__table__.columns) == 9
    assert len(review.ReviewValidationResult.__table__.columns) == 12
    assert len(review.ReviewIdempotencyKey.__table__.columns) == 12
    for immutable in (
        review.ReviewAuditEvent,
        review.ReviewAuditChange,
        review.ReviewValidationRun,
        review.ReviewValidationResult,
    ):
        assert "updated_at" not in immutable.__table__.columns
    assert "updated_at" in review.ReviewIdempotencyKey.__table__.columns


@pytest.mark.parametrize(
    "dsn,ack",
    [
        ("", ""),
        ("host=localhost dbname=production", "production"),
        (
            "host=db.example.com dbname=docusense_review_test_demo",
            "docusense_review_test_demo",
        ),
        (
            "host=localhost dbname=docusense_rag_test_demo",
            "docusense_rag_test_demo",
        ),
    ],
)
def test_offline_target_guards(dsn, ack):
    with pytest.raises(ValueError):
        disposable_name(dsn, ack)


def test_offline_locked_security_and_handoff_guards():
    sql_text = SQL_PATH.read_text(encoding="utf-8")
    migration = REV_PATH.read_text(encoding="utf-8")
    for token in (
        "to_regclass('public.audit_logs')",
        "source_row_key LIKE 'manual:%'",
        "DEFERRABLE INITIALLY DEFERRED",
        "REVOKE UPDATE, DELETE, TRUNCATE",
        "current_setting('docusense.review_event_id',true)",
        "DROP TRIGGER trg_invoices_immutable",
        "DROP TRIGGER trg_line_items_identity_immutable",
    ):
        assert token in sql_text
    assert "DROP TABLE" not in sql_text
    assert "DROP CASCADE" not in migration
    assert "no_active_consumers" in migration


class Database:
    def __init__(self, dsn: str, name: str, scripts: Path):
        self.dsn, self.name, self.scripts = dsn, name, scripts

    def connect(self):
        try:
            return psycopg.connect(
                self.dsn,
                autocommit=True,
                connect_timeout=5,
                options="-c statement_timeout=15000 -c lock_timeout=3000",
            )
        except psycopg.Error:
            raise RuntimeError(
                "Disposable PostgreSQL connection failed; connection details suppressed"
            ) from None

    def migrate(self, target=NEW_REVISION, *, down=False):
        engine = sa.create_engine("postgresql+psycopg://", creator=self.connect)
        try:
            with engine.connect() as connection:
                with connection.begin():
                    connection.execute(
                        sa.text("SELECT set_config('docusense.disposable_database',:name,true)"),
                        {"name": self.name},
                    )
                    connection.execute(
                        sa.text("SELECT set_config('docusense.no_active_consumers','confirmed',true)")
                    )
                    config = Config()
                    config.set_main_option("script_location", str(self.scripts).replace("%", "%%"))
                    config.attributes["connection"] = connection
                    (command.downgrade if down else command.upgrade)(config, target)
        finally:
            engine.dispose()


@pytest.fixture(scope="session")
def database():
    dsn = os.environ.get("HUMAN_REVIEW_TEST_DSN")
    if not dsn:
        pytest.skip("No acknowledged disposable PostgreSQL target; live review verification not performed")
    ack = os.environ.get("HUMAN_REVIEW_TEST_ACK", "")
    name = disposable_name(dsn, ack)
    if os.environ.get("HUMAN_REVIEW_TEST_NO_CONSUMERS") != "1":
        pytest.fail("Explicit no-active-consumers assertion is required")
    with tempfile.TemporaryDirectory(prefix="docusense-review-alembic-") as directory:
        scripts = Path(directory)
        versions = scripts / "versions"
        versions.mkdir()
        shutil.copy2(
            PROJECT_ROOT / "database" / "document_ingestion" / "tests" / "alembic_env.py",
            scripts / "env.py",
        )
        for source in (
            PROJECT_ROOT / "database" / "auth" / "migrations" / "20260901_0001_auth_tenancy_migration.py",
            PROJECT_ROOT / "database" / "document_ingestion" / "migrations" / "20260903_0002_document_ingestion_migration.py",
            PROJECT_ROOT / "database" / "document_ingestion" / "migrations" / "20260903_create_document_ingestion.sql",
            PROJECT_ROOT / "database" / "document_processing_rag" / "migrations" / "20260904_0003_document_processing_rag_migration.py",
            PROJECT_ROOT / "database" / "document_processing_rag" / "migrations" / "20260904_create_document_processing_rag.sql",
            REV_PATH,
            SQL_PATH,
        ):
            shutil.copy2(source, versions / source.name)
        db = Database(dsn, name, scripts)
        with db.connect() as connection:
            relation = connection.execute(
                "SELECT to_regclass('public.alembic_version')"
            ).fetchone()[0]
            head = (
                connection.execute("SELECT version_num FROM public.alembic_version").fetchone()[0]
                if relation else None
            )
            if head != PARENT_REVISION:
                pytest.fail("Expected a verified RAG predecessor at 20260904_0003")
        db.migrate()
        # Prove the empty disposable downgrade before fixtures make reversal illegal.
        db.migrate(PARENT_REVISION, down=True)
        db.migrate()
        with db.connect() as connection:
            assert seed(connection, ack, no_active_consumers=True) == "inserted"
            assert seed(connection, ack, no_active_consumers=True) == "unchanged"
        yield db


@pytest.fixture
def db(database):
    with database.connect() as connection:
        yield connection


def test_hra_db01_08_catalog_migration_and_orm(db, database):
    assert db.execute("SELECT version_num FROM public.alembic_version").fetchone()[0] == NEW_REVISION
    counts = db.execute(
        """SELECT table_name,count(*) FROM information_schema.columns
           WHERE table_schema='public' AND table_name=ANY(%s)
           GROUP BY table_name""",
        (list(TABLES),),
    ).fetchall()
    assert dict(counts) == {
        "review_audit_events": 12,
        "review_audit_changes": 7,
        "review_validation_runs": 9,
        "review_validation_results": 12,
        "review_idempotency_keys": 12,
    }
    assert db.execute(
        "SELECT review_revision,last_reviewed_by,last_reviewed_at FROM public.documents LIMIT 0"
    ).description
    auth, ingestion, rag, review = load_models()
    engine = sa.create_engine("postgresql+psycopg://", creator=database.connect)
    try:
        inspector = sa.inspect(engine)
        for table in TABLES:
            assert set(review.Base.metadata.tables[table].columns.keys()) == {
                column["name"] for column in inspector.get_columns(table, schema="public")
            }
    finally:
        engine.dispose()
    assert auth.Base is ingestion.Base is rag.Base is review.Base


def test_hra_db09_25_constraints_tenant_history_and_validation(db):
    with pytest.raises(psycopg.Error):
        with db.transaction():
            db.execute(
                "UPDATE public.review_audit_events SET note='mutated' WHERE id='e1000000-0000-4000-8000-000000000001'"
            )
    with pytest.raises(psycopg.Error):
        with db.transaction():
            db.execute(
                "UPDATE public.invoices SET grand_total=999 WHERE id='aaaaaaaa-aaaa-4aaa-8aaa-000000000001'"
            )
    with pytest.raises(psycopg.Error):
        with db.transaction():
            db.execute(
                """INSERT INTO public.review_audit_events
                   (document_id,actor_user_id,action,from_status,to_status,review_revision,
                    request_id,payload_hash)
                   VALUES ('66666666-6666-4666-8666-000000000003',
                           '33333333-3333-4333-8333-444444444444','approved',
                           'pending_review','approved',6,'foreign-tenant',repeat('a',64))"""
            )
    assert db.execute(
        "SELECT count(*) FROM public.review_validation_results WHERE status IN ('failed','missing','not_applicable')"
    ).fetchone()[0] >= 3
    class RollbackProbe(Exception):
        pass

    with pytest.raises(RollbackProbe):
        with db.transaction():
            db.execute(
                """INSERT INTO public.review_validation_results
                   (id,review_validation_run_id,rule_id,scope_key,status,message_code,
                    blocks_approval,difference,epsilon)
                   VALUES ('d1000000-0000-4000-8000-999999999991',
                           'a1000000-0000-4000-8000-000000000004',
                           'BR-03-TOTAL','regression.missing','missing','TOTAL_NOT_AVAILABLE',
                           true,NULL,NULL)"""
            )
            db.execute("SET CONSTRAINTS ALL IMMEDIATE")
            raise RollbackProbe
    with pytest.raises(psycopg.errors.CheckViolation):
        with db.transaction():
            db.execute(
                """INSERT INTO public.review_validation_results
                   (id,review_validation_run_id,rule_id,scope_key,status,message_code,
                    blocks_approval,difference,epsilon)
                   VALUES ('d1000000-0000-4000-8000-999999999992',
                           'a1000000-0000-4000-8000-000000000004',
                           'BR-03-TOTAL','regression.invalid','missing','TOTAL_NOT_AVAILABLE',
                           true,NULL,0.050000)"""
            )


def test_hra_db26_37_idempotency_fixture_and_tenant_reads(db):
    assert db.execute("SELECT count(*) FROM public.review_audit_events").fetchone()[0] >= 8
    assert db.execute("SELECT count(*) FROM public.review_idempotency_keys").fetchone()[0] >= 8
    tenant_a = db.execute(
        """SELECT count(*) FROM public.review_audit_events e
           JOIN public.documents d ON d.id=e.document_id
           WHERE d.company_id='11111111-1111-1111-1111-111111111111'"""
    ).fetchone()[0]
    tenant_b = db.execute(
        """SELECT count(*) FROM public.review_audit_events e
           JOIN public.documents d ON d.id=e.document_id
           WHERE d.company_id='11111111-1111-1111-1111-222222222222'"""
    ).fetchone()[0]
    assert (tenant_a, tenant_b) == (6, 2)
    rows = db.execute(
        """SELECT review_revision FROM public.review_audit_events
           WHERE document_id='66666666-6666-4666-8666-000000000003'
           ORDER BY created_at DESC,id DESC"""
    ).fetchall()
    assert [row[0] for row in rows] == [5, 4, 3, 2, 1]


def test_hra_db38_40_index_shapes_and_unsafe_downgrade(db, database):
    indexes = {
        row[0] for row in db.execute(
            "SELECT indexname FROM pg_indexes WHERE schemaname='public'"
        ).fetchall()
    }
    assert {
        "idx_documents_company_review_state",
        "idx_review_audit_document_created",
        "idx_review_audit_document_action",
        "idx_review_idempotency_expiry",
    } <= indexes
    with pytest.raises(sa.exc.DBAPIError, match="Rollback refused"):
        database.migrate(PARENT_REVISION, down=True)
    assert db.execute("SELECT count(*) FROM public.review_audit_events").fetchone()[0] >= 8
