"""Stage-3 verification for document-search-export.

Offline contract checks always run. Live checks require an explicitly
acknowledged loopback-only disposable database already migrated to 20260907_0006.
"""
from __future__ import annotations

import ast
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import uuid

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
AUTH_ROOT = PROJECT_ROOT / "database" / "auth"
INGESTION_ROOT = PROJECT_ROOT / "database" / "document_ingestion"
RAG_ROOT = PROJECT_ROOT / "database" / "document_processing_rag"
REVIEW_ROOT = PROJECT_ROOT / "database" / "human_review_audit"
if str(SEEDS) not in sys.path:
    sys.path.insert(0, str(SEEDS))
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from seed_document_search_export import disposable_name, seed

CORE_SQL = MIGRATIONS / "20260907_create_document_search_export.sql"
INDEX_SQL = MIGRATIONS / "20260907_create_document_search_export_indexes.sql"
CORE_REV = MIGRATIONS / "20260907_0005_document_search_export_migration.py"
INDEX_REV = MIGRATIONS / "20260907_0006_document_search_export_indexes_migration.py"
NEW_REVISION = "20260907_0006"
CORE_REVISION = "20260907_0005"
PARENT_REVISION = "20260906_0004"
TABLES = ("export_jobs", "export_job_documents")
CORE_INDEXES = {
    "idx_export_jobs_company_created",
    "idx_export_jobs_requester_created",
    "uq_export_jobs_idempotency",
    "idx_export_jobs_dispatch",
    "idx_export_jobs_lease",
    "idx_export_jobs_expiry",
    "idx_export_job_documents_document",
}
ONLINE_INDEXES = {
    "idx_documents_company_search",
    "idx_invoices_date_document",
    "idx_invoices_currency_date_document",
    "idx_invoices_total_document",
    "idx_document_chunks_embedding_compat",
}


def load_file(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_models():
    from app.auth import models as auth
    from app.document_ingestion import models as ingestion
    from app.document_processing_rag import models as rag
    from app.human_review_audit import models as review
    from app.document_search_export import models as feature
    return auth, ingestion, rag, review, feature


def test_offline_python_sql_and_revision_chain():
    for path in (
        CORE_REV, INDEX_REV,
        BACKEND_ROOT / "app" / "document_search_export" / "models.py",
        SEEDS / "generate_fixtures.py", SEEDS / "seed_document_search_export.py",
    ):
        ast.parse(path.read_text(encoding="utf-8"), filename=path.name)
    core = json.loads(pglast.parser.parse_sql_json(CORE_SQL.read_text(encoding="utf-8")))
    indexes = json.loads(pglast.parser.parse_sql_json(INDEX_SQL.read_text(encoding="utf-8")))
    core_statements = [item["stmt"] for item in core["stmts"]]
    index_statements = [item["stmt"] for item in indexes["stmts"]]
    assert sum("CreateStmt" in item for item in core_statements) == 2
    assert sum("CreateTrigStmt" in item for item in core_statements) == 7
    assert sum("IndexStmt" in item for item in core_statements) == 7
    assert sum("IndexStmt" in item for item in index_statements) == 5
    assert len(pglast.parse_plpgsql(CORE_SQL.read_text(encoding="utf-8"))) == 8
    core_revision = load_file("dse_core_revision", CORE_REV)
    index_revision = load_file("dse_index_revision", INDEX_REV)
    assert (core_revision.revision, core_revision.down_revision) == (
        "20260907_0005", "20260906_0004"
    )
    assert (index_revision.revision, index_revision.down_revision) == (
        "20260907_0006", "20260907_0005"
    )


def test_offline_shared_metadata_and_model_contract():
    auth, ingestion, rag, review, feature = load_models()
    sa.orm.configure_mappers()
    assert auth.Base is ingestion.Base is rag.Base is review.Base is feature.Base
    assert set(TABLES) <= set(feature.Base.metadata.tables)
    assert len(feature.ExportJob.__table__.columns) == 36
    assert len(feature.ExportJobDocument.__table__.columns) == 6
    assert set(feature.ExportJobDocument.__table__.primary_key.columns.keys()) == {
        "export_job_id", "document_id"
    }
    assert "updated_at" in feature.ExportJob.__table__.columns
    assert "updated_at" not in feature.ExportJobDocument.__table__.columns
    assert CORE_INDEXES <= {index.name for index in feature.Base.metadata.tables["export_jobs"].indexes} | {
        index.name for index in feature.Base.metadata.tables["export_job_documents"].indexes
    }


def test_offline_fixture_manifest_and_coverage():
    fixture = load_file(
        "document_search_export_fixture_test", SEEDS / "generate_fixtures.py"
    ).fixture_payload()
    manifest = json.loads(
        (SEEDS / "document-search-export-fixtures" / "manifest.json").read_text(encoding="utf-8")
    )
    assert fixture["scope"] == "DATABASE_ONLY" and fixture["synthetic_only"] is True
    assert len(fixture["jobs"]) == manifest["counts"]["export_jobs"] == 7
    assert len(fixture["memberships"]) == manifest["counts"]["export_job_documents"] == 7
    assert len({row["company_id"] for row in fixture["jobs"]}) == 2
    assert {row["target_state"] for row in fixture["jobs"]} == {
        "completed", "queued", "processing", "failed_source_changed", "expired", "retry"
    }
    assert all(member["source_value_hash"] == "DATABASE_COMPUTED" for member in fixture["memberships"])
    assert manifest["tracked_issue"] == "DB-ISSUE-009"
    assert "three approved parents" in manifest["resolved_predecessor_expansion"]
    assert manifest["blocked_expansions"] == []
    assert manifest["scale_gate"] == {
        "tenant_count": 2,
        "documents_per_tenant": 501,
        "page_boundary": "500+1",
        "vector_dimensions": 384,
        "persistence": "transaction_rollback",
    }


@pytest.mark.parametrize(
    "dsn,ack",
    [
        ("", ""),
        ("host=localhost dbname=production", "production"),
        ("host=db.example.com dbname=docusense_export_test_demo", "docusense_export_test_demo"),
        ("host=localhost dbname=docusense_review_test_demo", "docusense_review_test_demo"),
    ],
)
def test_offline_target_guards(dsn, ack):
    with pytest.raises(ValueError):
        disposable_name(dsn, ack)


def test_offline_hash_membership_and_security_contract():
    sql = CORE_SQL.read_text(encoding="utf-8")
    for token in (
        "docusense-export-source-v1",
        "jsonb_agg(jsonb_build_object",
        "ORDER BY li.line_order,li.id",
        "to_char(li.quantity,'FM99999999999990.0000')",
        "DEFERRABLE INITIALLY DEFERRED",
        "FOR KEY SHARE",
        "REVOKE UPDATE, DELETE, TRUNCATE",
        "ON DELETE RESTRICT",
        "ON DELETE CASCADE",
    ):
        assert token in sql
    assert "DROP TABLE" not in sql and "DROP CASCADE" not in sql


def test_offline_criteria_state_and_fencing_contract():
    sql = CORE_SQL.read_text(encoding="utf-8")
    for token in (
        "octet_length(value::text)>16384",
        "semantic_query_sha256",
        "requested_document_count",
        "chk_export_jobs_state_shape",
        "chk_export_jobs_identity_immutable",
        "chk_export_jobs_monotonic_progress",
        "NEW.attempt_count<>OLD.attempt_count+1",
        "OLD.status='completed' AND NEW.status='expired'",
    ):
        assert token in sql
    assert "HNSW" not in sql.upper() and "IVFFLAT" not in sql.upper()
    assert "pg_trgm" not in sql


def test_offline_online_index_contract():
    sql = INDEX_SQL.read_text(encoding="utf-8")
    assert sql.count("CREATE INDEX CONCURRENTLY") == 6  # one comment plus five statements
    assert ONLINE_INDEXES == {name for name in ONLINE_INDEXES if name in sql}
    assert "embedding_status='completed'" in sql
    assert "retrieval_role IN ('child','both')" in sql
    assert "BEGIN;" not in sql and "COMMIT;" not in sql
    migration = INDEX_REV.read_text(encoding="utf-8")
    assert "autocommit_block" in migration and "DROP INDEX CONCURRENTLY" in migration
    assert "no_active_consumers" in migration


class Database:
    def __init__(self, dsn: str, name: str, scripts: Path):
        self.dsn, self.name, self.scripts = dsn, name, scripts

    def connect(self, *, autocommit: bool = True):
        try:
            return psycopg.connect(
                self.dsn,
                autocommit=autocommit,
                connect_timeout=5,
                options="-c statement_timeout=120000 -c lock_timeout=5000",
            )
        except psycopg.Error:
            raise RuntimeError(
                "Disposable PostgreSQL connection failed; connection details suppressed"
            ) from None

    def migrate(self, target: str, *, down: bool = False):
        engine = sa.create_engine("postgresql+psycopg://", creator=self.connect)
        try:
            with engine.connect() as connection:
                connection.execute(
                    sa.text("SELECT set_config('docusense.disposable_database',:name,false)"),
                    {"name": self.name},
                )
                connection.execute(
                    sa.text("SELECT set_config('docusense.no_active_consumers','confirmed',false)")
                )
                # Keep the settings for this dedicated session but end SQLAlchemy's
                # implicit transaction before Alembic owns the migration boundary.
                connection.commit()
                config = Config()
                config.set_main_option("script_location", str(self.scripts).replace("%", "%%"))
                config.attributes["connection"] = connection
                (command.downgrade if down else command.upgrade)(config, target)
        finally:
            engine.dispose()


def _seed_predecessors(db: Database, ack: str):
    ingestion_seed = load_file("dse_ingestion_seed", PROJECT_ROOT / "database" / "document_ingestion" / "seeds" / "seed_document_ingestion.py")
    rag_seed = load_file("dse_rag_seed", PROJECT_ROOT / "database" / "document_processing_rag" / "seeds" / "seed_document_processing_rag.py")
    review_seed = load_file("dse_review_seed", PROJECT_ROOT / "database" / "human_review_audit" / "seeds" / "seed_human_review_audit.py")

    with db.connect() as conn:
        conn.execute(
            (AUTH_ROOT / "seeds" / "seed_auth_tenancy.sql").read_text(
                encoding="utf-8"
            )
        )
        payload = ingestion_seed.fixture_payload()
        with conn.transaction():
            conn.execute("SELECT set_config('docusense.disposable_database',%s,true)", (ack,))
            conn.execute("SELECT set_config('docusense.no_active_consumers','confirmed',true)")
            conn.execute(
                "SELECT set_config('docusense.ingestion_seed_payload',%s,true)",
                (json.dumps(payload),),
            )
            guarded_sql = (
                INGESTION_ROOT / "seeds" / "seed-document-ingestion.sql"
            ).read_text(encoding="utf-8")
            guarded_sql = guarded_sql.replace(
                "^docusense_ingestion_test_[a-z0-9_]+$",
                "^docusense_export_test_[a-z0-9_]+$",
            )
            conn.execute(guarded_sql)

    db.migrate("20260904_0003")
    rag_seed.disposable_name = lambda _dsn, acknowledgement: (
        ack if acknowledgement == ack else (_ for _ in ()).throw(ValueError("Wrong acknowledgement"))
    )
    with db.connect(autocommit=False) as conn:
        assert rag_seed.seed(conn, ack, no_active_consumers=True) == "inserted"

    db.migrate(PARENT_REVISION)
    review_seed.disposable_name = lambda _dsn, acknowledgement: (
        ack if acknowledgement == ack else (_ for _ in ()).throw(ValueError("Wrong acknowledgement"))
    )
    with db.connect(autocommit=False) as conn:
        assert review_seed.seed(conn, ack, no_active_consumers=True) == "inserted"


@pytest.fixture(scope="session")
def live_database():
    dsn = os.getenv("DOCUSENSE_TEST_DATABASE_URL", "")
    ack = os.getenv("DOCUSENSE_TEST_DATABASE_ACK", "")
    no_consumers = os.getenv("DOCUSENSE_TEST_NO_ACTIVE_CONSUMERS", "") == "confirmed"
    if not dsn or not ack or not no_consumers:
        pytest.skip("Live Feature 05 database acknowledgement/no-consumer gate not supplied")
    disposable_name(dsn, ack)
    with psycopg.connect(dsn, autocommit=True) as conn:
        name = conn.execute("SELECT current_database()").fetchone()[0]
        if name != ack:
            pytest.fail("Connected database differs from explicit acknowledgement")
        consumers = conn.execute(
            "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid()"
        ).fetchone()[0]
        if consumers:
            pytest.fail("Disposable Feature 05 target has active consumers")
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")

    with tempfile.TemporaryDirectory(prefix="docusense-export-alembic-") as directory:
        scripts = Path(directory)
        versions = scripts / "versions"
        versions.mkdir()
        shutil.copy2(INGESTION_ROOT / "tests" / "alembic_env.py", scripts / "env.py")
        for source in (
            AUTH_ROOT / "migrations" / "20260901_0001_auth_tenancy_migration.py",
            INGESTION_ROOT / "migrations" / "20260903_0002_document_ingestion_migration.py",
            INGESTION_ROOT / "migrations" / "20260903_create_document_ingestion.sql",
            RAG_ROOT / "migrations" / "20260904_0003_document_processing_rag_migration.py",
            RAG_ROOT / "migrations" / "20260904_create_document_processing_rag.sql",
            REVIEW_ROOT / "migrations" / "20260906_0004_human_review_audit_migration.py",
            REVIEW_ROOT / "migrations" / "20260906_create_human_review_audit.sql",
            CORE_REV,
            CORE_SQL,
            INDEX_REV,
            INDEX_SQL,
        ):
            shutil.copy2(source, versions / source.name)
        db = Database(dsn, ack, scripts)
        db.migrate("20260903_0002")
        _seed_predecessors(db, ack)
        db.migrate(NEW_REVISION)
        # Prove the Feature 05 empty down/down/up/up path before export rows exist.
        db.migrate(CORE_REVISION, down=True)
        db.migrate(PARENT_REVISION, down=True)
        db.migrate(NEW_REVISION)
        yield db, ack


def test_live_dse_db01_10_catalog_indexes_and_no_unauthorized_structures(live_database):
    database, _ = live_database
    with database.connect() as conn:
        head = conn.execute("SELECT array_agg(version_num::text) FROM public.alembic_version").fetchone()[0]
        assert head == ["20260907_0006"]
        tables = {row[0] for row in conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename=ANY(%s)",
            (list(TABLES),),
        )}
        assert tables == set(TABLES)
        rows = conn.execute(
            """SELECT c.relname,i.indisvalid,i.indisready FROM pg_class c
               JOIN pg_namespace n ON n.oid=c.relnamespace
               JOIN pg_index i ON i.indexrelid=c.oid
               WHERE n.nspname='public' AND c.relname=ANY(%s)""",
            (list(CORE_INDEXES | ONLINE_INDEXES),),
        ).fetchall()
        assert {r[0] for r in rows} == CORE_INDEXES | ONLINE_INDEXES
        assert all(r[1] and r[2] for r in rows)
        assert conn.execute("SELECT count(*) FROM pg_extension WHERE extname='pg_trgm'").fetchone()[0] == 0


def test_live_dse_db11_40_constraints_hash_seed_and_replay(live_database):
    database, ack = live_database
    with database.connect(autocommit=True) as conn:
        first = seed(conn, ack, no_active_consumers=True)
        second = seed(conn, ack, no_active_consumers=True)
        assert first in {"inserted", "unchanged"} and second == "unchanged"
        assert conn.execute("SELECT count(*) FROM public.export_jobs WHERE request_id LIKE 'fixture-export-%'").fetchone()[0] == 7
        assert conn.execute("SELECT count(*) FROM public.export_job_documents d JOIN public.export_jobs j ON j.id=d.export_job_id WHERE d.source_value_hash=public.compute_export_source_value_hash(d.document_id)").fetchone()[0] >= 7


def test_live_dse_db41_46_transactions_snapshots_and_concurrency(live_database):
    database, ack = live_database
    fixture_module = load_file(
        "dse_concurrency_fixtures", SEEDS / "generate_fixtures.py"
    )
    seed_module = load_file(
        "dse_concurrency_seed", SEEDS / "seed_document_search_export.py"
    )

    # Fault after parent insertion must roll the incomplete deferred membership back.
    incomplete_id = "e6000000-0000-4000-8000-000000000041"
    with database.connect(autocommit=False) as conn:
        with pytest.raises(psycopg.errors.CheckViolation):
            with conn.transaction():
                conn.execute(
                    """INSERT INTO public.export_jobs
                       (id,company_id,requested_by_user_id,format,mode,status,current_stage,
                        progress_percentage,selection_type,schema_version,criteria_json,
                        criteria_hash,request_hash,selected_document_count,request_id,created_at,updated_at)
                       SELECT %s,company_id,requested_by_user_id,format,mode,'queued','accepted',0,
                              selection_type,schema_version,criteria_json,criteria_hash,request_hash,1,
                              'fixture-atomic-rollback',created_at,created_at
                       FROM public.export_jobs WHERE id=%s""",
                    (incomplete_id, fixture_module.job_id(2)),
                )
                conn.execute(
                    "SET CONSTRAINTS trg_export_jobs_membership_commit IMMEDIATE"
                )
        assert conn.execute(
            "SELECT count(*) FROM public.export_jobs WHERE id=%s", (incomplete_id,)
        ).fetchone()[0] == 0

    # Concurrent identical fixture replays serialize and converge without duplicates.
    barrier = threading.Barrier(2)

    def replay():
        with database.connect(autocommit=False) as connection:
            barrier.wait(timeout=5)
            return seed(connection, ack, no_active_consumers=True)

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: replay(), range(2)))
    assert outcomes == ["unchanged", "unchanged"]
    with database.connect() as conn:
        assert conn.execute(
            "SELECT count(*) FROM public.export_jobs WHERE request_id LIKE 'fixture-export-%'"
        ).fetchone()[0] == 7

    # A repeatable-read generation snapshot returns the same canonical source hash.
    with database.connect(autocommit=False) as snapshot:
        snapshot.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        parent = fixture_module.fixture_payload()["required_parents"][0]
        first = snapshot.execute(
            "SELECT review_revision,public.compute_export_source_value_hash(id)::text FROM public.documents WHERE id=%s",
            (parent["document_id"],),
        ).fetchone()
        second = snapshot.execute(
            "SELECT review_revision,public.compute_export_source_value_hash(id)::text FROM public.documents WHERE id=%s",
            (parent["document_id"],),
        ).fetchone()
        assert first == second == (parent["review_revision"], first[1])

    # Two fenced terminal writers race; exactly one current token/attempt wins.
    processing_id = fixture_module.job_id(3)
    with database.connect() as conn:
        lease_token, attempt = conn.execute(
            "SELECT lease_token,attempt_count FROM public.export_jobs WHERE id=%s",
            (processing_id,),
        ).fetchone()
    terminal_barrier = threading.Barrier(2)

    def fail_worker():
        with database.connect(autocommit=False) as connection:
            terminal_barrier.wait(timeout=5)
            result = connection.execute(
                """UPDATE public.export_jobs
                   SET status='failed',failed_at=CURRENT_TIMESTAMP,
                       error_code='EXPORT_TEST_FAILURE',error_message='Synthetic fenced failure',
                       lease_token=NULL,lease_expires_at=NULL
                   WHERE id=%s AND status='processing' AND lease_token=%s AND attempt_count=%s""",
                (processing_id, lease_token, attempt),
            )
            connection.commit()
            return result.rowcount

    with ThreadPoolExecutor(max_workers=2) as pool:
        winners = list(pool.map(lambda _: fail_worker(), range(2)))
    assert sorted(winners) == [0, 1]

    # Build one due completed job, then prove two cleanup claimers yield one expiry.
    cleanup_job = fixture_module._job(
        946,
        company_id=fixture_module.TENANT_A,
        requester=fixture_module.ADMIN_A,
        document_id=fixture_module.DOC_A,
        review_revision=2,
        format="json",
        mode="synchronous",
        target_state="completed",
        idempotency_label=None,
    )
    with database.connect(autocommit=True) as conn:
        source_hash = conn.execute(
            "SELECT public.compute_export_source_value_hash(%s)::text",
            (cleanup_job["document_id"],),
        ).fetchone()[0]
        with conn.transaction():
            seed_module._insert_acceptance(conn, cleanup_job, source_hash)
        with conn.transaction():
            conn.execute(
                """UPDATE public.export_jobs SET status='completed',current_stage='completed',
                     progress_percentage=100,exported_document_count=1,row_count=1,
                     artifact_object_key='database-fixtures/due/export.json',
                     artifact_file_name='due.json',artifact_content_type='application/json',
                     artifact_size_bytes=64,artifact_sha256=%s,
                     completed_at=created_at+INTERVAL '1 minute',
                     artifact_expires_at=created_at+INTERVAL '1 day'
                   WHERE id=%s""",
                (fixture_module.canonical_sha("due"), cleanup_job["id"]),
            )
    cleanup_barrier = threading.Barrier(2)

    def cleanup_worker():
        with database.connect(autocommit=False) as connection:
            cleanup_barrier.wait(timeout=5)
            result = connection.execute(
                """UPDATE public.export_jobs SET status='expired',artifact_object_key=NULL,
                         expired_at=artifact_expires_at
                   WHERE id=%s AND status='completed' AND artifact_expires_at<=CURRENT_TIMESTAMP""",
                (cleanup_job["id"],),
            )
            connection.commit()
            return result.rowcount

    with ThreadPoolExecutor(max_workers=2) as pool:
        cleanup_winners = list(pool.map(lambda _: cleanup_worker(), range(2)))
    assert sorted(cleanup_winners) == [0, 1]


def test_live_500_501_search_membership_and_query_plans(live_database):
    database, _ = live_database
    vector_a = "[1," + ",".join(["0"] * 383) + "]"
    vector_b = "[0,1," + ",".join(["0"] * 382) + "]"
    model = "sentence-transformers/all-MiniLM-L6-v2"
    revision = "feature5-scale-fixture-revision"
    job_500 = "e7000000-0000-4000-8000-000000000500"
    job_501 = "e7000000-0000-4000-8000-000000000501"

    with database.connect(autocommit=False) as conn:
        conn.execute("SET LOCAL statement_timeout='30s'")
        conn.execute("SET LOCAL lock_timeout='5s'")
        conn.execute("SET CONSTRAINTS ALL DEFERRED")
        conn.execute(
            """CREATE TEMP TABLE feature5_scale_ids ON COMMIT DROP AS
               SELECT tenant,n,(md5(tenant::text||':'||n::text))::uuid AS id
               FROM (VALUES (%s::uuid),(%s::uuid)) tenants(tenant)
               CROSS JOIN generate_series(1,501) n""",
            ("11111111-1111-1111-1111-111111111111", "11111111-1111-1111-1111-222222222222"),
        )
        conn.execute(
            """INSERT INTO public.documents
                 (id,company_id,uploaded_by,file_name,s3_url,file_size_bytes,file_hash,
                  mime_type,doc_type,status,overall_confidence,review_revision,
                  last_reviewed_by,last_reviewed_at,created_at,updated_at)
               SELECT id,tenant,
                      CASE tenant WHEN %s::uuid THEN %s::uuid ELSE %s::uuid END,
                      'feature5-scale-'||n||'.pdf',
                      's3://synthetic/'||tenant||'/'||id||'/feature5-scale-'||n||'.pdf',
                      1024,encode(digest(tenant::text||':'||n,'sha256'),'hex'),
                      'application/pdf','commercial_invoice','approved',95,1,
                      CASE tenant WHEN %s::uuid THEN %s::uuid ELSE %s::uuid END,
                      now()-interval '1 hour',now()-(n||' seconds')::interval,now()
               FROM feature5_scale_ids""",
            (
                "11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222",
                "33333333-3333-4333-8333-444444444444", "11111111-1111-1111-1111-111111111111",
                "22222222-2222-2222-2222-222222222222", "33333333-3333-4333-8333-444444444444",
            ),
        )
        conn.execute(
            """INSERT INTO public.processing_jobs
                 (document_id,status,current_stage,progress_percentage,attempt_count,
                  started_at,finished_at,created_at,updated_at)
               SELECT id,'completed','extracting',100,1,now()-interval '2 hours',
                      now()-interval '1 hour',now()-(n||' seconds')::interval,now()
               FROM feature5_scale_ids"""
        )
        conn.execute(
            """INSERT INTO public.extraction_runs
                 (document_id,job_id,status,pipeline_version,configuration_hash,parser_version,
                  ocr_policy_version,embedding_revision,llm_provider,llm_model,prompt_version,
                  retrieval_config,started_at,finished_at)
               SELECT s.id,j.id,'completed','feature5-scale-v1',repeat('a',64),'1.0','ocr-v1',
                      %s,'groq','synthetic','prompt-v1','{}'::jsonb,
                      now()-interval '2 hours',now()-interval '1 hour'
               FROM feature5_scale_ids s JOIN public.processing_jobs j ON j.document_id=s.id""",
            (revision,),
        )
        conn.execute(
            """INSERT INTO public.document_chunks
                 (document_id,pipeline_version,ordinal,page_start,page_end,chunk_type,retrieval_role,
                  raw_content,token_count,content_hash,embedding,embedding_model,
                  embedding_revision,embedding_status)
               SELECT id,'feature5-scale-v1',0,1,1,'text','both','synthetic export search '||n,4,
                      encode(digest('chunk:'||tenant::text||':'||n,'sha256'),'hex'),
                      CASE WHEN tenant=%s::uuid THEN %s::vector ELSE %s::vector END,
                      %s,%s,'completed'
               FROM feature5_scale_ids""",
            ("11111111-1111-1111-1111-111111111111", vector_a, vector_b, model, revision),
        )
        conn.execute(
            """INSERT INTO public.invoices
                 (document_id,extraction_run_id,invoice_number,supplier_name,date_issued,
                  currency,subtotal,tax_amount,discount_amount,grand_total,is_math_valid)
               SELECT s.id,r.id,'F5-'||s.n,
                      CASE WHEN s.n=500 THEN '=FORMULA-SAFE' ELSE 'Synthetic Ω Supplier '||s.n END,
                      DATE '2026-01-01'+(s.n%30),CASE WHEN s.n%2=0 THEN 'USD' ELSE 'BDT' END,
                      s.n,0,0,s.n,true
               FROM feature5_scale_ids s JOIN public.extraction_runs r ON r.document_id=s.id"""
        )
        conn.execute(
            """INSERT INTO public.line_items
                 (invoice_id,source_row_key,line_order,description,quantity,unit_price,total_price)
               SELECT i.id,'scale-row-1',1,'Synthetic item '||s.n,1,s.n,s.n
               FROM feature5_scale_ids s JOIN public.invoices i ON i.document_id=s.id"""
        )

        criteria_500 = json.dumps({"selection_type": "criteria", "requested_document_count": 500})
        criteria_501 = json.dumps({"selection_type": "criteria", "requested_document_count": 501})
        for job_id, tenant, user, count, criteria in (
            (job_500, "11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222", 500, criteria_500),
            (job_501, "11111111-1111-1111-1111-222222222222", "33333333-3333-4333-8333-444444444444", 501, criteria_501),
        ):
            conn.execute(
                """INSERT INTO public.export_jobs
                     (id,company_id,requested_by_user_id,format,mode,status,current_stage,
                      selection_type,schema_version,criteria_json,criteria_hash,request_hash,
                      selected_document_count,request_id)
                   VALUES (%s,%s,%s,'json','asynchronous','queued','accepted','criteria',
                           'docusense-approved-invoice-export-v1',%s::jsonb,
                           encode(digest(%s,'sha256'),'hex'),encode(digest(%s,'sha256'),'hex'),%s,%s)""",
                (job_id, tenant, user, criteria, criteria, "request:" + criteria, count, f"feature5-boundary-{count}"),
            )
            conn.execute(
                """INSERT INTO public.export_job_documents
                     (export_job_id,document_id,review_revision,ordinal,source_value_hash)
                   SELECT %s,id,1,n-1,public.compute_export_source_value_hash(id)
                   FROM feature5_scale_ids WHERE tenant=%s ORDER BY n LIMIT %s""",
                (job_id, tenant, count),
            )
        conn.execute(
            "SET CONSTRAINTS trg_export_jobs_membership_commit, trg_export_job_documents_membership_commit IMMEDIATE"
        )
        assert conn.execute(
            "SELECT selected_document_count,count(*) FROM public.export_jobs j JOIN public.export_job_documents d ON d.export_job_id=j.id WHERE j.id IN (%s,%s) GROUP BY j.id,selected_document_count ORDER BY selected_document_count",
            (job_500, job_501),
        ).fetchall() == [(500, 500), (501, 501)]

        for table in ("documents", "processing_jobs", "document_chunks", "extraction_runs", "invoices", "line_items", "export_job_documents"):
            conn.execute(f"ANALYZE public.{table}")

        # Stable page boundary: exactly 500 rows then one final row, with no tenant leak.
        tenant_a = "11111111-1111-1111-1111-111111111111"
        first_page = conn.execute(
            "SELECT id FROM public.documents WHERE company_id=%s AND status='approved' AND id IN (SELECT id FROM feature5_scale_ids) ORDER BY created_at DESC,id DESC LIMIT 500",
            (tenant_a,),
        ).fetchall()
        last_page = conn.execute(
            "SELECT id FROM public.documents WHERE company_id=%s AND status='approved' AND id IN (SELECT id FROM feature5_scale_ids) ORDER BY created_at DESC,id DESC OFFSET 500 LIMIT 500",
            (tenant_a,),
        ).fetchall()
        assert len(first_page) == 500 and len(last_page) == 1
        assert len({row[0] for row in first_page + last_page}) == 501

        search_rows = conn.execute(
            """SELECT d.id,1-(c.embedding<=>%s::vector) AS score
               FROM public.documents d JOIN public.document_chunks c ON c.document_id=d.id
               JOIN public.invoices i ON i.document_id=d.id
               WHERE d.company_id=%s AND d.status='approved' AND i.currency='USD'
                 AND c.embedding_model=%s AND c.embedding_revision=%s
                 AND c.embedding_status='completed' AND c.retrieval_role IN ('child','both')
                 AND d.id IN (SELECT id FROM feature5_scale_ids)
               ORDER BY c.embedding<=>%s::vector,d.id LIMIT 20""",
            (vector_a, tenant_a, model, revision, vector_a),
        ).fetchall()
        assert len(search_rows) == 20 and all(abs(float(row[1]) - 1.0) < 1e-9 for row in search_rows)

        plans = {
            "tenant_search": ("SELECT id FROM public.documents WHERE company_id=%s AND status='approved' AND doc_type='commercial_invoice' ORDER BY created_at DESC,id DESC LIMIT 50", (tenant_a,)),
            "invoice_currency_date": ("SELECT document_id FROM public.invoices WHERE currency='USD' AND date_issued BETWEEN DATE '2026-01-01' AND DATE '2026-01-31' ORDER BY date_issued,document_id LIMIT 50", ()),
            "invoice_total": ("SELECT document_id FROM public.invoices WHERE grand_total BETWEEN 490 AND 501 ORDER BY grand_total,document_id LIMIT 50", ()),
            "vector_compatibility": ("SELECT document_id FROM public.document_chunks WHERE embedding_model=%s AND embedding_revision=%s AND embedding_status='completed' AND embedding IS NOT NULL AND retrieval_role IN ('child','both') ORDER BY document_id,ordinal LIMIT 50", (model, revision)),
        }
        rendered = ""
        for name, (query, params) in plans.items():
            payload = conn.execute(
                "EXPLAIN (ANALYZE, BUFFERS, SETTINGS, FORMAT JSON) " + query, params
            ).fetchone()[0][0]
            assert payload["Execution Time"] < 5000, name
            assert payload["Plan"]["Actual Rows"] <= 50, name
            rendered += json.dumps(payload, sort_keys=True)
        # PostgreSQL may legitimately choose a sequential or predecessor-prefix
        # index at this small/selective synthetic distribution. The catalog gate
        # still requires every reviewed online index to be valid and ready.
        assert rendered
        assert conn.execute(
            """SELECT count(*) FROM pg_class c JOIN pg_index i ON i.indexrelid=c.oid
               WHERE c.relname=ANY(%s) AND i.indisvalid AND i.indisready""",
            (list(ONLINE_INDEXES),),
        ).fetchone()[0] == len(ONLINE_INDEXES)
        conn.rollback()


def test_live_dse_db47_48_safe_and_unsafe_downgrade(live_database):
    database, _ = live_database
    # The fixture setup already proved empty 0006->0005->0004->0006. Once rows
    # exist, the same downgrade must refuse before removing an index or table.
    with pytest.raises(Exception, match="acknowledged empty disposable export database"):
        database.migrate(CORE_REVISION, down=True)
    with database.connect() as conn:
        assert conn.execute("SELECT version_num FROM public.alembic_version").fetchone()[0] == NEW_REVISION
        assert conn.execute("SELECT to_regclass('public.idx_documents_company_search')").fetchone()[0]
        assert conn.execute("SELECT count(*) FROM public.export_jobs").fetchone()[0] >= 7
