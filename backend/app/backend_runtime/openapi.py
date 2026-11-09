"""Deterministic OpenAPI authentication metadata for the composed gateway."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from pydantic.json_schema import models_json_schema

_METHODS = frozenset({"get", "post", "put", "patch", "delete"})
_DUAL_AUTH_PATHS = frozenset({
    "/api/v1/documents",
    "/api/v1/documents/upload",
    "/api/v1/documents/{document_id}/status",
})

_REVIEW_ERROR_DESCRIPTIONS = {
    "400": "Ambiguous authentication.",
    "401": "Authentication required.",
    "403": "Human review access is not permitted.",
    "404": "Document not found or not visible to this caller.",
    "409": "Document state, revision, transition, or idempotency conflict.",
    "422": "Review request, candidate, approval, or no-change validation failed.",
    "429": "Request limit exceeded.",
    "500": "Review data is inconsistent or an internal error occurred.",
    "503": "Review database or document source is temporarily unavailable.",
}

_SEARCH_EXPORT_ERROR_DESCRIPTIONS = {
    "400": "Ambiguous authentication.",
    "401": "Authentication required.",
    "403": "Search or export access is not permitted.",
    "404": "Document selection or export resource was not found.",
    "409": "Export source, readiness, or idempotency conflict.",
    "410": "Export artifact has expired.",
    "422": "Search, selection, format, range, or limit validation failed.",
    "429": "Search/export request or active-export limit exceeded.",
    "500": "Search/export data is inconsistent or an internal error occurred.",
    "503": "Search provider, database, or export storage is unavailable.",
}

_DASHBOARD_ACTIVITY_ERROR_DESCRIPTIONS = {
    "400": "Ambiguous authentication.",
    "401": "Authentication required.",
    "403": "Dashboard or activity access is not permitted.",
    "422": "Dashboard period, bucket, activity filter, or pagination validation failed.",
    "429": "Dashboard or activity request limit exceeded.",
    "500": "Analytics source data is inconsistent or an internal error occurred.",
    "503": "A required analytics source is temporarily unavailable.",
}

_PRIVATE_RESPONSE_HEADERS = {
    "Cache-Control": {
        "description": "Private response that must not be cached.",
        "schema": {"type": "string"},
    },
    "Pragma": {
        "description": "Legacy no-cache directive.",
        "schema": {"type": "string"},
    },
    "X-Content-Type-Options": {
        "description": "MIME sniffing is disabled.",
        "schema": {"type": "string", "enum": ["nosniff"]},
    },
}

_DIRECT_MEDIA = (
    "text/csv",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/json",
)
_DOWNLOAD_MEDIA = (*_DIRECT_MEDIA, "application/zip")


def _artifact_headers(*, direct: bool = False,
                      redirect: bool = False) -> dict[str, Any]:
    headers: dict[str, Any] = dict(_PRIVATE_RESPONSE_HEADERS)
    headers.update({
        "Content-Disposition": {
            "description": "Safe attachment filename.",
            "schema": {"type": "string"},
        },
        "X-Content-SHA256": {
            "description": "Lowercase SHA-256 checksum of the returned artifact.",
            "schema": {"type": "string", "pattern": r"^[0-9a-f]{64}$"},
        },
    })
    if direct:
        headers["X-Export-Id"] = {
            "description": "Durable export resource created for this direct download.",
            "schema": {"type": "string", "format": "uuid"},
        }
    if redirect:
        headers["Location"] = {
            "description": "Short-lived private signed artifact URL.",
            "schema": {"type": "string", "format": "uri"},
        }
    return headers


def _binary_response(description: str, media: tuple[str, ...], *,
                     direct: bool = False) -> dict[str, Any]:
    return {
        "description": description,
        "headers": _artifact_headers(direct=direct),
        "content": {
            content_type: {"schema": {"type": "string", "format": "binary"}}
            for content_type in media
        },
    }


def _search_export_error_response(status: str) -> dict[str, Any]:
    headers = dict(_PRIVATE_RESPONSE_HEADERS)
    if status == "429":
        headers["Retry-After"] = {
            "description": "Minimum seconds before retrying.",
            "schema": {"type": "integer", "minimum": 1},
        }
    return {
        "description": _SEARCH_EXPORT_ERROR_DESCRIPTIONS[status],
        "headers": headers,
        "content": {"application/json": {
            "schema": {"$ref": "#/components/schemas/ErrorEnvelope"},
        }},
    }


def _add_search_export_errors(operation: dict[str, Any],
                              statuses: tuple[str, ...]) -> None:
    responses = operation.setdefault("responses", {})
    for status in statuses:
        responses[status] = _search_export_error_response(status)


def _rewrite_schema_refs(value: Any, names: dict[str, str]) -> Any:
    if isinstance(value, dict):
        result = {
            key: _rewrite_schema_refs(item, names)
            for key, item in value.items()
        }
        reference = result.get("$ref")
        prefix = "#/components/schemas/"
        if isinstance(reference, str) and reference.startswith(prefix):
            source = reference.removeprefix(prefix)
            if source in names:
                result["$ref"] = f"{prefix}{names[source]}"
        return result
    if isinstance(value, list):
        return [_rewrite_schema_refs(item, names) for item in value]
    return value


def _dashboard_error_response(status: str) -> dict[str, Any]:
    headers = dict(_PRIVATE_RESPONSE_HEADERS)
    headers["X-Request-Id"] = {
        "description": "Request correlation identifier.",
        "schema": {"type": "string", "minLength": 1, "maxLength": 128},
    }
    if status == "429":
        headers["Retry-After"] = {
            "description": "Minimum seconds before retrying.",
            "schema": {"type": "integer", "minimum": 1},
        }
    return {
        "description": _DASHBOARD_ACTIVITY_ERROR_DESCRIPTIONS[status],
        "headers": headers,
        "content": {"application/json": {"schema": {
            "$ref": "#/components/schemas/DashboardActivityErrorEnvelope",
        }}},
    }


def _configure_dashboard_activity_contract(document: dict[str, Any]) -> None:
    """Publish Feature 06 contracts retained behind strict manual parsers."""
    from ..dashboard_activity.schemas import ErrorEnvelope

    _, definitions = models_json_schema(
        [(ErrorEnvelope, "serialization")],
        ref_template="#/components/schemas/{model}",
    )
    raw_definitions = definitions.get("$defs", {})
    names = {
        name: f"DashboardActivity{name}"
        for name in raw_definitions
    }
    schemas = document.setdefault("components", {}).setdefault("schemas", {})
    schemas.update({
        names[name]: _rewrite_schema_refs(schema, names)
        for name, schema in raw_definitions.items()
    })

    dashboard = document["paths"]["/api/v1/analytics/dashboard"]["get"]
    dashboard["description"] = (
        "Return one tenant-scoped, repeatable-read analytics snapshot. The "
        "optional from/to values must be supplied together as explicit RFC 3339 "
        "instants; unknown or repeated scalar query fields and request bodies "
        "are rejected."
    )
    dashboard["parameters"] = [
        {
            "name": field_name,
            "in": "query",
            "required": False,
            "schema": {"type": "string", "format": "date-time"},
        }
        for field_name in ("from", "to")
    ] + [{
        "name": "bucket",
        "in": "query",
        "required": False,
        "schema": {
            "type": "string",
            "enum": ["day", "week", "month"],
            "default": "day",
        },
    }]
    dashboard["x-query-rules"] = [
        "from and to must be supplied together",
        "from must be earlier than to",
        "the normalized range may not exceed 366 days or 366 buckets",
    ]

    activity = document["paths"]["/api/v1/activity-events"]["get"]
    activity["description"] = (
        "Return a role-filtered stable activity page. Page 1 forbids snapshot_at; "
        "later pages require the exact snapshot_at returned by page 1. Optional "
        "from/to values must be supplied together. Unknown fields, repeated "
        "scalar fields, duplicate event types, and request bodies are rejected."
    )
    event_types = [
        "document_uploaded", "processing_completed", "processing_failed",
        "review_saved", "document_approved", "document_rejected",
        "document_reopened", "export_requested", "export_completed",
        "export_failed", "export_expired",
    ]
    activity["parameters"] = [
        {
            "name": "page", "in": "query", "required": False,
            "schema": {"type": "integer", "minimum": 1, "default": 1},
        },
        {
            "name": "page_size", "in": "query", "required": False,
            "schema": {
                "type": "integer", "minimum": 1, "maximum": 100,
                "default": 20,
            },
        },
        {
            "name": "event_type", "in": "query", "required": False,
            "style": "form", "explode": True,
            "schema": {
                "type": "array", "uniqueItems": True,
                "items": {"type": "string", "enum": event_types},
            },
        },
        *[
            {
                "name": field_name,
                "in": "query",
                "required": False,
                "schema": {"type": "string", "format": "date-time"},
            }
            for field_name in ("from", "to", "snapshot_at")
        ],
    ]
    activity["x-query-rules"] = [
        "from and to must be supplied together",
        "from must be earlier than to and the range may not exceed 366 days",
        "snapshot_at is forbidden on page 1 and required after page 1",
    ]

    success_headers = dict(_PRIVATE_RESPONSE_HEADERS)
    success_headers["X-Request-Id"] = {
        "description": "Request correlation identifier.",
        "schema": {"type": "string", "minLength": 1, "maxLength": 128},
    }
    for operation in (dashboard, activity):
        operation.pop("requestBody", None)
        operation.setdefault("responses", {})["200"]["headers"] = success_headers
        for status in _DASHBOARD_ACTIVITY_ERROR_DESCRIPTIONS:
            operation["responses"][status] = _dashboard_error_response(status)


def _configure_search_export_contract(document: dict[str, Any]) -> None:
    """Publish Feature 05 contracts retained behind strict manual parsers."""
    from ..document_search_export.schemas import (
        CreateExportRequest,
        DocumentSearchRequest,
        ErrorEnvelope,
    )

    _, definitions = models_json_schema(
        [
            (DocumentSearchRequest, "validation"),
            (CreateExportRequest, "validation"),
            (ErrorEnvelope, "serialization"),
        ],
        ref_template="#/components/schemas/{model}",
    )
    schemas = document.setdefault("components", {}).setdefault("schemas", {})
    schemas.update(definitions.get("$defs", {}))

    criteria_fields = (
        "query", "document_statuses", "document_type", "supplier", "currency",
        "invoice_date_from", "invoice_date_to", "uploaded_from", "uploaded_to",
        "min_total", "max_total",
    )
    for name in ("SearchCriteria", "DocumentSearchRequest"):
        criteria_schema = schemas[name]
        criteria_schema["anyOf"] = [
            {"required": [field_name]} for field_name in criteria_fields
        ]
        criteria_schema.setdefault("allOf", []).append({
            "if": {
                "properties": {"sort_by": {"const": "relevance"}},
                "required": ["sort_by"],
            },
            "then": {"required": ["query"]},
        })

    schemas["CreateExportRequest"]["oneOf"] = [
        {"required": ["document_ids"], "not": {"required": ["criteria"]}},
        {"required": ["criteria"], "not": {"required": ["document_ids"]}},
    ]

    paths = document["paths"]
    search = paths["/api/v1/documents/search"]["post"]
    search["requestBody"] = {
        "required": True,
        "content": {"application/json": {
            "schema": {"$ref": "#/components/schemas/DocumentSearchRequest"},
        }},
    }
    _add_search_export_errors(
        search, ("400", "401", "403", "422", "429", "500", "503"),
    )

    direct = paths["/api/v1/documents/export"]["get"]
    direct["description"] = (
        "Compatibility-only synchronous export. Supply repeated document_id "
        "values or structured criteria; semantic query is not accepted."
    )
    direct["parameters"] = [
        {
            "name": "format", "in": "query", "required": True,
            "schema": {"type": "string", "enum": ["csv", "xlsx", "json"]},
        },
        {
            "name": "document_id", "in": "query", "required": False,
            "style": "form", "explode": True,
            "schema": {
                "type": "array", "items": {"type": "string", "format": "uuid"},
                "minItems": 1, "maxItems": 500, "uniqueItems": True,
            },
        },
        {
            "name": "document_statuses", "in": "query", "required": False,
            "style": "form", "explode": True,
            "schema": {
                "type": "array",
                "items": {"type": "string", "enum": [
                    "pending_review", "approved", "rejected",
                ]},
                "minItems": 1, "maxItems": 3, "uniqueItems": True,
            },
        },
        {
            "name": "document_type", "in": "query", "required": False,
            "schema": {"type": "string", "enum": [
                "commercial_invoice", "purchase_order", "packing_list",
            ]},
        },
        {
            "name": "supplier", "in": "query", "required": False,
            "schema": {"type": "string", "minLength": 1, "maxLength": 255},
        },
        {
            "name": "currency", "in": "query", "required": False,
            "schema": {"type": "string", "pattern": r"^[A-Z]{3}$"},
        },
        *[
            {
                "name": field_name, "in": "query", "required": False,
                "schema": {"type": "string", "format": "date"},
            }
            for field_name in ("invoice_date_from", "invoice_date_to")
        ],
        *[
            {
                "name": field_name, "in": "query", "required": False,
                "schema": {"type": "string", "format": "date-time"},
            }
            for field_name in ("uploaded_from", "uploaded_to")
        ],
        *[
            {
                "name": field_name, "in": "query", "required": False,
                "schema": {
                    "type": "string",
                    "pattern": r"^(?:0|[0-9]+)(?:\.[0-9]{1,2})?$",
                },
            }
            for field_name in ("min_total", "max_total")
        ],
        {
            "name": "sort_by", "in": "query", "required": False,
            "description": "relevance is invalid because this route accepts no semantic query.",
            "schema": {"type": "string", "enum": [
                "relevance", "date_issued", "grand_total", "created_at",
            ]},
        },
        {
            "name": "order", "in": "query", "required": False,
            "schema": {"type": "string", "enum": ["asc", "desc"], "default": "desc"},
        },
    ]
    direct["responses"] = {
        "200": _binary_response(
            "Synchronous private export artifact.", _DIRECT_MEDIA, direct=True,
        ),
    }
    _add_search_export_errors(
        direct, ("400", "401", "403", "404", "409", "422", "429", "500", "503"),
    )

    create = paths["/api/v1/exports"]["post"]
    create["requestBody"] = {
        "required": True,
        "content": {"application/json": {
            "schema": {"$ref": "#/components/schemas/CreateExportRequest"},
        }},
    }
    create["parameters"] = [{
        "name": "Idempotency-Key",
        "in": "header",
        "required": False,
        "description": "Visible ASCII key retained for retrying one identical request.",
        "schema": {
            "type": "string", "minLength": 1, "maxLength": 128,
            "pattern": r"^[\x21-\x7E]+$",
        },
    }]
    create["responses"] = {
        "201": {
            "description": "Synchronous export completed.",
            "headers": dict(_PRIVATE_RESPONSE_HEADERS),
            "content": {"application/json": {
                "schema": {"$ref": "#/components/schemas/Success_ExportResource_"},
            }},
        },
        "202": {
            "description": "Asynchronous export accepted.",
            "headers": dict(_PRIVATE_RESPONSE_HEADERS),
            "content": {"application/json": {
                "schema": {"$ref": "#/components/schemas/Success_ExportResource_"},
            }},
        },
    }
    _add_search_export_errors(
        create, ("400", "401", "403", "404", "409", "422", "429", "500", "503"),
    )

    status = paths["/api/v1/exports/{export_id}"]["get"]
    download = paths["/api/v1/exports/{export_id}/download"]["get"]
    for operation in (status, download):
        export_parameter = next(
            row for row in operation.get("parameters", [])
            if row.get("in") == "path" and row.get("name") == "export_id"
        )
        export_parameter["schema"] = {
            "type": "string", "format": "uuid", "title": "Export Id",
        }

    _add_search_export_errors(
        status, ("400", "401", "403", "404", "422", "429", "500", "503"),
    )

    download["responses"] = {
        "200": _binary_response(
            "Private export artifact stream.", _DOWNLOAD_MEDIA,
        ),
        "302": {
            "description": "Redirect to a short-lived private signed artifact URL.",
            "headers": _artifact_headers(redirect=True),
        },
    }
    _add_search_export_errors(
        download,
        ("400", "401", "403", "404", "409", "410", "422", "429", "500", "503"),
    )


def _configure_review_contract(document: dict[str, Any]) -> None:
    """Publish schemas for review routes that retain strict manual body parsing."""
    from ..human_review_audit.schemas import (
        ApproveReviewRequest,
        RejectReviewRequest,
        ReopenReviewRequest,
        ReviewValidationRequest,
        SaveReviewRequest,
    )

    request_models = (
        ReviewValidationRequest,
        SaveReviewRequest,
        ApproveReviewRequest,
        RejectReviewRequest,
        ReopenReviewRequest,
    )
    _, definitions = models_json_schema(
        [(model, "validation") for model in request_models],
        ref_template="#/components/schemas/{model}",
    )
    schemas = document.setdefault("components", {}).setdefault("schemas", {})
    schemas.update(definitions.get("$defs", {}))

    paths = document["paths"]
    preview = paths["/api/v1/documents/{document_id}/review-validations"]["post"]
    preview["requestBody"] = {
        "required": True,
        "content": {"application/json": {
            "schema": {"$ref": "#/components/schemas/ReviewValidationRequest"},
        }},
    }

    mutation = paths["/api/v1/documents/{document_id}/review"]["put"]
    mutation["requestBody"] = {
        "required": True,
        "content": {"application/json": {"schema": {
            "oneOf": [
                {"$ref": f"#/components/schemas/{model.__name__}"}
                for model in request_models[1:]
            ],
            "discriminator": {
                "propertyName": "action",
                "mapping": {
                    "save": "#/components/schemas/SaveReviewRequest",
                    "approve": "#/components/schemas/ApproveReviewRequest",
                    "reject": "#/components/schemas/RejectReviewRequest",
                    "reopen": "#/components/schemas/ReopenReviewRequest",
                },
            },
        }}},
    }
    mutation.setdefault("parameters", []).append({
        "name": "Idempotency-Key",
        "in": "header",
        "required": False,
        "description": "Visible ASCII key retained for retrying one identical mutation.",
        "schema": {
            "type": "string", "minLength": 1, "maxLength": 128,
            "pattern": r"^[\x21-\x7E]+$",
        },
    })

    audit = paths["/api/v1/documents/{document_id}/audit-logs"]["get"]
    audit.setdefault("parameters", []).extend([
        {
            "name": "page", "in": "query", "required": False,
            "schema": {"type": "integer", "minimum": 1, "default": 1},
        },
        {
            "name": "page_size", "in": "query", "required": False,
            "schema": {
                "type": "integer", "minimum": 1, "maximum": 100, "default": 20,
            },
        },
        {
            "name": "action", "in": "query", "required": False,
            "schema": {
                "type": "string",
                "enum": ["field_edited", "approved", "rejected", "reopened"],
            },
        },
    ])

    error_schema = {
        "$ref": "#/components/schemas/app__human_review_audit__schemas__ErrorEnvelope",
    }
    operation_errors = ((preview, _REVIEW_ERROR_DESCRIPTIONS),
                        (mutation, _REVIEW_ERROR_DESCRIPTIONS),
                        (audit, {
                            status: description
                            for status, description in _REVIEW_ERROR_DESCRIPTIONS.items()
                            if status != "409"
                        }))
    for operation, declared_errors in operation_errors:
        responses = operation.setdefault("responses", {})
        for status, description in declared_errors.items():
            responses[status] = {
                "description": description,
                "content": {"application/json": {"schema": error_schema}},
            }


def configure_openapi(app: FastAPI) -> None:
    """Attach resolvable auth schemes and accurate per-operation requirements."""

    def schema() -> dict[str, Any]:
        if app.openapi_schema is not None:
            return app.openapi_schema
        document = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        security_schemes = document.setdefault("components", {}).setdefault(
            "securitySchemes", {},
        )
        security_schemes.update({
            "BearerAuth": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
                "description": "DocuSense access token issued by POST /api/v1/auth/login.",
            },
            "ApiKeyAuth": {
                "type": "apiKey",
                "in": "header",
                "name": "X-API-Key",
                "description": "Company-scoped API key accepted only by ingestion reads/writes.",
            },
        })
        _configure_search_export_contract(document)
        _configure_review_contract(document)
        _configure_dashboard_activity_contract(document)
        for path, item in document.get("paths", {}).items():
            for method, operation in item.items():
                if method not in _METHODS or not isinstance(operation, dict):
                    continue
                if path == "/api/v1/auth/login":
                    operation["security"] = []
                elif path in _DUAL_AUTH_PATHS:
                    operation.setdefault("security", [
                        {"BearerAuth": []}, {"ApiKeyAuth": []},
                    ])
                else:
                    operation.setdefault("security", [{"BearerAuth": []}])
        app.openapi_schema = document
        return document

    app.openapi = schema  # type: ignore[method-assign]


__all__ = ["configure_openapi"]
