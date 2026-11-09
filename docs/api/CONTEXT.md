# Final Project API Contract Status

## Authority

The actual FastAPI application is created by:

```text
final_project/backend/app/main.py
    → app = create_api()
```

FastAPI/Pydantic and the generated `/openapi.json` document are authoritative for
frontend HTTP request/response shapes. Planning Markdown supplies intended
behavior and business rules; a handwritten TypeScript contract is not required.

## Current status

`openapi.yaml` is a generated, reviewed OpenAPI 3.1 contract as of 2026-09-16.
It contains 18 paths and 91 component schemas and declares both bearer JWT and
`X-API-Key` authentication. Feature 11 detail, status, chunk, and extraction-
evidence operations include their supported security, query, success, and
relevant stable error response shapes. Feature 12 review preview/mutation/audit
operations declare their request bodies, action discriminator, optional
`Idempotency-Key`, audit query parameters, bearer security, success envelopes,
and stable error response shapes.

Feature 13 search/export operations declare the structured search and canonical
export request bodies, all direct-export compatibility queries, optional
`Idempotency-Key`, UUID path parameters, exact success statuses, binary stream
and signed-redirect download alternatives, privacy/integrity/retry headers,
bearer security and stable error envelopes.

The artifact is generated from exact `app.main:app` after the canonical document
detail role/state repair. It uses JSON syntax, which is valid YAML 1.2, to avoid
an undeclared YAML serialization dependency. Do not format or hand-edit it.

Verification recorded on 2026-09-16:

- focused Backend Production Stage 3 host/OpenAPI regression: 5 passed;
- focused integrated final backend composition regression: 5 passed;
- generator validation and byte-for-byte stale check: passed.

This publication enables OpenAPI-derived/checked frontend types and contract
fixtures. It does not by itself prove live endpoint behavior against configured
PostgreSQL, Redis, S3, model providers, or representative users/documents.

## Publish procedure

1. Change FastAPI/Pydantic/host source and its tests first.
2. From `final_project/backend`, run
   `.venv/Scripts/python.exe scripts/export_openapi.py` on Windows.
3. Run the same command with `--check` to validate required Feature 11, 12 and 13 surfaces
   and prove the checked-in bytes match fresh `app.main:app` generation.
4. Run the integrated backend tests and review the generated diff.
5. Record generation date, backend state, results, and any known live-only gates.
6. Check/generate frontend wire types from the reviewed schema.

Do not manually invent missing endpoints in the OpenAPI file. Fix the Pydantic or
router composition source and regenerate it.
