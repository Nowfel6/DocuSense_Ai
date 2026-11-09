# Document Ingestion Database Artifacts

Placed from database production output on 2026-09-03 at the user's request.
Status remains PENDING_VERIFICATION; see the [final issues](../../issue_missing.md).
This folder contains database implementation and development support only.

- `migrations/` keeps revision `20260903_0002` beside its companion SQL file.
  Its parent is the existing `../auth/migrations/20260901_0001_auth_tenancy_migration.py`.
  The canonical path is Alembic; the SQL alternative does not stamp the version
  table and must not be applied again after the revision.
- `seeds/` keeps the loader, guarded seed SQL and synthetic fixture directory
  together. The loader uses sibling paths and does not create auth fixtures,
  upload objects, dispatch work, or delete data.
- `tests/` contains the existing database acceptance suite and its explicit-
  connection Alembic environment. That environment is not a deployment runner.
- `pytest.ini` points discovery at `tests/` and adds `seeds/` for the loader import.
- `requirements-dev.txt` retains the output's pinned verification dependencies;
  these do not belong in the backend runtime dependency list.

The test harness uses the existing auth SQL seed at
`../auth/seeds/seed_auth_tenancy.sql`, not the model-dependent auth Python seeder.
It prepares a temporary migration directory from the existing auth revision and
the two ingestion migration files. It needs no paths outside `final_project/`.

No tests, migrations or seeds were run during placement. For any future live test
run, the existing guards require a new empty PostgreSQL 15+ database on loopback,
named `docusense_ingestion_test_<suffix>`, with no active consumers:

| Setting | Required value |
| :--- | :--- |
| `INGESTION_TEST_DSN` | Explicit connection to that disposable loopback database; keep credentials outside committed files. |
| `INGESTION_TEST_ACK` | The exact disposable database name. |
| `INGESTION_TEST_NO_CONSUMERS` | `1`, only when no consumers are connected. |

The suite refuses an existing nonempty database before initializing its own
tables; individual live tests clean up the fixture rows it created. The loader's
CLI also requires matching `--acknowledge-disposable` and `--no-active-consumers`.
The missing ORM parity test is still explicitly skipped and must be implemented
after the verified mappings arrive.
