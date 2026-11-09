from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from pglast import parse_sql


TEST_ROOT = Path(__file__).resolve().parent
FEATURE_ROOT = TEST_ROOT.parent
SEEDS = FEATURE_ROOT / "seeds"
QUERY_FILE = FEATURE_ROOT / "queries" / "dashboard_activity.queries.sql"
FIXTURE_FILE = SEEDS / "generate_fixtures.py"
LOADER_FILE = SEEDS / "seed_dashboard_activity.py"
MANIFEST_FILE = SEEDS / "dashboard-activity-fixtures" / "manifest.json"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


fixtures = load_module("dashboard_activity_fixtures_test", FIXTURE_FILE)
loader = load_module("seed_dashboard_activity_test", LOADER_FILE)


def named_queries() -> dict[str, str]:
    source = QUERY_FILE.read_text(encoding="utf-8")
    matches = list(re.finditer(r"(?m)^-- name: ([a-z0-9_]+)\s*$", source))
    result: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(source)
        result[match.group(1)] = source[match.end():end].strip()
    return result


def live_settings() -> tuple[str, str]:
    url = os.getenv("DOCUSENSE_DASHBOARD_ACTIVITY_TEST_DATABASE_URL", "")
    acknowledgement = os.getenv("DOCUSENSE_DASHBOARD_ACTIVITY_TEST_ACK", "")
    if not url or not acknowledgement:
        pytest.skip("requires an explicitly acknowledged disposable dashboard database")
    return url, acknowledgement


@pytest.fixture(scope="session")
def live_engine():
    url, acknowledgement = live_settings()
    loader.preflight(
        url,
        acknowledgement,
        os.getenv("DOCUSENSE_DASHBOARD_ACTIVITY_NO_CONSUMERS", ""),
    )
    engine = sa.create_engine(url, future=True, pool_pre_ping=True)
    try:
        yield engine
    finally:
        engine.dispose()


def query_parameters(connection, *, company_id=None, from_at=None, to_at=None, bucket="day", page=1):
    if company_id is None:
        company_id = connection.scalar(sa.text(
            "SELECT company_id FROM documents GROUP BY company_id ORDER BY count(*) DESC, company_id LIMIT 1"
        ))
    catalog = connection.execute(sa.text(
        """SELECT DISTINCT r.pipeline_version,v.rule_id,v.scope_key,
                  true AS allows_not_applicable
           FROM extraction_runs r JOIN validation_results v ON v.extraction_run_id=r.id
           JOIN documents d ON d.id=r.document_id
           WHERE d.company_id=:company_id ORDER BY 1,2,3"""
    ), {"company_id": company_id}).mappings().all()
    return {
        "company_id": str(company_id),
        "from_at": from_at or datetime(2026, 1, 1, tzinfo=UTC),
        "to_at": to_at or datetime(2027, 1, 1, tzinfo=UTC),
        "snapshot_at": datetime(2027, 1, 1, tzinfo=UTC),
        "validation_catalog_json": json.dumps([dict(row) for row in catalog]),
        "event_types_json": "[]",
        "page_size": 20,
        "page": page,
        "bucket": bucket,
    }


def execute_query(connection, name: str, parameters: dict[str, object]):
    return connection.execute(sa.text(named_queries()[name]), parameters)


def parseable_sql(query: str) -> str:
    replacements = {
        ":company_id": "'da000000-0000-4000-8000-000000000001'",
        ":from_at": "'2026-08-12T12:00:00+00:00'",
        ":to_at": "'2026-09-11T12:00:00+00:00'",
        ":snapshot_at": "'2026-09-11T12:00:00+00:00'",
        ":validation_catalog_json": "'[]'",
        ":event_types_json": "'[]'",
        ":page_size": "20",
        ":page": "1",
        ":bucket": "'day'",
    }
    for bind, literal in sorted(replacements.items(), key=lambda item: -len(item[0])):
        query = query.replace(bind, literal)
    return query


def test_da_db_01_final_package_has_no_schema_migration():
    assert QUERY_FILE.is_file()
    assert not (FEATURE_ROOT / "migrations").exists()


def test_da_db_02_query_reference_has_the_locked_named_operations_and_parses():
    queries = named_queries()
    assert set(queries) == {
        "dashboard_status_snapshot",
        "dashboard_period_metrics",
        "dashboard_initial_validation",
        "dashboard_review_cycle_metrics",
        "dashboard_review_backlog_series",
        "activity_admin_operator_page",
        "activity_viewer_page",
    }
    for name, query in queries.items():
        assert len(parse_sql(parseable_sql(query))) == 1, name


def test_da_db_03_query_reference_is_read_only_and_tenant_scoped():
    source = QUERY_FILE.read_text(encoding="utf-8").lower()
    prohibited = ("create table", "alter table", "create index", "insert into", "update ", "delete from", "drop ")
    assert not any(token in source for token in prohibited)
    for query in named_queries().values():
        assert ":company_id" in query
    assert "union all" in source
    assert "enable_seqscan" not in source


def test_da_db_04_manifest_checksum_and_approved_targets_are_exact():
    manifest = fixtures.validate_manifest()
    assert manifest["contract_sha256"] == fixtures.contract_sha256()
    assert manifest["approved_p95_ms"] == fixtures.APPROVED_P95_MS
    assert fixtures.APPROVED_PERFORMANCE_CORPUS["documents_and_jobs_min"] == 20_000
    assert fixtures.INDEX_GATES == {
        "minimum_p95_improvement_percent": 25,
        "maximum_write_p95_regression_percent": 10,
        "maximum_lock_acquisition_seconds": 5,
    }


def test_da_db_05_oracle_covers_all_events_tenants_and_stable_order():
    expected = {
        "document_uploaded", "processing_completed", "processing_failed",
        "review_saved", "document_approved", "document_rejected",
        "document_reopened", "export_requested", "export_completed",
        "export_failed", "export_expired",
    }
    assert {event.event_type for event in fixtures.TENANT_A_EVENTS} == expected
    assert all(event.company_id == fixtures.TENANT_A for event in fixtures.TENANT_A_EVENTS)
    assert all(event.company_id == fixtures.TENANT_B for event in fixtures.TENANT_B_EVENTS)
    ordered = fixtures.ordered(fixtures.TENANT_A_EVENTS)
    assert ordered == fixtures.ordered(tuple(reversed(fixtures.TENANT_A_EVENTS)))


def test_da_db_06_viewer_export_identity_is_stable_opaque_and_matches_sql_contract():
    event_id = fixtures.opaque_viewer_export_event_id(fixtures.TENANT_A, fixtures.VIEWER_EXPORT_SOURCE)
    assert re.fullmatch(r"export_completed:opaque_[0-9a-f]{64}", event_id)
    assert str(fixtures.VIEWER_EXPORT_SOURCE) not in event_id
    canonical = (
        f"docusense-activity-viewer-v1\0{fixtures.TENANT_A}"
        f"\0export_completed\0{fixtures.VIEWER_EXPORT_SOURCE}"
    ).encode("utf-8")
    assert event_id.endswith(hashlib.sha256(canonical).hexdigest())
    viewer = named_queries()["activity_viewer_page"]
    assert "docusense-activity-viewer-v1" in viewer
    assert "digest(" in viewer and viewer.count("decode('00','hex')") == 3
    final_projection = viewer[viewer.rfind("SELECT event_id"):]
    assert "source_uuid AS" not in final_projection
    assert "NULL::uuid AS export_id" in final_projection


def test_da_db_07_viewer_filtering_happens_before_total_and_pagination():
    viewer = named_queries()["activity_viewer_page"]
    where_position = viewer.index("WHERE occurred_at <=")
    count_position = viewer.index("count(*) OVER")
    limit_position = viewer.index("LIMIT")
    assert where_position < count_position < limit_position
    assert "d.status = 'approved'" in viewer
    assert "e.company_id = CAST(:company_id AS uuid)" in viewer


@pytest.mark.parametrize(
    ("url", "ack", "confirmation", "message"),
    [
        ("postgresql+psycopg://u:p@example.com/db", "db", "I_CONFIRM_NO_CONSUMERS", "loopback"),
        ("postgresql+psycopg://u:p@localhost/other", "other", "I_CONFIRM_NO_CONSUMERS", "start with"),
        ("postgresql+psycopg://u:p@localhost/docusense_dashboard_activity_test_a", "wrong", "I_CONFIRM_NO_CONSUMERS", "exactly equal"),
        ("postgresql+psycopg://u:p@localhost/docusense_dashboard_activity_test_a", "docusense_dashboard_activity_test_a", "no", "explicit"),
    ],
)
def test_da_db_08_loader_refuses_unsafe_targets(url, ack, confirmation, message):
    with pytest.raises(ValueError, match=message):
        loader.validate_target(loader.make_url(url), ack, confirmation)


def test_da_db_09_no_optional_index_migration_exists_without_evidence():
    assert not (FEATURE_ROOT / "migrations" / "20260911_0007_dashboard_activity_migration.py").exists()
    assert not (FEATURE_ROOT / "migrations" / "20260911_dashboard_activity_indexes.sql").exists()


def test_da_db_10_live_target_preflight():
    url = os.getenv("DOCUSENSE_DASHBOARD_ACTIVITY_TEST_DATABASE_URL")
    acknowledgement = os.getenv("DOCUSENSE_DASHBOARD_ACTIVITY_TEST_ACK")
    if not url or not acknowledgement:
        pytest.skip("requires an explicitly acknowledged disposable dashboard database")
    result = loader.preflight(url, acknowledgement, os.getenv("DOCUSENSE_DASHBOARD_ACTIVITY_NO_CONSUMERS", ""))
    assert result["predecessor_head"] == fixtures.PREDECESSOR_HEAD
    assert result["writes_performed"] == 0


def test_live_da_db_01_10_catalog_head_indexes_and_prohibited_objects(live_engine):
    with live_engine.connect() as connection:
        assert connection.scalar(sa.text("SELECT version_num FROM alembic_version")) == "20260907_0006"
        assert int(connection.scalar(sa.text("SHOW server_version_num"))) >= 150000
        assert set(connection.execute(sa.text(
            "SELECT extname FROM pg_extension WHERE extname IN ('pgcrypto','vector')"
        )).scalars()) == {"pgcrypto", "vector"}
        prohibited = set(connection.execute(sa.text(
            """SELECT tablename FROM pg_tables WHERE schemaname='public'
               AND tablename IN ('dashboard_metrics','daily_metrics','activity_events',
                 'search_events','dashboard_cache','audit_logs')"""
        )).scalars())
        assert prohibited == set()
        assert connection.scalar(sa.text(
            "SELECT count(*) FROM alembic_version WHERE version_num LIKE '%0007'"
        )) == 0
        existing_indexes = set(connection.execute(sa.text(
            """SELECT indexname FROM pg_indexes WHERE schemaname='public' AND indexname IN
              ('idx_documents_company_created','idx_documents_company_status_created',
               'idx_documents_company_review_state','idx_review_audit_document_created',
               'idx_review_audit_document_action','idx_export_jobs_company_created')"""
        )).scalars())
        assert len(existing_indexes) == 6
        parameters = query_parameters(connection)
        for name in named_queries():
            rows = execute_query(connection, name, parameters).fetchall()
            assert rows is not None, name


def test_live_da_db_11_28_snapshot_time_cards_durations_and_validation(live_engine):
    with live_engine.connect() as connection:
        connection.execute(sa.text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        parameters = query_parameters(connection)
        company_id = parameters["company_id"]
        status = execute_query(connection, "dashboard_status_snapshot", parameters).mappings().one()
        direct = dict(connection.execute(sa.text(
            "SELECT status,count(*) FROM documents WHERE company_id=:company_id GROUP BY status"
        ), {"company_id": company_id}).all())
        assert status["total_documents"] == sum(direct.values())
        assert status["approved_documents"] == direct.get("approved", 0)
        assert status["rejected_documents"] == direct.get("rejected", 0)
        assert status["failed_documents"] == direct.get("failed", 0)
        assert sum(status["status_distribution"].values()) == status["total_documents"]

        period = execute_query(connection, "dashboard_period_metrics", parameters).mappings().one()
        expected_uploads = connection.scalar(sa.text(
            """SELECT count(*) FROM documents WHERE company_id=:company_id
               AND created_at>=:from_at AND created_at<:to_at"""
        ), parameters)
        assert period["uploaded"] == expected_uploads
        assert period["successful_processing_sample_count"] >= 0
        if period["successful_processing_sample_count"]:
            assert period["average_successful_processing_ms"] >= 0
            assert period["median_successful_processing_ms"] >= 0

        validation = execute_query(connection, "dashboard_initial_validation", parameters).mappings().one()
        assert validation["eligible_count"] >= validation["passed_count"]
        assert validation["incomplete_count"] >= 0
        assert validation["unknown_catalog_count"] == 0
        if validation["eligible_count"]:
            expected_rate = round(100 * validation["passed_count"] / validation["eligible_count"], 2)
            assert float(validation["initial_validation_pass_rate"]) == expected_rate

        boundary = dict(parameters)
        exact = connection.scalar(sa.text(
            "SELECT min(created_at) FROM documents WHERE company_id=:company_id"
        ), parameters)
        boundary.update(from_at=exact, to_at=exact)
        assert execute_query(connection, "dashboard_period_metrics", boundary).mappings().one()["uploaded"] == 0
        boundary["to_at"] = exact.replace(microsecond=exact.microsecond + 1)
        assert execute_query(connection, "dashboard_period_metrics", boundary).mappings().one()["uploaded"] >= 1
        connection.rollback()


def test_live_da_db_29_43_review_backlog_activity_order_and_redaction(live_engine):
    with live_engine.connect() as connection:
        parameters = query_parameters(connection)
        review = execute_query(connection, "dashboard_review_cycle_metrics", parameters).mappings().one()
        assert review["approval_cycle_count"] >= review["corrected_approval_cycle_count"] >= 0
        assert review["first_decision_sample_count"] >= 0
        assert review["review_timing_integrity_exclusion_count"] >= 0

        backlog = execute_query(connection, "dashboard_review_backlog_series", parameters).mappings().all()
        assert backlog
        assert [row["bucket_start"] for row in backlog] == sorted(row["bucket_start"] for row in backlog)
        assert not any(row["has_integrity_failure"] for row in backlog)

        admin = execute_query(connection, "activity_admin_operator_page", parameters).mappings().all()
        assert admin
        admin_keys = set(admin[0])
        assert not admin_keys.intersection({
            "reason", "note", "error_message", "criteria_json", "artifact_object_key",
            "source_value", "raw_content", "embedding",
        })
        ordering = [
            (-row["occurred_at"].timestamp(), row["event_type"], -uuid.UUID(row["event_id"].split(":", 1)[1]).int)
            for row in admin
        ]
        assert ordering == sorted(ordering)

        viewer = execute_query(connection, "activity_viewer_page", parameters).mappings().all()
        assert viewer
        assert {row["event_type"] for row in viewer} <= {"document_approved", "export_completed"}
        for row in viewer:
            if row["event_type"] == "export_completed":
                assert row["export_id"] is None and row["actor_user_id"] is None
                assert re.fullmatch(r"export_completed:opaque_[0-9a-f]{64}", row["event_id"])
        assert all(row["total_count"] == viewer[0]["total_count"] for row in viewer)

        foreign_company = connection.scalar(sa.text(
            "SELECT company_id FROM documents WHERE company_id<>CAST(:company_id AS uuid) LIMIT 1"
        ), parameters)
        foreign = dict(parameters, company_id=str(foreign_company))
        foreign_admin = execute_query(connection, "activity_admin_operator_page", foreign).mappings().all()
        assert {row["event_id"] for row in admin}.isdisjoint({row["event_id"] for row in foreign_admin})


def test_live_da_db_44_45_repeatable_read_and_failed_statement_cleanup(live_engine):
    company_id = None
    inserted_id = uuid.UUID("daff0000-0000-4000-8000-000000000044")
    first = live_engine.connect().execution_options(isolation_level="REPEATABLE READ")
    writer = live_engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    try:
        company_id = first.scalar(sa.text(
            "SELECT company_id FROM documents GROUP BY company_id ORDER BY count(*) DESC LIMIT 1"
        ))
        before = first.scalar(sa.text(
            "SELECT count(*) FROM documents WHERE company_id=:company_id"
        ), {"company_id": company_id})
        writer.execute(sa.text(
            """INSERT INTO documents
               SELECT (jsonb_populate_record(NULL::documents, to_jsonb(d) || jsonb_build_object(
                 'id',CAST(:id AS text),'file_name','snapshot-concurrency.pdf',
                 's3_url','s3://docusense-db-fixtures/' || CAST(:company_id AS text) ||
                   '/' || CAST(:id AS text) || '/snapshot-concurrency.pdf',
                 'file_hash',repeat('d',64),'status','queued',
                 'created_at','2026-09-11T11:59:59+00:00',
                 'updated_at','2026-09-11T11:59:59+00:00'))).*
               FROM documents d WHERE d.company_id=:company_id LIMIT 1"""
        ), {"id": str(inserted_id), "company_id": company_id})
        during = first.scalar(sa.text(
            "SELECT count(*) FROM documents WHERE company_id=:company_id"
        ), {"company_id": company_id})
        assert during == before
        first.rollback()
        assert first.scalar(sa.text(
            "SELECT count(*) FROM documents WHERE company_id=:company_id"
        ), {"company_id": company_id}) == before + 1
    finally:
        first.close()
        if company_id is not None:
            writer.execute(sa.text("DELETE FROM documents WHERE id=:id"), {"id": inserted_id})
        writer.close()

    with live_engine.connect() as connection:
        transaction = connection.begin()
        connection.execute(sa.text("SET LOCAL statement_timeout='1ms'"))
        with pytest.raises(sa.exc.DBAPIError):
            connection.execute(sa.text("SELECT pg_sleep(0.05)"))
        transaction.rollback()
        assert connection.scalar(sa.text("SELECT 1")) == 1


def create_representative_temp_corpus(connection) -> None:
    connection.execute(sa.text("SET LOCAL timezone='UTC'"))
    connection.execute(sa.text("SET LOCAL work_mem='64MB'"))
    schema_sql = """
      CREATE TEMP TABLE documents (
        id uuid PRIMARY KEY, company_id uuid NOT NULL, uploaded_by uuid,
        file_name text NOT NULL, status text NOT NULL, created_at timestamptz NOT NULL
      ) ON COMMIT DROP;
      CREATE TEMP TABLE processing_jobs (
        id uuid PRIMARY KEY, document_id uuid NOT NULL UNIQUE, status text NOT NULL,
        started_at timestamptz, finished_at timestamptz
      ) ON COMMIT DROP;
      CREATE TEMP TABLE extraction_runs (
        id uuid PRIMARY KEY, document_id uuid NOT NULL UNIQUE, status text NOT NULL,
        pipeline_version text NOT NULL, finished_at timestamptz
      ) ON COMMIT DROP;
      CREATE TEMP TABLE validation_results (
        id uuid PRIMARY KEY, extraction_run_id uuid NOT NULL, rule_id text NOT NULL,
        scope_key text NOT NULL, status text NOT NULL,
        UNIQUE(extraction_run_id,rule_id,scope_key)
      ) ON COMMIT DROP;
      CREATE TEMP TABLE review_audit_events (
        id uuid PRIMARY KEY, document_id uuid NOT NULL, actor_user_id uuid,
        action text NOT NULL, review_revision bigint NOT NULL, created_at timestamptz NOT NULL,
        UNIQUE(document_id,review_revision)
      ) ON COMMIT DROP;
      CREATE TEMP TABLE review_audit_changes (
        id uuid PRIMARY KEY, audit_event_id uuid NOT NULL
      ) ON COMMIT DROP;
      CREATE TEMP TABLE export_jobs (
        id uuid PRIMARY KEY, company_id uuid NOT NULL, requested_by_user_id uuid,
        format text NOT NULL, mode text NOT NULL, status text NOT NULL,
        selected_document_count integer NOT NULL, created_at timestamptz NOT NULL,
        completed_at timestamptz, failed_at timestamptz, expired_at timestamptz
      ) ON COMMIT DROP;

      CREATE INDEX idx_documents_company_created ON documents(company_id,created_at DESC,id DESC);
      CREATE INDEX idx_documents_company_status_created ON documents(company_id,status,created_at DESC,id DESC);
      CREATE INDEX idx_processing_jobs_dispatch ON processing_jobs(status,finished_at,document_id);
      CREATE INDEX idx_extraction_runs_document ON extraction_runs(document_id);
      CREATE INDEX idx_validation_results_run ON validation_results(extraction_run_id,rule_id,scope_key);
      CREATE INDEX idx_review_audit_document_created ON review_audit_events(document_id,created_at DESC,id DESC);
      CREATE INDEX idx_review_audit_document_action ON review_audit_events(document_id,action,review_revision);
      CREATE INDEX idx_review_changes_event ON review_audit_changes(audit_event_id);
      CREATE INDEX idx_export_jobs_company_created ON export_jobs(company_id,created_at DESC,id DESC);
    """
    for statement in (part.strip() for part in schema_sql.split(";") if part.strip()):
        connection.execute(sa.text(statement))
    population_sql = """
      INSERT INTO documents
      SELECT md5('doc-'||g)::uuid,
        CASE WHEN g<=18000 THEN CAST(:tenant_a AS uuid) ELSE CAST(:tenant_b AS uuid) END,
        md5('user-'||(g%3))::uuid, 'synthetic-'||g||'.pdf',
        (ARRAY['queued','partitioning','chunking','vectorizing','extracting',
          'pending_review','approved','rejected','failed'])[(g%9)+1],
        CAST(:snapshot_at AS timestamptz) - ((g%366)||' days')::interval
      FROM generate_series(1,20000) AS s(g);

      INSERT INTO processing_jobs
      SELECT md5('job-'||g)::uuid, md5('doc-'||g)::uuid,
        CASE WHEN g<=18000 THEN 'completed' ELSE 'failed' END,
        CAST(:snapshot_at AS timestamptz) - (((g%366)+2)||' days')::interval - interval '4 minutes',
        CAST(:snapshot_at AS timestamptz) - (((g%366)+2)||' days')::interval
      FROM generate_series(1,20000) AS s(g);

      INSERT INTO extraction_runs
      SELECT md5('run-'||g)::uuid, md5('doc-'||g)::uuid, 'completed',
        'dashboard-scale-v1', CAST(:snapshot_at AS timestamptz) - (((g%366)+1)||' days')::interval
      FROM generate_series(1,15000) AS s(g);

      INSERT INTO validation_results
      SELECT md5('validation-'||g||'-'||r)::uuid, md5('run-'||g)::uuid,
        'BR-'||lpad(r::text,2,'0'), 'document',
        CASE WHEN (g+r)%20=0 THEN 'failed' ELSE 'passed' END
      FROM generate_series(1,15000) AS s(g)
      CROSS JOIN generate_series(1,10) AS rules(r);

      INSERT INTO review_audit_events
      SELECT md5('review-'||g)::uuid,
        md5('doc-'||(((g-1)%18000)+1))::uuid,
        md5('reviewer-'||(g%3))::uuid,
        CASE WHEN g<=18000 THEN 'field_edited'
             WHEN g<=36000 THEN 'approved' ELSE 'reopened' END,
        ((g-1)/18000)+1,
        CAST(:snapshot_at AS timestamptz) - ((g%366)||' days')::interval + interval '1 hour'
      FROM generate_series(1,50000) AS s(g);

      INSERT INTO review_audit_changes
      SELECT md5('change-'||g)::uuid, md5('review-'||g)::uuid
      FROM generate_series(1,50000) AS s(g);

      INSERT INTO export_jobs
      SELECT md5('export-'||g)::uuid,
        CASE WHEN g<=9000 THEN CAST(:tenant_a AS uuid) ELSE CAST(:tenant_b AS uuid) END,
        md5('requester-'||(g%3))::uuid, 'csv', 'asynchronous',
        CASE (g%4) WHEN 0 THEN 'completed' WHEN 1 THEN 'failed'
          WHEN 2 THEN 'expired' ELSE 'queued' END,
        1, CAST(:snapshot_at AS timestamptz) - ((g%366)||' days')::interval,
        CASE WHEN g%4 IN (0,2) THEN CAST(:snapshot_at AS timestamptz) - ((g%366)||' days')::interval + interval '2 hours' END,
        CASE WHEN g%4=1 THEN CAST(:snapshot_at AS timestamptz) - ((g%366)||' days')::interval + interval '2 hours' END,
        CASE WHEN g%4=2 THEN CAST(:snapshot_at AS timestamptz) - ((g%366)||' days')::interval + interval '3 hours' END
      FROM generate_series(1,10000) AS s(g);

      ANALYZE documents; ANALYZE processing_jobs; ANALYZE extraction_runs;
      ANALYZE validation_results; ANALYZE review_audit_events;
      ANALYZE review_audit_changes; ANALYZE export_jobs;
    """
    population_parameters = {
        "tenant_a": str(fixtures.TENANT_A),
        "tenant_b": str(fixtures.TENANT_B),
        "snapshot_at": fixtures.SNAPSHOT_AT,
    }
    for statement in (part.strip() for part in population_sql.split(";") if part.strip()):
        connection.execute(sa.text(statement), population_parameters)


def p95(samples: list[float]) -> float:
    ordered = sorted(samples)
    return ordered[max(0, int(0.95 * len(ordered) + 0.999999) - 1)]


def timed_ms(connection, names: tuple[str, ...], parameters: dict[str, object], repetitions: int = 5) -> float:
    for name in names:
        execute_query(connection, name, parameters).fetchall()
    samples: list[float] = []
    for _ in range(repetitions):
        started = time.perf_counter()
        for name in names:
            execute_query(connection, name, parameters).fetchall()
        samples.append((time.perf_counter() - started) * 1000)
    return round(p95(samples), 3)


def test_live_da_db_46_50_representative_plans_targets_and_reconciliation(live_engine, capsys):
    with live_engine.connect() as connection:
        transaction = connection.begin()
        create_representative_temp_corpus(connection)
        counts = {
            "documents": connection.scalar(sa.text("SELECT count(*) FROM documents")),
            "jobs": connection.scalar(sa.text("SELECT count(*) FROM processing_jobs")),
            "runs": connection.scalar(sa.text("SELECT count(*) FROM extraction_runs")),
            "validations": connection.scalar(sa.text("SELECT count(*) FROM validation_results")),
            "reviews": connection.scalar(sa.text("SELECT count(*) FROM review_audit_events")),
            "changes": connection.scalar(sa.text("SELECT count(*) FROM review_audit_changes")),
            "exports": connection.scalar(sa.text("SELECT count(*) FROM export_jobs")),
        }
        assert counts == {
            "documents": 20000, "jobs": 20000, "runs": 15000,
            "validations": 150000, "reviews": 50000, "changes": 50000,
            "exports": 10000,
        }
        catalog = [
            {"pipeline_version": "dashboard-scale-v1", "rule_id": f"BR-{rule:02d}",
             "scope_key": "document", "allows_not_applicable": False}
            for rule in range(1, 11)
        ]
        base = {
            "company_id": str(fixtures.TENANT_A),
            "snapshot_at": fixtures.SNAPSHOT_AT,
            "validation_catalog_json": json.dumps(catalog),
            "event_types_json": "[]", "page_size": 20, "page": 1,
        }
        normal = dict(base, from_at=fixtures.NORMAL_FROM, to_at=fixtures.SNAPSHOT_AT, bucket="day")
        maximum = dict(base, from_at=fixtures.MAX_FROM, to_at=fixtures.SNAPSHOT_AT, bucket="month")
        dashboard_queries = (
            "dashboard_status_snapshot", "dashboard_period_metrics",
            "dashboard_initial_validation", "dashboard_review_cycle_metrics",
            "dashboard_review_backlog_series",
        )
        evidence = {
            "dashboard_30_day_p95_ms": timed_ms(connection, dashboard_queries, normal),
            "dashboard_366_day_p95_ms": timed_ms(connection, dashboard_queries, maximum),
            "activity_first_page_p95_ms": timed_ms(connection, ("activity_admin_operator_page",), normal),
            "activity_deep_page_p95_ms": timed_ms(
                connection, ("activity_admin_operator_page",), dict(normal, page=100)
            ),
        }
        individual = {
            name: timed_ms(connection, (name,), maximum, repetitions=2)
            for name in dashboard_queries
        }
        print("DASHBOARD_P95_EVIDENCE=" + json.dumps(
            {"combined": evidence, "maximum_individual": individual}, sort_keys=True
        ))
        assert evidence["dashboard_30_day_p95_ms"] <= fixtures.APPROVED_P95_MS["dashboard_30_day"]
        assert evidence["dashboard_366_day_p95_ms"] <= fixtures.APPROVED_P95_MS["dashboard_366_day"]
        assert evidence["activity_first_page_p95_ms"] <= fixtures.APPROVED_P95_MS["activity_first_page"]
        assert evidence["activity_deep_page_p95_ms"] <= fixtures.APPROVED_P95_MS["activity_deep_page"]

        plans = {}
        for name in dashboard_queries + ("activity_admin_operator_page", "activity_viewer_page"):
            plan = connection.execute(
                sa.text("EXPLAIN (ANALYZE, BUFFERS, SETTINGS, FORMAT JSON) " + named_queries()[name]),
                normal,
            ).scalar_one()[0]
            plans[name] = round(float(plan["Execution Time"]), 3)
        status = execute_query(connection, "dashboard_status_snapshot", normal).mappings().one()
        direct_total = connection.scalar(sa.text(
            "SELECT count(*) FROM documents WHERE company_id=CAST(:company_id AS uuid)"
        ), normal)
        assert status["total_documents"] == direct_total == 18000
        print("DASHBOARD_SCALE_EVIDENCE=" + json.dumps({
            "counts": counts, "p95_ms": evidence, "plan_execution_ms": plans,
            "new_index_required": False,
        }, sort_keys=True))
        transaction.rollback()
