# Local foundation setup

The foundation plan is **Phase 0 of the existing
[serial master plan](../../../planning_room/drafts/master-plan/docusense-serial-project-masterplan.md)**.
This guide owns operational instructions and evidence. It does not replace the plan.

## User-dependent prerequisites

| When | Required action | Verification |
| :--- | :--- | :--- |
| Before Python setup | Install/use Python 3.11+; 3.12 is the tested baseline. No global package installation. | The project virtual environment reports Python 3.11+. |
| Before services | Install Docker Desktop if missing, enable its Linux-container backend, open it and wait for the engine. Complete any installation/virtualization prompts it presents. | `docker info --format '{{.OSType}}'` prints `linux`. |
| First setup | Allow package/image downloads and MinIO source compilation. The initial build takes substantially longer than later starts. | Dependency installs and `foundation.py up` exit successfully. |
| Before downloads/builds | Keep free space on Windows' system drive and Docker's disk-storage drive; free space or relocate Docker storage if needed. | No low-space/write errors; startup checks pass. The helper rejects a Windows system drive below 1 GiB free; this is a guard, not a build-size estimate. |
| Before frontend development | Install Node.js 20.9+ and npm; this checkout uses Node 22 and npm 10.9.2. | `npm run check:toolchain` succeeds. |
| Before database acceptance tests | Use a fresh disposable database, confirm no consumers, and use its explicit test settings. | Existing test guards accept its loopback name and empty database. |
| Before Phase 6 | Follow the future approved parser/embedding/LLM plan for exact model/revision, hardware, downloads, cache, accounts/keys or license steps. | Model loading and provider checks defined by that plan pass. |

No Hugging Face download, GPU, cloud account or LLM key is required for Phase 0,
authentication, or upload acceptance. The local setup generates development secrets.
Application users will not need these developer setup steps.

## First setup on Windows

Run from `final_project/`. Use a Python 3.11+ executable in the first command;
if `python --version` reports an older installation, use the full path to the
supported interpreter. Activation is optional with these explicit commands.

```powershell
python -m venv backend/.venv
.\backend\.venv\Scripts\python.exe -m pip install -c backend/requirements-foundation-lock.txt -e './backend[foundation]'
.\backend\.venv\Scripts\python.exe infrastructure/foundation.py init
.\backend\.venv\Scripts\python.exe infrastructure/foundation.py up
npm.cmd --prefix frontend ci
npm.cmd --prefix frontend run check:toolchain
```

The dependency snapshot was resolved on Windows/Python 3.12; changes for another
platform must be checked and recorded. `pyproject.toml` is the direct dependency
definition; the constraints file pins its resolved foundation environment.

On Linux/macOS, use a supported `python3` for creation and replace the virtual
environment executable with `backend/.venv/bin/python`; use `npm` instead of
`npm.cmd`. These platforms need their own verification evidence.

`init` creates ignored `.env` and `infrastructure/local/certs/` files with random
credentials, a development encryption key and a one-year self-signed TLS
certificate. A repeated init preserves them; partial existing setup produces an
error instead of silently rotating keys. Preserve `.env` with the MinIO volume:
objects encrypted under its key need that same key after restart.

The certificate is trusted explicitly by the SDK/checker through `AWS_CA_BUNDLE`;
setup does not modify the operating system trust store. Optional browser access
to the local MinIO console may require you to trust this particular development
certificate after checking it. Never disable SDK certificate verification.

`up` builds/starts only this Compose project, waits for healthy services, creates
the bucket if absent, and performs authenticated service checks. All published
ports bind to loopback. Database, Redis and object contents persist in named volumes.

| Service | Host connection | Container connection for future worker wiring |
| :--- | :--- | :--- |
| PostgreSQL + pgvector | `127.0.0.1:55465` | `postgres:5432` |
| Redis | `127.0.0.1:56379` | `redis:6379` |
| MinIO S3 | `https://localhost:39500` | `https://minio:9000` |
| MinIO console | not published on the host | `minio:9001` |

Credentials and configurable ports are in `.env`. Keep `DATABASE_URL`, `REDIS_URL`
and `S3_ENDPOINT` consistent with any port changes. Local credentials have development
administrative privileges; production needs separate least-privilege identities.

## Daily startup, check and shutdown

Open Docker Desktop first, then from `final_project/`:

```powershell
.\backend\.venv\Scripts\python.exe infrastructure/foundation.py up
.\backend\.venv\Scripts\python.exe infrastructure/foundation.py check
.\backend\.venv\Scripts\python.exe infrastructure/foundation.py down
```

`down` preserves volumes and credentials. It never requests volume deletion.
`check` verifies authenticated SQL, an actual pgvector operation, Redis ping,
trusted HTTPS, private-bucket policy, AES256 encrypted object write/read/delete,
and denial of anonymous reads. It touches only one unique synthetic check object.
Failure exits nonzero and does not record READY. If a download times out, retry
`up`; cached layers are reused. If Docker permission is denied to an agent, allow
the check outside its sandbox rather than changing Docker's access controls.

The Compose file is under `infrastructure/`. For direct Docker commands, pass
both `--env-file .env` and `-f infrastructure/docker-compose.yml` from this folder.
Do not print resolved Compose configuration into shared logs: it includes secrets.

## Configuration and feature startup

The example file is documentation; it is not loaded automatically by feature code.
The helper explicitly loads `.env`, resolves certificate/cache paths against
`final_project/`, and puts the backend virtual environment first on PATH:

```powershell
.\backend\.venv\Scripts\python.exe infrastructure/foundation.py run -- python --version
```

Use the same wrapper for future approved application commands. `DATABASE_URL`
uses a PostgreSQL URI; the future SQLAlchemy integration must select its matching
driver explicitly. Worker containers must use the container addresses above and
mount the local CA certificate. Celery's documentation does not support native
Windows workers; use Linux containers/WSL when the actual worker is implemented.

Phase 0 prepares the Next.js/React/TypeScript/Tailwind dependencies and lockfile.
Application pages, Tailwind styling configuration, auth routing, `app.main`,
repositories and Celery workers remain their existing later-phase work. No dev
server or worker command is presented as runnable before those modules exist.

## Disposable database for the existing acceptance suite

```powershell
.\backend\.venv\Scripts\python.exe infrastructure/foundation.py test-db
```

Creates a unique empty loopback database named `docusense_ingestion_test_<suffix>`
and stores `INGESTION_TEST_DSN`, its matching acknowledgement, and the initial
no-consumer assertion in ignored `.env.test`. No feature migration, seed or test
is executed. It refuses to overwrite an existing `.env.test`. Preserve that
record until its database is intentionally retired; no automatic drop is provided.

After the feature owner is ready, install its declared verification requirements,
confirm no consumers and follow the [database feature notes](../../database/document_ingestion/README.md).
The wrapper can load test settings explicitly:

```powershell
.\backend\.venv\Scripts\python.exe infrastructure/foundation.py --test-env run -- python -m pytest -c database/document_ingestion/pytest.ini database/document_ingestion/tests
```

The above suite requires additional dependencies from its own `requirements-dev.txt`.
Creating a test database does not resolve missing ORM mappings or prove migrations
and concurrency behavior. Existing DB/BE/FP issue IDs remain open until verified.

## API envelopes and logging convention

The existing [API guidelines](../../../planning_room/docs/api-guidelines.md)
remain authoritative: `success`, `data`/`error`, `message`, `meta.request_id`,
`meta.timestamp`, and pagination where applicable. Do not introduce another envelope.

Runtime modules must emit one JSON log event per line with UTC `timestamp`,
`level`, `service`, `event`, `request_id`, and `tenant_id` (null before verified
authentication). Obtain tenant identity from authenticated context. Add `job_id`
and `document_id` for worker events. Never log passwords, JWT/API keys, connection
strings, signed URLs, raw document content, or full environment configuration.
Actual request middleware/logging integration belongs to backend foundation work.

## Verification record — 2026-09-03

**Storage follow-up:** The user authorized moving Docker disk storage to F:.
Docker is now using `F:\DockerDesktop\disk\docker_data.vhdx`, confirmed by the
active file handle, working Linux engine and preserved images. The old C: disk
was removed only after verifying its SHA-256 against the preserved copy at
`F:\DockerDesktop\DockerDesktopWSL\disk\docker_data.vhdx`. That copy is a migration
backup, not the active disk. Settings backup and migration record are also under
`F:\DockerDesktop`. About 8.45 GiB became available on C: after removal.
The MinIO build and full foundation verification subsequently passed on F:.

- Backend virtual environment created with Python 3.12.13; declared foundation
  extra installed; `pip check` passed; dependency constraints captured.
- Repeat initialization retained secrets and certificates; Python syntax check passed.
- The existing ingestion `StorageSettings` and `TimingSettings` accepted the
  generated configuration through the environment wrapper. Its Windows executable
  resolution was corrected to use the backend virtual environment explicitly.
- Frontend dependency installation completed with zero audit findings.
- `npm run check:toolchain` passed: Next.js 16.3.4 and TypeScript 5.9.3.
- Docker Desktop was started and reported its Linux engine. PostgreSQL and Redis
  images downloaded successfully (Redis needed a retry after a registry timeout).
- **Resolved initial failure:** MinIO source build reported read-only filesystem and I/O errors;
  the host C: drive reported **0 bytes free**. The build was interrupted. No
  successful live verification was claimed at that time. See FP-ISSUE-005.
- **Final result: Phase 0 READY.** MinIO built from the pinned source release;
  Compose reported PostgreSQL, Redis and MinIO healthy. Authenticated SQL and
  pgvector cosine-distance checks, authenticated Redis ping, trusted HTTPS,
  private bucket, AES256 object write/read/delete and anonymous-read denial passed.
- **2026-09-12 local port update:** Windows reserved the former MinIO ports
  59000/59001. The loopback bindings moved to 59100/59101 with the existing
  credentials and named volume preserved; the complete foundation check passed.
- **2026-09-19 local port update:** The high loopback range (≈49000–65535) is
  reserved by Docker Desktop on this host; bind() returns EPERM even with no
  listener. Loopback ports in the 38000–48000 range bind successfully. The
  MinIO S3 mapping was moved to `127.0.0.1:39500:9000`, the MinIO console port
  is no longer published (unused by application code), and `foundation.py up`
  was narrowed to start only the `postgres`, `redis` and `minio` services so
  the backend image is not built or started in Docker — the local backend is
  run from `backend/.venv`. All `.env`/`docker-compose.yml`/`.env.example`
  defaults now match. Complete foundation check passed.
- **Disposable database verified:** `docusense_ingestion_test_99b37996e0bf`, loopback
  connection, matching acknowledgement, no public tables and no other consumers.
  Credentials are in ignored `.env.test`. No feature migrations/seeds/tests ran.
- **Pending user action for this machine's Phase 0:** None. Docker must be running
  for daily work. Provider/model downloads and credentials remain later Phase 6 work.
- Existing auth/ingestion feature runtime remains `PENDING_VERIFICATION`.

## Upstream references

- [Docker Compose service health and startup](https://docs.docker.com/reference/compose-file/services/)
- [pgvector Docker and extension instructions](https://github.com/pgvector/pgvector)
- [MinIO final security release and source-build instructions](https://github.com/minio/minio/releases/tag/RELEASE.2025-10-15T17-29-55Z)
- [MinIO static development KMS configuration](https://github.com/minio/minio/blob/master/docs/kms/IAM.md)
- [Celery Windows support](https://docs.celeryq.dev/en/main/faq.html#does-celery-support-windows)

MinIO's community repository is archived. This setup follows the approved local
MinIO architecture and builds its final security release; production storage
selection and maintenance remain part of the production-hardening phase.
