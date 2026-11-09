"""Composition tests for the concrete API host and worker/recovery runners."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.backend_runtime.auth import AuthService
from app.backend_runtime.host import HostSettings, create_application
from app.backend_runtime.queue import DOCUMENT_TASK, EXPORT_TASK, create_celery
from app.backend_runtime.settings import RuntimeSettings
from app.backend_runtime.workers import RuntimeReconciler, WorkerRunner
from app.document_ingestion.dispatcher import DispatchResult


class _Lifecycle:
    def __init__(self):
        self.starts = 0
        self.closes = 0

    async def start(self):
        self.starts += 1

    async def close(self):
        self.closes += 1


class _Database:
    @asynccontextmanager
    async def session(self):
        yield object()


class _Auth:
    async def resolve(self, _credential):
        raise AssertionError("Route dependency must not run during composition")


class _Limiter:
    async def check(self, *_args):
        return None


def _policy() -> HostSettings:
    return HostSettings(
        cors_origins=("https://ui.example.test",),
        trusted_hosts=("api.example.test", "testserver"),
        supported_currencies=frozenset({"USD", "EUR", "BDT"}),
    )


def _assert_search_export_openapi(schema) -> None:
    paths = schema["paths"]
    components = schema["components"]["schemas"]
    assert {
        "DocumentSearchRequest", "SearchCriteria", "CreateExportRequest",
        "ErrorEnvelope",
    } <= set(components)

    search = paths["/api/v1/documents/search"]["post"]
    assert search["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/DocumentSearchRequest",
    }
    assert search["security"] == [{"BearerAuth": []}]
    assert {"200", "400", "401", "403", "422", "429", "500", "503"} <= set(
        search["responses"]
    )

    direct = paths["/api/v1/documents/export"]["get"]
    assert {
        row["name"] for row in direct["parameters"] if row["in"] == "query"
    } == {
        "format", "document_id", "document_statuses", "document_type",
        "supplier", "currency", "invoice_date_from", "invoice_date_to",
        "uploaded_from", "uploaded_to", "min_total", "max_total", "sort_by",
        "order",
    }
    assert set(direct["responses"]["200"]["content"]) == {
        "text/csv",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/json",
    }
    assert {"Content-Disposition", "X-Content-SHA256", "X-Export-Id"} <= set(
        direct["responses"]["200"]["headers"]
    )

    create = paths["/api/v1/exports"]["post"]
    assert create["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/CreateExportRequest",
    }
    assert {
        row["name"] for row in create["parameters"] if row["in"] == "header"
    } == {"Idempotency-Key"}
    assert "200" not in create["responses"]
    assert {"201", "202"} <= set(create["responses"])

    status = paths["/api/v1/exports/{export_id}"]["get"]
    download = paths["/api/v1/exports/{export_id}/download"]["get"]
    for operation in (status, download):
        export_id = next(
            row for row in operation["parameters"]
            if row["in"] == "path" and row["name"] == "export_id"
        )
        assert export_id["schema"]["format"] == "uuid"
        assert operation["security"] == [{"BearerAuth": []}]

    assert set(download["responses"]["200"]["content"]) == {
        "text/csv",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/json",
        "application/zip",
    }
    assert {"Location", "Content-Disposition", "X-Content-SHA256"} <= set(
        download["responses"]["302"]["headers"]
    )

    error_ref = {"$ref": "#/components/schemas/ErrorEnvelope"}
    for operation in (search, direct, create, status, download):
        assert operation["responses"]["422"]["content"]["application/json"][
            "schema"
        ] == error_ref
        assert "Retry-After" in operation["responses"]["429"]["headers"]


def _assert_dashboard_activity_openapi(schema) -> None:
    paths = schema["paths"]
    components = schema["components"]["schemas"]
    assert {
        "DashboardActivityErrorEnvelope", "DashboardActivityErrorBody",
        "DashboardActivityErrorDetail", "DashboardActivityMeta",
    } <= set(components)
    dashboard = paths["/api/v1/analytics/dashboard"]["get"]
    activity = paths["/api/v1/activity-events"]["get"]
    assert {
        row["name"] for row in dashboard["parameters"] if row["in"] == "query"
    } == {"from", "to", "bucket"}
    assert {
        row["name"] for row in activity["parameters"] if row["in"] == "query"
    } == {"page", "page_size", "event_type", "from", "to", "snapshot_at"}
    assert dashboard["security"] == activity["security"] == [{"BearerAuth": []}]
    expected_responses = {"200", "400", "401", "403", "422", "429", "500", "503"}
    error_ref = {"$ref": "#/components/schemas/DashboardActivityErrorEnvelope"}
    required_headers = {
        "Cache-Control", "Pragma", "X-Content-Type-Options", "X-Request-Id",
    }
    for operation in (dashboard, activity):
        assert "requestBody" not in operation
        assert expected_responses <= set(operation["responses"])
        assert required_headers <= set(operation["responses"]["200"]["headers"])
        assert operation["responses"]["422"]["content"]["application/json"][
            "schema"
        ] == error_ref
        assert "Retry-After" in operation["responses"]["429"]["headers"]
        assert len(operation["x-query-rules"]) == 3
    event_type = next(
        row for row in activity["parameters"] if row["name"] == "event_type"
    )
    assert event_type["style"] == "form" and event_type["explode"] is True
    assert event_type["schema"]["uniqueItems"] is True
    assert len(event_type["schema"]["items"]["enum"]) == 11


def test_host_policy_rejects_wildcard_or_unsafe_origins() -> None:
    with pytest.raises(ValueError):
        HostSettings(cors_origins=("*",), supported_currencies=frozenset({"USD"}))
    with pytest.raises(ValueError):
        HostSettings(
            cors_origins=("http://public.example.test",),
            supported_currencies=frozenset({"USD"}),
        )


def test_runtime_settings_require_kms_key_when_kms_is_selected(tmp_path) -> None:
    ca = tmp_path / "ca.pem"
    ca.write_text("test", encoding="utf-8")
    values = {
        "DATABASE_URL": "postgresql://user:password@localhost:5432/test",
        "REDIS_URL": "redis://localhost:6379/0",
        "JWT_SECRET_KEY": "j" * 32,
        "S3_ENDPOINT": "https://storage.example.test",
        "S3_BUCKET": "private-documents",
        "S3_ACCESS_KEY": "access",
        "S3_SECRET_KEY": "secret",
        "S3_ENCRYPTION": "aws:kms",
        "AWS_CA_BUNDLE": ca,
        "EMBEDDING_MODEL": "sentence-transformers/all-MiniLM-L6-v2",
        "EMBEDDING_REVISION": "a" * 40,
        "EMBEDDING_DIMENSIONS": 384,
        "HF_HOME": tmp_path,
        "DOCLING_ARTIFACTS_PATH": tmp_path,
        "EASYOCR_MODULE_PATH": tmp_path,
        "RAG_PIPELINE_VERSION": "rag-v1",
        "RAG_PARSER_VERSION": "docling-test",
        "RAG_OCR_POLICY_VERSION": "ocr-v1",
        "LLM_PROVIDER": "groq",
        "LLM_API_KEY": "g" * 20,
        "RAG_LLM_MODEL": "openai/gpt-oss-20b",
        "RAG_PROMPT_VERSION": "prompt-v1",
    }
    with pytest.raises(ValueError, match="S3_KMS_KEY_ID"):
        RuntimeSettings(**values)
    assert RuntimeSettings(**values, S3_KMS_KEY_ID="alias/key").s3_kms_key_id is not None


def test_gateway_has_one_owner_per_method_and_path() -> None:
    lifecycle = _Lifecycle()
    graph = SimpleNamespace(
        policy=_policy(), auth_service=AuthService("x" * 32), database=_Database(),
        ingestion_service=object(), ingestion_auth=_Auth(), limiter=_Limiter(),
        rag_service=object(), rag_auth=_Auth(),
        search_service=object(), export_command=object(), export_query=object(),
        export_auth=_Auth(), review_query=object(), review_validation=object(),
        review_command=object(), review_auth=_Auth(),
        dashboard_analytics=object(), dashboard_activity=object(),
        dashboard_auth=_Auth(),
        start=lifecycle.start, close=lifecycle.close,
        ready=lambda: None,
    )
    app = create_application(graph)
    def flattened(routes):
        for route in routes:
            if hasattr(route, "path"):
                yield route
            else:
                yield from flattened(getattr(route, "routes", ()))

    routes = list(flattened(app.routes))
    pairs = []
    for route in routes:
        for method in getattr(route, "methods", ()):
            if method not in {"HEAD", "OPTIONS"}:
                pairs.append((method, route.path))
    assert len(pairs) == len(set(pairs))
    schema = app.openapi()
    schema_paths = schema["paths"]
    assert "/api/v1/documents/export" in schema_paths
    assert "/api/v1/analytics/dashboard" in schema_paths
    assert "/api/v1/activity-events" in schema_paths
    assert "/api/v1/documents/{document_id}" in schema_paths
    assert schema_paths["/api/v1/documents/{document_id}"]["get"]["tags"] == [
        "document-review"
    ]
    assert set(schema["components"]["securitySchemes"]) == {
        "BearerAuth", "ApiKeyAuth",
    }
    assert schema_paths["/api/v1/documents/{document_id}"]["get"]["security"] == [
        {"BearerAuth": []},
    ]
    _assert_search_export_openapi(schema)
    _assert_dashboard_activity_openapi(schema)
    chunk_operation = schema_paths["/api/v1/documents/{document_id}/chunks"]["get"]
    assert {row["name"] for row in chunk_operation["parameters"]} == {
        "document_id", "page", "page_size", "chunk_type", "page_number",
        "retrieval_role", "section", "sort_by", "order",
    }
    assert {"200", "400", "401", "403", "404", "409", "422", "429", "500", "503"} <= set(
        chunk_operation["responses"]
    )
    preview_operation = schema_paths[
        "/api/v1/documents/{document_id}/review-validations"
    ]["post"]
    assert preview_operation["requestBody"]["content"]["application/json"][
        "schema"
    ] == {"$ref": "#/components/schemas/ReviewValidationRequest"}
    mutation_operation = schema_paths[
        "/api/v1/documents/{document_id}/review"
    ]["put"]
    mutation_schema = mutation_operation["requestBody"]["content"][
        "application/json"
    ]["schema"]
    assert {row["$ref"] for row in mutation_schema["oneOf"]} == {
        "#/components/schemas/SaveReviewRequest",
        "#/components/schemas/ApproveReviewRequest",
        "#/components/schemas/RejectReviewRequest",
        "#/components/schemas/ReopenReviewRequest",
    }
    assert mutation_schema["discriminator"]["propertyName"] == "action"
    assert {
        row["name"] for row in mutation_operation["parameters"]
        if row["in"] == "header"
    } == {"Idempotency-Key"}
    idempotency_schema = next(
        row["schema"] for row in mutation_operation["parameters"]
        if row["in"] == "header" and row["name"] == "Idempotency-Key"
    )
    assert idempotency_schema == {
        "type": "string", "minLength": 1, "maxLength": 128,
        "pattern": r"^[\x21-\x7E]+$",
    }
    audit_operation = schema_paths[
        "/api/v1/documents/{document_id}/audit-logs"
    ]["get"]
    assert {
        row["name"] for row in audit_operation["parameters"]
        if row["in"] == "query"
    } == {"page", "page_size", "action"}
    review_errors = {"200", "400", "401", "403", "404", "409", "422",
                     "429", "500", "503"}
    for operation in (preview_operation, mutation_operation):
        assert operation["security"] == [{"BearerAuth": []}]
        assert review_errors <= set(operation["responses"])
    assert audit_operation["security"] == [{"BearerAuth": []}]
    assert review_errors - {"409"} <= set(audit_operation["responses"])
    for operation in (preview_operation, mutation_operation, audit_operation):
        assert operation["responses"]["422"]["content"]["application/json"][
            "schema"
        ] == {
            "$ref": "#/components/schemas/app__human_review_audit__schemas__ErrorEnvelope",
        }


@pytest.mark.asyncio
async def test_reconciler_recovers_before_export_dispatch_and_expiry() -> None:
    calls = []

    class Documents:
        async def tick(self):
            calls.append("documents")
            return DispatchResult(2, 1, False)

    class Repository:
        async def recover_expired_leases(self, *, limit):
            calls.append(("recover", limit))
            return (uuid4(), uuid4())

    class Exports:
        async def dispatch_due(self, limit):
            calls.append(("dispatch", limit))
            return 3

    class Expiry:
        async def expire_due(self, limit):
            calls.append(("expiry", limit))
            return 1

    runner = RuntimeReconciler(
        Documents(), Repository(), Exports(), Expiry(), batch_size=25,
    )
    result = await runner.tick()
    assert calls == ["documents", ("recover", 25), ("dispatch", 25), ("expiry", 25)]
    assert (result.recovered_exports, result.export_dispatches, result.expired_exports) == (2, 3, 1)


def test_worker_registers_id_only_tasks_on_one_persistent_loop() -> None:
    lifecycle = _Lifecycle()
    loops = []

    async def document(document_id, job_id):
        loops.append(asyncio.get_running_loop())
        return document_id != job_id

    async def export(export_id):
        loops.append(asyncio.get_running_loop())
        return bool(export_id)

    app = create_celery("redis://localhost:6379/15")
    worker = WorkerRunner(app, lifecycle, document, export)
    first, second = uuid4(), uuid4()
    assert app.tasks[DOCUMENT_TASK].run(str(first), str(second)) is True
    assert app.tasks[EXPORT_TASK].run(str(first)) is True
    assert lifecycle.starts == 1
    assert loops[0] is loops[1]
    worker.shutdown()
    assert lifecycle.closes == 1
