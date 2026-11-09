# DocuSense AI

DocuSense AI is a multi-tenant document intelligence application: tenants upload
commercial-invoice style documents, a FastAPI + Celery processing pipeline
parses, chunks, embeds and extracts evidence using RAG, and everything is
validated under a human review/audit workflow with governed exports.

```text
Next.js (React/TypeScript/Tailwind)  →  FastAPI (Pydantic/SQLAlchemy/Alembic)
                                             ↓
                            Celery workers (Redis broker)
                                             ↓
                       PostgreSQL + pgvector · MinIO (S3 API)
                                             ↓
                 Docling parsing · local embeddings · Groq LLM
```

## Status

All five reviewed feature packages (authentication/tenancy, document ingestion,
document processing/RAG, human review/audit, document search/governed export)
are integrated in canonical feature-first paths, with one shared SQLAlchemy
registry of 19 tables and the runtime entry points `app.main:app`,
`app.worker:celery_app`, and `python -m app.reconciler`.

The combined production handoff remains **`PENDING_VERIFICATION`** until the
remaining held-out quality, security/performance and safe object-orphan gates
are complete, and Feature 12 (Human Review Studio) frontend is integrated in
`CONTRACT_FIXTURE` mode. A fresh machine clone has **not** been
end-to-end verified yet; see [open issues](issue_missing.md) for remaining
work, including the recreated local-infrastructure helper below.

## Prerequisites

| Tool | Version | Why |
| :--- | :--- | :--- |
| Git | any recent | Clone this repository. |
| Python | 3.11+ (3.12 is the tested baseline) | Backend + local foundation helper. |
| Docker Desktop | current | Runs PostgreSQL + pgvector, Redis, and MinIO. Enable Linux containers, open it, and wait for the engine before `up`. |
| Node.js + npm | 20.9+ (Node 22 / npm 10.9.2 was the tested baseline) | Frontend. |

You also need **your own** [Groq](https://console.groq.com) API key (the backend
validates `LLM_API_KEY` at startup) and, on **first document upload**, an
internet connection so the pinned local embedding model and Docling/EasyOCR
artifacts are downloaded into personal model-cache directories. No cloud
account is required for anything else.

> This repository is the `final_project/` codebase only. A few deep-dive docs
> reference sibling `planning_room/` files in the original multi-room
> workspace; those files are not part of this repository and those relative
> links will not resolve after cloning.

## What lives where

| Path | Contents |
| :--- | :--- |
| `backend/` | FastAPI application (`app/`, one package per feature), runtime adapters in `app/backend_runtime/`, feature tests, `pyproject.toml` + pinned lock file. Runs only inside `backend/.venv`. |
| `frontend/` | Canonical Next.js app (`src/app`, features under `src/features/`), Vitest/Playwright tests. |
| `database/` | Per-feature Alembic revisions (`.py` + companion `.sql`), query files, and optional demo seeds for tests. |
| `docs/` | `development/` (this setup, deeper detail), `api/openapi.yaml`, architecture notes. |
| `infrastructure/` | `docker-compose.yml` (local services), `minio/Dockerfile` (pinned source-built MinIO image), `foundation.py` (init/up/check/down/migrate/test-db/run), `postgres-init.sql`, local certs (generated, git-ignored). |
| `.env.example` | Documents every expected variable; `foundation.py init` writes the real `.env`. |

Neither lane ever crosses: the frontend never touches PostgreSQL and holds no
database credentials — it only talks to FastAPI through server-only gateway
routes in `src/app/api/backend/[...path]/route.ts`.

## First-time setup

Run everything from the repository root. Windows examples use PowerShell; a
macOS/Linux translation is given below the Windows block.

```powershell
# 1. Clone
git clone <your-repo-url> docusense
cd docusense

# 2. Backend virtual environment (Python 3.11+; 3.12 tested)
python -m venv backend/.venv
.\backend\.venv\Scripts\python.exe -m pip install -c backend/requirements-foundation-lock.txt -e "./backend[foundation]"

# 3. Local credentials, TLS certificate and frontend env generation
.\backend\.venv\Scripts\python.exe infrastructure/foundation.py init

# 4. Start PostgreSQL + pgvector, Redis, MinIO (builds the pinned MinIO image on
#    first run — this takes several minutes and needs ~2 GB of downloads)
.\backend\.venv\Scripts\python.exe infrastructure/foundation.py up

# 5. Create the 19-table schema from the six Alembic feature revisions
.\backend\.venv\Scripts\python.exe infrastructure/foundation.py migrate

# 6. Backend dependencies' sanity check
.\backend\.venv\Scripts\python.exe infrastructure/foundation.py check

# 7. Frontend dependencies and toolchain
npm --prefix frontend ci
npm --prefix frontend run check:toolchain
```

On Linux/macOS replace each venv path invocation with
`backend/.venv/bin/python` and use `npm` (no `.cmd`); those platforms have not
been verified yet, so treat them as experimental paths and record what you had
to adjust.

`init` generates **ignored** files with random per-machine secrets:

- `.env` — all backend/service configuration (database, Redis, MinIO TLS + a
  long-term AES256 key, JWT secret, RAG identities).
- `frontend/.env.local` — server-only `BACKEND_API_ORIGIN`,
  `EXPORT_DOWNLOAD_ALLOWED_ORIGINS` and `FRONTEND_SESSION_SIGNING_SECRET`.
- `infrastructure/local/certs/` — one-year self-signed certificate the MinIO
  container trusts and every S3 SDK call pins through `AWS_CA_BUNDLE`.
- Model cache directories (`HF_HOME`, `DOCLING_ARTIFACTS_PATH`,
  `EASYOCR_MODULE_PATH`) under your home directory.

A repeated `init` preserves all of these. **Never commit any of them, and
preserve `.env`/certs together with the Docker volumes** — objects written AES256
encrypted can only be read under the same generated key (set `MINIO_KMS_SECRET_KEY`).

### Edit `.env` for you (one-time, per developer)

```ini
# Required before the backend will start: get your writable key at
# https://console.groq.com
LLM_API_KEY=gsk_your_personal_groq_key
```

If ports `55465`, `56379` or `39500` are taken on your machine, edit the
`*_PORT` values in `.env` and the URLs in `.env` / `frontend/.env.local` that
contain them, then rerun `foundation.py up` (first `down` if containers exist).

## Daily startup and shutdown

Open Docker Desktop first, then:

```powershell
.\backend\.venv\Scripts\python.exe infrastructure/foundation.py up
.\backend\.venv\Scripts\python.exe infrastructure/foundation.py check
```

`down` stops the trio and **preserves** all volumes and credentials;
`check` verifies authenticated SQL + an actual pgvector cosine operation,
Redis PING, trusted HTTPS, the private-bucket policy, an AES256 object
write/read/delete round-trip and denial of anonymous reads. On `up` failure
after a timeout, retry — Docker layer caches are reused.

## Running the application

After `up` and `migrate`, open this many (same venv in every terminal; extra
workers are optional):

```powershell
# Terminal 1 — FastAPI (Windows Psycopg loop-safe entry point)
cd backend
.\.venv\Scripts\python.exe run_server.py

# Terminal 2 — Celery worker
cd backend
.\.venv\Scripts\python.exe -m celery -A app.worker:celery_app worker -Q documents,exports --pool=solo

# Terminal 3 — durable reconciler
cd backend
.\.venv\Scripts\python.exe -m app.reconciler

# Terminal 4 — Next.js frontend
npm --prefix frontend run dev
```

Then use:

| Surface | URL |
| :--- | :--- |
| Web app | http://localhost:3000 |
| API health probes | http://127.0.0.1:8000/health/live, `/health/ready` |
| MinIO S3 API (TLS) | https://localhost:39500 |

First sign-in: use **`/signup`** to create a company + admin (posts to
`POST /api/v1/auth/signup`, then you're redirected to the workspace). Adding
operators/viewers into an existing tenant is still SQL-only today (no invite
UI) — see [issue_missing.md](issue_missing.md) FP-ISSUE-028.

First document upload triggers model downloads into the cache directories from
`.env`; it needs internet access and finishes asynchronously. The happy path is
upload → monitor → document detail/chunk inspector → human review → governed
export.

## Tests

Backend + database packages target a **fresh disposable database**:

```powershell
.\backend\.venv\Scripts\python.exe infrastructure/foundation.py test-db
```

Then follow the per-feature notes under `database/[feature]/README.md` for that
feature's verification requirements; frontend suites run with
`npm --prefix frontend run test`. Additional detail lives in
[docs/development/README.md](docs/development/README.md).

## Regen/replace pointers

- Regenerating `docs/api/openapi.yaml` after backend changes:
  `backend/scripts/export_openapi.py` (needs the runtime stack running).
- Reset forgotten local demo passwords: `backend/scripts/reset_demo_passwords.py`.
- Debugging helpers were left present as `backend/scripts/*.py`; they are not
  part of the verified runtime but illustrate the local diagnosis flow.

## Where to read next

- [docs/development/README.md](docs/development/README.md) — the detailed,
  evidence-logged foundation guide (compose services, cert trust, verification
  record, disposable DB policy, logging conventions).
- [registry.md](registry.md) — source-to-destination mapping of every verified
  handoff integration.
- [COMPLETED.md](COMPLETED.md) — placement record and scope.
- [issue_missing.md](issue_missing.md) — every remaining open item. Note in
  particular that `infrastructure/foundation.py` and
  `infrastructure/docker-compose.yml` were **regenerated on 2026-11-09** after
  being lost from the checkout; a fresh clone has not been verified end-to-end
  yet.
