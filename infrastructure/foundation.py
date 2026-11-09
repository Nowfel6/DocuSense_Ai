"""DocuSense AI local development foundation helper.

Idempotent, explicit, and local-only. Commands (all run from final_project/):

    init       Generate .env + frontend/.env.local + local self-signed TLS certs.
    up         Build/start postgres, redis, minio; wait for healthy; provision bucket.
    check      Authenticated readiness checks (SQL + pgvector, Redis, MinIO TLS/KMS).
    down       Stop the services; named volumes are never deleted.
    migrate    Apply the six feature Alembic revisions to the local database.
    test-db    Provision a disposable, acknowledged acceptance-test database.
    run --     Run a command with .env values loaded into the process environment.

Security rules enforced here:
- Never print resolved Compose configuration, URLs with credentials, or secrets.
- Never commit .env, .env.test, frontend/.env.local, or infrastructure/local/.
- A repeated init preserves existing secrets and caches; incomplete setups raise
  an error instead of silently rotating keys, because the MinIO volume already
  holds AES256 objects tied to the generated key.
"""

from __future__ import annotations

import base64
import ipaddress
import json
import platform
import re
import secrets
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import NoReturn
from urllib.parse import urlparse

APP_NAME = "docusense-local"
PROJECT_DIR = Path(__file__).resolve().parents[1]
INFRA_DIR = PROJECT_DIR / "infrastructure"
ENV_FILE = PROJECT_DIR / ".env"
ENV_TEST_FILE = PROJECT_DIR / ".env.test"
FRONTEND_DIR = PROJECT_DIR / "frontend"
FRONTEND_ENV_FILE = FRONTEND_DIR / ".env.local"
CERT_DIR = INFRA_DIR / "local" / "certs"
CERT_FILE = CERT_DIR / "public.crt"
KEY_FILE = CERT_DIR / "private.key"
COMPOSE_FILE = INFRA_DIR / "docker-compose.yml"
COMPOSE_SERVICES = ("postgres", "redis", "minio")
EXPECTED_HEAD = "20260907_0006"
MIGRATION_FEATURES = (
    "auth",
    "document_ingestion",
    "document_processing_rag",
    "human_review_audit",
    "document_search_export",
)

REQUIRED_ENV_KEYS = (
    "POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_PORT",
    "DATABASE_URL", "REDIS_PASSWORD", "REDIS_PORT", "REDIS_URL",
    "S3_PORT", "S3_CONSOLE_PORT", "S3_ENDPOINT", "S3_BUCKET",
    "S3_ACCESS_KEY", "S3_SECRET_KEY", "S3_REGION", "S3_ENCRYPTION",
    "AWS_CA_BUNDLE", "MINIO_KMS_SECRET_KEY", "JWT_SECRET_KEY", "LOG_LEVEL",
    "DOCUSENSE_CORS_ORIGINS", "DOCUSENSE_TRUSTED_HOSTS",
    "DOCUSENSE_SUPPORTED_CURRENCIES",
    "BACKEND_API_ORIGIN", "FRONTEND_SESSION_SIGNING_SECRET",
    "EXPORT_DOWNLOAD_ALLOWED_ORIGINS",
    "EMBEDDING_PROVIDER", "EMBEDDING_MODEL", "EMBEDDING_REVISION",
    "EMBEDDING_DIMENSIONS", "HF_HOME", "DOCLING_ARTIFACTS_PATH",
    "EASYOCR_MODULE_PATH",
    "LLM_PROVIDER", "LLM_API_KEY",
    "RAG_PIPELINE_VERSION", "RAG_PARSER_VERSION", "RAG_OCR_POLICY_VERSION",
    "RAG_EMBEDDING_MODEL", "RAG_EMBEDDING_REVISION",
    "RAG_LLM_PROVIDER", "RAG_LLM_MODEL", "RAG_PROMPT_VERSION",
    "PROCESSING_AUTO_APPROVAL_ENABLED",
)

FRONTEND_ENV_KEYS = (
    "BACKEND_API_ORIGIN",
    "EXPORT_DOWNLOAD_ALLOWED_ORIGINS",
    "FRONTEND_SESSION_SIGNING_SECRET",
)

RV_RE = re.compile(r'^\s*revision\s*(?::[^=]+)?=\s*["\']([^"\']+)["\']', re.M)
DOWN_RE = re.compile(
    r'^\s*down_revision\s*(?::[^=]+)?=\s*(?:["\']([^"\']*)["\']|None\b)', re.M
)


def fail(message: str) -> NoReturn:
    print(f"foundation: ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def read_env(path: Path) -> dict[str, str]:
    from dotenv import dotenv_values

    return {k: v for k, v in dotenv_values(path).items() if v is not None}


def require_env() -> dict[str, str]:
    if not ENV_FILE.is_file():
        fail(".env is missing; run 'init' first (python infrastructure/foundation.py init)")
    env = read_env(ENV_FILE)
    missing = [k for k in REQUIRED_ENV_KEYS if not env.get(k)]
    if missing:
        # LLM_API_KEY is the one key the user must supply personally.
        missing_except_llm = [k for k in missing if k != "LLM_API_KEY"]
        if missing_except_llm:
            fail(
                f"{ENV_FILE.name} is incomplete; restore values for: "
                + ", ".join(missing_except_llm)
            )
    return env


# --------------------------------------------------------------------------
# init
# --------------------------------------------------------------------------


def generate_kms_secret_key() -> str:
    """Long-term built-in KMS key: <key-name>:<base64 of 32 random bytes>."""
    return "docusense-local:" + base64.b64encode(secrets.token_bytes(32)).decode("ascii")


def generate_certificates() -> None:
    """Idempotent one-year self-signed development certificate provision.

    The single certificate carries CA:TRUE (keyCertSign), serverAuth and SANs
    localhost, minio, 127.0.0.1, so it works as the MinIO server certificate and
    as the AWS_CA_BUNDLE trust anchor. It never touches the OS trust store.
    """
    if CERT_FILE.is_file() and KEY_FILE.is_file():
        print("foundation: existing development TLS certificate preserved")
        return
    if CERT_FILE.is_file() or KEY_FILE.is_file():
        fail(
            f"{CERT_DIR} is incomplete: both {CERT_FILE.name} and {KEY_FILE.name} "
            "must be present; restore the missing file before continuing"
        )
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    CERT_DIR.mkdir(parents=True, exist_ok=True)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.now(timezone.utc)
    subject = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "docusense-local-development")]
    )
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, key_cert_sign=True, crl_sign=False,
                content_commitment=False, key_encipherment=True,
                data_encipherment=False, key_agreement=False,
                encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName("localhost"),
                x509.DNSName("minio"),
                x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
            ]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    KEY_FILE.write_bytes(key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ))
    CERT_FILE.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    print("foundation: generated self-signed development TLS certificate (valid 1 year)")


def build_env_text() -> str:
    db_name = "docusense"
    db_user = "docusense"
    db_password = secrets.token_urlsafe(24)
    redis_password = secrets.token_urlsafe(24)
    s3_secret = secrets.token_urlsafe(32)
    jwt = secrets.token_hex(32)
    session = secrets.token_hex(32)
    kms = generate_kms_secret_key()
    db_port, redis_port, s3_port = 55465, 56379, 39500
    database_url = f"postgresql://{db_user}:{db_password}@127.0.0.1:{db_port}/{db_name}"
    redis_url = f"redis://:{redis_password}@127.0.0.1:{redis_port}/0"
    home = Path.home() / "DocuSenseModels"
    return f"""# Generated by infrastructure/foundation.py init on {datetime.now(timezone.utc).isoformat()}
# Development secrets; never commit this file. Preserve this file together with
# the Docker volumes: the MinIO AES256 decryption key must not change under
# existing objects.

POSTGRES_DB={db_name}
POSTGRES_USER={db_user}
POSTGRES_PASSWORD={db_password}
POSTGRES_PORT={db_port}
DATABASE_URL={database_url}
REDIS_PASSWORD={redis_password}
REDIS_PORT={redis_port}
REDIS_URL={redis_url}

# Private local MinIO with TLS and server-side encryption. Loopback ports in
# 38000-48000 avoid the range Docker Desktop reserves on Windows.
S3_PORT={s3_port}
S3_CONSOLE_PORT=39501
S3_ENDPOINT=https://localhost:{s3_port}
S3_BUCKET=docusense-documents
S3_ACCESS_KEY=docusense-{secrets.token_hex(8)}
S3_SECRET_KEY={s3_secret}
S3_REGION=us-east-1
S3_ENCRYPTION=AES256
AWS_CA_BUNDLE=infrastructure/local/certs/public.crt
MINIO_KMS_SECRET_KEY={kms}
JWT_SECRET_KEY={jwt}
LOG_LEVEL=INFO

DOCUSENSE_CORS_ORIGINS=["http://localhost:3000"]
DOCUSENSE_TRUSTED_HOSTS=["localhost","127.0.0.1","testserver"]
DOCUSENSE_SUPPORTED_CURRENCIES=["USD","EUR","BDT"]

# Frontend server-only session and FastAPI gateway configuration. Never expose
# either value through a NEXT_PUBLIC_ variable.
BACKEND_API_ORIGIN=http://127.0.0.1:8000
FRONTEND_SESSION_SIGNING_SECRET={session}
EXPORT_DOWNLOAD_ALLOWED_ORIGINS=https://localhost:{s3_port}

# RAG provider identities. Replace LLM_API_KEY with your own Groq API key
# (https://console.groq.com) before uploading documents for RAG extraction.
# Model cache directories are personal to each machine and created on first
# use; the first document parse/populate step needs internet access.
EMBEDDING_PROVIDER=local
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
EMBEDDING_REVISION=1110a243fdf4706b3f48f1d95db1a4f5529b4d41
EMBEDDING_DIMENSIONS=384
HF_HOME={home.as_posix()}/huggingface
DOCLING_ARTIFACTS_PATH={home.as_posix()}/docling
EASYOCR_MODULE_PATH={home.as_posix()}/docling/EasyOcr
LLM_PROVIDER=groq
LLM_API_KEY=
RAG_PIPELINE_VERSION=document-processing-rag-v1
RAG_PARSER_VERSION=docling-2.126.0
RAG_OCR_POLICY_VERSION=conditional-easyocr-en-v1
RAG_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
RAG_EMBEDDING_REVISION=1110a243fdf4706b3f48f1d95db1a4f5529b4d41
RAG_LLM_PROVIDER=groq
RAG_LLM_MODEL=openai/gpt-oss-20b
RAG_PROMPT_VERSION=commercial-invoice-v1
# Optional manual override for local model cache locations:
# HF_HOME=/absolute/path/to/huggingface-cache
# DOCLING_ARTIFACTS_PATH=/absolute/path/to/docling-artifacts
# EASYOCR_MODULE_PATH=/absolute/path/to/EasyOcr
PROCESSING_AUTO_APPROVAL_ENABLED=false
"""


def build_frontend_env_text(env: dict[str, str]) -> str:
    lines = [
        "# Generated by infrastructure/foundation.py init; server-only values.",
        "# Never commit this file and never move values to NEXT_PUBLIC_* variables.",
    ]
    lines.extend(f"{key}={env[key]}" for key in FRONTEND_ENV_KEYS)
    return "\n".join(lines) + "\n"


def cmd_init(_args: list[str]) -> None:
    generate_certificates()

    if ENV_FILE.exists():
        print(f"foundation: existing {ENV_FILE.name} preserved")
        read_env(ENV_FILE)  # Later commands validate completeness.
    else:
        ENV_FILE.write_text(build_env_text(), encoding="utf-8", newline="\n")
        print(f"foundation: generated {ENV_FILE.name} with random development secrets")

    env = require_env()
    if FRONTEND_ENV_FILE.exists():
        print(f"foundation: existing frontend/{FRONTEND_ENV_FILE.name} preserved")
    else:
        FRONTEND_ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
        FRONTEND_ENV_FILE.write_text(
            build_frontend_env_text(env), encoding="utf-8", newline="\n"
        )
        print(f"foundation: generated frontend/{FRONTEND_ENV_FILE.name}")

    for key in ("HF_HOME", "DOCLING_ARTIFACTS_PATH", "EASYOCR_MODULE_PATH"):
        path = Path(env[key])
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass  # A personal override the user must create themselves.

    if not env.get("LLM_API_KEY"):
        print(
            "foundation: NOTE LLM_API_KEY is empty. The backend validates a "
            "Groq key at startup, so add one to .env before the first run"
        )


# --------------------------------------------------------------------------
# Docker Compose helpers
# --------------------------------------------------------------------------


def require_docker() -> None:
    try:
        completed = subprocess.run(
            ["docker", "info", "--format", "{{.OSType}}"],
            capture_output=True, text=True, check=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        fail(
            "Docker is not reachable. Install Docker Desktop for your OS, open "
            f"it and wait for the engine to start ({exc})"
        )
    engine = completed.stdout.strip()
    if engine != "linux":
        fail(f"Docker engine OS type is '{engine}'; enable Linux containers")


def require_free_space() -> None:
    if platform.system() != "Windows":
        return
    try:
        free = shutil.disk_usage(os.environ.get("SystemDrive", "C:") + "\\").free
    except OSError:
        return
    if free < 1024 ** 3:
        fail("Windows system drive has less than 1 GiB free; free space and retry")


def compose_base() -> list[str]:
    return [
        "docker", "compose",
        "--env-file", str(ENV_FILE),
        "-f", str(COMPOSE_FILE),
    ]


def compose_wait_healthy(timeout_seconds: int = 900) -> None:
    print("foundation: waiting for postgres, redis and minio to become healthy…")
    if platform.system() == "Windows":
        # MinIO's first build compiles Go sources and can take a long time.
        timeout_seconds = max(timeout_seconds, 1800)
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        completed = subprocess.run(
            compose_base() + ["ps", "--format", "{{.Name}}: {{.Status}}"],
            capture_output=True, text=True, check=True,
        )
        statuses: dict[str, str] = {}
        for line in completed.stdout.splitlines():
            name, _, status = line.strip().partition(":")
            if name.strip():
                statuses[name.strip()] = status.strip()
        healthy = [
            s for s in COMPOSE_SERVICES
            if "(healthy)" in statuses.get(f"{APP_NAME}-{s}-1", "")
        ]
        if len(healthy) == len(COMPOSE_SERVICES):
            print("foundation: all three services healthy")
            return
        time.sleep(5)
    subprocess.run(compose_base() + ["ps"], check=False)
    fail("Services did not become healthy in time; see the table above")


def cmd_up(_args: list[str]) -> None:
    require_docker()
    require_free_space()
    require_env()
    subprocess.run(
        compose_base() + ["up", "-d", "--build", *COMPOSE_SERVICES], check=True
    )
    compose_wait_healthy()
    ensure_bucket()
    check_storage()
    print("foundation: up complete")


def cmd_down(_args: list[str]) -> None:
    require_docker()
    # Named volumes are intentionally preserved; this helper never deletes data.
    subprocess.run(compose_base() + ["down"], check=False)


# --------------------------------------------------------------------------
# check — authenticated readiness probes
# --------------------------------------------------------------------------


def check_sql(env: dict[str, str]) -> None:
    import psycopg

    with psycopg.connect(env["DATABASE_URL"], connect_timeout=10) as conn:
        row = conn.execute(
            "SELECT extversion FROM pg_extension WHERE extname='vector'"
        ).fetchone()
        if row is None:
            fail("pgvector extension is not present in the target database")
        distance = conn.execute("SELECT '[3,1]'::vector <=> '[1,2]'::vector").fetchone()[0]
        if not isinstance(distance, float):
            fail("pgvector cosine-distance operation returned an unexpected type")
        tables = conn.execute(
            "SELECT count(*) FROM pg_tables WHERE schemaname='public'"
        ).fetchone()[0]
        head_unknown = conn.execute(
            "SELECT to_regclass('public.alembic_version') IS NULL"
        ).fetchone()[0]
        note = "" if head_unknown else " (alembic_version present)"
        print(
            f"foundation: SQL ok — pgvector {row[0]}, cosine-distance ok, "
            f"{tables} public table(s){note}"
        )


def check_redis(env: dict[str, str]) -> None:
    import redis as redis_lib

    client = redis_lib.Redis.from_url(env["REDIS_URL"], socket_connect_timeout=10)
    try:
        if not client.ping():
            fail("Redis PING returned false")
        print("foundation: Redis ok — authenticated PING")
    finally:
        client.close()


def make_botocore_client(env: dict[str, str], *, unsigned: bool = False):
    import botocore.session

    session = botocore.session.get_session()
    session.set_config_variable("region", env["S3_REGION"])
    if unsigned:
        session.set_credentials("", "")
    else:
        session.set_credentials(env["S3_ACCESS_KEY"], env["S3_SECRET_KEY"])
    return session.create_client(
        "s3",
        endpoint_url=env["S3_ENDPOINT"].rstrip("/"),
        verify=str((PROJECT_DIR / env["AWS_CA_BUNDLE"]).resolve()),
    )


def check_storage(env: dict[str, str]) -> None:
    bucket = env["S3_BUCKET"]
    client = make_botocore_client(env)
    client.head_bucket(Bucket=bucket)
    key = "docusense-foundation-check/check-object"
    payload = b"foundation-encrypted-round-trip"
    client.put_object(
        Bucket=bucket, Key=key, Body=payload,
        ServerSideEncryption=env["S3_ENCRYPTION"],
    )
    stored = client.get_object(Bucket=bucket, Key=key)["Body"].read()
    if stored != payload:
        fail("Encrypted object round-trip mismatch")
    client.delete_object(Bucket=bucket, Key=key)
    try:
        client.get_object(Bucket=bucket, Key=key)
        fail("Deleted object unexpectedly readable")
    except client.exceptions.NoSuchKey:
        pass
    print(
        f"foundation: MinIO ok — TLS trusted, authenticated access to '{bucket}' "
        f"with {env['S3_ENCRYPTION']} write/read/delete"
    )
    import botocore.exceptions

    anonymous = make_botocore_client(env, unsigned=True)
    try:
        anonymous.get_object(Bucket=bucket, Key=key)
        fail("Anonymous read unexpectedly allowed; bucket policy is too open")
    except botocore.exceptions.ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code not in {"AccessDenied", "403"}:
            fail(f"Unexpected anonymous-read response: {code}")
    except botocore.exceptions.NoCredentialsError:
        pass  # Unsigned credentials were rejected client-side: still denied.
    print("foundation: anonymous object reads denied")


def ensure_bucket(env: dict[str, str]) -> None:
    bucket = env["S3_BUCKET"]
    client = make_botocore_client(env)
    client.head_bucket(Bucket=bucket)
    print(f"foundation: bucket '{bucket}' present")
    try:
        client.get_bucket_policy(Bucket=bucket)
        print(f"foundation: existing bucket policy preserved for '{bucket}'")
    except client.exceptions.NoSuchBucketPolicy:
        policy = {
            "Version": "2012-10-17",
            "Statement": [{
                "Sid": "DenyAnonymousRead",
                "Effect": "Deny",
                "Principal": {"AWS": ["*"]},
                "Action": ["s3:GetObject"],
                "Resource": f"arn:aws:s3:::{bucket}/*",
            }],
        }
        client.put_bucket_policy(Bucket=bucket, Policy=json.dumps(policy))
        print(f"foundation: private deny-anonymous policy applied to '{bucket}'")


def _tls_context(env: dict[str, str]) -> ssl.SSLContext:
    import ssl

    return ssl.create_default_context(
        cafile=str((PROJECT_DIR / env["AWS_CA_BUNDLE"]).resolve())
    )


def check_minio_tls(env: dict[str, str]) -> None:
    try:
        with urllib.request.urlopen(
            urllib.request.Request(f"{env['S3_ENDPOINT']}/minio/health/ready"),
            timeout=10,
            context=_tls_context(env),
        ) as response:
            if response.status != 200:
                fail(f"MinIO health/ready returned HTTP {response.status}")
    except (urllib.error.URLError, OSError) as exc:
        fail(f"MinIO TLS endpoint unreachable ({exc})")
    print(f"foundation: MinIO TLS healthy at {env['S3_ENDPOINT']}")


def cmd_check(_args: list[str]) -> None:
    require_docker()
    env = require_env()
    check_minio_tls(env)
    check_sql(env)
    check_redis(env)
    check_storage(env)
    print("foundation: check PASSED")


# --------------------------------------------------------------------------
# migrate — apply all feature revisions to the local database
# --------------------------------------------------------------------------

ALEMBIC_ENV_TEMPLATE = '''"""Programmatic online Alembic environment for the local migration runner."""

from alembic import context
from sqlalchemy import create_engine

url = context.config.attributes.get("docusense_database_url")
if not url:
    raise RuntimeError("docusense_database_url attribute missing")


def run_migrations_online() -> None:
    with create_engine(url).connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=None,
            transaction_per_migration=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    raise RuntimeError("Offline sql mode is unsupported; apply online")
else:
    run_migrations_online()
'''


def load_revision_chain() -> list[tuple[str, Path, str | None]]:
    """[(revision, source path, down_revision)] parsed from every feature."""
    revisions: dict[str, tuple[Path, str | None]] = {}
    for feature in MIGRATION_FEATURES:
        directory = PROJECT_DIR / "database" / feature / "migrations"
        for path in sorted(directory.glob("*_migration.py")):
            text = path.read_text(encoding="utf-8")
            rev_match = RV_RE.search(text)
            down_match = DOWN_RE.search(text)
            if rev_match is None or down_match is None:
                fail(f"cannot parse revision chain in {path.name}")
            revision = rev_match.group(1)
            parent = down_match.group(1) or None
            revisions[revision] = (path, parent)
    ordered: list[tuple[str, Path, str | None]] = []
    current: str | None = None
    while current != EXPECTED_HEAD:
        children = [
            rev for rev, (_, parent) in revisions.items() if parent == current
        ]
        if len(children) != 1:
            fail(f"migration chain broken: expected one child of {current!r}, got {children}")
        current = children[0]
        path, parent = revisions[current]
        ordered.append((current, path, parent))
    return ordered


def cmd_migrate(_args: list[str]) -> None:
    import tempfile

    import alembic.command
    import alembic.config

    env = require_env()
    url = env["DATABASE_URL"].strip()
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url.removeprefix("postgresql://")
    elif not url.startswith("postgresql+psycopg://"):
        fail("DATABASE_URL must be a PostgreSQL URI")

    chained = load_revision_chain()
    for revision, path, parent in chained:
        print(f"foundation: queued {revision} (parent {parent}, from {path.relative_to(PROJECT_DIR)})")
        _ = parent
    # Alembic expects revision files under one versions/ directory, and the
    # revisions read companion .sql files from beside themselves. Copy both.
    with tempfile.TemporaryDirectory(prefix="docusense-alembic-") as tmp:
        root = Path(tmp)
        versions = root / "versions"
        versions.mkdir()
        seen: set[str] = set()
        for _, source_path, _ in chained:
            if source_path.name in seen:
                fail(f"duplicate migration file name: {source_path.name}")
            seen.add(source_path.name)
            (versions / source_path.name).write_text(
                source_path.read_text(encoding="utf-8"), encoding="utf-8"
            )
            for companion in source_path.parent.glob("*.sql"):
                (versions / companion.name).write_text(
                    companion.read_text(encoding="utf-8"), encoding="utf-8"
                )

        config = alembic.config.Config()
        config.set_main_option("script_location", str(root))
        config.attributes["docusense_database_url"] = url
        alembic.command.upgrade(config, "head")
        print(f"foundation: migrations applied; database now at {EXPECTED_HEAD}")


# --------------------------------------------------------------------------
# test-db — disposable acknowledged acceptance database
# --------------------------------------------------------------------------


def cmd_test_db(_args: list[str]) -> None:
    import psycopg

    env = require_env()
    if ENV_TEST_FILE.exists():
        fail(f"{ENV_TEST_FILE.name} exists; it is created exactly once and is "
             "never overwritten. Retire the old record first.")
    database = f"docusense_ingestion_test_{secrets.token_hex(4)}"
    dsn_prefix = env["DATABASE_URL"].rsplit("/", 1)[0]
    with psycopg.connect(env["DATABASE_URL"], autocommit=True,
                         connect_timeout=10) as conn:
        name = conn.execute("SELECT current_database()").fetchone()[0]
        consumers = conn.execute(
            "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()"
        ).fetchone()[0]
        conn.execute(f'CREATE DATABASE "{database}"')
    dsn = f"{dsn_prefix}/{database}"
    ENV_TEST_FILE.write_text(
        "# Generated disposable acceptance-test database record.\n"
        f"INGESTION_TEST_DSN={dsn}\n"
        "DOCUSENSE_DISPOSABLE_DATABASE_ACKNOWLEDGED=true\n"
        "DOCUSENSE_DISPOSABLE_NO_CONSUMERS_ASSERTED=true\n"
        "# Explicitly acknowledged as existing by infrastructure/foundation.py "
        "test-db.\n",
        encoding="utf-8", newline="\n",
    )
    print(
        f"foundation: disposable database '{database}' created on server of "
        f"'{name}' (baseline consumers: {consumers}); record written to .env.test"
    )


# --------------------------------------------------------------------------
# run -- execute a command with .env loaded
# --------------------------------------------------------------------------


def cmd_run(args: list[str]) -> None:
    env = require_env()
    # Values already present in the process environment take precedence.
    for key, value in env.items():
        os.environ.setdefault(key, value)
    if not args:
        fail("run: no command provided (use 'run -- <command> [args...]')")
    try:
        completed = subprocess.run(args, check=False, env=mapped_environment())
    except FileNotFoundError:
        fail(f"command not found: {args[0]}")
    raise SystemExit(completed.returncode)


def mapped_environment() -> dict[str, str]:
    # The helper itself always runs under the backend virtual environment.
    venv_bin = Path(sys.executable).resolve().parent
    path_env = os.environ["PATH"]
    if venv_bin.as_posix() not in path_env:
        os.environ["PATH"] = str(venv_bin) + os.pathsep + path_env
    return os.environ


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def main(argv: list[str]) -> None:
    if not argv:
        fail(
            "usage: foundation.py {init | up | check | down | migrate | test-db | "
            "run -- <command> [args...]}"
        )
    command, rest = argv[0], argv[1:]
    if rest and rest[0] == "--":
        rest = rest[1:]
    handlers = {
        "init": cmd_init,
        "up": cmd_up,
        "check": cmd_check,
        "down": cmd_down,
        "migrate": cmd_migrate,
        "test-db": cmd_test_db,
        "run": cmd_run,
    }
    if command not in handlers:
        fail(f"unknown command: {command}")
    handlers[command](rest)


if __name__ == "__main__":
    main(sys.argv[1:])
