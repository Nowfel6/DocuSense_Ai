"""Guarded preflight for the Feature 06 disposable verification fixture.

Feature 06 adds no persistent entity.  Source rows are created transactionally by
the live test harness and rolled back.  This command validates the exact target,
predecessor head, extensions, catalog and fixture checksum before that harness is
allowed to run; it never writes production/demo data.
"""

from __future__ import annotations

import argparse
import importlib.util
import ipaddress
import re
import sys
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.engine import URL, make_url


BUILD_DIR = Path(__file__).resolve().parent
FIXTURE_FILE = BUILD_DIR / "generate_fixtures.py"
REQUIRED_TABLES = {
    "companies", "users", "documents", "processing_jobs",
    "extraction_runs", "validation_results", "review_audit_events",
    "review_audit_changes", "export_jobs", "export_job_documents",
}


def load_fixture_module():
    spec = importlib.util.spec_from_file_location("dashboard_activity_fixtures", FIXTURE_FILE)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load dashboard activity fixture contract")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def is_loopback(host: str | None) -> bool:
    if not host:
        return False
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def validate_target(url: URL, acknowledgement: str, no_consumers: str) -> None:
    database = url.database or ""
    if acknowledgement != database:
        raise ValueError("--acknowledge-database must exactly equal the URL database name")
    if no_consumers != "I_CONFIRM_NO_CONSUMERS":
        raise ValueError("explicit --confirm-no-consumers I_CONFIRM_NO_CONSUMERS is required")
    if not is_loopback(url.host):
        raise ValueError("dashboard fixtures are restricted to loopback PostgreSQL")
    if not re.fullmatch(
        r"docusense_(?:dashboard_activity_test_|export_test_dashboard_)[a-z0-9_]+",
        database,
    ):
        raise ValueError(
            "database name must start with docusense_dashboard_activity_test_ "
            "or docusense_export_test_dashboard_"
        )


def preflight(database_url: str, acknowledgement: str, no_consumers: str) -> dict[str, object]:
    fixture = load_fixture_module()
    manifest = fixture.validate_manifest()
    url = make_url(database_url)
    validate_target(url, acknowledgement, no_consumers)

    engine = sa.create_engine(url, future=True, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            actual_db = connection.scalar(sa.text("SELECT current_database()"))
            if actual_db != acknowledgement:
                raise RuntimeError("connected database differs from acknowledgement")
            server_version = int(connection.scalar(sa.text("SHOW server_version_num")))
            if server_version < 150000:
                raise RuntimeError("PostgreSQL 15 or newer is required")
            consumers = connection.scalar(sa.text(
                "SELECT count(*) FROM pg_stat_activity "
                "WHERE datname=current_database() AND pid<>pg_backend_pid()"
            ))
            if consumers:
                raise RuntimeError("target has active consumers")
            head = connection.scalar(sa.text("SELECT version_num FROM alembic_version"))
            if head != fixture.PREDECESSOR_HEAD:
                raise RuntimeError(f"expected predecessor head {fixture.PREDECESSOR_HEAD}, got {head}")
            extensions = set(connection.execute(sa.text(
                "SELECT extname FROM pg_extension WHERE extname IN ('pgcrypto','vector')"
            )).scalars())
            if extensions != {"pgcrypto", "vector"}:
                raise RuntimeError("pgcrypto and vector extensions are required")
            tables = set(connection.execute(sa.text(
                "SELECT tablename FROM pg_tables WHERE schemaname='public'"
            )).scalars())
            missing = sorted(REQUIRED_TABLES - tables)
            if missing:
                raise RuntimeError(f"missing predecessor tables: {', '.join(missing)}")
    finally:
        engine.dispose()

    return {
        "database": acknowledgement,
        "predecessor_head": fixture.PREDECESSOR_HEAD,
        "fixture_version": manifest["fixture_version"],
        "contract_sha256": manifest["contract_sha256"],
        "writes_performed": 0,
        "next_step": "run the live transaction-scoped dashboard test harness",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--acknowledge-database", required=True)
    parser.add_argument("--confirm-no-consumers", required=True)
    args = parser.parse_args()
    result = preflight(args.database_url, args.acknowledge_database, args.confirm_no_consumers)
    print("dashboard activity disposable target preflight passed")
    print(f"database={result['database']} predecessor_head={result['predecessor_head']}")
    print("writes_performed=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
