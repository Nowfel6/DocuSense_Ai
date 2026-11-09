"""Export and validate the checked-in OpenAPI contract from the exact ASGI app."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
FINAL_ROOT = BACKEND_ROOT.parent
DEFAULT_OUTPUT = FINAL_ROOT / "docs" / "api" / "openapi.yaml"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def _operation(schema: dict[str, Any], path: str,
               method: str = "get") -> dict[str, Any]:
    try:
        return schema["paths"][path][method]
    except (KeyError, TypeError) as exc:
        raise RuntimeError(
            f"Required {method.upper()} operation is missing: {path}"
        ) from exc


def _validate_search_export(schema: dict[str, Any]) -> None:
    components = schema.get("components", {}).get("schemas", {})
    required_components = {
        "DocumentSearchRequest", "SearchCriteria", "CreateExportRequest",
        "ErrorEnvelope", "ErrorBody", "ErrorDetail", "Meta",
    }
    if not required_components <= set(components):
        raise RuntimeError("Search/export request or error components are incomplete")

    criteria_fields = {
        "query", "document_statuses", "document_type", "supplier", "currency",
        "invoice_date_from", "invoice_date_to", "uploaded_from", "uploaded_to",
        "min_total", "max_total",
    }
    for name in ("SearchCriteria", "DocumentSearchRequest"):
        actual = {
            row.get("required", [None])[0]
            for row in components[name].get("anyOf", [])
        }
        if actual != criteria_fields:
            raise RuntimeError(f"At-least-one criterion is incomplete for {name}")

    create_selection = {
        tuple(row.get("required", []))
        for row in components["CreateExportRequest"].get("oneOf", [])
    }
    if create_selection != {("document_ids",), ("criteria",)}:
        raise RuntimeError("Export selection exclusivity is incomplete")

    bearer = [{"BearerAuth": []}]
    error_ref = {"$ref": "#/components/schemas/ErrorEnvelope"}

    search = _operation(schema, "/api/v1/documents/search", "post")
    if search.get("requestBody", {}).get("content", {}).get(
        "application/json", {},
    ).get("schema") != {"$ref": "#/components/schemas/DocumentSearchRequest"}:
        raise RuntimeError("Document search request body is incomplete")
    if search.get("security") != bearer:
        raise RuntimeError("Document search must be bearer-only")
    if not {"200", "400", "401", "403", "422", "429", "500", "503"} <= set(
        search.get("responses", {})
    ):
        raise RuntimeError("Document search responses are incomplete")

    direct = _operation(schema, "/api/v1/documents/export")
    expected_direct_queries = {
        "format", "document_id", "document_statuses", "document_type",
        "supplier", "currency", "invoice_date_from", "invoice_date_to",
        "uploaded_from", "uploaded_to", "min_total", "max_total", "sort_by",
        "order",
    }
    direct_queries = {
        row.get("name") for row in direct.get("parameters", [])
        if row.get("in") == "query"
    }
    if direct_queries != expected_direct_queries or "query" in direct_queries:
        raise RuntimeError("Compatibility direct-export queries are incomplete")
    direct_200 = direct.get("responses", {}).get("200", {})
    expected_direct_media = {
        "text/csv",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/json",
    }
    if set(direct_200.get("content", {})) != expected_direct_media:
        raise RuntimeError("Compatibility direct-export media are incomplete")
    if not {"Content-Disposition", "X-Content-SHA256", "X-Export-Id"} <= set(
        direct_200.get("headers", {})
    ):
        raise RuntimeError("Compatibility direct-export headers are incomplete")

    create = _operation(schema, "/api/v1/exports", "post")
    if create.get("requestBody", {}).get("content", {}).get(
        "application/json", {},
    ).get("schema") != {"$ref": "#/components/schemas/CreateExportRequest"}:
        raise RuntimeError("Create-export request body is incomplete")
    create_headers = {
        row.get("name") for row in create.get("parameters", [])
        if row.get("in") == "header"
    }
    if create_headers != {"Idempotency-Key"}:
        raise RuntimeError("Create-export idempotency header is incomplete")
    create_responses = create.get("responses", {})
    if "200" in create_responses or not {"201", "202"} <= set(create_responses):
        raise RuntimeError("Create-export 201/202 responses are incomplete")

    status = _operation(schema, "/api/v1/exports/{export_id}")
    download = _operation(schema, "/api/v1/exports/{export_id}/download")
    for name, operation in (
        ("direct", direct), ("create", create), ("status", status),
        ("download", download),
    ):
        if operation.get("security") != bearer:
            raise RuntimeError(f"Search/export {name} operation must be bearer-only")
        if operation.get("responses", {}).get("422", {}).get(
            "content", {},
        ).get("application/json", {}).get("schema") != error_ref:
            raise RuntimeError(f"Search/export {name} 422 error envelope is incomplete")

    for name, operation in (("status", status), ("download", download)):
        export_id = next(
            (row for row in operation.get("parameters", [])
             if row.get("in") == "path" and row.get("name") == "export_id"),
            None,
        )
        if export_id is None or export_id.get("schema", {}).get("format") != "uuid":
            raise RuntimeError(f"{name} export_id must be a UUID")

    download_responses = download.get("responses", {})
    expected_download_media = expected_direct_media | {"application/zip"}
    if set(download_responses.get("200", {}).get("content", {})) != expected_download_media:
        raise RuntimeError("Export download media are incomplete")
    redirect_headers = download_responses.get("302", {}).get("headers", {})
    if not {"Location", "Content-Disposition", "X-Content-SHA256"} <= set(
        redirect_headers
    ):
        raise RuntimeError("Export signed-redirect response is incomplete")

    expected_error_statuses = {
        "direct": {"400", "401", "403", "404", "409", "422", "429", "500", "503"},
        "create": {"400", "401", "403", "404", "409", "422", "429", "500", "503"},
        "status": {"400", "401", "403", "404", "422", "429", "500", "503"},
        "download": {"400", "401", "403", "404", "409", "410", "422", "429", "500", "503"},
    }
    for name, operation in (
        ("direct", direct), ("create", create), ("status", status),
        ("download", download),
    ):
        if not expected_error_statuses[name] <= set(operation.get("responses", {})):
            raise RuntimeError(f"Search/export {name} error responses are incomplete")

    for operation in (search, direct, create, status, download):
        response_429 = operation.get("responses", {}).get("429", {})
        if "Retry-After" not in response_429.get("headers", {}):
            raise RuntimeError("Search/export 429 must declare Retry-After")


def _validate_dashboard_activity(schema: dict[str, Any]) -> None:
    components = schema.get("components", {}).get("schemas", {})
    required_components = {
        "DashboardActivityErrorEnvelope", "DashboardActivityErrorBody",
        "DashboardActivityErrorDetail", "DashboardActivityMeta",
    }
    if not required_components <= set(components):
        raise RuntimeError("Dashboard/activity error components are incomplete")

    bearer = [{"BearerAuth": []}]
    error_ref = {
        "$ref": "#/components/schemas/DashboardActivityErrorEnvelope",
    }
    dashboard = _operation(schema, "/api/v1/analytics/dashboard")
    activity = _operation(schema, "/api/v1/activity-events")
    expected_queries = {
        "dashboard": {"from", "to", "bucket"},
        "activity": {
            "page", "page_size", "event_type", "from", "to", "snapshot_at",
        },
    }
    for name, operation in (("dashboard", dashboard), ("activity", activity)):
        actual_queries = {
            row.get("name") for row in operation.get("parameters", [])
            if row.get("in") == "query"
        }
        if actual_queries != expected_queries[name]:
            raise RuntimeError(f"Dashboard/activity {name} queries are incomplete")
        if "requestBody" in operation:
            raise RuntimeError(f"Dashboard/activity {name} must not declare a body")
        if operation.get("security") != bearer:
            raise RuntimeError(f"Dashboard/activity {name} must be bearer-only")
        expected_responses = {"200", "400", "401", "403", "422", "429", "500", "503"}
        if not expected_responses <= set(operation.get("responses", {})):
            raise RuntimeError(f"Dashboard/activity {name} responses are incomplete")
        for status in expected_responses - {"200"}:
            actual_ref = operation["responses"][status]["content"][
                "application/json"
            ]["schema"]
            if actual_ref != error_ref:
                raise RuntimeError(
                    f"Dashboard/activity {name} {status} error envelope is incomplete"
                )
        required_headers = {
            "Cache-Control", "Pragma", "X-Content-Type-Options", "X-Request-Id",
        }
        if not required_headers <= set(operation["responses"]["200"].get("headers", {})):
            raise RuntimeError(f"Dashboard/activity {name} success headers are incomplete")
        if "Retry-After" not in operation["responses"]["429"].get("headers", {}):
            raise RuntimeError(f"Dashboard/activity {name} 429 must declare Retry-After")

    dashboard_parameters = {
        row["name"]: row for row in dashboard["parameters"]
    }
    if dashboard_parameters["bucket"]["schema"] != {
        "type": "string", "enum": ["day", "week", "month"], "default": "day",
    }:
        raise RuntimeError("Dashboard bucket contract is incomplete")
    for field_name in ("from", "to"):
        if dashboard_parameters[field_name]["schema"].get("format") != "date-time":
            raise RuntimeError("Dashboard time query contract is incomplete")

    activity_parameters = {
        row["name"]: row for row in activity["parameters"]
    }
    if activity_parameters["page"]["schema"] != {
        "type": "integer", "minimum": 1, "default": 1,
    }:
        raise RuntimeError("Activity page contract is incomplete")
    if activity_parameters["page_size"]["schema"] != {
        "type": "integer", "minimum": 1, "maximum": 100, "default": 20,
    }:
        raise RuntimeError("Activity page-size contract is incomplete")
    event_schema = activity_parameters["event_type"]["schema"]
    expected_events = {
        "document_uploaded", "processing_completed", "processing_failed",
        "review_saved", "document_approved", "document_rejected",
        "document_reopened", "export_requested", "export_completed",
        "export_failed", "export_expired",
    }
    if (event_schema.get("type") != "array"
            or event_schema.get("uniqueItems") is not True
            or set(event_schema.get("items", {}).get("enum", [])) != expected_events):
        raise RuntimeError("Activity event-type contract is incomplete")
    for field_name in ("from", "to", "snapshot_at"):
        if activity_parameters[field_name]["schema"].get("format") != "date-time":
            raise RuntimeError("Activity time query contract is incomplete")
    if len(dashboard.get("x-query-rules", [])) != 3 or len(
        activity.get("x-query-rules", [])
    ) != 3:
        raise RuntimeError("Dashboard/activity cross-field query rules are incomplete")


def validate(schema: dict[str, Any]) -> None:
    if not str(schema.get("openapi", "")).startswith("3.1."):
        raise RuntimeError("Expected an OpenAPI 3.1 document")
    schemes = schema.get("components", {}).get("securitySchemes", {})
    if set(schemes) != {"BearerAuth", "ApiKeyAuth"}:
        raise RuntimeError("BearerAuth and ApiKeyAuth must both be declared")

    detail = _operation(schema, "/api/v1/documents/{document_id}")
    if detail.get("security") != [{"BearerAuth": []}]:
        raise RuntimeError("Document detail must declare bearer-only authentication")
    required_detail_responses = {"200", "400", "401", "403", "404", "409",
                                 "422", "429", "500", "503"}
    if not required_detail_responses <= set(detail.get("responses", {})):
        raise RuntimeError("Document detail error responses are incomplete")

    expected_queries = {
        "/api/v1/documents/{document_id}/chunks": {
            "page", "page_size", "chunk_type", "page_number", "retrieval_role",
            "section", "sort_by", "order",
        },
        "/api/v1/documents/{document_id}/extraction-evidence": {
            "page", "page_size", "field_path", "validation_state", "min_confidence",
        },
    }
    for path, expected in expected_queries.items():
        operation = _operation(schema, path)
        actual = {
            parameter["name"] for parameter in operation.get("parameters", [])
            if parameter.get("in") == "query"
        }
        if actual != expected:
            raise RuntimeError(f"Query contract mismatch for {path}: {sorted(actual)}")
        if operation.get("security") != [{"BearerAuth": []}]:
            raise RuntimeError(f"Technical endpoint must be bearer-only: {path}")

    status = _operation(schema, "/api/v1/documents/{document_id}/status")
    if status.get("security") != [{"BearerAuth": []}, {"ApiKeyAuth": []}]:
        raise RuntimeError("Status endpoint must declare bearer-or-API-key authentication")

    _validate_search_export(schema)
    _validate_dashboard_activity(schema)

    review_errors = {"200", "400", "401", "403", "404", "409", "422",
                     "429", "500", "503"}
    preview = _operation(
        schema, "/api/v1/documents/{document_id}/review-validations", "post",
    )
    preview_schema = preview.get("requestBody", {}).get("content", {}).get(
        "application/json", {},
    ).get("schema")
    if preview_schema != {"$ref": "#/components/schemas/ReviewValidationRequest"}:
        raise RuntimeError("Review preview request body is incomplete")

    mutation = _operation(
        schema, "/api/v1/documents/{document_id}/review", "put",
    )
    mutation_schema = mutation.get("requestBody", {}).get("content", {}).get(
        "application/json", {},
    ).get("schema", {})
    action_refs = {
        row.get("$ref") for row in mutation_schema.get("oneOf", [])
        if isinstance(row, dict)
    }
    expected_action_refs = {
        f"#/components/schemas/{name}ReviewRequest"
        for name in ("Save", "Approve", "Reject", "Reopen")
    }
    if action_refs != expected_action_refs or mutation_schema.get(
        "discriminator", {},
    ).get("propertyName") != "action":
        raise RuntimeError("Review mutation discriminated request body is incomplete")
    mutation_headers = {
        parameter.get("name") for parameter in mutation.get("parameters", [])
        if parameter.get("in") == "header"
    }
    if mutation_headers != {"Idempotency-Key"}:
        raise RuntimeError("Review mutation idempotency header is incomplete")
    idempotency = next(
        parameter for parameter in mutation.get("parameters", [])
        if parameter.get("in") == "header"
        and parameter.get("name") == "Idempotency-Key"
    )
    idempotency_schema = idempotency.get("schema", {})
    if (idempotency_schema.get("minLength") != 1
            or idempotency_schema.get("maxLength") != 128
            or idempotency_schema.get("pattern") != r"^[\x21-\x7E]+$"):
        raise RuntimeError("Review mutation idempotency constraints are incomplete")

    audit = _operation(schema, "/api/v1/documents/{document_id}/audit-logs")
    audit_queries = {
        parameter.get("name") for parameter in audit.get("parameters", [])
        if parameter.get("in") == "query"
    }
    if audit_queries != {"page", "page_size", "action"}:
        raise RuntimeError("Review audit query contract is incomplete")

    expected_review_errors = {
        "preview": review_errors,
        "mutation": review_errors,
        "audit": review_errors - {"409"},
    }
    for name, operation in (("preview", preview), ("mutation", mutation),
                            ("audit", audit)):
        if operation.get("security") != [{"BearerAuth": []}]:
            raise RuntimeError(f"Review {name} must declare bearer-only authentication")
        if not expected_review_errors[name] <= set(operation.get("responses", {})):
            raise RuntimeError(f"Review {name} error responses are incomplete")
        error_ref = operation["responses"]["422"]["content"][
            "application/json"
        ]["schema"].get("$ref")
        if error_ref != "#/components/schemas/app__human_review_audit__schemas__ErrorEnvelope":
            raise RuntimeError(f"Review {name} 422 must use the review error envelope")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true",
                        help="Validate that the checked-in file matches the runtime schema.")
    arguments = parser.parse_args()

    from app.main import app

    schema = app.openapi()
    validate(schema)
    rendered = json.dumps(schema, indent=2, ensure_ascii=False) + "\n"
    output = arguments.output.resolve()
    if arguments.check:
        if not output.is_file() or output.read_text(encoding="utf-8") != rendered:
            raise RuntimeError(f"OpenAPI artifact is stale: {output}")
        print(f"OpenAPI artifact is current: {output}")
        return 0
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8", newline="\n")
    print(f"Wrote validated OpenAPI contract: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
