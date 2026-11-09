"""Stage 3 database verification for document-processing-rag.

Offline checks always run. Live checks require the explicitly acknowledged
loopback disposable database used by the ingestion acceptance suite.
"""
from __future__ import annotations

import ast
import importlib.util
import json
import math
import os
from pathlib import Path
import shutil
import sys
import tempfile
import uuid

from alembic import command
from alembic.config import Config
import pglast
import psycopg
from psycopg import sql
import pytest
import sqlalchemy as sa

TEST_ROOT = Path(__file__).resolve().parent
FEATURE_ROOT = TEST_ROOT.parent
PROJECT_ROOT = FEATURE_ROOT.parents[1]
MIGRATIONS = FEATURE_ROOT / "migrations"
SEEDS = FEATURE_ROOT / "seeds"
BACKEND_ROOT = PROJECT_ROOT / "backend"
SQL_PATH = MIGRATIONS / "20260904_create_document_processing_rag.sql"
REV_PATH = MIGRATIONS / "20260904_0003_document_processing_rag_migration.py"
if str(SEEDS) not in sys.path:
    sys.path.insert(0, str(SEEDS))
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from seed_document_processing_rag import disposable_name, seed
NEW_REVISION = "20260904_0003"
PARENT_REVISION = "20260903_0002"
DOC_E = "66666666-6666-4666-8666-000000000001"
DOC_A = "66666666-6666-4666-8666-000000000003"
DOC_B = "66666666-6666-4666-8666-000000000004"
DOC_C = "66666666-6666-4666-8666-000000000005"
DOC_D = "66666666-6666-4666-8666-000000000006"
RAG_DOCUMENTS = [DOC_E, DOC_A, DOC_B, DOC_C, DOC_D]


def load_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_offline_python_sql_and_revision_identity():
    for path in [REV_PATH, BACKEND_ROOT / "app" / "document_processing_rag" / "models.py",
                 SEEDS / "generate_fixtures.py", SEEDS / "seed_document_processing_rag.py"]:
        ast.parse(path.read_text(encoding="utf-8"), filename=path.name)
    tree = json.loads(pglast.parser.parse_sql_json(SQL_PATH.read_text(encoding="utf-8")))
    statements = [entry["stmt"] for entry in tree["stmts"]]
    assert sum("CreateStmt" in item for item in statements) == 7
    assert sum("CreateTrigStmt" in item for item in statements) == 16
    assert sum("CreateFunctionStmt" in item for item in statements) == 11
    assert sum("IndexStmt" in item for item in statements) == 7
    assert len(pglast.parse_plpgsql(SQL_PATH.read_text(encoding="utf-8"))) == 13
    revision = load_file("rag_revision", REV_PATH)
    assert (revision.revision, revision.down_revision) == (NEW_REVISION, PARENT_REVISION)
    assert "BEGIN;" not in revision.upgrade_sql().split("DO $preflight$")[0]


def test_offline_fixture_dimensions_norms_and_tenant_split():
    fixture = load_file("rag_fixture_test", SEEDS / "generate_fixtures.py").fixture_payload()
    vectors = [chunk["embedding"] for chunk in fixture["chunks"] if chunk["embedding"] is not None]
    assert vectors and all(len(vector) == 384 for vector in vectors)
    assert all(all(math.isfinite(value) for value in vector) for vector in vectors)
    assert all(abs(math.sqrt(sum(value * value for value in vector)) - 1.0) < 1e-12 for vector in vectors)
    assert {run["document_id"] for run in fixture["runs"]} == set(RAG_DOCUMENTS)
    manifest = json.loads((SEEDS / "document-processing-rag-fixtures" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["counts"] == {"document_partitions": 5, "document_chunks": 7, "extraction_runs": 5, "invoices": 4,
                                  "line_items": 5, "field_evidence": 2, "validation_results": 2}


def load_models():
    from app.auth import models as auth
    from app.document_ingestion import models as ingestion
    from app.document_processing_rag import models as rag
    return auth, ingestion, rag


def test_offline_single_metadata_and_model_contract():
    auth, ingestion, rag = load_models()
    sa.orm.configure_mappers()
    assert auth.Base is ingestion.Base is rag.Base
    assert set(rag.Base.metadata.tables) >= {"companies", "users", "api_keys", "documents", "processing_jobs",
                                              "document_partitions", "document_chunks", "extraction_runs", "invoices", "line_items",
                                              "field_evidence", "validation_results"}
    assert len(rag.DocumentPartition.__table__.columns) == 13
    assert len(rag.ExtractionRun.__table__.columns) == 25
    assert "updated_at" not in rag.FieldEvidence.__table__.columns
    assert "updated_at" not in rag.ValidationResult.__table__.columns
    assert str(rag.DocumentChunk.__table__.c.embedding.type) == "VECTOR(384)"


@pytest.mark.parametrize("dsn,ack", [("", ""), ("host=localhost dbname=production", "production"),
                                      ("host=db.example.com dbname=docusense_rag_test_demo", "docusense_rag_test_demo")])
def test_offline_target_guards(dsn, ack):
    with pytest.raises(ValueError):
        disposable_name(dsn, ack)


class Database:
    def __init__(self, dsn, name, scripts):
        self.dsn, self.name, self.scripts = dsn, name, scripts

    def connect(self):
        try:
            return psycopg.connect(self.dsn, autocommit=True, connect_timeout=5,
                                   options="-c statement_timeout=15000 -c lock_timeout=3000")
        except psycopg.Error:
            raise RuntimeError("Disposable PostgreSQL connection failed; connection details suppressed") from None

    def migrate(self, target=NEW_REVISION, *, down=False):
        engine = sa.create_engine("postgresql+psycopg://", creator=self.connect)
        try:
            with engine.connect() as connection:
                with connection.begin():
                    connection.execute(sa.text("SELECT set_config('docusense.disposable_database', :name, true)"), {"name": self.name})
                    config = Config()
                    config.set_main_option("script_location", str(self.scripts).replace("%", "%%"))
                    config.attributes["connection"] = connection
                    (command.downgrade if down else command.upgrade)(config, target)
        finally:
            engine.dispose()


@pytest.fixture(scope="session")
def database():
    dsn = os.environ.get("RAG_TEST_DSN") or os.environ.get("INGESTION_TEST_DSN")
    if not dsn:
        pytest.skip("No acknowledged disposable PostgreSQL target; live RAG verification not performed")
    ack = os.environ.get("RAG_TEST_ACK") or os.environ.get("INGESTION_TEST_ACK", "")
    name = disposable_name(dsn, ack)
    if (os.environ.get("RAG_TEST_NO_CONSUMERS") or os.environ.get("INGESTION_TEST_NO_CONSUMERS")) != "1":
        pytest.fail("Explicit no-active-consumers assertion is required")
    with tempfile.TemporaryDirectory(prefix="docusense-rag-alembic-") as directory:
        scripts = Path(directory)
        versions = scripts / "versions"
        versions.mkdir()
        shutil.copy2(PROJECT_ROOT / "database" / "document_ingestion" / "tests" / "alembic_env.py", scripts / "env.py")
        sources = [
            PROJECT_ROOT / "database" / "auth" / "migrations" / "20260901_0001_auth_tenancy_migration.py",
            PROJECT_ROOT / "database" / "document_ingestion" / "migrations" / "20260903_0002_document_ingestion_migration.py",
            PROJECT_ROOT / "database" / "document_ingestion" / "migrations" / "20260903_create_document_ingestion.sql", REV_PATH, SQL_PATH,
        ]
        for source in sources:
            shutil.copy2(source, versions / source.name)
        db = Database(dsn, name, scripts)
        with db.connect() as conn:
            head = conn.execute("SELECT to_regclass('public.alembic_version')").fetchone()[0]
            head = conn.execute("SELECT version_num FROM public.alembic_version").fetchone()[0] if head else None
            if head != PARENT_REVISION:
                pytest.fail("Run the reviewed ingestion live suite first; expected verified predecessor 20260903_0002")
            parents = conn.execute("SELECT count(*) FROM public.documents WHERE id=ANY(%s::uuid[])", (RAG_DOCUMENTS,)).fetchone()[0]
            if parents != len(RAG_DOCUMENTS):
                pytest.fail("Verified ingestion fixture parents are missing")
        db.migrate()
        with db.connect() as conn:
            assert seed(conn, ack, no_active_consumers=True) == "inserted"
            assert seed(conn, ack, no_active_consumers=True) == "unchanged"
        yield db


@pytest.fixture
def db(database):
    with database.connect() as conn:
        yield conn


def test_rag_db01_05_catalog_vector_and_no_ann(db):
    assert db.execute("SELECT version_num FROM public.alembic_version").fetchone()[0] == NEW_REVISION
    counts = db.execute("""SELECT table_name,count(*) FROM information_schema.columns
      WHERE table_schema='public' AND table_name=ANY(%s) GROUP BY table_name""",
      (["document_partitions","document_chunks","extraction_runs","invoices","line_items","field_evidence","validation_results"],)).fetchall()
    assert dict(counts) == {"document_partitions": 13, "document_chunks": 23, "extraction_runs": 25, "invoices": 17,
                            "line_items": 12, "field_evidence": 16, "validation_results": 11}
    assert db.execute("SELECT extversion FROM pg_extension WHERE extname='vector'").fetchone()[0]
    assert db.execute("""SELECT format_type(atttypid,atttypmod) FROM pg_attribute
      WHERE attrelid='public.document_chunks'::regclass AND attname='embedding'""").fetchone()[0] == "vector(384)"
    assert not db.execute("""SELECT 1 FROM pg_indexes WHERE schemaname='public' AND tablename='document_chunks'
      AND indexdef ~* 'using (hnsw|ivfflat|gin)'""").fetchone()


def test_rag_db08_18_constraints_and_pairs(db):
    with pytest.raises(psycopg.Error):
        with db.transaction():
            db.execute("UPDATE public.document_chunks SET parent_chunk_id=%s WHERE id=%s",
                       ("88888888-8888-4888-8888-000000000002", "88888888-8888-4888-8888-000000000001"))
    with pytest.raises(psycopg.Error):
        with db.transaction():
            db.execute("""INSERT INTO public.extraction_runs
              (id,document_id,job_id,pipeline_version,configuration_hash,parser_version,ocr_policy_version,
               embedding_revision,llm_provider,llm_model,prompt_version,retrieval_config)
              VALUES (%s,%s,%s,'v1',repeat('a',64),'v','v','fixture','p','m','v','{}')""",
              (uuid.uuid4(), "66666666-6666-4666-8666-000000000002", "77777777-7777-4777-8777-000000000001"))
    with pytest.raises(psycopg.Error):
        with db.transaction():
            db.execute("UPDATE public.invoices SET grand_total=999 WHERE id='aaaaaaaa-aaaa-4aaa-8aaa-000000000001'")
    with pytest.raises(psycopg.Error):
        with db.transaction():
            db.execute("UPDATE public.field_evidence SET confidence_score=1 WHERE id='cccccccc-cccc-4ccc-8ccc-000000000001'")


def test_rag_db19_cascade_aware_immutability_and_direct_delete(db):
    with pytest.raises(psycopg.Error):
        with db.transaction():
            db.execute("DELETE FROM public.validation_results WHERE id='dddddddd-dddd-4ddd-8ddd-000000000001'")
    assert db.execute("SELECT count(*) FROM public.validation_results").fetchone()[0] == 2


def test_rag_db20_29_orm_catalog_parity(db, database):
    auth, ingestion, rag = load_models()
    engine = sa.create_engine("postgresql+psycopg://", creator=database.connect)
    try:
        inspector = sa.inspect(engine)
        for name in ("document_partitions","document_chunks","extraction_runs","invoices","line_items","field_evidence","validation_results"):
            mapped = rag.Base.metadata.tables[name]
            assert set(mapped.columns.keys()) == {column["name"] for column in inspector.get_columns(name, schema="public")}
            assert {index.name for index in mapped.indexes} <= {index["name"] for index in inspector.get_indexes(name, schema="public")}
    finally:
        engine.dispose()
    assert auth.Base is ingestion.Base is rag.Base
def test_rag_db30_34_tenant_scoped_exact_retrieval(db):
    query = '[' + ','.join(['1'] + ['0'] * 383) + ']'
    rows = db.execute("""SELECT c.document_id::text,c.id::text,1-(c.embedding <=> %s::vector) AS score
      FROM public.document_chunks c JOIN public.documents d ON d.id=c.document_id
      WHERE d.company_id=(SELECT company_id FROM public.documents WHERE id=%s)
        AND c.document_id=%s AND c.embedding_status='completed'
      ORDER BY c.embedding <=> %s::vector,c.ordinal,c.id LIMIT 5""", (query, DOC_A, DOC_A, query)).fetchall()
    assert [row[1] for row in rows] == ["88888888-8888-4888-8888-000000000002",
                                          "88888888-8888-4888-8888-000000000003"]
    assert all(row[0] == DOC_A for row in rows)
    assert rows[0][2] > rows[1][2]
    selected = db.execute("SELECT * FROM public.document_chunks LIMIT 0").description
    assert "embedding" in {column.name for column in selected}  # persistence has it
    api_columns = db.execute("SELECT id,ordinal,page_start,page_end,raw_content FROM public.document_chunks LIMIT 0").description
    assert "embedding" not in {column.name for column in api_columns}


def test_zz_rag_db06_07_guarded_downgrade_and_parent_preservation(database):
    with database.connect() as conn:
        with pytest.raises(sa.exc.DBAPIError, match="Rollback refused"):
            database.migrate(PARENT_REVISION, down=True)
        survivor = conn.execute("SELECT to_jsonb(d) FROM public.documents d WHERE id='66666666-6666-4666-8666-000000000001'").fetchone()[0]
        conn.execute("DELETE FROM public.documents WHERE id=ANY(%s::uuid[])", ([DOC_A, DOC_B, DOC_C, DOC_D],))
        assert all(conn.execute(sql.SQL("SELECT count(*) FROM public.{}").format(sql.Identifier(table))).fetchone()[0] == 0
                   for table in ("document_partitions","document_chunks","extraction_runs","invoices","line_items","field_evidence","validation_results"))
    database.migrate(PARENT_REVISION, down=True)
    with database.connect() as conn:
        assert conn.execute("SELECT to_regclass('public.document_chunks')").fetchone()[0] is None
        assert conn.execute("SELECT to_jsonb(d) FROM public.documents d WHERE id='66666666-6666-4666-8666-000000000001'").fetchone()[0] == survivor
        assert conn.execute("SELECT version_num FROM public.alembic_version").fetchone()[0] == PARENT_REVISION
    database.migrate()
