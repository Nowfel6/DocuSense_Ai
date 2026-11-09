# Final Project Code Registry

This registry records code artifacts integrated into `final_project/` from the
production-room `04-output/` handoff folders.

## Maintenance Rule

Update this file whenever a code file is added, moved, replaced, or removed in
`final_project/`. For production handoffs, record both the verified source path
and its final destination. Do not register manifests, planning documents,
temporary files, virtual environments, caches, or generated build output as
application code.

Each code artifact must have one canonical location in `final_project/`. Keep
feature-specific backend code together under `backend/app/[feature]/`, its tests
under `backend/tests/[feature]/`, and its database artifacts under
`database/[feature]/`. Do not create empty placeholder folders.

## Public Landing Frontend Integration — 2026-09-16 — STATIC PUBLIC CONTENT

The verified `public-landing` Stage 4 package was selectively integrated into the
canonical frontend. The `/` route is statically prerendered, makes no backend or
third-party request, reads no session/tenant data, and exposes only real
same-origin sign-in navigation. Login retains its existing `PublicShell` through
a new route-specific layout.

Source handoff:
`frontend_production/workflows/04-output/public-landing/HANDOFF.md`.

### Integrated paths

| Verified Stage 4 source | Canonical final destination | Integration role |
| :--- | :--- | :--- |
| `public-landing/src/app/(public)/layout.tsx` | `frontend/src/app/(public)/layout.tsx` | Neutral public route-group boundary so route-specific shells own landmarks. |
| `public-landing/src/app/(public)/page.tsx` | `frontend/src/app/(public)/page.tsx` | Static landing route and metadata. |
| `public-landing/src/app/(public)/login/layout.tsx` | `frontend/src/app/(public)/login/layout.tsx` | Preserves the existing narrow Login `PublicShell`. |
| `public-landing/src/components/shell/public-shell.tsx` | `frontend/src/components/shell/public-shell.tsx` | Changes the public wordmark home target from `/login` to `/`. |
| `public-landing/src/features/public-landing/landing-shell.tsx` | `frontend/src/features/public-landing/landing-shell.tsx` | Feature-owned skip/header/main/footer composition. |
| `public-landing/src/features/public-landing/public-landing-view.tsx` | `frontend/src/features/public-landing/public-landing-view.tsx` | Approved hero, outcomes, workflow, governance and CTA content. |
| `public-landing/src/features/public-landing/public-landing.module.css` | `frontend/src/features/public-landing/public-landing.module.css` | Token-based responsive, forced-color and reduced-motion styling. |
| `public-landing/src/test/public-landing.test.tsx` | `frontend/src/test/public-landing.test.tsx` | Three focused content, navigation, zero-request and semantic tests. |
| `public-landing/src/test/auth-login-shell.test.tsx` | `frontend/src/test/auth-login-shell.test.tsx` | Adds one Login-shell/wordmark regression while preserving existing shell coverage. |

All nine final destinations are byte-identical to the Stage 4 output.

Integrated verification:

- typecheck passed after Next regenerated route types;
- ESLint passed with zero reported warnings/errors;
- focused landing/Login-shell run passed **2 files / 7 tests**;
- Next.js 16.3.4 webpack production build passed and reported static `○ /`,
  dynamic `/login`, and all existing routes;
- package and lock files were unchanged;
- the full final suite reported **100 passing / 2 failing** tests. Both failures
  are existing OpenAPI freshness tests whose cwd-relative paths resolve to the
  nonexistent `E:\final_project\docs\api\openapi.yaml` when run from the canonical
  frontend. The same complete suite passed **102/102** in the deeper Stage 3
  workspace and the failures do not import or exercise Feature 16.

API readiness is `NOT_APPLICABLE — STATIC PUBLIC CONTENT`; no fixture exists or
is required. Real-browser responsive, keyboard/focus, 200% zoom, forced-color and
screen-reader evidence remains open and is not claimed by this integration.

## Settings API Placeholder Frontend Integration — 2026-09-16 — STATIC PLACEHOLDER

The verified `settings-api-placeholder` Stage 4 package was selectively merged
into the canonical frontend. Four destinations were new. The existing shared
navigation differed from the verified package by exactly the two approved
changes: enable the already-declared admin-only Settings item and add the exact
Settings/API breadcrumb case.

Source handoff:
`frontend_production/workflows/04-output/settings-api-placeholder/HANDOFF.md`.

| Verified output source | Canonical final destination | Adaptation / role |
| :--- | :--- | :--- |
| `settings-api-placeholder/src/app/(authenticated)/settings/api/page.tsx` | `frontend/src/app/(authenticated)/settings/api/page.tsx` | Dynamic protected route; admin view and safe operator/viewer denial. |
| `settings-api-placeholder/src/features/settings-api-placeholder/settings-api-placeholder-view.tsx` | `frontend/src/features/settings-api-placeholder/settings-api-placeholder-view.tsx` | Static server-compatible release-state composition with no feature request. |
| `settings-api-placeholder/src/features/settings-api-placeholder/settings-api-placeholder.module.css` | `frontend/src/features/settings-api-placeholder/settings-api-placeholder.module.css` | Token-based bounded wide and intentional narrow layout. |
| `settings-api-placeholder/src/components/shell/navigation.ts` | `frontend/src/components/shell/navigation.ts` | Enables the existing admin-only item and adds centralized Settings breadcrumbs. |
| `settings-api-placeholder/src/test/settings-api-placeholder.test.tsx` | `frontend/src/test/settings-api-placeholder.test.tsx` | Four focused role, route, copy, navigation, breadcrumb and zero-request tests. |

All **5** final source/test files are byte-identical to the verified Stage 4
package. At the user's direction, the already-passing Stage 3 checks were not
rerun: typecheck, zero-warning lint, **1 focused file / 4 tests**, **21 complete
files / 98 tests**, and the supported Next.js 16.3.4 Webpack production build
with dynamic `/settings/api` had passed. No fixture, dependency, lockfile,
environment, proxy, backend, database or OpenAPI file changed. API readiness is
`NOT_APPLICABLE — STATIC_DEFERRED_PLACEHOLDER`; final manual responsive and
accessibility evidence remains tracked separately.

## Dashboard & Recent Activity Frontend Integration — 2026-09-16 — CONTRACT_FIXTURE

The verified `dashboard-activity` Stage 4 package was selectively merged into
the canonical frontend. The existing temporary Dashboard route was the expected
Feature 09 placeholder and was replaced. The existing Feature 13 core test
differed only by its stale OpenAPI schema count (`91` rather than the corrected
`95`). Every other destination was absent before placement.

Source handoff:
`frontend_production/workflows/04-output/dashboard-activity/HANDOFF.md`.

### Route and feature-owned modules

| Verified output source | Canonical final destination | Adaptation / role |
| :--- | :--- | :--- |
| `dashboard-activity/src/app/(authenticated)/dashboard/page.tsx` | `frontend/src/app/(authenticated)/dashboard/page.tsx` | Replaces the temporary workspace screen with the thin protected Dashboard route and validated canonical report state. |
| `dashboard-activity/src/features/dashboard-activity/types.ts` | `frontend/src/features/dashboard-activity/types.ts` | Feature-scoped dashboard, metric, trend, activity, pagination and report-state types. |
| `dashboard-activity/src/features/dashboard-activity/api.ts` | `frontend/src/features/dashboard-activity/api.ts` | Strict dashboard/activity decoder, cross-field invariants, UTC report serialization and snapshot-aware requests. |
| `dashboard-activity/src/features/dashboard-activity/format.ts` | `frontend/src/features/dashboard-activity/format.ts` | Percentage-unit, duration, integer, UTC and bucket presentation helpers. |
| `dashboard-activity/src/features/dashboard-activity/safe-activity-link.ts` | `frontend/src/features/dashboard-activity/safe-activity-link.ts` | Exact role-safe canonical document-detail link validation. |
| `dashboard-activity/src/features/dashboard-activity/report-controls.tsx` | `frontend/src/features/dashboard-activity/report-controls.tsx` | Explicit server-default/custom UTC range and bucket controls with client validation. |
| `dashboard-activity/src/features/dashboard-activity/current-workload.tsx` | `frontend/src/features/dashboard-activity/current-workload.tsx` | Snapshot-labelled current workload cards kept separate from period facts. |
| `dashboard-activity/src/features/dashboard-activity/period-overview.tsx` | `frontend/src/features/dashboard-activity/period-overview.tsx` | Period headline, processing-quality and review-quality metrics with denominators and exclusions. |
| `dashboard-activity/src/features/dashboard-activity/accessible-data-table.tsx` | `frontend/src/features/dashboard-activity/accessible-data-table.tsx` | Native disclosure and exact-value table alternative for visual summaries. |
| `dashboard-activity/src/features/dashboard-activity/dashboard-visualizations.tsx` | `frontend/src/features/dashboard-activity/dashboard-visualizations.tsx` | Five dependency-free visual groups with canonical spines, null gaps and separate review/backlog scales. |
| `dashboard-activity/src/features/dashboard-activity/recent-activity.tsx` | `frontend/src/features/dashboard-activity/recent-activity.tsx` | Trusted event summaries, responsive table/cards, role-safe actions and pagination controls. |
| `dashboard-activity/src/features/dashboard-activity/dashboard-activity-view.tsx` | `frontend/src/features/dashboard-activity/dashboard-activity-view.tsx` | Request cancellation, latest-response ownership, refresh, retry, offline, forbidden and partial-failure orchestration. |
| `dashboard-activity/src/features/dashboard-activity/dashboard-activity.module.css` | `frontend/src/features/dashboard-activity/dashboard-activity.module.css` | Token-based wide/tablet/mobile dashboard, charts and activity layouts. |

### Focused tests and shared freshness synchronization

| Verified output source | Canonical final destination | Coverage / adaptation |
| :--- | :--- | :--- |
| `dashboard-activity/src/test/fixtures/dashboard-activity.ts` | `frontend/src/test/fixtures/dashboard-activity.ts` | Synthetic reviewed-contract analytics/activity fixtures. |
| `dashboard-activity/src/test/dashboard-activity-core.test.ts` | `frontend/src/test/dashboard-activity-core.test.ts` | OpenAPI, UTC query, snapshot, invariant, redaction, rate and safe-link coverage. |
| `dashboard-activity/src/test/dashboard-activity-components.test.tsx` | `frontend/src/test/dashboard-activity-components.test.tsx` | Principal loaded-state and explicit UTC range interaction coverage. |
| `dashboard-activity/src/test/document-search-export-core.test.ts` | `frontend/src/test/document-search-export-core.test.ts` | Preserves Feature 13 coverage while synchronizing the reviewed OpenAPI total from 91 to 95 schemas. |

All **17** final source/test files are byte-identical to the verified Stage 4
package. At the user's direction, the already-passing Stage 3 checks were not
rerun: typecheck, zero-warning lint, **2 focused files / 8 tests**, **20 complete
files / 94 tests**, and the supported Next.js 16.3.4 Webpack production build
with dynamic `/dashboard` had passed. No dependency, lockfile, environment,
backend, database or generated OpenAPI file changed. This placement is
`CONTRACT_FIXTURE`; representative configured role/tenant/state/live-data and
manual responsive/accessibility evidence remains open.

## Document Search & Export Frontend Integration — 2026-09-16 — CONTRACT_FIXTURE

The verified `document-search-export` Stage 4 package was selectively merged
into the canonical frontend. All thirteen route, feature and test destinations
were absent before placement. The five shared destinations were inspected first;
their differences were exactly the approved Feature 13 adaptations, so no
unrelated final-app work was displaced.

Source handoff:
`frontend_production/workflows/04-output/document-search-export/HANDOFF.md`.

### Route and feature-owned modules

| Verified output source | Canonical final destination | Adaptation / role |
| :--- | :--- | :--- |
| `document-search-export/src/app/(authenticated)/documents/search/page.tsx` | `frontend/src/app/(authenticated)/documents/search/page.tsx` | Thin protected Search & Export route with canonical URL input. |
| `document-search-export/src/features/document-search-export/types.ts` | `frontend/src/features/document-search-export/types.ts` | Feature-scoped search/export wire, filter, result and lifecycle types. |
| `document-search-export/src/features/document-search-export/api.ts` | `frontend/src/features/document-search-export/api.ts` | Strict OpenAPI-aligned search, create and status adapters. |
| `document-search-export/src/features/document-search-export/search-query.ts` | `frontend/src/features/document-search-export/search-query.ts` | Structured-filter URL parsing, normalization and serialization without semantic text. |
| `document-search-export/src/features/document-search-export/format.ts` | `frontend/src/features/document-search-export/format.ts` | Exact amount, date, similarity and same-origin download formatting. |
| `document-search-export/src/features/document-search-export/document-search-export-hub.tsx` | `frontend/src/features/document-search-export/document-search-export-hub.tsx` | Search, request identity, selection, export creation, recovery and polling orchestration. |
| `document-search-export/src/features/document-search-export/search-composer.tsx` | `frontend/src/features/document-search-export/search-composer.tsx` | Explicit semantic/structured search form and safe validation feedback. |
| `document-search-export/src/features/document-search-export/search-results.tsx` | `frontend/src/features/document-search-export/search-results.tsx` | Role-safe responsive results, paging and current-page eligible selection. |
| `document-search-export/src/features/document-search-export/export-status-panel.tsx` | `frontend/src/features/document-search-export/export-status-panel.tsx` | Export progress, recovery, terminal state and completed download action. |
| `document-search-export/src/features/document-search-export/document-search-export.module.css` | `frontend/src/features/document-search-export/document-search-export.module.css` | Token-based wide, tablet and narrow Search Hub layouts. |

### Shared frontend adaptations

| Verified output source | Canonical final destination | Adaptation / role |
| :--- | :--- | :--- |
| `document-search-export/src/app/api/backend/[...path]/route.ts` | `frontend/src/app/api/backend/[...path]/route.ts` | Adds approved artifact headers, private no-store proxy errors and exact allowlisted HTTPS export redirects. |
| `document-search-export/src/lib/api/client.ts` | `frontend/src/lib/api/client.ts` | Adds a backward-compatible status-aware response helper for exact `201`/`202` handling. |
| `document-search-export/src/lib/api/proxy-policy.ts` | `frontend/src/lib/api/proxy-policy.ts` | Adds exact export-download redirect validation against server-only configured origins. |
| `document-search-export/src/components/shell/navigation.ts` | `frontend/src/components/shell/navigation.ts` | Releases Search & export and adds its exact breadcrumb. |
| `document-search-export/src/lib/auth/return-path.ts` | `frontend/src/lib/auth/return-path.ts` | Allows canonical structured Search Hub queries while stripping private semantic state. |

### Focused regression tests

| Verified output source | Canonical final destination | Coverage |
| :--- | :--- | :--- |
| `document-search-export/src/test/document-search-export-components.test.tsx` | `frontend/src/test/document-search-export-components.test.tsx` | Viewer, eligible-selection and completed-only download composition regressions. |
| `document-search-export/src/test/fixtures/document-search-export.ts` | `frontend/src/test/fixtures/document-search-export.ts` | Reserved contract-fixture identities and representative search/export resources. |

At original Feature 13 placement all **18** source/test files were byte-identical
to its verified Stage 4 package. Feature 14 later changed only the registered
OpenAPI schema-count assertion in the Feature 13 core test; its current provenance
is recorded in the Dashboard section above. Per the integration request, the
already-passing Stage 3 checks were not
rerun: typecheck, zero-warning lint, **18 files / 86 tests**, production build
(including `/documents/search`), and backend OpenAPI `--check` had passed. No
dependency, lockfile, environment, backend, database or generated OpenAPI change
was introduced. This placement is `CONTRACT_FIXTURE`, not configured-live
acceptance; representative endpoint/role/state/idempotency/polling/download and
manual browser/accessibility evidence remains open. Signed external downloads
also require a known server-only `EXPORT_DOWNLOAD_ALLOWED_ORIGINS` value.

## Feature 13 Search/Export OpenAPI Synchronization — 2026-09-16

The existing composed backend now publishes the complete search/export HTTP
contract required by the approved frontend plan. Runtime and database behavior
are unchanged.

| Production source / generator | Canonical final destination | Role |
| :--- | :--- | :--- |
| `backend_production/workflows/04-output/backend_runtime/openapi.py` | `backend/app/backend_runtime/openapi.py` | Pydantic-derived search/export bodies, queries, idempotency, UUID paths, statuses, download media/headers and stable errors; package-relative import retained. |
| `final_project/backend/scripts/export_openapi.py` | same | Validates Feature 11, 12 and 13 contract surfaces and stale bytes. |
| `backend_production/workflows/04-output/backend_runtime_host.test.py` | `backend/tests/test_runtime_composition.py` | Integrated search/export OpenAPI regression adapted to the final package suite. |
| exact generated `app.main:app` schema | `docs/api/openapi.yaml` | Reviewed OpenAPI 3.1 artifact: **18 paths / 91 schemas**. |

Verification: generation and `--check` passed; focused Backend Production Stage
3 and integrated final suites each passed **5 tests**. The Feature 13 frontend
was subsequently integrated in `CONTRACT_FIXTURE` mode; configured-live and
manual browser verification remain open.

## Feature 12 Review OpenAPI Synchronization — 2026-09-15

The existing composed OpenAPI source now publishes the complete, already-
implemented Human Review Studio HTTP contract without changing runtime route or
database behavior.

| Production source / generator | Canonical final destination | Role |
| :--- | :--- | :--- |
| `backend_production/workflows/04-output/backend_runtime/openapi.py` | `backend/app/backend_runtime/openapi.py` | Pydantic-derived review request schemas, discriminator, header/query and stable errors; package-relative import retained in final project. |
| `final_project/backend/scripts/export_openapi.py` | same | Validates Feature 11 and 12 contract surfaces and stale bytes. |
| `backend_production/workflows/04-output/backend_runtime_host.test.py` | `backend/tests/test_runtime_composition.py` | Integrated review OpenAPI regression adapted to the final package test suite. |
| exact generated `app.main:app` schema | `docs/api/openapi.yaml` | Reviewed OpenAPI 3.1 artifact: 18 paths, 84 schemas. |

Verification: generation and `--check` passed; focused Backend Production Stage 3
and integrated final suites each passed **5 tests**. Representative live review
behavior remains a later frontend/final integration gate.

## Human Review Studio Frontend Integration — 2026-09-15 — CONTRACT_FIXTURE

The verified `human-review-studio` Stage 4 package was selectively merged into
the canonical frontend. All twelve new destinations were absent before
placement. The six shared destinations were merged only after their differences
were confirmed to be the approved Feature 12 changes, so no unrelated final-app
work was displaced.

Source handoff:
`frontend_production/workflows/04-output/human-review-studio/HANDOFF.md`.

### Route and feature-owned modules

| Verified output source | Canonical final destination | Adaptation / role |
| :--- | :--- | :--- |
| `human-review-studio/src/app/(authenticated)/documents/[id]/review/page.tsx` | `frontend/src/app/(authenticated)/documents/[id]/review/page.tsx` | Thin signed-session, role and document-ID guarded review route. |
| `human-review-studio/src/features/human-review-studio/types.ts` | `frontend/src/features/human-review-studio/types.ts` | Feature-scoped review, validation, source and audit wire/view types. |
| `human-review-studio/src/features/human-review-studio/candidate.ts` | `frontend/src/features/human-review-studio/candidate.ts` | Candidate normalization, dirty-state comparison and mutation payload rules. |
| `human-review-studio/src/features/human-review-studio/api.ts` | `frontend/src/features/human-review-studio/api.ts` | Strict OpenAPI-aligned detail, preview, mutation, source and audit adapters. |
| `human-review-studio/src/features/human-review-studio/review-studio-view.tsx` | `frontend/src/features/human-review-studio/review-studio-view.tsx` | Review loading, edit, preview, action, conflict, source and audit orchestration. |
| `human-review-studio/src/features/human-review-studio/invoice-fields.tsx` | `frontend/src/features/human-review-studio/invoice-fields.tsx` | Accessible invoice-field corrections and field-level validation rendering. |
| `human-review-studio/src/features/human-review-studio/line-items-editor.tsx` | `frontend/src/features/human-review-studio/line-items-editor.tsx` | Stable editable line-item rows and mutation-safe item handling. |
| `human-review-studio/src/features/human-review-studio/validation-panel.tsx` | `frontend/src/features/human-review-studio/validation-panel.tsx` | Preview state, blocking findings and review-decision actions. |
| `human-review-studio/src/features/human-review-studio/source-evidence-pane.tsx` | `frontend/src/features/human-review-studio/source-evidence-pane.tsx` | Source refresh/open and extraction evidence presentation. |
| `human-review-studio/src/features/human-review-studio/audit-history.tsx` | `frontend/src/features/human-review-studio/audit-history.tsx` | Lazy, paginated immutable review history. |
| `human-review-studio/src/features/human-review-studio/human-review-studio.module.css` | `frontend/src/features/human-review-studio/human-review-studio.module.css` | Token-based responsive review workspace layouts and states. |

### Shared frontend adaptations

| Verified output source | Canonical final destination | Adaptation / role |
| :--- | :--- | :--- |
| `human-review-studio/src/app/api/backend/[...path]/route.ts` | `frontend/src/app/api/backend/[...path]/route.ts` | Applies route-aware request-size enforcement before backend forwarding. |
| `human-review-studio/src/lib/api/proxy-policy.ts` | `frontend/src/lib/api/proxy-policy.ts` | Preserves the 2 MiB JSON and 55 MiB upload caps and applies the backend-aligned **20 MiB** review mutation/preview cap. |
| `human-review-studio/src/components/shell/navigation.ts` | `frontend/src/components/shell/navigation.ts` | Adds the Review breadcrumb without a new global navigation item. |
| `human-review-studio/src/lib/auth/return-path.ts` | `frontend/src/lib/auth/return-path.ts` | Allows the query-free review route as a safe protected return target. |
| `human-review-studio/src/features/document-detail-chunk-inspector/document-detail-view.tsx` | `frontend/src/features/document-detail-chunk-inspector/document-detail-view.tsx` | Adds the authorized Review entry action from document detail. |

### Focused regression tests

| Verified output source | Canonical final destination | Coverage |
| :--- | :--- | :--- |
| `human-review-studio/src/test/human-review-core.test.ts` | `frontend/src/test/human-review-core.test.ts` | Candidate normalization, dirty-state, payload, decoder and review policy regressions. |
| `human-review-studio/src/test/proxy-policy.test.ts` | `frontend/src/test/proxy-policy.test.ts` | Existing proxy rules plus exact 20 MiB review request-cap behavior. |

All **18** final source/test files are byte-identical to the verified Stage 4
package. Per the integration request, the already-passing Stage 3 checks were not
rerun: typecheck, zero-warning lint, **16 files / 75 tests**, production build
(including `/documents/[id]/review`), and backend OpenAPI `--check` had passed.
No dependency, lockfile, environment, backend, database, or generated OpenAPI
change was introduced. This placement is `CONTRACT_FIXTURE`, not configured-live
acceptance; representative endpoint/role/state/conflict/idempotency/source and
manual browser/accessibility evidence remains open.

## Feature 11 Backend/OpenAPI Synchronization — 2026-09-14

The approved Feature 11 prerequisite repair updates existing canonical backend
modules; it adds no route, database artifact, dependency, queue, worker, or
provider. The composed generic detail route retains one owner and now covers all
approved role/state cases. OpenAPI is generated from exact `app.main:app`.

| Production source / generator | Canonical final destination | Role |
| :--- | :--- | :--- |
| `backend_production/workflows/04-output/human_review_audit.schemas.py` | `backend/app/human_review_audit/schemas.py` | Base-plus-optional-review detail wire shape. |
| `backend_production/workflows/04-output/human_review_audit.service.py` | `backend/app/human_review_audit/service.py` | All-state human detail authorization/projection. |
| `backend_production/workflows/04-output/human_review_audit.routes.py` | `backend/app/human_review_audit/routes.py` | Detail auth/error OpenAPI declarations. |
| `backend_production/workflows/04-output/document_ingestion.routes.py` | `backend/app/document_ingestion/routes.py` | Status auth/error OpenAPI declarations. |
| `backend_production/workflows/04-output/document_processing_rag.schemas.py` | `backend/app/document_processing_rag/schemas.py` | Typed RAG error envelope. |
| `backend_production/workflows/04-output/document_processing_rag.routes.py` | `backend/app/document_processing_rag/routes.py` | Chunk/evidence query/auth/error OpenAPI declarations. |
| `backend_production/workflows/04-output/backend_runtime/review_source.py` | `backend/app/backend_runtime/review_source.py` | Authorized approved-viewer source signing support. |
| `backend_production/workflows/04-output/backend_runtime/openapi.py` | `backend/app/backend_runtime/openapi.py` | Composed security schemes and per-operation requirements. |
| `final_project/backend/scripts/export_openapi.py` | same | Exact-app generator, validation, and stale-file check. |
| exact generated `app.main:app` schema | `docs/api/openapi.yaml` | Reviewed OpenAPI 3.1 artifact: 18 paths, 78 schemas. |

Verification: complete Backend Production suite **347 passed**; integrated backend
suite **10 passed**; OpenAPI generation and `--check` passed. Feature 11 frontend
is now integrated in `CONTRACT_FIXTURE` mode; representative live endpoint/E2E
evidence remains pending.

## Document Detail and Chunk Inspector Frontend Integration — 2026-09-15 — CONTRACT_FIXTURE

The reviewed `document-detail-chunk-inspector` Stage 4 package was selectively
merged into the canonical frontend. Before placement, all six shared
destinations differed only by the approved Feature 11 edits and all eighteen new
destinations were absent. No newer or unrelated final-project implementation was
displaced.

Source handoff:
`frontend_production/workflows/04-output/document-detail-chunk-inspector/HANDOFF.md`.

### Routes and feature-owned modules

| Verified output source | Canonical final destination | Adaptation / role |
| :--- | :--- | :--- |
| `document-detail-chunk-inspector/src/app/(authenticated)/documents/[id]/page.tsx` | `frontend/src/app/(authenticated)/documents/[id]/page.tsx` | Thin dynamic detail route with signed-session and UUID gates. |
| `document-detail-chunk-inspector/src/app/(authenticated)/documents/[id]/chunks/page.tsx` | `frontend/src/app/(authenticated)/documents/[id]/chunks/page.tsx` | Thin dynamic workbench route with server-side viewer denial. |
| `document-detail-chunk-inspector/src/features/document-detail-chunk-inspector/types.ts` | `frontend/src/features/document-detail-chunk-inspector/types.ts` | Feature-scoped OpenAPI wire and view types. |
| `document-detail-chunk-inspector/src/features/document-detail-chunk-inspector/api.ts` | `frontend/src/features/document-detail-chunk-inspector/api.ts` | Strict detail, chunk, evidence, pagination, URL and invariant decoders. |
| `document-detail-chunk-inspector/src/features/document-detail-chunk-inspector/source-view.ts` | `frontend/src/features/document-detail-chunk-inspector/source-view.ts` | HTTPS, expiry-safety and PDF page-fragment policy. |
| `document-detail-chunk-inspector/src/features/document-detail-chunk-inspector/workbench-query.ts` | `frontend/src/features/document-detail-chunk-inspector/workbench-query.ts` | Exact mode-aware URL normalization and backend query projection. |
| `document-detail-chunk-inspector/src/features/document-detail-chunk-inspector/document-detail-view.tsx` | `frontend/src/features/document-detail-chunk-inspector/document-detail-view.tsx` | Detail request/state orchestration and route actions. |
| `document-detail-chunk-inspector/src/features/document-detail-chunk-inspector/document-overview.tsx` | `frontend/src/features/document-detail-chunk-inspector/document-overview.tsx` | Read-only file, processing, extraction, validation and review summary. |
| `document-detail-chunk-inspector/src/features/document-detail-chunk-inspector/line-item-summary.tsx` | `frontend/src/features/document-detail-chunk-inspector/line-item-summary.tsx` | Bounded 20-at-a-time invoice line-item reveal. |
| `document-detail-chunk-inspector/src/features/document-detail-chunk-inspector/source-view-action.tsx` | `frontend/src/features/document-detail-chunk-inspector/source-view-action.tsx` | Explicit current/expired source open-or-refresh action. |
| `document-detail-chunk-inspector/src/features/document-detail-chunk-inspector/workbench-view.tsx` | `frontend/src/features/document-detail-chunk-inspector/workbench-view.tsx` | Chunk/evidence mode, request, status, selection and URL orchestration. |
| `document-detail-chunk-inspector/src/features/document-detail-chunk-inspector/workbench-filter-form.tsx` | `frontend/src/features/document-detail-chunk-inspector/workbench-filter-form.tsx` | Exact mode-specific filter drafts and local errors. |
| `document-detail-chunk-inspector/src/features/document-detail-chunk-inspector/workbench-results.tsx` | `frontend/src/features/document-detail-chunk-inspector/workbench-results.tsx` | Responsive chunk/evidence results and server pagination. |
| `document-detail-chunk-inspector/src/features/document-detail-chunk-inspector/item-inspector.tsx` | `frontend/src/features/document-detail-chunk-inspector/item-inspector.tsx` | Wide aside/narrow Drawer technical inspection. |
| `document-detail-chunk-inspector/src/features/document-detail-chunk-inspector/structured-table-view.tsx` | `frontend/src/features/document-detail-chunk-inspector/structured-table-view.tsx` | Inert accessible structured-table rendering. |
| `document-detail-chunk-inspector/src/features/document-detail-chunk-inspector/document-detail-chunk-inspector.module.css` | `frontend/src/features/document-detail-chunk-inspector/document-detail-chunk-inspector.module.css` | Token-based responsive overview, workbench, inspector and card layouts. |

### Shared frontend adaptations

| Verified output source | Canonical final destination | Adaptation / role |
| :--- | :--- | :--- |
| `document-detail-chunk-inspector/src/components/shell/global-sidebar.tsx` | `frontend/src/components/shell/global-sidebar.tsx` | Keeps Documents selected on detail/workbench routes. |
| `document-detail-chunk-inspector/src/components/shell/navigation.ts` | `frontend/src/components/shell/navigation.ts` | Adds safe static dynamic breadcrumbs without a new global item. |
| `document-detail-chunk-inspector/src/features/documents-list-upload-monitor/document-collection.tsx` | `frontend/src/features/documents-list-upload-monitor/document-collection.tsx` | Adds View details to every row/card and preserves authorized active Monitor. |
| `document-detail-chunk-inspector/src/features/documents-list-upload-monitor/documents-list-upload-monitor.module.css` | `frontend/src/features/documents-list-upload-monitor/documents-list-upload-monitor.module.css` | Adds responsive list action grouping only. |
| `document-detail-chunk-inspector/src/lib/auth/return-path.ts` | `frontend/src/lib/auth/return-path.ts` | Adds UUID- and mode-constrained nested return destinations. |

### Focused tests and synthetic fixtures

| Verified output source | Canonical final destination | Adaptation / role |
| :--- | :--- | :--- |
| `document-detail-chunk-inspector/src/test/document-detail-core.test.ts` | `frontend/src/test/document-detail-core.test.ts` | Consolidated OpenAPI/decoder/query/source/return-path coverage. |
| `document-detail-chunk-inspector/src/test/fixtures/document-detail-chunk-inspector.ts` | `frontend/src/test/fixtures/document-detail-chunk-inspector.ts` | Fictional `*.invalid` contract envelopes only. |
| `document-detail-chunk-inspector/src/test/documents-components.test.tsx` | `frontend/src/test/documents-components.test.tsx` | Existing viewer action regression extended for View details. |

All 24 promoted files are byte-identical to their Stage 4 sources. A comparison
against the successful Stage 3 tree covered 119 source/configuration/test files:
118 match exactly, and the sole excluded difference is Next-generated
`next-env.d.ts` switching between `.next/types` and `.next/dev/types`. It contains
no product behavior.

Per the user's instruction, the already successful Stage 3 commands were not
repeated after this byte-identical placement. Inherited evidence remains:
TypeScript passed, ESLint passed with no findings, focused Vitest passed **2
files / 9 tests**, Next.js 16.3.4 production build passed with dynamic detail and
workbench routes, and the backend OpenAPI exporter freshness check passed.

No dependency, lockfile, environment, backend, database, storage, queue, or
worker file changed. The integration is `CONTRACT_FIXTURE`, not `LIVE_API`:
representative live role/state/error/source journeys and manual responsive/
accessibility verification remain required before a live-readiness claim.

## Dashboard Analytics/Activity Placement — 2026-09-12 — READY

Feature 06 backend and database output are integrated in dedicated final-project
packages. Backend dotted artifact names were converted to normal module names and
package-relative imports. The database query/fixture/preflight/test paths were
rebased to the feature-first final layout. Feature 06 adds no ORM model,
migration, table, index, cache, or task.

### Backend artifacts

| Output source | Canonical final destination | Adaptation / role |
| :--- | :--- | :--- |
| `backend_production/workflows/04-output/dashboard_activity.schemas.py` | `backend/app/dashboard_activity/schemas.py` | Strict query, response, envelope, pagination, and integrity models. |
| `backend_production/workflows/04-output/dashboard_activity.errors.py` | `backend/app/dashboard_activity/errors.py` | Package-relative sanitized public errors. |
| `backend_production/workflows/04-output/dashboard_activity.settings.py` | `backend/app/dashboard_activity/settings.py` | Locked non-secret period/page/timeout policy. |
| `backend_production/workflows/04-output/dashboard_activity.repository.py` | `backend/app/dashboard_activity/repository.py` | Package-relative read-only repeatable-read PostgreSQL repository. |
| `backend_production/workflows/04-output/dashboard_activity.service.py` | `backend/app/dashboard_activity/service.py` | Package-relative metrics, catalog, pagination, and role-redaction services. |
| `backend_production/workflows/04-output/dashboard_activity.routes.py` | `backend/app/dashboard_activity/routes.py` | Package-relative dashboard/activity FastAPI router. |
| `backend_production/workflows/04-output/dashboard_activity/__init__.py` | `backend/app/dashboard_activity/__init__.py` | Dotted loader replaced by a normal final-project package initializer. |

The promoted `backend_runtime/auth_adapters.py`, `backend_runtime/host.py`, and
`backend_runtime/__init__.py` were synchronized into their existing canonical
final paths with final-package imports. They add human-only Feature 06 auth,
repository/service construction, both routes, and public runtime exports.

### Database artifacts

| Output source | Canonical final destination | Adaptation / role |
| :--- | :--- | :--- |
| `database_production/workflows/04-output/dashboard_activity.queries.sql` | `database/dashboard_activity/queries/dashboard_activity.queries.sql` | Byte-identical seven-query read-only reference. |
| `database_production/workflows/04-output/dashboard_activity.fixtures.py` | `database/dashboard_activity/seeds/generate_fixtures.py` | Renamed deterministic two-tenant/performance oracle. |
| `database_production/workflows/04-output/dashboard-activity-fixtures/manifest.json` | `database/dashboard_activity/seeds/dashboard-activity-fixtures/manifest.json` | Byte-identical checksummed fixture contract. |
| `database_production/workflows/04-output/seed_dashboard_activity.py` | `database/dashboard_activity/seeds/seed_dashboard_activity.py` | Rebased zero-write disposable-target preflight. |
| `database_production/workflows/04-output/dashboard_activity.db.test.py` | `database/dashboard_activity/tests/test_dashboard_activity.py` | Rebased correctness, isolation, cleanup, and scale-plan suite. |
| `database_production/workflows/04-output/dashboard-activity.requirements.txt` | `database/dashboard_activity/requirements-dev.txt` | Verification-only dependency pins. |

Verification passed **13 Feature 06 contract tests** against the final backend
package, **10 final backend tests**, **18/18 final database tests**, and **3/3
live backend tests**. Final backend p95 was 47.310ms/31.991ms for 30/366-day
dashboard and 12.627ms/10.152ms for first/deep activity pages. The real host
registered both Feature 06 routes and passed startup, readiness, and shutdown
against the migrated disposable database plus PostgreSQL, Redis, and private
MinIO. `pip check` reports no broken requirements.

## Integrated Backend Production Code

| Source | Final destination | Integration note |
| :--- | :--- | :--- |
| `backend_production/workflows/04-output/auth.routes.py` | `backend/app/auth/routes.py` | Placed in the authentication feature module. |
| `backend_production/workflows/04-output/auth.service.py` | `backend/app/auth/service.py` | Placed in the authentication feature module. |
| `backend_production/workflows/04-output/auth.test.py` | `backend/tests/auth/test_auth.py` | Placed in the matching authentication test module. |

## Integrated Concrete Backend Runtime — 2026-09-11

The promoted runtime output is adapted only for the final project's normal
`app.*` package layout. All repository/provider/worker behavior is retained.

| Output source | Final destination | Adaptation / role |
| :--- | :--- | :--- |
| `backend_production/workflows/04-output/backend_runtime/__init__.py` | `backend/app/backend_runtime/__init__.py` | Package exports adapted to the final namespace. |
| `backend_production/workflows/04-output/backend_runtime/auth.py` | `backend/app/backend_runtime/auth.py` | Uses the final auth package directly instead of the dotted-artifact loader. |
| `backend_production/workflows/04-output/backend_runtime/auth_adapters.py` | `backend/app/backend_runtime/auth_adapters.py` | Feature-specific caller conversion, including human-only Feature 06. |
| `backend_production/workflows/04-output/backend_runtime/database.py` | `backend/app/backend_runtime/database.py` | Uses the final package-native shared Base/model chain. |
| `backend_production/workflows/04-output/backend_runtime/entrypoints.py` | `backend/app/backend_runtime/entrypoints.py` | Defaults artifact paths to this final project; environment overrides remain supported. |
| `backend_production/workflows/04-output/backend_runtime/export_repositories.py` | `backend/app/backend_runtime/export_repositories.py` | Feature 5 PostgreSQL/pgvector repository; imports made package-relative. |
| `backend_production/workflows/04-output/backend_runtime/host.py` | `backend/app/backend_runtime/host.py` | Six-feature FastAPI dependency graph and lifecycle; imports made package-relative. |
| `backend_production/workflows/04-output/backend_runtime/providers.py` | `backend/app/backend_runtime/providers.py` | Pinned MiniLM/Docling/Groq adapters; imports made package-relative. |
| `backend_production/workflows/04-output/backend_runtime/queue.py` | `backend/app/backend_runtime/queue.py` | Identifier-only Celery configuration and registration. |
| `backend_production/workflows/04-output/backend_runtime/rag_repositories.py` | `backend/app/backend_runtime/rag_repositories.py` | Fenced RAG PostgreSQL repository; imports made package-relative. |
| `backend_production/workflows/04-output/backend_runtime/rate_limit.py` | `backend/app/backend_runtime/rate_limit.py` | Atomic shared Redis rate limiter. |
| `backend_production/workflows/04-output/backend_runtime/repositories.py` | `backend/app/backend_runtime/repositories.py` | Ingestion PostgreSQL repository; imports made package-relative. |
| `backend_production/workflows/04-output/backend_runtime/review_repositories.py` | `backend/app/backend_runtime/review_repositories.py` | Review/audit PostgreSQL repository; imports made package-relative. |
| `backend_production/workflows/04-output/backend_runtime/review_source.py` | `backend/app/backend_runtime/review_source.py` | Private source-view signing adapter; imports made package-relative. |
| `backend_production/workflows/04-output/backend_runtime/settings.py` | `backend/app/backend_runtime/settings.py` | Strict environment-backed external dependency settings. |
| `backend_production/workflows/04-output/backend_runtime/storage.py` | `backend/app/backend_runtime/storage.py` | Managed TLS S3 lifecycle, RAG source reader, and export storage. |
| `backend_production/workflows/04-output/backend_runtime/workers.py` | `backend/app/backend_runtime/workers.py` | Persistent-loop Celery runner and bounded reconciler. |
| `backend_production/workflows/04-output/backend_runtime_host.test.py` | `backend/tests/test_runtime_composition.py` | Imports adapted to `app.backend_runtime`; four composition tests pass. |

Local entry points derived from the promoted runtime are
`backend/app/main.py`, `backend/app/worker.py`, and `backend/app/reconciler.py`.
The host-required non-secret CORS, trusted-host, and supported-currency settings
are recorded in `.env.example`; local `.env` received the same non-secret values.

## Integrated Database Production Code

| Source | Final destination | Integration note |
| :--- | :--- | :--- |
| `database_production/workflows/04-output/20260901_create_auth_tenancy.sql` | `database/auth/migrations/20260901_create_auth_tenancy.sql` | Standalone PostgreSQL migration for the authentication feature. |
| `database_production/workflows/04-output/20260901_0001_auth_tenancy_migration.py` | `database/auth/migrations/20260901_0001_auth_tenancy_migration.py` | Alembic revision for the authentication feature. |
| `database_production/workflows/04-output/seed_auth_tenancy.py` | `database/auth/seeds/seed_auth_tenancy.py` | Python seed implementation for the authentication feature. |
| `database_production/workflows/04-output/seed-auth-tenancy.sql` | `database/auth/seeds/seed_auth_tenancy.sql` | SQL seed implementation for the authentication feature. |

## Local Integration Support

| Path | Purpose |
| :--- | :--- |
| `backend/app/__init__.py` | Marks the backend application package; invalid placeholder syntax was removed during refinement. |
| `backend/app/auth/__init__.py` | Marks the authentication feature package. |
| `backend/app/main.py` | Concrete ASGI application entry point built from the promoted runtime. |
| `backend/app/worker.py` | Concrete Celery application entry point with process-local persistent async loop. |
| `backend/app/reconciler.py` | Companion bounded recovery/redispatch/expiry process entry point. |

## Foundation Environment — 2026-09-03

Direct cross-feature environment work authorized by the user, implementing Phase 0
of the existing master plan. No production feature module was fabricated or promoted.

| Canonical path | Purpose / readiness |
| :--- | :--- |
| `infrastructure/docker-compose.yml` | Postgres/pgvector, Redis, TLS MinIO and persistent local volumes. All services healthy; foundation checks passed. |
| `infrastructure/minio.Dockerfile` | Pinned MinIO security release built from source after moving Docker storage to F:. |
| `infrastructure/.dockerignore` | Excludes local secrets/certificates from build context. |
| `infrastructure/postgres-init.sql` | Infrastructure pgvector extension, separate from feature migrations. |
| `infrastructure/foundation.py` | Idempotent local credentials/TLS setup, service checks, shutdown, process settings and disposable DB provisioning. |
| `backend/pyproject.toml` | Ingestion/RAG runtime pins plus optional foundation tooling. Current editable installation and dependency check passed. |
| `backend/requirements-foundation-lock.txt` | Resolved Python 3.12/Windows foundation dependency constraints. |
| `frontend/package.json`, `frontend/package-lock.json` | Next.js/React/TypeScript/Tailwind toolchain and npm lockfile; installed and version-checked. UI implementation is later work. |
| `.env.example`, `.gitignore` | Documented settings and exclusions for generated secrets, TLS keys, caches and installations. |

**2026-11-09 regeneration note:** after `foundation.py`, `docker-compose.yml`
and `minio.Dockerfile` were lost from a later checkout (see FP-ISSUE-029), all
three were recreated in this canonical layout (image tags: pgvector/pgvector:pg16,
redis:7.4-alpine, MinIO source tag RELEASE.2025-10-15T17-29-55Z). The recreated
`foundation.py` adds `migrate` (applies all six feature revisions in chain
order), generates `frontend/.env.local` during `init`, and defaults model cache
paths to the developer's home directory. Compose resolution and the revision
chain are verified; the first full fresh-clone MinIO build is not.

Generated `.env`, certificates, virtual environments and downloaded dependencies
are local resources, not registered application code. Foundation readiness and
verification results are in the development guide and resolved FP-ISSUE-005;
existing feature readiness remains unchanged.

## Document Ingestion Placement — 2026-09-03

The user explicitly requested placement from both production output folders.
Source placement is complete; runtime integration remains `PENDING_VERIFICATION`.
The matching production manifests still contain open implementation and database
verification issues. This registry records provenance, not a new READY approval.
See [COMPLETED.md](COMPLETED.md) and [issue_missing.md](issue_missing.md).

Source paths below are relative to the workspace root; destinations are relative
to `final_project/`. All production originals were retained.

| Output source | Canonical final destination | Adaptation / role |
| :--- | :--- | :--- |
| `backend_production/workflows/04-output/document_ingestion.schemas.py` | `backend/app/document_ingestion/schemas.py` | Typed schemas; source unchanged. |
| `backend_production/workflows/04-output/document_ingestion.errors.py` | `backend/app/document_ingestion/errors.py` | Package-relative imports. |
| `backend_production/workflows/04-output/document_ingestion.settings.py` | `backend/app/document_ingestion/settings.py` | Runtime settings; source unchanged. |
| `backend_production/workflows/04-output/document_ingestion.validation.py` | `backend/app/document_ingestion/validation.py` | Package-relative imports. |
| `backend_production/workflows/04-output/document_ingestion.pipeline.py` | `backend/app/document_ingestion/pipeline.py` | Package-relative imports; pure policy only. |
| `backend_production/workflows/04-output/document_ingestion.storage.py` | `backend/app/document_ingestion/storage.py` | Package-relative imports; private S3 support. |
| `backend_production/workflows/04-output/document_ingestion.repository.py` | `backend/app/document_ingestion/repository.py` | Package-relative imports; interfaces only. |
| `backend_production/workflows/04-output/document_ingestion.service.py` | `backend/app/document_ingestion/service.py` | Package-relative imports; requires real adapters. |
| `backend_production/workflows/04-output/document_ingestion.routes.py` | `backend/app/document_ingestion/routes.py` | Package-relative imports; requires shared auth and rate limiting. |
| `backend_production/workflows/04-output/document_ingestion.dispatcher.py` | `backend/app/document_ingestion/dispatcher.py` | Package-relative imports; requires due-job repository and publisher. |
| `backend_production/workflows/04-output/document_ingestion/__init__.py` | `backend/app/document_ingestion/__init__.py` | Replaced build loader with an ordinary package initializer; modules now have normal filenames. |
| `backend_production/workflows/04-output/document-ingestion.requirements.txt` | `backend/pyproject.toml` | Merged all six runtime pins into valid project metadata, replacing the invalid `[]` placeholder. Other runtime dependencies remain pending. |
| `database_production/workflows/04-output/20260903_create_document_ingestion.sql` | `database/document_ingestion/migrations/20260903_create_document_ingestion.sql` | Unchanged; kept beside Alembic revision. |
| `database_production/workflows/04-output/20260903_0002_document_ingestion_migration.py` | `database/document_ingestion/migrations/20260903_0002_document_ingestion_migration.py` | Unchanged child of existing auth revision `20260901_0001`. |
| `database_production/workflows/04-output/seed-document-ingestion.sql` | `database/document_ingestion/seeds/seed-document-ingestion.sql` | Unchanged guarded seed transaction component. |
| `database_production/workflows/04-output/seed_document_ingestion.py` | `database/document_ingestion/seeds/seed_document_ingestion.py` | Unchanged; companion SQL and fixtures remain beside it. |
| `database_production/workflows/04-output/document_ingestion.fixtures.py` | `database/document_ingestion/seeds/generate_fixtures.py` | Renamed; content unchanged. Development support only. |
| `database_production/workflows/04-output/document_ingestion.db.test.py` | `database/document_ingestion/tests/test_document_ingestion.py` | Updated paths to local migrations, seeds, test environment and existing auth artifacts; preserved safety gates and test assertions. |
| `database_production/workflows/04-output/document_ingestion.alembic-env.py` | `database/document_ingestion/tests/alembic_env.py` | Renamed; unchanged test-only environment, not deployment configuration. |
| `database_production/workflows/04-output/pytest.ini` | `database/document_ingestion/pytest.ini` | Adapted discovery to tests and import path to seeds. |
| `database_production/workflows/04-output/document-ingestion.requirements.txt` | `database/document_ingestion/requirements-dev.txt` | Unchanged database verification pins, separate from backend runtime. |

### Database Fixture Resources

The output's `database_production/workflows/04-output/document-ingestion-fixtures/`
resources were copied unchanged to
`database/document_ingestion/seeds/document-ingestion-fixtures/`:
`manifest.json`, `synthetic-invoice.pdf`, `synthetic-order.png`,
`synthetic-packing.jpg`, and `synthetic-failed.pdf`. These are development
resources, not application code or customer documents.

No virtual environments, caches, logs, raw builds, or duplicate auth files were
added. The backend output contains no ingestion tests; none were imported from
builds. The database test files were placed but not executed.

## Known Integration Gaps

- The shared auth, ingestion and RAG ORM mappings are now present in their
  canonical backend feature packages, but upstream/final live catalog parity and
  transaction verification remain pending.
- The current authentication code still requires working database and current-user
  dependencies, valid ORM models, application startup wiring, and real tests.
- Document ingestion shares the pending model-verification and auth dependencies
  and still requires concrete repositories, worker/publisher/recovery wiring and live
  verification. See FP-ISSUE-001 through 004 and FP-ISSUE-006 in
  [issue_missing.md](issue_missing.md).

## Document Processing/RAG Placement — 2026-09-05

The user explicitly requested final-project placement from both production output
folders. Canonical source placement is complete. The production handoffs remain
`PENDING_VERIFICATION`, so this registry records integration and validation
evidence without claiming a fully wired or live-verified processor.

### Backend and ORM artifacts

| Output source | Canonical final destination | Adaptation / role |
| :--- | :--- | :--- |
| `backend_production/workflows/04-output/document_processing_rag.schemas.py` | `backend/app/document_processing_rag/schemas.py` | Normal filename and package-relative imports. |
| `backend_production/workflows/04-output/document_processing_rag.errors.py` | `backend/app/document_processing_rag/errors.py` | Normal filename; sanitized failure contracts. |
| `backend_production/workflows/04-output/document_processing_rag.settings.py` | `backend/app/document_processing_rag/settings.py` | Package-relative imports; immutable identity/settings contract. |
| `backend_production/workflows/04-output/document_processing_rag.parser.py` | `backend/app/document_processing_rag/parser.py` | Package-relative imports; parser protocol and OCR policy. |
| `backend_production/workflows/04-output/document_processing_rag.chunking.py` | `backend/app/document_processing_rag/chunking.py` | Package-relative imports; deterministic chunking. |
| `backend_production/workflows/04-output/document_processing_rag.embedding.py` | `backend/app/document_processing_rag/embedding.py` | Package-relative imports; provider response validation. |
| `backend_production/workflows/04-output/document_processing_rag.repository.py` | `backend/app/document_processing_rag/repository.py` | Package-relative imports; repository ports, not a concrete adapter. |
| `backend_production/workflows/04-output/document_processing_rag.retrieval.py` | `backend/app/document_processing_rag/retrieval.py` | Package-relative imports; bounded retrieval coordination. |
| `backend_production/workflows/04-output/document_processing_rag.extraction.py` | `backend/app/document_processing_rag/extraction.py` | Package-relative imports; strict extraction over an LLM port. |
| `backend_production/workflows/04-output/document_processing_rag.validation.py` | `backend/app/document_processing_rag/validation.py` | Package-relative imports; Decimal business rules. |
| `backend_production/workflows/04-output/document_processing_rag.confidence.py` | `backend/app/document_processing_rag/confidence.py` | Package-relative imports; evidence-first confidence. |
| `backend_production/workflows/04-output/document_processing_rag.service.py` | `backend/app/document_processing_rag/service.py` | Package-relative imports; technical-read service. |
| `backend_production/workflows/04-output/document_processing_rag.routes.py` | `backend/app/document_processing_rag/routes.py` | Package-relative imports; route factory still requires shared adapters. |
| `backend_production/workflows/04-output/document_processing_rag.orchestrator.py` | `backend/app/document_processing_rag/orchestrator.py` | Package-relative imports; fenced orchestration over ports. |
| `backend_production/workflows/04-output/document_processing_rag.tasks.py` | `backend/app/document_processing_rag/tasks.py` | Package-relative imports; logical task boundary, not Celery registration. |
| `backend_production/workflows/04-output/document_processing_rag/__init__.py` | `backend/app/document_processing_rag/__init__.py` | Replaced the dotted-file loader with a normal package initializer. |
| `backend_production/workflows/04-output/document-processing-rag.requirements.txt` | `backend/pyproject.toml` | Existing FastAPI/Pydantic pins retained; database-owned SQLAlchemy 2.0.52 and pgvector 0.5.0 added for integrated ORM models. |
| `database_production/workflows/04-output/models.py` | `backend/app/auth/models.py` | Canonical shared Base/auth mappings required by ingestion and RAG; source structure preserved. |
| `database_production/workflows/04-output/document_ingestion.models.py` | `backend/app/document_ingestion/models.py` | Canonical ingestion mappings; Base import adapted to the auth feature package. |
| `database_production/workflows/04-output/document_processing_rag.models.py` | `backend/app/document_processing_rag/models.py` | Canonical RAG/result mappings; Base import adapted to the auth feature package. |
| `backend_production/workflows/04-output/document_ingestion.schemas.py` | `backend/app/document_ingestion/schemas.py` | Synchronized terminal invoice result with a cross-feature package import. |
| `backend_production/workflows/04-output/document_ingestion.service.py` | `backend/app/document_ingestion/service.py` | Synchronized invoice-reader port and completed-invoice integrity check. |
| `backend_production/workflows/04-output/document_ingestion.settings.py` | `backend/app/document_ingestion/settings.py` | Synchronized shared 300-second lease/30-second heartbeat defaults. |

### Database artifacts

| Output source | Canonical final destination | Adaptation / role |
| :--- | :--- | :--- |
| `database_production/workflows/04-output/20260904_create_document_processing_rag.sql` | `database/document_processing_rag/migrations/20260904_create_document_processing_rag.sql` | Unchanged companion PostgreSQL/pgvector SQL. |
| `database_production/workflows/04-output/20260904_0003_document_processing_rag_migration.py` | `database/document_processing_rag/migrations/20260904_0003_document_processing_rag_migration.py` | Unchanged child of ingestion revision `20260903_0002`; kept beside companion SQL. |
| `database_production/workflows/04-output/document_processing_rag.fixtures.py` | `database/document_processing_rag/seeds/generate_fixtures.py` | Renamed deterministic database-only fixture generator. |
| `database_production/workflows/04-output/seed_document_processing_rag.py` | `database/document_processing_rag/seeds/seed_document_processing_rag.py` | Fixture path adapted to the canonical renamed generator. |
| `database_production/workflows/04-output/document_processing_rag.db.test.py` | `database/document_processing_rag/tests/test_document_processing_rag.py` | Adapted to canonical auth/ingestion/RAG models, migrations, seed and fixture paths. |
| `database_production/workflows/04-output/document-processing-rag.requirements.txt` | `database/document_processing_rag/requirements-dev.txt` | pgvector pin combined with the existing ingestion database verification toolchain. |

The database-only fixture manifest was placed at
`database/document_processing_rag/seeds/document-processing-rag-fixtures/manifest.json`.
The final `.env.example` now lists the required non-secret RAG identity settings.
No handoff manifest, virtual environment, cache, generated log, or customer data
was copied as application code.

Validation after placement:

- final backend editable dependency installation and `pip check` passed;
- all 17 final RAG backend Python files imported/parsed successfully;
- shared auth/ingestion/RAG metadata configured on one Base with all 11 tables;
- the 60 upstream RAG tests passed against the adapted final backend package;
- the adapted final database suite reported 6 offline passes and 6 live-only skips.

Live PostgreSQL/pgvector, concurrency, rollback, query-plan, private-storage,
Redis/Celery, parser/model/LLM, security, coverage, performance and held-out
AI-quality gates remain tracked in [issue_missing.md](issue_missing.md).

## Human Review/Audit Placement — 2026-09-06

The user explicitly requested final-project placement from the reviewed backend
and database production output folders. Canonical source placement is complete.
Both upstream handoffs remain `PENDING_VERIFICATION`, so this registry records
provenance and packaging adaptations without claiming a fully wired or live-
verified review service.

### Backend and ORM artifacts

| Output source | Canonical final destination | Adaptation / role |
| :--- | :--- | :--- |
| `backend_production/workflows/04-output/human_review_audit.schemas.py` | `backend/app/human_review_audit/schemas.py` | Normal filename; strict public/domain schemas. |
| `backend_production/workflows/04-output/human_review_audit.errors.py` | `backend/app/human_review_audit/errors.py` | Normal filename and package-relative schema import. |
| `backend_production/workflows/04-output/human_review_audit.diff.py` | `backend/app/human_review_audit/diff.py` | Normal filename and package-relative imports; canonical hashing/diffs. |
| `backend_production/workflows/04-output/human_review_audit.validation.py` | `backend/app/human_review_audit/validation.py` | Package-relative imports; exact Decimal BR-02/BR-03 behavior. |
| `backend_production/workflows/04-output/human_review_audit.repository.py` | `backend/app/human_review_audit/repository.py` | Package-relative imports; repository/source ports, not concrete adapters. |
| `backend_production/workflows/04-output/human_review_audit.service.py` | `backend/app/human_review_audit/service.py` | Package-relative imports; query/preview/command coordination. |
| `backend_production/workflows/04-output/human_review_audit.routes.py` | `backend/app/human_review_audit/routes.py` | Package-relative imports; route factory still requires shared adapters. |
| `backend_production/workflows/04-output/human_review_audit/__init__.py` | `backend/app/human_review_audit/__init__.py` | Replaced dotted-file loader with an ordinary package initializer. |
| `backend_production/workflows/04-output/human-review-audit.requirements.txt` | `backend/pyproject.toml` | Existing FastAPI/Pydantic runtime pins already satisfy this handoff; test-only pins were not added to runtime metadata. |
| `database_production/workflows/04-output/human_review_audit.models.py` | `backend/app/human_review_audit/models.py` | Canonical shared-Base mappings; predecessor imports adapted to final feature packages. |
| `database_production/workflows/04-output/document_ingestion.models.py` | `backend/app/document_ingestion/models.py` | Synchronized reviewed explicit `Document.uploader` foreign-key selection; shared Base import retained as package-relative. |

### Database artifacts

| Output source | Canonical final destination | Adaptation / role |
| :--- | :--- | :--- |
| `database_production/workflows/04-output/20260906_create_human_review_audit.sql` | `database/human_review_audit/migrations/20260906_create_human_review_audit.sql` | Unchanged companion PostgreSQL migration SQL. |
| `database_production/workflows/04-output/20260906_0004_human_review_audit_migration.py` | `database/human_review_audit/migrations/20260906_0004_human_review_audit_migration.py` | Unchanged Alembic child of RAG revision `20260904_0003`. |
| `database_production/workflows/04-output/human_review_audit.fixtures.py` | `database/human_review_audit/seeds/generate_fixtures.py` | Renamed deterministic database-only fixture generator; content unchanged. |
| `database_production/workflows/04-output/seed_human_review_audit.py` | `database/human_review_audit/seeds/seed_human_review_audit.py` | Fixture-module path adapted to the canonical renamed generator. |
| `database_production/workflows/04-output/human-review-audit-fixtures/manifest.json` | `database/human_review_audit/seeds/human-review-audit-fixtures/manifest.json` | Unchanged synthetic fixture scope/count/coverage manifest. |
| `database_production/workflows/04-output/human_review_audit.db.test.py` | `database/human_review_audit/tests/test_human_review_audit.py` | Rebased to canonical final migrations, backend models, seed, fixture and predecessor paths. |
| `database_production/workflows/04-output/human-review-audit.requirements.txt` | `database/human_review_audit/requirements-dev.txt` | Reuses the already pinned RAG/database verification toolchain; no new dependency. |

No production-room manifest, backend test file, virtual environment, cache, build
report, log, or generated artifact was registered as application code. The
database feature notes are at
[database/human_review_audit/README.md](database/human_review_audit/README.md).

Validation after placement:

- all 58 upstream human-review backend tests passed against the adapted final
  package;
- all eight backend feature modules and the ORM package imported successfully;
- auth, ingestion, RAG and review mappings configured on one Base with 16 tables;
- the adapted human-review database suite reported 8 offline passes and four
  live-only skips;
- the combined final ingestion/RAG/review database suite reported 22 offline
  passes and 74 live-only skips after using an isolated local test-temp path;
- the final backend virtual environment dependency check passed.

This paragraph records the original 2026-09-06 placement state. The later READY
synchronization below replaces the BR-03 migration/mapping and resolves
FP-ISSUE-008. The later runtime integration section records concrete final
repository and host composition.

## Five-Feature READY Synchronization — 2026-09-11

The database production room now reports every database issue resolved and all
five feature packages `READY`. Corrected RAG checkpoint and human-review BR-03
artifacts were synchronized into their existing canonical destinations. The
repaired auth service/router/test were synchronized into backend `04-output`
before retaining their existing final destinations, restoring truthful
source-to-destination provenance.

The backend production room still reports its combined output as
`PENDING_VERIFICATION`, but its concrete runtime, application host, worker runner,
and reconciler are now promoted and copied here. Wider release gates remain.

## Document Search/Governed Export Placement — 2026-09-11

### Backend and ORM artifacts

| Output source | Canonical final destination | Adaptation / role |
| :--- | :--- | :--- |
| `backend_production/workflows/04-output/document_search_export.schemas.py` | `backend/app/document_search_export/schemas.py` | Strict wire/domain models; normal filename and package-relative imports. |
| `backend_production/workflows/04-output/document_search_export.errors.py` | `backend/app/document_search_export/errors.py` | Stable public and worker errors; package-relative import. |
| `backend_production/workflows/04-output/document_search_export.settings.py` | `backend/app/document_search_export/settings.py` | Bounded Feature 5 settings contract. |
| `backend_production/workflows/04-output/document_search_export.repository.py` | `backend/app/document_search_export/repository.py` | Typed search/export/storage/queue ports. |
| `backend_production/workflows/04-output/document_search_export.search.py` | `backend/app/document_search_export/search.py` | Tenant/role-safe search coordination. |
| `backend_production/workflows/04-output/document_search_export.formatters.py` | `backend/app/document_search_export/formatters.py` | Deterministic CSV/XLSX/JSON/ZIP formatting. |
| `backend_production/workflows/04-output/document_search_export.storage.py` | `backend/app/document_search_export/storage.py` | Private-object key and artifact integrity guards. |
| `backend_production/workflows/04-output/document_search_export.export.py` | `backend/app/document_search_export/export.py` | Acceptance, idempotency, direct export and status/download services. |
| `backend_production/workflows/04-output/document_search_export.worker.py` | `backend/app/document_search_export/worker.py` | Fenced async export, retry, recovery and expiry coordination over ports. |
| `backend_production/workflows/04-output/document_search_export.routes.py` | `backend/app/document_search_export/routes.py` | FastAPI route factory requiring explicit auth, rate limit and service dependencies. |
| `backend_production/workflows/04-output/document_search_export.tasks.py` | `backend/app/document_search_export/tasks.py` | Logical export task callable; final Celery registration remains pending. |
| `backend_production/workflows/04-output/document_search_export/__init__.py` | `backend/app/document_search_export/__init__.py` | Replaced dotted-artifact loader with a normal package initializer. |
| `database_production/workflows/04-output/document_search_export.models.py` | `backend/app/document_search_export/models.py` | Shared-Base export job/membership mappings with final package imports. |
| `backend_production/workflows/04-output/document-search-export.requirements.txt` | `backend/pyproject.toml` | Required runtime pins were already present; no duplicate dependency file added. |

### Database artifacts

| Output source | Canonical final destination | Adaptation / role |
| :--- | :--- | :--- |
| `database_production/workflows/04-output/20260907_create_document_search_export.sql` | `database/document_search_export/migrations/20260907_create_document_search_export.sql` | Byte-identical core migration SQL. |
| `database_production/workflows/04-output/20260907_0005_document_search_export_migration.py` | `database/document_search_export/migrations/20260907_0005_document_search_export_migration.py` | Byte-identical Alembic child of human review. |
| `database_production/workflows/04-output/20260907_create_document_search_export_indexes.sql` | `database/document_search_export/migrations/20260907_create_document_search_export_indexes.sql` | Byte-identical concurrent-index SQL. |
| `database_production/workflows/04-output/20260907_0006_document_search_export_indexes_migration.py` | `database/document_search_export/migrations/20260907_0006_document_search_export_indexes_migration.py` | Byte-identical index revision. |
| `database_production/workflows/04-output/document_search_export.fixtures.py` | `database/document_search_export/seeds/generate_fixtures.py` | Renamed deterministic fixture generator. |
| `database_production/workflows/04-output/document-search-export-fixtures/manifest.json` | `database/document_search_export/seeds/document-search-export-fixtures/manifest.json` | Byte-identical fixture manifest. |
| `database_production/workflows/04-output/seed_document_search_export.py` | `database/document_search_export/seeds/seed_document_search_export.py` | Rebased to the canonical renamed fixture generator. |
| `database_production/workflows/04-output/document_search_export.db.test.py` | `database/document_search_export/tests/test_document_search_export.py` | Rebased to canonical migrations, seeds and backend models; corrected early seed import and concurrency fixture paths. |
| `database_production/workflows/04-output/document-search-export.requirements.txt` | `database/document_search_export/requirements-dev.txt` | Database verification pins only. |

Post-placement verification passed 312 ingestion/RAG/review/export contract tests
against the adapted final packages (including 68 Feature 5 tests), five final
auth tests, and shared mapper configuration with all 19 application tables. The guarded final
Feature 5 database suite then passed **15/15** against the explicitly authorized
`docusense_export_test_99b37996e0bf` target and left it restored at Alembic head
`20260907_0006`.

## Auth Login Frontend Integration — 2026-09-14 — DESIGN_FIXTURE

The reviewed `auth-login` Stage 4 package was selectively merged into the
canonical frontend after a three-way comparison against the integrated
foundation. All application-code overlaps still matched the foundation, so no
newer or unrelated final-project implementation was displaced. Placement is
complete; live-backend readiness remains pending.

Source handoff:
`frontend_production/workflows/04-output/auth-login/HANDOFF.md`.

### Integration configuration

| Verified output source | Canonical final destination | Adaptation / role |
| :--- | :--- | :--- |
| `frontend_production/workflows/04-output/auth-login/package.json` | `frontend/package.json` | Preserved the canonical `docusense-frontend` name and `check:toolchain`; added real-app auth E2E, fixture-backend, preserved-foundation E2E, and combined E2E scripts. No dependency or lockfile change was required. |
| `frontend_production/workflows/04-output/auth-login/.gitignore` | `frontend/.gitignore` | Preserved generated-artifact exclusions and added defense-in-depth exclusions for frontend-local environment files. |
| `frontend_production/workflows/04-output/auth-login/next.config.ts` | `frontend/next.config.ts` | Enabled typed routes now that `/login` and `/dashboard` exist. |
| `frontend_production/workflows/04-output/auth-login/playwright.config.ts` | `frontend/playwright.config.ts` | Auth browser suite against the real final app plus synthetic backend; constrained to `auth-login.spec.ts`. |
| `frontend_production/workflows/04-output/frontend-foundation-completion/playwright.config.ts` | `frontend/playwright.foundation.config.ts` | Retained as a separate foundation-fixture regression configuration, constrained to `foundation-shell.spec.ts`. |

### Routes, server boundary, and feature UI

| Verified output source | Canonical final destination | Adaptation / role |
| :--- | :--- | :--- |
| `frontend_production/workflows/04-output/auth-login/src/app/(public)/login/page.tsx` | `frontend/src/app/(public)/login/page.tsx` | Public request-dynamic Login route with valid-session redirect. |
| `frontend_production/workflows/04-output/auth-login/src/app/(authenticated)/layout.tsx` | `frontend/src/app/(authenticated)/layout.tsx` | Request-dynamic session protection and Dashboard breadcrumb. |
| `frontend_production/workflows/04-output/auth-login/src/app/api/session/login/route.ts` | `frontend/src/app/api/session/login/route.ts` | Stable error normalization, concrete company-field mapping, server-only bearer token, and bounded backend exchange. |
| `frontend_production/workflows/04-output/auth-login/src/app/globals.css` | `frontend/src/app/globals.css` | Merged verified Login, password-control, account-menu, and temporary Dashboard styles over unchanged foundation tokens. |
| `frontend_production/workflows/04-output/auth-login/src/features/auth-login/login-form.tsx` | `frontend/src/features/auth-login/login-form.tsx` | Accessible form state, validation, focus, duplicate prevention, and sanitized feedback. |
| `frontend_production/workflows/04-output/auth-login/src/features/auth-login/login-view.tsx` | `frontend/src/features/auth-login/login-view.tsx` | Approved Login hierarchy and safe query-state notices. |
| `frontend_production/workflows/04-output/auth-login/src/features/auth-login/password-field.tsx` | `frontend/src/features/auth-login/password-field.tsx` | Value-preserving password visibility control. |
| `frontend_production/workflows/04-output/auth-login/src/features/auth-login/session-client.ts` | `frontend/src/features/auth-login/session-client.ts` | Same-origin browser session adapter with a 20-second ceiling and no retry. |
| `frontend_production/workflows/04-output/auth-login/src/lib/auth/return-path.ts` | `frontend/src/lib/auth/return-path.ts` | Restricts post-login return paths to the currently released `/dashboard` route. |

### Shared shell adaptations

| Verified output source | Canonical final destination | Adaptation / role |
| :--- | :--- | :--- |
| `frontend_production/workflows/04-output/auth-login/src/components/shell/app-shell.tsx` | `frontend/src/components/shell/app-shell.tsx` | Hydration-ready authenticated shell state. |
| `frontend_production/workflows/04-output/auth-login/src/components/shell/global-sidebar.tsx` | `frontend/src/components/shell/global-sidebar.tsx` | Typed available-route links across desktop and mobile navigation. |
| `frontend_production/workflows/04-output/auth-login/src/components/shell/navigation.ts` | `frontend/src/components/shell/navigation.ts` | Dashboard-only released navigation for all approved roles. |
| `frontend_production/workflows/04-output/auth-login/src/components/shell/public-shell.tsx` | `frontend/src/components/shell/public-shell.tsx` | Login-oriented public shell composition. |
| `frontend_production/workflows/04-output/auth-login/src/components/shell/top-context-bar.tsx` | `frontend/src/components/shell/top-context-bar.tsx` | Organization/account context, session expiry, guarded local logout, and hidden unavailable notifications. |
| `frontend_production/workflows/04-output/auth-login/src/components/shell/wordmark.tsx` | `frontend/src/components/shell/wordmark.tsx` | Typed wordmark link to the released Dashboard route. |
| `frontend_production/workflows/04-output/auth-login/src/components/ui/feedback.tsx` | `frontend/src/components/ui/feedback.tsx` | Typed safe route-state action links. |

### Regression and browser fixtures

| Verified output source | Canonical final destination | Adaptation / role |
| :--- | :--- | :--- |
| `frontend_production/workflows/04-output/auth-login/src/test/app-shell.test.tsx` | `frontend/src/test/app-shell.test.tsx` | Foundation shell regression updated for Dashboard-only route availability. |
| `frontend_production/workflows/04-output/auth-login/src/test/auth-api.test.ts` | `frontend/src/test/auth-api.test.ts` | Session/proxy regression updated for the released return-path policy. |
| `frontend_production/workflows/04-output/auth-login/src/test/auth-login-form.test.tsx` | `frontend/src/test/auth-login-form.test.tsx` | Form validation, focus, pending, password, and error tests. |
| `frontend_production/workflows/04-output/auth-login/src/test/auth-login-route.test.ts` | `frontend/src/test/auth-login-route.test.ts` | Login route contract and sanitization tests. |
| `frontend_production/workflows/04-output/auth-login/src/test/auth-login-routing.test.tsx` | `frontend/src/test/auth-login-routing.test.tsx` | Login/Dashboard routing behavior tests. |
| `frontend_production/workflows/04-output/auth-login/src/test/auth-login-session.test.ts` | `frontend/src/test/auth-login-session.test.ts` | Browser session adapter timeout and error behavior tests. |
| `frontend_production/workflows/04-output/auth-login/src/test/auth-login-shell.test.tsx` | `frontend/src/test/auth-login-shell.test.tsx` | Navigation, account, expiry, and logout tests. |
| `frontend_production/workflows/04-output/auth-login/src/test/fixtures/auth-login.ts` | `frontend/src/test/fixtures/auth-login.ts` | Explicit synthetic auth identity and response fixtures. |
| `frontend_production/workflows/04-output/auth-login/e2e/auth-login.spec.ts` | `frontend/e2e/auth-login.spec.ts` | Responsive Login/session/Dashboard/logout browser regression. |
| `frontend_production/workflows/04-output/auth-login/e2e/fixture-backend.mjs` | `frontend/e2e/fixture-backend.mjs` | Test-only synthetic backend; not a production account or service. |

All 27 promoted Stage 4 application/test files are byte-identical to their
verified sources. Final-project verification passed typecheck, lint, **12 Vitest
files / 49 tests**, a Next.js 16.3.4 production build, one representative auth
browser journey, and one preserved foundation browser regression. The route
table now contains dynamic `/login` and `/dashboard` routes.

The integration remains `DESIGN_FIXTURE`: generated OpenAPI is now available,
but the auth adapter/fixture has not yet completed its expiry-field reconciliation;
the real backend does not provide authoritative `expires_in`, and live tenant/login
behavior was not exercised, and logout clears only the local frontend session
until a token-revocation contract is approved.

The documented loopback backend origin and one generated 256-bit signing secret
were added to the ignored local project environment and the frontend-local Next
environment. These local secret files are runtime resources and are not
registered as application code.

## Self-Service Tenant Signup — 2026-09-20 — CONTRACT_FIXTURE

First-pass self-service signup was added in-tree against the existing Stage 4
auth backend and the canonical frontend. No production-room handoff was
available, so the implementation follows the existing `auth-login` and public
landing patterns byte-for-byte rather than byte-identical promotion. The new
flow lets a visitor create a fresh tenant (`companies` row + first
`admin` user) and is signed in immediately by reusing the existing
`writeSession` pipeline.

### Backend additions

| Canonical final destination | Role |
| :--- | :--- |
| `backend/app/auth/service.py` | Added `SIGNUP_BUSINESS_TYPES = {importer, trading, logistics}` (subset of `chk_companies_business_type`), `_validate_signup_inputs` (length, regex, NFKC normalization, control-char guard), and `AuthService.signup_company_and_admin` that atomically inserts the company and the admin user and converts a unique-email collision into `AuthFailure("EMAIL_TAKEN", 409)`. |
| `backend/app/auth/routes.py` | Added `SignupRequest` Pydantic model with `extra="forbid"` (full_name 1–100, organization_name 1–255, business_type ∈ SIGNUP_BUSINESS_TYPES, country ISO 3166-1 alpha-2, email `EmailStr`, password 8–128, agree_to_terms bool) and `POST /api/v1/auth/signup` that returns the same envelope shape as `/login` (201 Created, access_token, expires_in, user, message). Maps `EMAIL_TAKEN` → 409, `VALIDATION_ERROR` → 400. Exported in `__all__`. |
| `backend/app/auth/routes.py`, `backend/app/auth/service.py` | The existing `AuthService.create_access_token` and `_raise_auth` helpers are reused unchanged. No new dependencies, no new ORM model, no new migration, no new table. |

### Frontend additions

| Canonical final destination | Role |
| :--- | :--- |
| `frontend/src/lib/api/proxy-policy.ts` | One-line addition: `{ method: "POST", path: /^\/api\/v1\/auth\/signup$/ }` allowlists the new backend route through the existing catch-all proxy. |
| `frontend/src/app/api/session/signup/route.ts` *(NEW)* | Same-origin server-side handler that posts to the backend, parses the response, and writes the session cookies via the existing `writeSession`. 8 KiB body cap, 15 s backend timeout, full set of sanitized error codes (`INVALID_REQUEST`, `EMAIL_TAKEN`, `VALIDATION_ERROR`, `RATE_LIMITED`, `AUTH_CONTRACT_INVALID`, `AUTH_SERVICE_UNAVAILABLE`, `AUTH_RESPONSE_INVALID`, `SESSION_UNAVAILABLE`, `INVALID_ORIGIN`). |
| `frontend/src/features/auth-signup/signup-client.ts` *(NEW)* | Browser fetch wrapper that posts to `/api/session/signup` with a 20 s ceiling and a 12-error `SignupError` class mirroring the `LoginError` shape. |
| `frontend/src/features/auth-signup/signup-form.tsx` *(NEW)* | Reducer-driven form with client-side validation for full name (1–100), organization name (1–255), business type (one of three), country (ISO alpha-2 from a 30-country dropdown), email (existing pattern), password (8–128 + letter + digit), confirm-password (matches), and terms checkbox (must be true). First-invalid-field focus, 20 s submission ceiling, abort-safe. |
| `frontend/src/features/auth-signup/signup-view.tsx` *(NEW)* | Card wrapper with the approved copy, `session-expired` notice support, and a footer link to `/login?returnTo=…`. |
| `frontend/src/app/(public)/signup/layout.tsx` *(NEW)* | Mirrors the existing `app/(public)/login/layout.tsx` — wraps with `PublicShell`. |
| `frontend/src/app/(public)/signup/page.tsx` *(NEW)* | Mirrors the existing `app/(public)/login/page.tsx` — server-side `readSession()` redirect to `returnTo` (default `/dashboard`), parses `reason=session-expired`, `dynamic = "force-dynamic"`. |

### Shared frontend adaptations

| Canonical final destination | Adaptation / role |
| :--- | :--- |
| `frontend/src/features/public-landing/landing-shell.tsx` | Header now pairs "Sign up" (secondary) with "Sign in" (primary) inside a new `.headerActions` flex wrapper. |
| `frontend/src/features/public-landing/public-landing-view.tsx` | Hero and final CTA each gain a paired "Sign in" + "Create account" button group; the existing `data-variant="primary"` "Sign in" copy is preserved. New `.finalCtaActions` wrapper mirrors `.heroActions`. |
| `frontend/src/features/public-landing/public-landing.module.css` | Added `.headerActions { display:flex; gap:12px }`, gave `.heroActions` `flex-wrap` + `gap:12px`, renamed `.finalCta > a` selector to `.finalCtaActions a`, and updated the `@media (max-width: 767px)` rule to match. |
| `frontend/src/features/auth-login/login-view.tsx` | Added "New to DocuSense? Create a workspace" footer link that round-trips `returnTo` to `/signup`. |
| `frontend/src/app/globals.css` | Added `.ds-signup-card`, `.ds-signup-heading`, `.ds-signup-form`, `.ds-signup-error-summary`, `.ds-signup-request-id`, `.ds-signup-security-note`, `.ds-signup-footer` rules and `.ds-login-footer` rule, plus the matching mobile breakpoint for `.ds-signup-card`. |

### Verification

- `npx tsc --noEmit -p tsconfig.json` exited **0** with all four `/signup` hrefs
  cast to `Route` (typed routes regenerate on next dev start).
- Backend `app.auth.routes.SignupRequest.model_json_schema()` reports exactly
  the seven required fields (`agree_to_terms`, `business_type`, `country`,
  `email`, `full_name`, `organization_name`, `password`).
- `AuthService.signup_company_and_admin` exists and `SIGNUP_BUSINESS_TYPES`
  exports `{importer, logistics, trading}`.
- No backend dependency, lockfile, environment, database artifact, ORM model,
  migration, queue, or worker file changed. The signup endpoint reuses
  `hash_password`, `create_access_token`, and the `_validate_signup_inputs`
  helper; the same `AuthFailure` codes and `_raise_auth` mapping are used.

### API readiness and known gaps

- **API readiness:** `CONTRACT_FIXTURE` — request shapes, response envelopes,
  error codes, and validator allowlists all line up with the backend and
  proxy policy. Real tenant-creation smoke tests, email-collision retries,
  multi-tenant isolation, RBAC propagation to operator/viewer accounts, manual
  responsive/keyboard/screen-reader evidence, and a representative configured-
  live journey with a fresh tenant are all still open.
- **Operator/viewer bootstrapping:** the new admin is created in the same
  INSERT as the company. There is **no UI** to invite additional operators or
  viewers into the same tenant yet — those roles still require SQL seeding
  (e.g. via `backend/scripts/reset_demo_passwords.py`). See
  [issue_missing.md](issue_missing.md#fp-issue-028--self-service-signup-live-contract-verification).
- **OpenAPI export:** the regenerated `docs/api/openapi.yaml` after a backend
  restart will now include `POST /api/v1/auth/signup`. No prior OpenAPI
  artifact was changed by this integration.

## Documents List, Upload, and Pipeline Monitor Frontend Integration — 2026-09-14 — DESIGN_FIXTURE

The reviewed `documents-list-upload-monitor` Stage 4 package was selectively
merged into the canonical frontend. Before placement, all 12 shared destinations
matched the previously verified Auth Login output and all 21 new destinations
were absent, so no newer or unrelated final-project implementation was displaced.

Source handoff:
`frontend_production/workflows/04-output/documents-list-upload-monitor/HANDOFF.md`.

### Routes and feature module

| Verified output source | Canonical final destination | Adaptation / role |
| :--- | :--- | :--- |
| `documents-list-upload-monitor/src/app/(authenticated)/documents/page.tsx` | `frontend/src/app/(authenticated)/documents/page.tsx` | Thin signed-session Documents route for admin/operator/viewer. |
| `documents-list-upload-monitor/src/app/(authenticated)/documents/upload/page.tsx` | `frontend/src/app/(authenticated)/documents/upload/page.tsx` | Thin Upload/Monitor route with server-side viewer denial. |
| `documents-list-upload-monitor/src/features/documents-list-upload-monitor/types.ts` | `frontend/src/features/documents-list-upload-monitor/types.ts` | Feature-scoped design-fixture wire and view types pending reviewed OpenAPI. |
| `documents-list-upload-monitor/src/features/documents-list-upload-monitor/capabilities.ts` | `frontend/src/features/documents-list-upload-monitor/capabilities.ts` | Canonical document types and the single inclusive 10 MiB client capability. |
| `documents-list-upload-monitor/src/features/documents-list-upload-monitor/list-query.ts` | `frontend/src/features/documents-list-upload-monitor/list-query.ts` | Exact URL allowlisting, normalization, defaults, serialization and paging. |
| `documents-list-upload-monitor/src/features/documents-list-upload-monitor/api.ts` | `frontend/src/features/documents-list-upload-monitor/api.ts` | Strict list/upload/status envelope and ID/path validation. |
| `documents-list-upload-monitor/src/features/documents-list-upload-monitor/upload-transport.ts` | `frontend/src/features/documents-list-upload-monitor/upload-transport.ts` | Same-origin XHR multipart transport with byte progress, abort and timeout. |
| `documents-list-upload-monitor/src/features/documents-list-upload-monitor/documents-view.tsx` | `frontend/src/features/documents-list-upload-monitor/documents-view.tsx` | URL/request ownership plus loading, refresh, error and empty orchestration. |
| `documents-list-upload-monitor/src/features/documents-list-upload-monitor/document-filter-form.tsx` | `frontend/src/features/documents-list-upload-monitor/document-filter-form.tsx` | Explicit Apply/Clear filter draft and ordered-date validation. |
| `documents-list-upload-monitor/src/features/documents-list-upload-monitor/document-collection.tsx` | `frontend/src/features/documents-list-upload-monitor/document-collection.tsx` | Responsive document table/cards, status, pagination and permitted Monitor action. |
| `documents-list-upload-monitor/src/features/documents-list-upload-monitor/upload-monitor-view.tsx` | `frontend/src/features/documents-list-upload-monitor/upload-monitor-view.tsx` | Composer/monitor route state and validated recovery query. |
| `documents-list-upload-monitor/src/features/documents-list-upload-monitor/upload-composer.tsx` | `frontend/src/features/documents-list-upload-monitor/upload-composer.tsx` | One-file form, explicit duplicate consent, safe error and cancellation states. |
| `documents-list-upload-monitor/src/features/documents-list-upload-monitor/file-drop-zone.tsx` | `frontend/src/features/documents-list-upload-monitor/file-drop-zone.tsx` | Accessible choose/drop/replace/clear file interaction. |
| `documents-list-upload-monitor/src/features/documents-list-upload-monitor/processing-monitor.tsx` | `frontend/src/features/documents-list-upload-monitor/processing-monitor.tsx` | Persisted job/document state, warnings, stale/offline and terminal presentation. |
| `documents-list-upload-monitor/src/features/documents-list-upload-monitor/processing-stage-rail.tsx` | `frontend/src/features/documents-list-upload-monitor/processing-stage-rail.tsx` | Exact five-stage horizontal/vertical semantic rail. |
| `documents-list-upload-monitor/src/features/documents-list-upload-monitor/use-document-monitor.ts` | `frontend/src/features/documents-list-upload-monitor/use-document-monitor.ts` | Non-overlapping polling, visibility/online pause, bounded backoff and terminal stop. |
| `documents-list-upload-monitor/src/features/documents-list-upload-monitor/documents-list-upload-monitor.module.css` | `frontend/src/features/documents-list-upload-monitor/documents-list-upload-monitor.module.css` | Token-based wide/tablet/mobile list, upload and monitor layouts. |

### Shared frontend adaptations

| Verified output source | Canonical final destination | Adaptation / role |
| :--- | :--- | :--- |
| `documents-list-upload-monitor/src/app/(authenticated)/layout.tsx` | `frontend/src/app/(authenticated)/layout.tsx` | Preserves validated protected destinations through a client redirect boundary while retaining fail-closed signed sessions. |
| `documents-list-upload-monitor/src/app/api/backend/[...path]/route.ts` | `frontend/src/app/api/backend/[...path]/route.ts` | Adds only `retry-after` to the safe response-header forwarding list. |
| `documents-list-upload-monitor/src/components/shell/app-shell.tsx` | `frontend/src/components/shell/app-shell.tsx` | Adds pathname-aware breadcrumbs without changing account/logout behavior. |
| `documents-list-upload-monitor/src/components/shell/navigation.ts` | `frontend/src/components/shell/navigation.ts` | Releases Documents for every role and Upload for admin/operator; retains deferred routes. |
| `documents-list-upload-monitor/src/components/shell/session-required-redirect.tsx` | `frontend/src/components/shell/session-required-redirect.tsx` | Sanitizes and preserves released return paths for signed-out protected navigation. |
| `documents-list-upload-monitor/src/components/ui/overlays.tsx` | `frontend/src/components/ui/overlays.tsx` | Adds optional Cancel/Confirm initial focus while retaining dialog focus return and pending dismissal guards. |
| `documents-list-upload-monitor/src/lib/api/client.ts` | `frontend/src/lib/api/client.ts` | Adds backward-compatible complete-envelope requests and shared payload error construction. |
| `documents-list-upload-monitor/src/lib/api/errors.ts` | `frontend/src/lib/api/errors.ts` | Adds bounded integer delta `Retry-After` metadata. |
| `documents-list-upload-monitor/src/lib/auth/return-path.ts` | `frontend/src/lib/auth/return-path.ts` | Releases and validates exact Documents/list and Upload/monitor return destinations. |

### Focused tests and synthetic fixtures

| Verified output source | Canonical final destination | Adaptation / role |
| :--- | :--- | :--- |
| `documents-list-upload-monitor/src/test/documents-core.test.ts` | `frontend/src/test/documents-core.test.ts` | Query, envelope, file, retry/backoff and return-path contract-critical coverage. |
| `documents-list-upload-monitor/src/test/documents-components.test.tsx` | `frontend/src/test/documents-components.test.tsx` | Viewer collection, exact stage rail and duplicate-consent/focus coverage. |
| `documents-list-upload-monitor/src/test/fixtures/documents-list-upload-monitor.ts` | `frontend/src/test/fixtures/documents-list-upload-monitor.ts` | Synthetic design-fixture UUIDs, documents, uploads and processing status only. |
| `documents-list-upload-monitor/src/test/app-shell.test.tsx` | `frontend/src/test/app-shell.test.tsx` | Existing shell regression updated for Documents/Upload release. |
| `documents-list-upload-monitor/src/test/auth-api.test.ts` | `frontend/src/test/auth-api.test.ts` | Existing auth/API safety regression updated for released return paths. |
| `documents-list-upload-monitor/src/test/auth-login-routing.test.tsx` | `frontend/src/test/auth-login-routing.test.tsx` | Existing login routing expectations updated for released document routes. |
| `documents-list-upload-monitor/src/test/auth-login-shell.test.tsx` | `frontend/src/test/auth-login-shell.test.tsx` | Existing Auth shell expectations updated for role-available navigation. |

All 33 promoted Stage 4 files are byte-identical to their verified sources.
After placement, a SHA-256 comparison across all 99 comparable Stage 3 source,
configuration and test files found **0 missing and 0 changed files** in the final
frontend. Because the final tree exactly matches the already successful build,
the user-approved integration reused Stage 3 evidence instead of rerunning the
same commands: TypeScript passed, ESLint passed, **14 Vitest files / 62 tests**
passed, and the Next.js 16.3.4 production build exposed dynamic `/documents` and
`/documents/upload` routes.

No dependency, lockfile, environment, backend, database, storage, queue or worker
file changed during that frontend placement. The integration remains
`DESIGN_FIXTURE`: OpenAPI is now published, but the Feature 10 adapters/fixtures
still require an explicit schema reconciliation and live envelope/header/auth/
RBAC/storage/processing verification before a contract-fixture or live readiness
claim. Responsive browser screenshots and
manual screen-reader/zoom/high-contrast checks also remain open.

## Frontend Foundation Integration — 2026-09-14

The verified `frontend-foundation-completion` Stage 4 package was selectively
merged into the canonical frontend. The target previously contained only the
initial package manifest, lockfile, and generated dependencies, so no existing
page or component implementation was displaced. API readiness remains
`DESIGN_FIXTURE`; this integration does not claim that live backend workflows or
feature pages are complete.

Source handoff:
`frontend_production/workflows/04-output/frontend-foundation-completion/HANDOFF.md`.

### Toolchain and configuration

| Verified output source | Canonical final destination | Adaptation / role |
| :--- | :--- | :--- |
| `frontend-foundation-completion/package.json` | `frontend/package.json` | Preserved the canonical `docusense-frontend` name and existing `check:toolchain`; merged verified scripts and pinned dependencies. |
| `frontend-foundation-completion/package-lock.json` | `frontend/package-lock.json` | Preserved the canonical package name; dependency graph otherwise matches the verified output. |
| `frontend-foundation-completion/.gitignore` | `frontend/.gitignore` | Excludes Node, Next, coverage and browser-test generated artifacts. |
| `frontend-foundation-completion/next.config.ts` | `frontend/next.config.ts` | Shared Next.js configuration; typed routes remain disabled until domain pages exist. |
| `frontend-foundation-completion/tsconfig.json` | `frontend/tsconfig.json` | Strict TypeScript, `@/*` alias, and test exclusions. |
| `frontend-foundation-completion/postcss.config.mjs` | `frontend/postcss.config.mjs` | Tailwind CSS PostCSS integration. |
| `frontend-foundation-completion/eslint.config.mjs` | `frontend/eslint.config.mjs` | Next.js/TypeScript lint configuration and generated-artifact exclusions. |
| `frontend-foundation-completion/vitest.config.mts` | `frontend/vitest.config.mts` | Component/unit test environment. |
| `frontend-foundation-completion/playwright.config.ts` | `frontend/playwright.config.ts` | Responsive browser test configuration using a test-only Next fixture app. |
| Stage 4 server-only configuration requirements | `.env.example` | Added `BACKEND_API_ORIGIN` and `FRONTEND_SESSION_SIGNING_SECRET` placeholders; no actual secret was written. |

### Application root and server boundary

| Verified output source | Canonical final destination | Adaptation / role |
| :--- | :--- | :--- |
| `frontend-foundation-completion/src/app/layout.tsx` | `frontend/src/app/layout.tsx` | Root metadata, document language and global stylesheet. |
| `frontend-foundation-completion/src/app/globals.css` | `frontend/src/app/globals.css` | Approved semantic dark tokens, scratched-metal atmosphere, responsive shell and component styling. |
| `frontend-foundation-completion/src/app/loading.tsx` | `frontend/src/app/loading.tsx` | Safe root loading state. |
| `frontend-foundation-completion/src/app/error.tsx` | `frontend/src/app/error.tsx` | Safe client error boundary. |
| `frontend-foundation-completion/src/app/not-found.tsx` | `frontend/src/app/not-found.tsx` | Shared not-found state. |
| `frontend-foundation-completion/src/app/(public)/layout.tsx` | `frontend/src/app/(public)/layout.tsx` | Public shell for the later Login page and other unauthenticated routes. |
| `frontend-foundation-completion/src/app/(authenticated)/layout.tsx` | `frontend/src/app/(authenticated)/layout.tsx` | Fail-closed session check and authenticated application shell. |
| `frontend-foundation-completion/src/app/api/session/login/route.ts` | `frontend/src/app/api/session/login/route.ts` | Same-origin server-side credential exchange and signed HttpOnly session creation. |
| `frontend-foundation-completion/src/app/api/session/logout/route.ts` | `frontend/src/app/api/session/logout/route.ts` | Same-origin local session-cookie invalidation. |
| `frontend-foundation-completion/src/app/api/backend/[...path]/route.ts` | `frontend/src/app/api/backend/[...path]/route.ts` | Authenticated, allowlisted, bounded same-origin proxy for 16 approved backend operations. |

### Shared UI and shell

| Verified output source | Canonical final destination | Adaptation / role |
| :--- | :--- | :--- |
| `frontend-foundation-completion/src/components/ui/button.tsx` | `frontend/src/components/ui/button.tsx` | Button and icon-button variants. |
| `frontend-foundation-completion/src/components/ui/fields.tsx` | `frontend/src/components/ui/fields.tsx` | Text, select, checkbox and form-message controls. |
| `frontend-foundation-completion/src/components/ui/feedback.tsx` | `frontend/src/components/ui/feedback.tsx` | Badges, document statuses, alerts, skeletons, empty and route states. |
| `frontend-foundation-completion/src/components/ui/overlays.tsx` | `frontend/src/components/ui/overlays.tsx` | Dialog, drawer and tooltip with focus handling. |
| `frontend-foundation-completion/src/components/ui/page-header.tsx` | `frontend/src/components/ui/page-header.tsx` | Shared page title/description/action composition. |
| `frontend-foundation-completion/src/components/ui/table.tsx` | `frontend/src/components/ui/table.tsx` | Ready/loading/empty/error table frame and complete pagination. |
| `frontend-foundation-completion/src/components/ui/tabs.tsx` | `frontend/src/components/ui/tabs.tsx` | Keyboard-operable manual-activation tabs. |
| `frontend-foundation-completion/src/components/ui/toast.tsx` | `frontend/src/components/ui/toast.tsx` | Polite dismissible feedback region. |
| `frontend-foundation-completion/src/components/ui/index.ts` | `frontend/src/components/ui/index.ts` | Canonical UI public exports. |
| `frontend-foundation-completion/src/components/shell/app-shell.tsx` | `frontend/src/components/shell/app-shell.tsx` | Responsive authenticated shell composition. |
| `frontend-foundation-completion/src/components/shell/global-sidebar.tsx` | `frontend/src/components/shell/global-sidebar.tsx` | Desktop navigation and narrow-screen drawer. |
| `frontend-foundation-completion/src/components/shell/navigation.ts` | `frontend/src/components/shell/navigation.ts` | Typed, role-filtered global navigation model. |
| `frontend-foundation-completion/src/components/shell/public-shell.tsx` | `frontend/src/components/shell/public-shell.tsx` | Centered unauthenticated shell. |
| `frontend-foundation-completion/src/components/shell/skip-link.tsx` | `frontend/src/components/shell/skip-link.tsx` | Keyboard skip navigation. |
| `frontend-foundation-completion/src/components/shell/top-context-bar.tsx` | `frontend/src/components/shell/top-context-bar.tsx` | Breadcrumb, organization and account context. |
| `frontend-foundation-completion/src/components/shell/wordmark.tsx` | `frontend/src/components/shell/wordmark.tsx` | Balanced temporary DocuSense wordmark without a dedicated logo asset. |
| `frontend-foundation-completion/src/components/shell/index.ts` | `frontend/src/components/shell/index.ts` | Canonical shell public exports. |

### Shared client, session, tests and fixtures

| Verified output source | Canonical final destination | Adaptation / role |
| :--- | :--- | :--- |
| `frontend-foundation-completion/src/lib/api/client.ts` | `frontend/src/lib/api/client.ts` | Shared JSON/FormData API client and response-envelope handling. |
| `frontend-foundation-completion/src/lib/api/errors.ts` | `frontend/src/lib/api/errors.ts` | Sanitized normalized frontend error model. |
| `frontend-foundation-completion/src/lib/api/proxy-policy.ts` | `frontend/src/lib/api/proxy-policy.ts` | Exact method/path allowlist; API-key creation is intentionally excluded. |
| `frontend-foundation-completion/src/lib/auth/session.ts` | `frontend/src/lib/auth/session.ts` | Server-only signed profile and opaque backend token cookies. |
| `frontend-foundation-completion/src/lib/auth/session-types.ts` | `frontend/src/lib/auth/session-types.ts` | Minimal session and role types. |
| `frontend-foundation-completion/src/lib/auth/return-path.ts` | `frontend/src/lib/auth/return-path.ts` | Safe same-origin return-path validation. |
| `frontend-foundation-completion/src/lib/auth/request-security.ts` | `frontend/src/lib/auth/request-security.ts` | Same-origin mutation-request validation. |
| `frontend-foundation-completion/src/lib/formatting/format.ts` | `frontend/src/lib/formatting/format.ts` | Presentation-only shared formatters. |
| `frontend-foundation-completion/src/test/` | `frontend/src/test/` | Seven unit/component test files, setup, and explicitly synthetic `DESIGN_FIXTURE` data. |
| `frontend-foundation-completion/e2e/` | `frontend/e2e/` | Browser suite plus isolated test-only Next app; no preview route exists in the production `src/app` tree. |

Integrated verification:

- clean `npm ci` passed and installed 465 packages from the lockfile;
- `npm run check` passed TypeScript, ESLint, 7 test files / 26 tests and
  the Next.js 16.3.4 production build;
- the production route table contains only `/_not-found`, the two session routes
  and the allowlisted backend proxy—no preview/product feature route was added;
- `npm run test:e2e` passed 16 browser checks at 390, 768, 1366, 1440 and
  1920px; four non-390 drawer-only cases were skipped intentionally.

Live API behavior, OpenAPI-to-frontend reconciliation, screen-reader/200% zoom checks,
feature-owned pages, permanent branding and runtime environment values remain
open. API-key creation remains explicitly deferred.
