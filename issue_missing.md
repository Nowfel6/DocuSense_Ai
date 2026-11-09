# Final Project — Integration Issues

Updated 2026-09-19 after FP-ISSUE-024 retrieval-cap fix, FP-ISSUE-025 line-items path-namespace fix, FP-ISSUE-026 Groq 429 rate-limit fix, and FP-ISSUE-027 successful-but-zero-confidence extraction-quality findings.
Updated 2026-09-20 with FP-ISSUE-028 self-service tenant signup integration.
Updated 2026-11-06 with FP-ISSUE-029 local environment recovery (Docker restart, MinIO TLS regeneration, hydration-warning mitigation, hidden health-probe aliases).
Database and reviewed backend feature-package and concrete runtime placement are
complete through Feature 06, and frontend slices through Feature 16 are integrated
under their declared fixture boundaries.
Release status remains `PENDING_VERIFICATION` because wider held-out
quality/security/performance, safe object-orphan, and live frontend contract
gates remain open.

| ID | Status | Remaining work | Upstream tracking |
| :--- | :--- | :--- | :--- |
| FP-ISSUE-001 | RESOLVED | All five shared-Base mappings are consumed by the integrated concrete repositories and guarded at startup. | DB-ISSUE-001/002 and BE-ISSUE-001/002 resolved. |
| FP-ISSUE-002 | RESOLVED | All five READY database packages, including the RAG checkpoint amendment, are synchronized in canonical final paths and pass final offline checks. | BE-ISSUE-002 and all database issues resolved. |
| FP-ISSUE-003 | RESOLVED | Repaired auth plus all feature auth adapters and atomic Redis rate limiting are composed in the shared host. | BE-ISSUE-003/004 resolved. |
| FP-ISSUE-004 | RESOLVED | Database/S3/Redis lifecycle, all repositories/providers, API startup, Celery runner, and bounded database recovery/redispatch/expiry wiring are integrated and live-tested. | BE-ISSUE-006 host/worker gap closed. |
| FP-ISSUE-005 | RESOLVED | Docker disk moved to F:; foundation service and disposable-database checks passed. | Master plan Phase 0; development verification record. |
| FP-ISSUE-006 | BLOCKED | Concrete Docling/MiniLM/Groq adapters and RAG persistence/host/worker integration pass focused live checks; held-out quality/security/performance evidence remains. | DB-ISSUE-015 resolved; BE-ISSUE-005/006/011. |
| FP-ISSUE-007 | BLOCKED | Human-review repository/auth/rate-limit/source/routes are composed and live-tested; the full security/coverage/performance matrix remains. | BE-ISSUE-007. |
| FP-ISSUE-008 | RESOLVED | Corrected BR-03 migration/mapping are synchronized and the adapted final review database checks pass. | DB-ISSUE-010 and BE-ISSUE-009 resolved. |
| FP-ISSUE-009 | BLOCKED | Feature 05 database, backend, concrete adapters, worker and host are merged/live-tested; only the complete Feature 05 release matrix remains. | BE-ISSUE-010. |
| FP-ISSUE-010 | RESOLVED | Runtime packages, local Docling/OCR/MiniLM artifacts, immutable embedding revision, and Groq model access are installed/configured and smoke-tested. | BE-ISSUE-011. |
| FP-ISSUE-011 | RESOLVED | The durable RAG checkpoint and concrete fenced processing repository are merged and live-tested through the final runtime. | DB-ISSUE-015 resolved; BE-ISSUE-005 retains quality gates. |
| FP-ISSUE-012 | RESOLVED | Feature 06 backend/database packages and shared host wiring are integrated and pass final offline, live, privacy, snapshot, cancellation, and p95 gates. | DB-ISSUE-018 and BE-ISSUE-012 resolved. |
| FP-ISSUE-013 | BLOCKED | Auth Login is integrated and fixture-verified; OpenAPI is now published, while authoritative token expiry, a live tenant/login smoke test, and an approved token-revocation contract remain. | `frontend_production/workflows/04-output/auth-login/HANDOFF.md`. |
| FP-ISSUE-014 | BLOCKED | Feature 11 frontend is integrated in `CONTRACT_FIXTURE` mode; representative configured-infrastructure role/state/source/chunk/evidence verification remains. | `frontend_production/workflows/04-output/document-detail-chunk-inspector/HANDOFF.md`. |
| FP-ISSUE-015 | BLOCKED | Feature 12 frontend is integrated in `CONTRACT_FIXTURE` mode with the backend-aligned 20 MiB review proxy limit; representative configured-infrastructure role/state/conflict/idempotency/source/audit verification and manual browser/accessibility evidence remain. | `frontend_production/workflows/04-output/human-review-studio/HANDOFF.md`. |
| FP-ISSUE-016 | BLOCKED | Feature 13 frontend is integrated in `CONTRACT_FIXTURE` mode; representative configured role/state searches, export idempotency/lifecycle/polling, expiry/source-change, streamed/signed downloads and manual browser/accessibility evidence remain. | `frontend_production/workflows/04-output/document-search-export/HANDOFF.md`. |
| FP-ISSUE-017 | BLOCKED | Feature 14 frontend is integrated in `CONTRACT_FIXTURE` mode; representative configured tenant/role analytics, zero/integrity/error states, multi-page concurrent activity and manual responsive/accessibility evidence remain. | `frontend_production/workflows/04-output/dashboard-activity/HANDOFF.md`. |
| FP-ISSUE-018 | BLOCKED | Feature 15 static admin-only placeholder is integrated with no API/fixture dependency; only final manual responsive, keyboard, screen-reader, zoom, contrast and forced-colors evidence remains. | `frontend_production/workflows/04-output/settings-api-placeholder/HANDOFF.md`. |
| FP-ISSUE-019 | BLOCKED | Feature 16 static public landing is integrated with no API/fixture dependency; final manual responsive, keyboard/focus, screen-reader, 200% zoom, text-spacing and forced-colors evidence remains. | `frontend_production/workflows/04-output/public-landing/HANDOFF.md`. |
| FP-ISSUE-020 | OPEN | The canonical frontend full suite has two cwd-relative OpenAPI-path failures even though all 102 tests pass from the deeper Frontend Production build tree; make those two tests locate `final_project/docs/api/openapi.yaml` independently of checkout depth. | `src/test/dashboard-activity-core.test.ts`, `src/test/document-search-export-core.test.ts`. |
| FP-ISSUE-021 | RESOLVED | `MiniLMEmbeddingAdapter.__init__` stored the model name on `self.model_name` but the orchestrator reads `self.embedder.model`, so every embedding batch raised `AttributeError` and Celery aborted with `result=False`. The constructor now also assigns `self.model`. End-to-end parse → chunk → embed → extract now reaches `pending_review`. | `backend/app/backend_runtime/providers.py::MiniLMEmbeddingAdapter.__init__`. |
| FP-ISSUE-022 | RESOLVED | Groq returned `HTTP 200` for both attempts but `ExtractionService.extract()` raised `INVALID_STRUCTURED_OUTPUT` because the LLM was emitting flat `field_path` values (`invoice_number`, `buyer_name`) while `CandidateEvidence.field_path` requires a dotted path (`^[a-z][a-z0-9_]*(?:\.[A-Za-z0-9_-]+)+$`). `RawEvidence.field_path` now exposes the same pattern to the JSON schema sent to Groq, the system prompt explicitly requires dotted paths with `ABSOLUTE RULE`, and a permissive `_normalize_field_paths` repair layer auto-prefixes bare top-level names with `invoice.` and bare `line_items.N` with the inferred order before strict validation. The RAG pipeline now writes an invoice row and routes the document to Human Review. | `backend/app/document_processing_rag/extraction.py::RawEvidence,_normalize_field_paths`, `backend/app/backend_runtime/providers.py::GroqExtractionAdapter.extract`. |
| FP-ISSUE-023 | RESOLVED | A second Docling upload (`c4766e4d-…` `docusenseai pdf maker 2.pdf`) reached `progress_percentage=80 / current_stage=extracting` then failed with `error_code=INVALID_STRUCTURED_OUTPUT` after `attempt_count=3`. The error code was the same as FP-ISSUE-022 because `gpt-oss-20b` was again emitting bare top-level `field_path` values (`invoice_number`, `buyer_name`, `subtotal`, …) on a different document. The P3 prompt update already included the explicit dot-requirement, but the LLM only partially complied. Resolved by (a) strengthening the Groq system prompt with an `ABSOLUTE RULE` section that names every legal dotted path, and (b) adding a `_normalize_field_paths` repair layer in `extraction.py` that auto-prefixes bare top-level names with `invoice.` and bare `line_items.N` references with the inferred `line_items.<order>.` namespace before Pydantic validation. Three smoke tests (`bare`, `spaced`, `line_items`) all repair successfully. The orchestrator now reaches `pending_review` for this document class. | `backend/app/document_processing_rag/extraction.py::_normalize_field_paths`, `backend/app/backend_runtime/providers.py::GroqExtractionAdapter.extract`. |
| FP-ISSUE-024 | RESOLVED | After bumping `retrieval_candidates` from 12 to 24 (FP-ISSUE-023 follow-up), the next Docling upload (`c5726ac5-…` `docusenseai pdf maker 4.pdf`) failed at `progress_percentage=80 / current_stage=extracting` with `error_code=EMBEDDING_CONFIGURATION_MISMATCH`. The embedding phase had completed successfully (all 18 chunks `embedding_status='completed'`) but the call into `VectorSearchRepository.search` raised because the guard `if not 1 <= limit <= 12` rejected the new `candidate_limit=24`. The hardcoded cap lived in `rag_repositories.py::VectorSearchRepository.search` and was a leftover from the original 12-candidate contract. Resolved by relaxing the cap to `1 <= limit <= 24` to match the new `ProcessingSettings.retrieval_candidates`. | `backend/app/backend_runtime/rag_repositories.py::VectorSearchRepository.search`. |
| FP-ISSUE-025 | RESOLVED | After lifting the FP-ISSUE-024 cap, a fourth Docling upload (`72c83bf0-…` `docusenseai pdf maker 5.pdf`) reached `score_invoice` for the first time and crashed with `ValueError: Evidence contains an unknown canonical field path` (raised from `validation.build_evidence`). The LLM had emitted dotted paths of the form `line_items.1.description`, `line_items.1.quantity`, … using the 1-based ordinal, but `build_evidence` derived its expected keys from `line.source_row_key` (`row-1`, `row-2`, …) instead of `line.line_order`, so the diff `set(supplied).difference(values)` was non-empty and the orchestrator caught the exception as a generic `PROCESSING_FAILED`. Root cause was a path-namespace mismatch in our code, not the LLM. Resolved by changing `validation.build_evidence` to prefix line-items paths with `line_items.{line.line_order}.` (matching the prompt and the repair layer), and by wrapping `score_invoice(invoice)` in a precise `try/except ValueError` in the orchestrator that re-raises as `ProcessingError("INVALID_STRUCTURED_OUTPUT")` so future mismatches surface the right error code. Subsequent retries also hit Groq `429 RateLimitError` (8000 TPM cap on `openai/gpt-oss-20b`) but that is operational, not a code defect. | `backend/app/document_processing_rag/validation.py::build_evidence`, `backend/app/document_processing_rag/orchestrator.py::_execute`. |
| FP-ISSUE-026 | RESOLVED | After fixing the FP-ISSUE-025 path-namespace bug, the next Docling upload (`42ce71d6-…` `docusenseai pdf maker 6.pdf`) reached the Groq call but hit `groq.RateLimitError: 429 Rate limit reached for model openai/gpt-oss-20b ... Limit 8000, Used 5826, Requested 2681` on the corrective retry and every subsequent attempt. Three back-to-back retries inside ~90 s consume ~3×6 k = 18 k tokens against the 8000 TPM cap, so the second and third attempts always 429. The orchestrator caught the `groq.RateLimitError` as a generic `PROCESSING_FAILED` and the short `RETRY_DELAYS = {1:5, 2:10, 3:20}` seconds meant every retry happened before the token bucket could refill. Resolved by (a) wrapping `GroqExtractionAdapter.extract` in a `try/except groq.RateLimitError` that re-raises as `ProcessingError("LLM_RATE_LIMITED")` (a new entry in `PROCESSING_CODES`), and (b) extending `RETRY_DELAYS` to `{1: 60, 2: 90, 3: 120}` seconds so each attempt lets the TPM bucket refill fully. The new code is retryable, so the orchestrator's `schedule_retry` path still kicks in. | `backend/app/backend_runtime/providers.py::GroqExtractionAdapter.extract`, `backend/app/document_processing_rag/errors.py::PROCESSING_CODES`, `backend/app/document_processing_rag/orchestrator.py::RETRY_DELAYS`. |
| FP-ISSUE-027 | OPEN | A successful run (`12545abe-…` `docusenseai pdf maker 7.pdf`, attempt 1, `result=True`) reached `documents.status='pending_review'` but `overall_confidence=0.00`. The pipeline machinery (parsing, chunking, embedding, extraction, BR-03 math validation) all works; the LLM simply failed to emit two required header values (`invoice.invoice_number='inv-2026-0638'`, `invoice.date_issued='2026-09-19'`) that exist in `document_chunks` ordinals 2 and 12. The per-field penalties for the two missing fields (−30 + −20 = −50) eclipse the weighted total of the six extracted numerics (+45), clamping the document score to 0. A secondary issue: `supplier_name` was emitted as `crestline manufacturing co.` (the buyer); the actual supplier `novagrid systems ltd.` is in chunk ordinal=4 but the cosine retrieval ranked the buyer body chunk higher, so the LLM saw the buyer first. Three levers proposed: (1) tighten the prompt to require emitting invoice_number/date_issued explicitly, (2) post-extraction sanity-fill from text chunks, (3) bind the Supplier header chunk to its body chunk during evidence assembly. | `backend/app/backend_runtime/providers.py::GroqExtractionAdapter._call`, `backend/app/document_processing_rag/orchestrator.py::assemble_evidence`. |
| FP-ISSUE-028 | BLOCKED | Self-service tenant signup (`POST /api/v1/auth/signup` + `/signup` page + landing CTAs) is integrated in `CONTRACT_FIXTURE` mode against the existing auth backend. Real tenant-creation smoke tests, configured-infrastructure multi-tenant isolation, RBAC propagation to operator/viewer roles, manual responsive/keyboard/screen-reader evidence, and a representative end-to-end journey with a fresh tenant remain open. Operator/viewer onboarding into an existing tenant is still SQL-only. | `backend/app/auth/routes.py::SignupRequest`, `frontend/src/features/auth-signup/signup-form.tsx`. |
| FP-ISSUE-029 | RESOLVED | 2026-11-06 local-environment recovery: Docker Compose containers restarted after ~6 weeks stopped, the lost `postgres-init.sql` file and MinIO TLS certificates were regenerated, all three services verified healthy again. Dev-only hidden `/health` and `/v1/models` probe aliases added to the host. Optional dev-only auto-reload entry script (`run_server_dev.py`) and the `opencode.jsonc` permissions file were documented but intentionally **not** created pending user approval. | `infrastructure/postgres-init.sql`, `infrastructure/local/certs/`, `backend/app/backend_runtime/host.py`, `frontend/src/app/layout.tsx`, `docs/development/README.md`. |

Upstream evidence and closure details:
[database issues](../database_production/issue_missing.md) and
[backend issues](../backend_production/issue_missing.md). Preserve these IDs and
record evidence when their status changes.

## FP-ISSUE-001 — ORM Mapping Verification and Consumption

The database-owned shared auth, ingestion, RAG, human-review and export mappings exist at
`backend/app/auth/models.py`, `backend/app/document_ingestion/models.py`, and
`backend/app/document_processing_rag/models.py`, with review extensions at
`backend/app/human_review_audit/models.py` and export mappings at
`backend/app/document_search_export/models.py`. Mapper configuration confirms one
shared Base and 19 application tables. On 2026-09-09 upstream auth and
ingestion DB-01/DB-24 live catalog parity passed and Stage-3/Stage-4 hashes matched.
Concrete tenant-safe SQLAlchemy/pgvector repositories now consume those mappings;
startup verifies the shared metadata and physical database head/tables. Final
composition and live readiness checks pass, resolving this consumption issue.

## FP-ISSUE-002 — Database Verification and Synchronization Complete

**Resolved 2026-09-12 for final-project source synchronization.** All six
database packages are `READY` upstream and their corrected artifacts are present
in canonical final paths. The four adapted final offline suites pass 32 tests;
their 79 live-only cases remain explicitly skipped in that placement run. The
upstream clean live, concurrency, scale-plan and migration-cycle evidence remains
the release evidence for the synchronized sources.

The adapted combined ingestion/RAG/review database suite reported 22 offline
passes and 74 live-only skips because no acknowledged disposable DSN was supplied
to that run. On 2026-09-09 all three foundation services reported healthy and a
read-only check confirmed the acknowledged disposable database is reachable,
empty, and consumer-free. The upstream focused gate then passed ingestion **20**,
RAG **12** before fixture expansion plus **11/11** afterward, and human review
**12** tests. Migration, core concurrency/idempotency, rollback, catalog/ORM,
VECTOR(384), tenant, cascade and BR-03 behavior are now evidenced. The copied suites use
canonical final-project paths and retain explicit disposable-database safeguards.
Complete the intentionally omitted release cases and representative larger-data
query-plan evidence before closing or reporting READY.

## FP-ISSUE-003 — Authentication and Authorization Dependencies

The synchronized auth package now uses direct Argon2, strict issuer/expiry JWTs,
persisted identity/API-key checks and a session-injected route factory. Its five
final auth tests pass, and the three upstream output files match their verified
Stage-3 sources. Feature-specific auth adapters and the Redis rate limiter are
now promoted, composed, and covered by the final host tests. This issue is resolved.

## FP-ISSUE-004 — Runtime Assembly Complete

Resolved 2026-09-11. `backend/app/backend_runtime/` now composes every concrete
repository, shared auth/rate limiting, real providers, TLS object storage, the
single FastAPI route graph, and both identifier-only Celery tasks. `app.main`,
`app.worker`, and `app.reconciler` are the concrete process entry points. The
review handler is the sole owner of generic document detail; static Feature 5
paths are registered ahead of it.

`backend/pyproject.toml` now declares the database/auth/worker/provider/test
runtime pins, including SQLAlchemy, pgvector, psycopg, Alembic, Argon2, PyJWT,
Celery/Redis, Docling/EasyOCR, Sentence Transformers, Groq and pytest. Editable
installation, compilation, and `pip check` pass. Startup verifies the Alembic
head, all 19 application tables, Redis, and the private S3 bucket before readiness
succeeds. Windows processes install the selector policy required by async Psycopg.

The concrete runtime passed 332 upstream offline tests, 12 promoted-output live
tests, five final composition tests, and a final-project startup/readiness check.
The intentionally separate safe object-orphan and wider release matrices remain
tracked under FP-ISSUE-006/007/009; they do not reopen runtime assembly.

## FP-ISSUE-005 — Foundation Infrastructure Verification

- **Status/date:** RESOLVED, 2026-09-03; foundation implementation authorized by the user.
- **Implemented:** real Compose services, pgvector initialization, persistent
  volumes, private TLS/encrypted MinIO configuration, generated `.env`, isolated
  backend dependencies and lock snapshot, frontend dependencies/lockfile,
  startup/check/shutdown commands and separate disposable-database provisioning.
- **Passed:** backend installation, `pip check`, Python syntax, idempotent init,
  frontend installation (zero audit findings) and Next.js/TypeScript version checks.
- **Failure evidence:** Docker Linux engine became available; PostgreSQL/Redis
  images downloaded. MinIO source compilation then reported read-only filesystem
  and I/O errors. Host drive inspection reported C: free bytes = 0. The build was
  interrupted; live service verification and test-db creation did not complete.
- **Resolution:** user authorized moving Docker storage to F:. The active disk is
  `F:\DockerDesktop\disk\docker_data.vhdx`. The old C: disk was removed only after
  SHA-256 verification against its preserved F: backup; existing images remained
  available. Stale runtime socket directories were preserved under backup names
  to resolve Docker restart errors. No image/volume purge or factory reset occurred.
- **Closure evidence:** MinIO source build completed; all three Compose services
  reported healthy. Authenticated SQL/vector/Redis checks, trusted TLS, private
  bucket, encrypted object round trip and anonymous denial passed. The newly
  created `docusense_ingestion_test_99b37996e0bf` database was verified empty,
  loopback-only in its connection settings, correctly acknowledged and without
  other consumers. See [foundation evidence](docs/development/README.md).
- **2026-09-09 recheck:** PostgreSQL, Redis, and MinIO again reported healthy;
  the acknowledged disposable database was reachable with zero public base tables
  and no other connections.
- **2026-09-10 host-port repair:** Windows reserved the configured PostgreSQL port
  55432. `.env` now uses unreserved loopback port 55465; only the PostgreSQL
  container was recreated, its named data volume was preserved, and the service
  is healthy/reachable at `127.0.0.1:55465`.
- **2026-09-12 MinIO port repair:** after Docker Desktop restarted, Windows
  reserved 58966–59065, covering ports 59000/59001. Local MinIO moved to
  59100/59101; its volume and credentials were preserved, and the complete
  foundation service check passed.
- **Remaining scope:** FP-ISSUE-001 through 004 and FP-ISSUE-006 through 009 stay open.
  Environment readiness does not verify their ORM/catalog parity, migrations,
  auth, API, workers, providers or full processing.

## FP-ISSUE-006 — Real RAG Providers and Quality Gates

- **Status/date:** BLOCKED, updated 2026-09-09 after provider/model setup.
- **Present:** Strict schemas, OCR policy, deterministic chunking, embedding response
  validation, retrieval, extraction/normalization, Decimal validation/confidence,
  read routes/services, fenced orchestration, task boundary and ORM/migration assets.
- **Passed:** 60 deterministic RAG backend tests against the adapted final package;
  AST/import/dependency checks; shared mapper metadata; six database offline checks;
  offline 384-dimensional MiniLM embedding; offline Docling conversion; and Groq
  authentication/configured-model availability.
- **Available prerequisites:** Docling/EasyOCR layout/table/OCR artifacts, pinned
  `all-MiniLM-L6-v2` revision
  `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`, Groq
  `openai/gpt-oss-20b`, and required Python packages. No local LLM is required.
- **Remaining:** Approved benchmark fixtures; complete coverage, security,
  crash/fencing/performance tests; held-out AI metrics; and provenance-safe
  object-orphan cleanup. The real adapters are promoted and composed.
- **Close when:** The approved live-service and quality matrix passes with recorded
  evidence and no upstream `PENDING_VERIFICATION` dependency remains.
- **2026-09-11 runtime update:** Concrete local Docling/EasyOCR, immutable MiniLM,
  JSON-only Groq and fenced RAG SQL adapters are promoted and pass real calls.
  The remaining blocker is the wider quality/security/performance evidence.

## FP-ISSUE-007 — Human Review/Audit Runtime Integration

- **Status/date:** BLOCKED after canonical source placement, 2026-09-06.
- **Present:** Strict review schemas/errors, canonical hashes and diffs, exact
  Decimal validation, query/preview/command services, FastAPI route factory,
  persistence/source ports, shared-Base ORM mappings, migration, guarded synthetic
  fixtures/seed, and adapted database verification tests.
- **Passed:** All 58 upstream human-review backend tests against the adapted final
  package; final backend imports and dependency check; one-Base mapper configuration
  with 16 tables; upstream human-review live database suite **12 passed**, including
  migration, catalog/ORM, seed repeat, tenant, BR-03, history and downgrade checks;
  synchronized database output offline regression **23 passed**.
- **Remaining:** Wider live security, coverage and performance evidence. The SQL
  repository, auth adapter, Redis limiter, private-source signer, exact CORS and
  collision-free application route composition are present and tested.
- **Composition result:** The review detail handler is the sole owner of the
  generic document detail path; the host suppresses ingestion's standalone detail
  handler and registers Feature 5 static paths first.
- **Close when:** FP-ISSUE-001..004 and FP-ISSUE-008 are resolved, verified database
  mappings are consumed by the real repository, shared dependencies are composed,
  and the approved live/integration matrix passes with recorded evidence.

## FP-ISSUE-008 — BR-03 Missing-Result Database Constraint Conflict

- **Status/date:** RESOLVED by final-project synchronization, 2026-09-11.
- **Evidence:** Database Stage-3/Stage-4 SQL and ORM were corrected so missing and
  not-applicable BR-03 rows keep null numeric fields. The upstream live regression
  accepted the approved shape, rejected the malformed epsilon-bearing shape, and
  the human-review suite passed **12 tests**. DB-ISSUE-010 and BE-ISSUE-009 are resolved.
- **Resolution:** The corrected verified migration and mapping are now synchronized.
  The adapted human-review database suite passes its eight offline checks; the
  authoritative upstream live suite passed 14/14 plus its representative-scale
  plan gate.

## FP-ISSUE-009 — Feature 05 Release Matrix Pending

- **Status/date:** BLOCKED only on the complete release matrix, updated 2026-09-11.
- **Evidence:** The READY database package and reviewed backend feature package
  now exist at `database/document_search_export/` and
  `backend/app/document_search_export/`. The adapted final feature packages pass
  312 ingestion/RAG/review/export contract tests (including 68 Feature 5 tests)
  plus five auth tests; the guarded database suite passes 15/15, and shared mapper
  configuration reports 19 application tables. The disposable target was left
  restored at `20260907_0006`.
- **Runtime update:** The concrete repository, auth/rate-limit/storage adapters,
  worker service and host routes are promoted into the final project. The output
  live suite passes 12/12 and final composition/startup checks pass.
- **Remaining:** Complete the specified security/concurrency/performance matrix
  before changing the combined production handoff to READY.

## FP-ISSUE-010 — Runtime and Model Setup

- **Status/date:** RESOLVED, 2026-09-09.
- **Evidence:** Required runtime/test packages install cleanly and `pip check`
  reports no broken requirements. Docling layout, TableFormer, and English EasyOCR
  artifacts are cached under `F:\DocuSenseModels\docling`; the immutable MiniLM
  revision is cached under `F:\DocuSenseModels\huggingface`. MiniLM passed both
  download-time and offline 384-dimensional finite normalized-vector checks.
  Docling converted the synthetic invoice with network access disabled. A
  read-only Groq model-list request authenticated and confirmed the configured
  hosted model is available. Environment examples now record the non-secret model
  identities and F: artifact paths; the Groq key remains only in `.env`.
- **Resolution boundary:** No further manual model download is required. Runtime
  assembly issues FP-ISSUE-001/003/004/011 are now closed; the wider matrices in
  FP-ISSUE-006/007/009 remain.

## FP-ISSUE-011 — Durable RAG Partition Checkpoint Integrated

- **Status/date:** RESOLVED after final backend runtime consumption, 2026-09-11.
- **Evidence:** The locked processing workflow and backend repository port require
  the canonical partition to be persisted and reloaded at `partitioning / 20`.
  Upstream schema 1.1 now provides the dedicated 13-column `document_partitions`
  table with tenant ownership, bounded canonical JSON, configuration identity,
  attempt/lease fencing, database-derived hash, immutability and cascade cleanup.
- **Evidence:** Upstream RAG Stage 3 and Stage 4 each passed **16/16**; both
  downstream Feature 5 suites passed **15/15**; hashes match and the disposable
  target was restored at `20260907_0006`.
- **Resolution:** The database blocker, final database synchronization, concrete
  backend repository, checkpoint reuse, worker composition, and final runtime
  consumption are complete and live-tested. Held-out RAG quality work remains
  separately under FP-ISSUE-006.

## FP-ISSUE-012 — Dashboard Analytics/Activity Integrated

- **Status/date:** RESOLVED, 2026-09-12.
- **Placement:** Seven backend artifacts are adapted under
  `backend/app/dashboard_activity`; six database query/verification artifacts are
  adapted under `database/dashboard_activity`. The existing shared auth adapter,
  host, and runtime exports now compose Feature 06.
- **Evidence:** 13 Feature 06 contract tests, 10 final backend tests, 18 guarded
  final database tests, and 3 final backend live tests pass. The live matrix covers
  two tenants, role redaction, opaque viewer IDs, stable pagination,
  repeatable-read concurrency, cancellation/pool reuse, cleanup, and latency.
  The real host registers both routes and passes startup/readiness/shutdown with
  the fully migrated disposable database and all three local services.
- **Boundary:** No Feature 06 migration, table, model, index, cache, Redis state,
  Celery task, or persistent fixture was introduced. Existing unrelated release
  blockers under FP-ISSUE-006/007/009 remain unchanged.

## FP-ISSUE-013 — Auth Login Live Contract Verification

- **Status/date:** BLOCKED for live readiness, 2026-09-14; fixture-mode final
  integration is complete.
- **Present:** Dynamic `/login`, protected temporary `/dashboard`, same-origin
  login exchange, signed HttpOnly session storage, safe return paths, released
  shell navigation, local logout, and synthetic browser infrastructure.
- **Evidence:** Final typecheck and lint pass; all 12 Vitest files / 49 tests pass;
  the production build emits both product routes; representative auth and
  preserved-foundation Playwright journeys each pass 1/1 at 1366x768.
- **Resolved prerequisite:** Reviewed OpenAPI 3.1 is generated from exact
  `app.main:app`; the stale-file check passes.
- **Remaining:** Approve and implement an authoritative `expires_in` response field, run the
  real tenant/Login/logout smoke journey with approved synthetic users, and add
  backend token revocation if that contract is approved. Manual screen-reader,
  200% zoom, short-viewport, localization, and platform high-contrast checks are
  also outstanding.
- **Boundary:** The current one-hour expiry fallback and local-only logout are
  documented fixture-mode behavior, not live release evidence.

## FP-ISSUE-014 — Document Detail and Chunk Inspector Frontend/Live Work

- **Status/date:** PENDING, 2026-09-14.
- **Complete:** Feature 11 plan/test plan approved; canonical detail supports
  admin/operator all-state and viewer approved-only reads; source/review data is
  role-safe; chunk/evidence query and error contracts are published; Backend
  Production passes 347 tests; final backend passes 10; OpenAPI check passes.
- **Remaining:** Execute the Frontend Production four-stage workflow, selectively
  integrate verified output, then run the approved representative live role/state,
  source-expiry, chunk/evidence, responsive, and accessibility matrix.
- **Boundary:** No database change is required. Published OpenAPI enables contract
  work but is not itself live endpoint evidence.

## FP-ISSUE-017 — Dashboard & Recent Activity Frontend Live Work

- **Status/date:** BLOCKED for configured-live acceptance, 2026-09-16; selective
  `CONTRACT_FIXTURE` integration is complete.
- **Present:** Protected `/dashboard`, validated UTC report URL state, current and
  period metrics, five accessible visualization groups, exact data tables,
  snapshot-consistent recent activity, strict success decoding, safe role-aware
  document links, independent refresh/retry/offline/forbidden states, and focused
  synthetic fixtures/tests.
- **Evidence:** Stage 3 typecheck and zero-warning lint passed; the focused suite
  passed 2 files / 8 tests, the complete frontend suite passed 20 files / 94
  tests, and the Next.js 16.3.4 supported Webpack production build emitted dynamic
  `/dashboard`. Stage 4 and final placement each proved 17/17 executable/test
  files byte-identical without rerunning the same successful suite.
- **Remaining:** Exercise representative configured admin/operator/viewer tenants,
  genuine zero metrics, unavailable/integrity/rate-limit responses, multiple
  activity pages during concurrent writes, UTC range boundaries, and manual
  360/768/1024/1440 responsive, keyboard, screen-reader and 200% zoom checks.
- **Boundary:** No frontend dependency, backend behavior, database artifact,
  environment setting or generated OpenAPI artifact changed during integration.

## FP-ISSUE-018 — Settings API Placeholder Manual Verification

- **Status/date:** BLOCKED only on final manual presentation evidence, 2026-09-16;
  selective static-placeholder integration is complete.
- **Present:** Dynamic protected `/settings/api`, server-side admin gate, generic
  operator/viewer forbidden state, admin-only navigation, centralized Settings
  breadcrumbs, approved deferred-feature copy and one safe Dashboard link.
- **Evidence:** Stage 3 typecheck and zero-warning lint passed; the focused suite
  passed 1 file / 4 tests, the complete frontend suite passed 21 files / 98 tests,
  and the Next.js 16.3.4 supported Webpack build emitted dynamic `/settings/api`.
  Stage 4 and final placement proved all 5 source/test files byte-identical without
  rerunning the same successful commands.
- **Remaining:** Record browser evidence at 360/768/1024/1440 CSS pixels plus
  keyboard-only, screen-reader, 200% zoom, contrast and forced-colors checks.
- **Boundary:** This page deliberately consumes no backend operation or fixture.
  Functional API keys/webhooks remain deferred Feature 07 work. No package,
  proxy, backend, database, environment or OpenAPI artifact changed.

## Resolved Placement Problems — 2026-09-03

- Replaced the backend's dotted build-file loader with normal feature module
  filenames and package-relative imports.
- Rebased database test discovery, migration paths and seed paths to existing
  final-project files, keeping each artifact in one canonical location.
- Replaced the invalid backend `pyproject.toml` placeholder with valid project
  metadata. The 2026-09-09 setup expanded and installed the required runtime/test
  pins successfully; concrete runtime composition is now verified under
  FP-ISSUE-004.
- Placed the RAG backend under a normal feature package, adapted internal imports,
  synchronized invoice-detail/shared-lease ingestion integration, and installed
  the database-owned mappings on one canonical shared Base.
- Rebased RAG migration, fixture, seed and test paths to their canonical final
  feature directories without duplicating auth or ingestion predecessors.
- Placed human-review backend/database sources once in feature-first destinations,
  converted dotted runtime files to a normal package, rebased database support
  paths, and synchronized the reviewed ingestion relationship disambiguation.

The original ingestion packaging changes were manually reviewed. The later RAG
and human-review placements used the existing final/backend and production-room
build virtual environments for dependency, import, mapper and offline test
verification; no virtual environment was copied or created.

---

## FP-ISSUE-021 — End-to-End PDF Processing Pipeline (Session-4 Live Debug)

- **Status/date:** IN PROGRESS, 2026-09-19.
- **Goal:** Get a real PDF upload to `processing_jobs.status='completed'` so the frontend can render the extraction evidence.

### What is achieved

- Sign-in works with `admin@acme.com / AdminPassword123!` (run `scripts/reset_demo_passwords.py` once).
- Celery worker runs and connects to Redis with:
  `.venv\Scripts\python.exe -m celery -A app.worker worker --loglevel=info --pool=solo -n celery@SHOWAIB -Q docusense,documents,exports`
- Docling parses both stuck PDFs in ~35–42 seconds.
- Chunker produces 70 chunks cleanly (was previously failing at `chunking.py:155` on empty tables).
- Pipeline advances from 20% → 40% (partitioning → chunking) on every attempt.

### Patches applied in this session

1. **`app/backend_runtime/storage.py`** — `S3SourceObjectReader.read()` now streams via `Body.iter_chunks(chunk_size=65536)` instead of `Body.read(maximum_bytes + 1)`. Eliminates the aioboto truncation bug that produced masked `SOURCE_OBJECT_UNAVAILABLE` errors.
2. **`app/document_processing_rag/chunking.py`** — `_table_chunks()` gracefully handles empty tables (zero headers + zero rows) by falling back to text chunking on `element.text`, or skipping the element silently.
3. **`app/backend_runtime/entrypoints.py`** — `run_reconciler()` installs `WindowsSelectorEventLoopPolicy` before `asyncio.run`. Without this, the reconciler's asyncpg sessions cannot open on Windows (ProactorEventLoop).
4. **`app/backend_runtime/workers.py`** — Added `print()` wrappers around `process_document`/`generate_export` so the real traceback surfaces in the Celery terminal when a task fails. Also added a per-tick `print` to the reconciler.

### Diagnostic scripts added under `scripts/`

- `reset_demo_passwords.py` — seeds companies/users with Argon2 hashes.
- `inspect_jobs.py` — job status + env sanity check.
- `show_jobs.py` — short status dump.
- `watch_jobs.py` — 2-second heartbeat poller.
- `s3_tls_check.py`, `s3_reader_diag.py`, `s3_reader_trace.py` — isolate the S3 read failure.
- `diag_chunking.py` — load persisted partition, run chunker, surface real exception.
- `diag_full_pipeline.py` — chunker → embedder → retriever → LLM in one process.
- `test_reconciler_graph.py`, `test_reconciler_fix.py`, `probe_publish.py`, `time_import.py` — verify reconciler behaviour.

### What is remaining

1. **Find the real exception after `persist_chunks`.** Both stuck jobs sit at `current_stage='chunking'`, `progress=40%`, `error_code='PROCESSING_FAILED'` (catch-all mask), `attempt_count=3`. One more failure marks them `failed` terminally. Need to:
   - Kill all python/celery: `Get-Process python,celery -ErrorAction SilentlyContinue | Stop-Process -Force`
   - Start Celery with the full command above.
   - Start reconciler in a separate terminal: `.venv\Scripts\python.exe -m app.backend_runtime.entrypoints run_reconciler`
   - Wait ~30s for the patched print wrapper to emit `document_task FAILED:` followed by the traceback.
   - Paste the traceback back.
2. Once the real exception is found, the fix is usually a single conditional or import. The pipeline should reach `status='completed'`.
3. **Revert debug prints** in `app/backend_runtime/workers.py` after the fix is verified.
4. The PDF is essentially blank — reaching completion with empty `line_items` is expected and proves the mechanism works.

### Reminders for next session

1. Celery command MUST include `--pool=solo` (avoid billiard/Prefork errors) and `-Q docusense,documents,exports` (publisher targets `queue="documents"`).
2. Three processes are required: uvicorn, Celery worker, reconciler. Without the reconciler no retries/dispatches happen.
3. First `import app.backend_runtime.settings` takes ~15 s (loads torch). Be patient before judging the reconciler "silent".
4. `scripts/watch_jobs.py` is the canonical heartbeat indicator.
5. `PROCESSING_FAILED` is the catch-all; only `ProcessingError(*)` instances carry specific error codes.

### Key files for next session

- `app/document_processing_rag/orchestrator.py` — orchestrator + retry/heartbeat.
- `app/backend_runtime/rag_repositories.py` line 234 — chunking check; line 410 — `schedule_retry`.
- `app/backend_runtime/queue.py` line 38 — why `-Q documents` matters.
- `app/backend_runtime/workers.py` — reconciler + the print-wrapped task handlers.
- `app/document_processing_rag/chunking.py` — empty-table fix is here.

---

## FP-ISSUE-021 — EmbeddingAdapter missing `self.model` attribute

### Symptom

`documents.process` Celery tasks returned `result=False` in ~24 s after parsing finished.
The orchestrator was raising `AttributeError: 'MiniLMEmbeddingAdapter' object has no
attribute 'model'. Did you mean: '_model'?` from
`orchestrator.py::process._execute` while iterating `pending_embeddings`.

### Diagnosis

- `MiniLMEmbeddingAdapter.__init__` set `self.model_name = model` and `self._model = None`,
  but `orchestrator.py` line ~189 reads `self.embedder.model`, expecting the public
  identifier on `self.model`.
- The constructor had never been updated for the post-refactor attribute naming.
- The orchestrator wraps generic exceptions with a `logging.exception` call (added during
  this incident), but Celery's `docusense.orchestrator` logger was silenced by the
  default task-log filter, so the traceback never reached the worker stdout.

### Fix

Assign `self.model = model` in `MiniLMEmbeddingAdapter.__init__` (kept `self.model_name`
as a public alias). Verified by re-running parsing → embedding → LLM extraction on
document `0f05613d-f913-40c3-a443-138a8bcaa3fe`. The pipeline now reaches
`documents.status='pending_review'`, `overall_confidence=40.00`.

### Evidence

- DB row after the fix:
  - `documents.status='pending_review'`, `overall_confidence=40.00`.
  - `invoices`: `inv-2026-0042`, buyer=`global trade analytics inc.`, USD,
    subtotal=`2180.00`, tax=`218.00`, discount=`50.00`, grand_total=`2348.00`,
    `is_math_valid=false`.
- Celery log after the fix: `result=True`, `succeeded in 6.485s`.

---

## FP-ISSUE-022 — Groq extraction returned valid JSON but failed Pydantic normalization

### Symptom

The corrective retry (`ExtractionService.extract()` second attempt) and the original
attempt both produced `HTTP/1.1 200 OK`, but the run was marked
`processing_jobs.error_code='INVALID_STRUCTURED_OUTPUT'`, `extraction_runs.status='failed'`,
`documents.status='failed'`. No traceback was emitted; the orchestrator reported
`result=False` after exactly two Groq calls, matching the documented
`corrective=(False, True)` loop.

### Diagnosis

- Captured both LLM responses by temporarily appending each payload to
  `backend/llm_capture.log` from inside `GroqExtractionAdapter.extract`.
- `RawInvoice.model_validate_json(...)` succeeded on both payloads, but
  `_normalize(...)` failed at:
  `CandidateEvidence.field_path: String should match pattern
  '^[a-z][a-z0-9_]*(?:\.[A-Za-z0-9_-]+)+$'`
  with `input_value='invoice_number'`.
- `RawEvidence.field_path` was declared as `Field(min_length=1, max_length=255)`
  with **no pattern**, so the JSON schema sent to Groq did not advertise the
  dotted-path requirement that `CandidateEvidence.field_path` enforces in
  `app/document_processing_rag/schemas.py`. The LLM faithfully returned
  `invoice_number`, `buyer_name`, `currency`, etc.

### Fix

1. `app/document_processing_rag/extraction.py::RawEvidence`:
   ```python
   FIELD_PATH_PATTERN = r"^[a-z][a-z0-9_]*(?:\.[A-Za-z0-9_-]+)+$"
   class RawEvidence(StrictModel):
       field_path: Annotated[str, StringConstraints(
           min_length=1, max_length=255, pattern=FIELD_PATH_PATTERN,
       )]
       ...
   ```
   The pattern now appears in the JSON schema attached to the system prompt.
2. `app/backend_runtime/providers.py::GroqExtractionAdapter.extract` system prompt
   explicitly requires dotted paths:
   > Each `evidence.field_path` MUST be a dotted path with at least one dot
   > (e.g. `invoice.invoice_number`, `line_items.0.description`). Bare top-level
   > field names like `invoice_number` are invalid.
3. Removed the temporary `llm_capture.log` write inside `GroqExtractionAdapter`.

### Evidence

- DB row after the fix:
  `documents.status='pending_review'`, `overall_confidence=40.00`,
  `invoices.inv-2026-0042` populated, `processing_jobs.error_code=NULL`,
  `extraction_runs.status='completed'`.
- Celery log: first run after restart -> `result=True` (6.5 s).
- See `improvement.md` for follow-ups on retrieving line-item table cells and
  raising confidence above the 40/100 ceiling.

## FP-ISSUE-023 — Re-occurrence of bare-`field_path` failure on second Docling upload

### Symptom

After the FP-ISSUE-022 fix, a second Docling upload of
`docusenseai pdf maker 2.pdf` (`c4766e4d-bc15-4a70-8f0f-abccf22e8f71`) at
14:37:17 reached `progress_percentage=80 / current_stage=extracting` and then
failed with `error_code=INVALID_STRUCTURED_OUTPUT` after three retries,
finishing at 14:42:54. The UI snapshot at 20% was a stale read taken before the
third retry completed; the orchestrator had in fact advanced to the
`extracting` stage before failing.

### Root cause

`gpt-oss-20b` (the Groq model) is still emitting bare top-level `field_path`
values on a different document even after the FP-ISSUE-022 prompt edit, e.g.:

```json
{"field_path":"invoice_number","source_value":"inv-2026-0042"}
{"field_path":"buyer_name","source_value":"global trade analytics inc."}
{"field_path":"subtotal","source_value":"2180.00"}
```

The `CandidateEvidence` schema regex
`^[a-z][a-z0-9_]*(?:\.[A-Za-z0-9_-]+)+$` requires at least one dot, so every
such entry is rejected by Pydantic. The original P3 prompt instructed "MUST
be a dotted path with at least one dot" — the LLM understood the rule on
`commercial_invoice_rag_test.pdf` but ignored it on `docusenseai pdf maker 2.pdf`,
presumably because the second PDF has a different narrative structure and the
model decided to skip the prefix.

### Fix (deployed)

1. **Stronger system prompt** in
   `app/backend_runtime/providers.py::GroqExtractionAdapter.extract` adds an
   `ABSOLUTE RULE` block that (a) names the exact regex the validator applies,
   (b) lists every legal top-level dotted prefix
   (`invoice.invoice_number`, `invoice.supplier_name`, …), and (c) explicitly
   warns that `invoice_number` and `subtotal` will be rejected.
2. **Permissive repair layer** in
   `app/document_processing_rag/extraction.py::_normalize_field_paths`
   intercepts the LLM response before Pydantic validation. It walks every
   evidence entry and:
   - accepts paths that already match the dotted regex unchanged,
   - collapses stray whitespace around dots (`inv - 2026 - 0042` →
     `inv-2026-0042`) when the result is valid,
   - prefixes any bare top-level name from a fixed allowlist
     (`invoice_number`, `supplier_name`, …) with `invoice.`,
   - prefixes bare `line_items.N` references with the inferred order from the
     `line_items` array when the leaf is in the line-fields allowlist,
   - raises `ValueError` for paths it cannot salvage so the corrective retry
     is triggered.
3. **`ExtractionService.extract`** now calls `_normalize_field_paths(response)`
   before `RawInvoice.model_validate_json(response)`, wrapping both in the
   same `try/except (ValidationError, ValueError, InvalidOperation): continue`
   block, so the corrective Groq retry still fires for genuinely unrepairable
   payloads.

### Evidence

- Three smoke tests in `smoke_repair.py` (since removed): bare-name, spaced,
  and line-items payloads all repair to a schema-valid `RawInvoice`.
- The orchestrator path is unchanged downstream of `_normalize_field_paths` —
  `_normalize` continues to apply the `_decimal`, `_date`, `_text` and
  allowlist constraints for values, only the path namespace is now repaired.
- The currently failed document `c4766e4d-…` will need a manual reset+redispatch
  to retry with the new code; resetting is a separate operation (see
  `reset_doc.py`).

## FP-ISSUE-024 — `EMBEDDING_CONFIGURATION_MISMATCH` raised after bumping `top_k` to 24

### Symptom

After the FP-ISSUE-023 follow-up bumped `retrieval_candidates` from 12 to 24
in `ProcessingSettings`, a fresh Docling upload
(`c5726ac5-06c5-432d-bc89-a849110ebbb6`, `docusenseai pdf maker 4.pdf`)
succeeded through partitioning, chunking, and embedding (all 18 chunks
write `embedding_status='completed'`), advanced to
`progress_percentage=80 / current_stage=extracting`, then failed with
`error_code=EMBEDDING_CONFIGURATION_MISMATCH` after `attempt_count=1`.

### Root cause

`VectorSearchRepository.search` retained a hard-coded safety guard from the
original 12-candidate contract:

```python
if model != MODEL or len(vector) != 384 or not 1 <= limit <= 12:
    raise ProcessingError("EMBEDDING_CONFIGURATION_MISMATCH")
```

When the new `retrieval_candidates=24` value flowed from
`ProcessingSettings` into `RetrievalService.candidate_limit` and from there
into `repository.search(..., limit=24)`, the `1 <= limit <= 12` cap rejected
the call. The error code is misleading — it suggests the embedding model or
revision drifted, when in reality the only thing that changed was the
retrieval fan-out.

### Fix (deployed)

Relax the cap to match the new contract:

```python
if not 1 <= limit <= 24:
    raise ProcessingError("EMBEDDING_CONFIGURATION_MISMATCH")
```

`ProcessingSettings.retrieval_candidates` is now also bound by this cap
through `RetrievalService.__init__` (`candidate_limit <= 24`).

### Evidence

- DB after the failure shows embeddings fully persisted:
  `('header','both','completed',5)`, `('table','both','completed',2)`,
  `('text','both','completed',11)`. Only the search call rejected.
- The orchestrator reached `progress_percentage=80` exactly once (after
  `mark_extracting`) and immediately bailed out.
- A Celery restart picking up the patched file is required to retry this
  document.

## FP-ISSUE-025 — Line-items `field_path` namespace mismatch in `build_evidence`

### Symptom

After lifting the FP-ISSUE-024 cap, a fourth Docling upload
(`72c83bf0-5c05-4c93-8a36-9a75c92e83b6`, `docusenseai pdf maker 5.pdf`) reached
the post-extraction phase for the first time. The first attempt produced a
200 OK from Groq with the new P3 prompt; `_normalize_field_paths` accepted the
response; `_normalize` produced a valid `InvoiceCandidate`; but the call to
`score_invoice(invoice)` in the orchestrator raised
`ValueError: Evidence contains an unknown canonical field path` from
`validation.build_evidence`. The orchestrator's generic `except Exception`
swallowed it as `ProcessingError("PROCESSING_FAILED")`. Subsequent retries
then hit Groq `429 RateLimitError` (`Limit 8000 TPM`) for the same document
because each attempt re-sent a ~5k token prompt.

### Root cause

The P3 system prompt tells the LLM to emit line-items paths of the form
`line_items.<order>.<leaf>` (1-based ordinal, e.g. `line_items.1.description`).
Our repair layer mirrors that. But `build_evidence` was building its expected
key set using `f"line_items.{line.source_row_key}"` which produces
`line_items.row-1.description`. The diff
`set(supplied).difference(values)` was non-empty, raising
`ValueError`. This was a path-namespace mismatch in our code, not in the
LLM's output.

### Fix (deployed)

1. `validation.build_evidence` now prefixes line-items paths with
   `line_items.{line.line_order}.` (1-based ordinal), matching the prompt
   and the repair layer.
2. `orchestrator._execute` wraps `score_invoice(invoice)` in a precise
   `try/except ValueError` that re-raises as
   `ProcessingError("INVALID_STRUCTURED_OUTPUT")`, so future mismatches
   surface the right error code (was previously masked as
   `PROCESSING_FAILED`).

### Evidence

- Smoke-tested `build_evidence` with an invoice carrying 3 line items and
  paths of the form `line_items.<1..3>.<leaf>` — returns 29 rows including
  18 line-items rows, no `ValueError`.
- The currently failed `72c83bf0-…` will need a Celery restart + reset+redispatch
  to retry with the new code.

### Operational note on the 429s

`openai/gpt-oss-20b` on the Groq on-demand tier is capped at 8000 TPM.
With `context_tokens=8000` plus schema and prompt overhead, each extraction
call consumes ~5–8 k tokens. Three retries within 90 s will exceed the
limit and start getting 429s. Workarounds in priority order:

1. Increase the inter-attempt delay in `RETRY_DELAYS` from
   `{1: 5, 2: 10, 3: 20}` to `{1: 30, 2: 60, 3: 120}` (gives the
   token bucket time to refill).
2. Reduce `context_tokens` back to 6000 (trims ~25% of each request).
3. Switch to a paid Groq tier for higher TPM.

Until (1) is in place, treat 429s on retries as a hint that the request
window was overshot, not as a code bug.

## FP-ISSUE-026 — Groq 429 `RateLimitError` short-circuiting retries

### Symptom

After the FP-ISSUE-025 fix (line-items namespace), the next Docling upload
(`42ce71d6-…`, `docusenseai pdf maker 6.pdf`) crossed the LLM boundary and
triggered `groq.RateLimitError: Error code: 429 ... Limit 8000, Used 5826,
Requested 2681`. The corrective retry also 429'd, then the second retry 429'd
again. The orchestrator caught each `groq.RateLimitError` as a generic
`ProcessingError("PROCESSING_FAILED")` (because the exception type was not a
`ProcessingError` and not a timeout), and the old `RETRY_DELAYS = {1: 5,
2: 10, 3: 20}` seconds put every attempt inside the same 1-minute TPM window.
The document then failed terminally after three retries with no rate-limit
telemetry.

### Root cause

`openai/gpt-oss-20b` on the Groq on-demand tier is capped at 8000 TPM. With
`context_tokens=8000` plus schema + system prompt overhead, one corrective
extraction call consumes ~5–8 k tokens. The short retry ladder meant every
attempt happened inside the same TPM bucket, so attempts 2 and 3 were
*guaranteed* to 429. The orchestrator also had no way to distinguish "the
provider told us to back off" from "the LLM returned garbage" — both surfaced
as the catch-all `PROCESSING_FAILED` mask.

### Fix (deployed)

1. **New error code `LLM_RATE_LIMITED`** added to
   `app/document_processing_rag/errors.py::PROCESSING_CODES`. It is **not** in
   `TERMINAL_CODES`, so it is retryable. The next attempt will go through the
   normal `schedule_retry` path.
2. **Provider-level catch** in
   `app/backend_runtime/providers.py::GroqExtractionAdapter.extract`:
   ```python
   try:
       return await self._call(evidence, schema_version, corrective)
   except _GroqRateLimited as exc:
       from ..document_processing_rag.errors import ProcessingError
       raise ProcessingError("LLM_RATE_LIMITED") from exc
   ```
   `_GroqRateLimited` is `groq.RateLimitError` aliased at module import time.
   The new `extract()` wraps the original `_call()` body, so existing prompt
   code is unchanged.
3. **Slowed retry ladder** in
   `app/document_processing_rag/orchestrator.py::RETRY_DELAYS`:
   ```python
   RETRY_DELAYS = {1: 60, 2: 90, 3: 120}  # was {1: 5, 2: 10, 3: 20}
   ```
   With one retry costing ~5–8 k tokens, three retries must span at least
   two minutes so the token bucket can refill between attempts. The comment
   in the file now records this rationale explicitly.

### Evidence

- `ProcessingError("LLM_RATE_LIMITED").retryable is True` (confirmed at runtime).
- After the FP-ISSUE-025 fix, the document `72c83bf0-…` saw its last retry 429
  and recorded `error_code='PROCESSING_FAILED'`. The new code would have
  recorded `error_code='LLM_RATE_LIMITED'` and waited 120 s before the next
  attempt.
- A Celery restart is required to pick up `RETRY_DELAYS`,
  `GroqExtractionAdapter.extract`, and the new `PROCESSING_CODES` entry, then
  a reset+redispatch of `42ce71d6-…` (or a fresh upload) should let the next
  attempt slip past the 1-minute TPM refill window.

## FP-ISSUE-027 — `overall_confidence=0.00` despite successful end-to-end (extraction-quality)

### Symptom

`docusenseai pdf maker 7.pdf` (`12545abe-…`) reached
`documents.status='pending_review'` with `processing_jobs.status='completed'`
in a single attempt. `invoices.is_math_valid=True` and the financial totals
reconcile (`subtotal=3860.00, tax=289.50, discount=110.00, grand_total=4039.50`).
The LLM emitted 3 line_items with correct descriptions matching the table.
Yet `documents.overall_confidence=0.00`.

### Root cause

`confidence.score_invoice` computes
`weighted_total − penalty`, clamped to `[0, 100]`. The header-only weights
total to 100 (`invoice.invoice_number` 15, `supplier_name` 15, `date_issued` 10,
`currency` 10, `subtotal` 10, `tax_amount` 5, `discount_amount` 5,
`grand_total` 30) and the penalties are:

- `-30` if `invoice_number is None`
- `-20` if `date_issued is None`
- `-40` if `grand_total is None`
- `-15` if `supplier_name is None`
- `-35` if any BR-03 financial rule failed

For this document:

- `supplier_name='crestline manufacturing co.'` (valid 60): 60 × 15 / 100 = **9.0**
- `currency='USD'` (valid 60): 60 × 10 / 100 = **6.0**
- `subtotal=3860.00` (valid 60): 60 × 10 / 100 = **6.0**
- `tax_amount=289.50` (valid 60): 60 × 5 / 100 = **3.0**
- `discount_amount=110.00` (valid 60): 60 × 5 / 100 = **3.0**
- `grand_total=4039.50` (valid 60): 60 × 30 / 100 = **18.0**
- `invoice.invoice_number=None` → 0 × 15 = **0**; penalty **−30**
- `invoice.date_issued=None` → 0 × 10 = **0**; penalty **−20**

Total = 45 − 50 = **−5 → clamped to 0.00**. The penalties for the two missing
required header fields alone eclipse the entire weighted score.

The penalty weights (30/20/40/15) are deliberately harsh so a document with no
extracted invoice_number can never reach human review at high confidence, but
in this document the values exist in source:

- **Invoice number** `inv-2026-0638` lives in `document_chunks.ordinal=2`
  (chunk_type=`text`, raw_content = `inv - 2026 - 0638`).
- **Issue date** `2026-09-19` lives in ordinal=12 (text).
- The LLM did not emit those two values in the corrective attempt and the
  Groq call returned `200 OK` only once (no retry triggered by
  `_normalize_field_paths`), so the run wrote an invoice with two `null`
  required header fields.

Secondary issue visible in the same run: `supplier_name` was emitted as
`crestline manufacturing co.`, which is the buyer
(`buyer/bill to` chunk ordinal=14). The actual supplier
`novagrid systems ltd.` sits in ordinal=4 alongside its tax id. The LLM
apparently picked up the wrong named entity because the "Supplier" header
separator at ordinal=3 did not group strongly enough with its body chunk
during retrieval — the supplier chunk scored below the buyer chunk in cosine
similarity, so the LLM saw the buyer first.

### Fix (deployed)

This is an extraction-quality issue, not a pipeline defect. Three levers, in
priority order:

1. **Tighten the prompt to make `inv-2026-NNNN` patterns and ISO dates
   individually required.** A second bullet in the Groq system prompt:

   > Required header facts you MUST emit (emit `null` only if they are truly
   > absent from the evidence, never omit them silently):
   > - `invoice.invoice_number` from `inv-2026-NNNN` style numbers
   > - `invoice.date_issued` from `YYYY-MM-DD` style issue dates

2. **Add a post-extraction sanity check.** After `_normalize_field_paths`,
   if `invoice.invoice_number` is None but the evidence contains a token
   matching `inv-\d{4}-\d{4}` or similar, populate it from the most
   text-typed chunk that mentions it. Same for `date_issued` matching
   `\d{4}-\d{2}-\d{2}` that no line_item already claimed.

3. **Strengthen `assemble_evidence` for the supplier block.** Treat the
   `Supplier` header chunk and its immediate body chunk as a hard pair
   (always both included, both at full weight). This prevents retrieval
   ranking from splitting them.

Without (1)–(3) the document continues to land on `pending_review` with
confidence=0, and a human reviewer has to type the invoice number and date
back in.

### Evidence

- `documents` row: `status='pending_review'`, `overall_confidence=0.00`,
  no `error_code`.
- `invoices`: `is_math_valid=True`, supplier=`crestline manufacturing co.`
  (wrong — that's the buyer), header numeric values reconcile.
- `field_evidence` (29 rows): supplier/currency/subtotal/tax/discount/grand_total
  are `valid` 60; invoice_number/buyer_name/date_issued/supplier_tax_id/due_date
  are `missing` 0; line_item descriptions are `valid` 60 but the numeric
  columns of every line are `invalid` 0 (LLM did not emit evidence citations
  for them — only the descriptions got citations).
- `document_chunks`: 2 table chunks and 1 supplier/body chunk group confirm
  the source content is correctly parsed.
- `1` succeeded in ~18 s with the new `LLM_RATE_LIMITED` code + slowed
  `RETRY_DELAYS` unchanged from FP-ISSUE-026.

## FP-ISSUE-028 — Self-Service Tenant Signup Live Contract Verification

- **Status/date:** BLOCKED for configured-live acceptance, 2026-09-20;
  selective `CONTRACT_FIXTURE` integration is complete.
- **Present:** `POST /api/v1/auth/signup` on the backend (201 Created on success,
  400 on validation, 409 on email collision, 500 on backend failure), the same
  envelope shape as `/login` (access_token, expires_in, user). `AuthService.signup_company_and_admin`
  atomically inserts the tenant (`public.companies`) and the first admin user
  (`public.users`) and converts the unique-email violation into
  `AuthFailure("EMAIL_TAKEN", 409)`. Frontend `/signup` page with a
  reducer-driven form (full name, organization name, business type, country,
  work email, password, confirm password, terms), paired "Sign up" + "Sign in"
  CTAs in the landing header / hero / final section, paired footer link from
  `/login`, new `.ds-signup-*` styles, and a new proxy allowlist entry
  (`POST /api/v1/auth/signup`). Reuses `writeSession`, `readProfile`, the
  shared UUID_PATTERN, the same-origin session route pattern, and the existing
  `PublicShell` layout.
- **Evidence:** `npx tsc --noEmit -p tsconfig.json` exited **0**;
  `SignupRequest.model_json_schema()` reports exactly the seven required fields
  (`agree_to_terms`, `business_type`, `country`, `email`, `full_name`,
  `organization_name`, `password`); `AuthService.signup_company_and_admin` and
  `SIGNUP_BUSINESS_TYPES` are exposed; `frontend/src/lib/api/proxy-policy.ts`
  lists the new allowlist entry. No backend dependency, lockfile, environment,
  database artifact, ORM model, migration, queue, or worker file changed.
- **Remaining:** Real tenant-creation smoke journey (one fresh tenant end to
  end through `/documents`, `/documents/[id]`, `/documents/[id]/review`),
  email-collision retry behavior on the UI, multi-tenant isolation check (two
  fresh tenants cannot see each other's documents), RBAC propagation when the
  admin later invites operators/viewers, manual responsive / keyboard /
  screen-reader / 200% zoom / text-spacing / forced-colors evidence, and a
  regenerated `docs/api/openapi.yaml` that includes the new path.
- **Known gap:** There is **no UI** to invite operators or viewers into a
  freshly created tenant. Today, additional `operator` / `viewer` accounts
  must still be seeded via SQL (e.g. by extending
  `backend/scripts/reset_demo_passwords.py`). The signup flow only creates the
  bootstrap admin. A subsequent "Invite member" feature is a separate task.
- **Close when:** Representative configured-infrastructure tenant/role/state
  isolation is exercised, manual browser / accessibility evidence is recorded,
  and a regenerated OpenAPI artifact includes the new signup path.

## FP-ISSUE-029 — Local Environment Recovery, TLS Regeneration, and Probe Noise (2026-11-06)

Resolved 2026-11-06 in a live support session after the local stack had been
stopped for ~6 weeks (the Docker containers showed `Exited` from 2026-09-24).
Four distinct environment problems were found and fixed; no application
business logic, database artifact, dependency pin, or OpenAPI contract changed.

### 1. PostgreSQL container failed to start — `postgres-init.sql` had become a directory

`docker start docusense-local-postgres-1` failed with
`error mounting "…/infrastructure/postgres-init.sql" to rootfs at
"/docker-entrypoint-initdb.d/01-vector.sql": not a directory`. The container's
baked-in bind mount expects `infrastructure/postgres-init.sql` to be a **file**
(read-only single-file mount), but on disk the path had been replaced by an
**empty directory** at some point after the original `foundation.py init` run.

- **Fix:** verified the directory was empty, removed it, recreated the path as
  a file containing `CREATE EXTENSION IF NOT EXISTS vector;` (40 bytes).
- **Evidence:** container started; `psql` query inside the container returned
  `vector 0.8.6` from the existing `docusense` database. The
  `docusense-local_postgres-data` named volume was untouched throughout, so no
  data was affected (the initdb script only runs on a fresh volume anyway).

### 2. MinIO started `unhealthy` — local TLS certificates were lost

`infrastructure/local/certs/` was completely empty on disk (the original
certificates were generated by `foundation.py init`, which no longer exists in
this checkout). The MinIO container binds that directory to `/certs`, so the
server silently started in **plain HTTP** while its healthcheck command
(`curl --cacert /certs/public.crt https://localhost:9000/minio/health/ready`)
kept failing with curl exit 77 (certificate load error) — hence `unhealthy`.

- **Fix:** regenerated a one-year self-signed development certificate with the
  backend venv's `cryptography` 46.0.7, writing:
  - `infrastructure/local/certs/private.key` (2048-bit RSA, unencrypted PEM)
  - `infrastructure/local/certs/public.crt` (valid until **2027-11-05**)

  The single certificate carries `BasicConstraints CA:TRUE`,
  `keyCertSign` + `serverAuth`, and SANs `localhost`, `minio`, `127.0.0.1`, so
  it works simultaneously as the MinIO server certificate and as the trust
  anchor referenced by `.env`'s `AWS_CA_BUNDLE=infrastructure/local/certs/public.crt`
  and by the container healthcheck's `--cacert`.
- **Evidence:** `docker restart docusense-local-minio-1` → container report
  `healthy`; host-side `urllib.request.urlopen('https://localhost:39500/minio/health/ready')`
  verified with the regenerated CA returned **HTTP 200**; in-container
  healthcheck-style curl passed.
- **Unchanged on purpose:** `MINIO_KMS_SECRET_KEY` in `.env` was never rotated,
  so the server-side-encrypted objects remain readable. `.env` was not modified.

### 3. Frontend hydration-mismatch warnings — Bitwarden extension attributes

Next.js 16 (Turbopack) reported two console hydration errors while the page
worked. The diff showed injected attributes `bis_skin_checked="1"`,
`bis_register=...`, and `__processed_<uuid>="true"` on `<html>`, `<body>`, and
landing-page `<div>`s — the signature of the **Bitwarden browser extension**
mutating the DOM before React hydrates, not an application defect.

- **Fix (code):** added `suppressHydrationWarning` to `<html>` and `<body>` in
  `frontend/src/app/layout.tsx`, the officially recommended React/Next.js
  workaround; the first error is silenced.
- **Fix (user-side, remaining):** the second error (injected attributes on
  every landing-shell `<div>`) requires excluding `localhost:3000` from
  Bitwarden autofill or using an extension-free dev profile. The user chose to
  keep Bitwarden as-is; the warnings are cosmetic and do not affect the app.

### 4. `GET /health` 404 noise in the backend log — not our listeners

After the backend was confirmed healthy (`/health/live` → 200,
`/health/ready` → 200), the log still showed periodic
`GET /health HTTP/1.1" 404` lines. The poller was identified by matching
`Get-NetTCPConnection -RemotePort 8000` clients: **`opencode.exe serve --service`**,
the OpenCode tool's background service scanning common localhost dev ports
(`GET /health` then `GET /v1/models` to detect an OpenAI-compatible local LLM
server). Frontend, Docker, and application code were excluded as sources.

- **Fix:** two dev-convenience aliases in
  `backend/app/backend_runtime/host.py`, both `include_in_schema=False` and
  therefore invisible to the published OpenAPI artifact and to fixtures:
  ```python
  @app.get("/health", include_in_schema=False)
  async def health() -> dict[str, str]:
      return {"status": "ok"}

  @app.get("/v1/models", include_in_schema=False)
  async def probe_models() -> dict[str, object]:
      return {"object": "list", "data": []}
  ```
- **Evidence:** after a server restart the user's log showed
  `GET /health HTTP/1.1" 200 OK` and `GET /v1/models` no longer erroring.
- Also noted here to save future diagnosis: the process list showed apparent
  duplicates (one server, one celery, one reconciler, each twice). The
  `.venv\Scripts\python.exe` launcher spawns the codex base interpreter, so
  each logical service appears as two processes sharing one start timestamp —
  there is only one instance of each.

### Documentation/README deltas

- `docs/development/README.md` still references `infrastructure/foundation.py`.
  Both `foundation.py` and `infrastructure/docker-compose.yml` are absent from
  this checkout while the Compose-created containers persist. Daily startup
  currently works via `docker start docusense-local-postgres-1
  docusense-local-redis-1 docusense-local-minio-1` after opening Docker
  Desktop. Regenerating `foundation.py` + compose file (or re-adding them from
  upstream `04-output`) is follow-up work, not blocking.
- **RESOLVED 2026-11-09 (regeneration, pending fresh-clone verification):**
  `infrastructure/docker-compose.yml` (pgvector/pgvector:pg16, redis:7.4-alpine,
  source-built MinIO at tag RELEASE.2025-10-15T17-29-55Z, loopback-only ports
  55465/56379/39500) and `infrastructure/minio/Dockerfile` were recreated from
  the documented architecture, and `infrastructure/foundation.py` was
  regenerated with `init`/`up`/`check`/`down`/`migrate`/`test-db`/`run --`.
  `migrate` is new: it applies the six feature revisions to a fresh volume in
  chain order (0001 → 20260907_0006). `init` additionally generates
  `frontend/.env.local` (three server-only values) and defaults model cache
  paths to `%HOME%/DocuSenseModels` instead of an `F:` path. Compose
  configuration resolves (`docker compose config --quiet` passed) and the
  revision-chain parser reproduces the expected head. A full fresh clone
  verification (first `up` MinIO build, `migrate` on an empty volume, then
  server/worker/reconciler/frontend) is still outstanding.

### Deferred items requiring user approval (not implemented)

1. `backend/run_server_dev.py` — auto-reloading dev entry point
   (`uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True,
   access_log=True)` with the top-level `WindowsSelectorEventLoopPolicy` set
   for the reloader child). Full source was provided in chat; file creation
   awaits approval.
2. `opencode.jsonc` permissions configuration
   (`{ "action": "edit", "resource": "*", "effect": "ask" }` +
   `{ "action": "shell", "resource": "*", "effect": "ask" }`) so the agent
   prompts before any file or shell change. Documented in chat; the user will
   create the file themselves either at
   `final_project/opencode.jsonc` (project) or
   `~/.config/opencode/opencode.jsonc` (global).

### Verification snapshot (end of session)

| Check | Result |
| --- | --- |
| `docker ps` (postgres, redis, minio) | all three `healthy` |
| pgvector extension | `vector 0.8.6` present |
| `GET /health/live`, `/health/ready` | 200 / 200 |
| `GET /health`, `/v1/models` (probe aliases) | 200 / 200 |
| MinIO HTTPS `ready` from host via `AWS_CA_BUNDLE` | HTTP 200 |
| Frontend `next dev` + login/dashboard flows | working (200 OK) |
| Backend runtime processes | 1 server + 1 celery + 1 reconciler (launcher pairs explained) |
