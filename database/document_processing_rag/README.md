# Document Processing/RAG Database Artifacts

Placed from database production output on 2026-09-05 at the user's request.
Source placement is complete; integration remains `PENDING_VERIFICATION` under
the [final project issue log](../../issue_missing.md).

- `migrations/` contains revision `20260904_0003` beside its companion SQL. Its
  parent is `../document_ingestion/migrations/20260903_0002_document_ingestion_migration.py`.
- `seeds/` contains the guarded disposable-database loader, deterministic fixture
  generator, and database-only manifest. It does not contain customer data.
- `tests/` contains the production database verification suite adapted to canonical
  final-project migration, model, fixture, and seed paths.
- `requirements-dev.txt` reuses the ingestion database test toolchain and adds the
  output's pinned pgvector adapter. It is not a backend runtime lock.
- ORM mappings have one canonical application location under
  `backend/app/auth/models.py`, `backend/app/document_ingestion/models.py`, and
  `backend/app/document_processing_rag/models.py`; they are not duplicated here.

The test suite accepts `RAG_TEST_DSN`/`RAG_TEST_ACK`/`RAG_TEST_NO_CONSUMERS`, or
the equivalent ingestion test settings. Its safeguards require an explicitly
acknowledged loopback disposable database and refuse production-like targets.
Run the ingestion predecessor migration/fixture verification before the RAG live
suite. Offline checks do not establish live catalog, pgvector, concurrency,
rollback, tenant-isolation, or query-plan readiness.
