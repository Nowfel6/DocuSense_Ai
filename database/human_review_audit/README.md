# Human Review and Immutable Audit Database Artifacts

Placed from database production output on 2026-09-06 at the user's request.
Canonical source placement is complete; integration remains
`PENDING_VERIFICATION` under the [final project issue log](../../issue_missing.md).

- `migrations/` contains revision `20260906_0004` and its companion SQL. Its
  parent is the document-processing/RAG revision `20260904_0003`.
- `seeds/` contains the guarded disposable-database loader, deterministic fixture
  generator, and database-only manifest. It creates no predecessor data.
- `tests/` contains the database verification suite rebased to canonical final
  migrations, backend models, fixtures, and seed paths.
- `requirements-dev.txt` reuses the existing database verification toolchain; it
  is not a backend runtime lock.
- ORM mappings have one canonical application location under
  `backend/app/human_review_audit/models.py` and are not duplicated here.

The live suite accepts `HUMAN_REVIEW_TEST_DSN`, `HUMAN_REVIEW_TEST_ACK`, and
`HUMAN_REVIEW_TEST_NO_CONSUMERS=1`. Safeguards require an explicitly acknowledged
loopback disposable database already migrated and verified at RAG revision
`20260904_0003`. Offline checks do not establish live constraints, tenant
isolation, concurrency, rollback, idempotency, or query-plan readiness.

The current upstream migration/mapping also retains the tracked BE-ISSUE-009 /
FP-ISSUE-008 BR-03 missing-result constraint conflict. Do not claim the database
feature READY until the upstream output is corrected, synchronized, and verified.
