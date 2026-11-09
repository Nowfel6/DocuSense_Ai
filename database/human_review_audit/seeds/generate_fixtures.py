"""Deterministic synthetic database-only fixtures for human review/audit."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

TENANT_A = "11111111-1111-1111-1111-111111111111"
TENANT_B = "11111111-1111-1111-1111-222222222222"
ADMIN_A = "22222222-2222-2222-2222-222222222222"
OPERATOR_A = "33333333-3333-3333-3333-333333333333"
OPERATOR_B = "33333333-3333-4333-8333-444444444444"

DOC_A = "66666666-6666-4666-8666-000000000003"
DOC_B = "66666666-6666-4666-8666-000000000005"
DOC_C = "66666666-6666-4666-8666-000000000006"
DOC_D = "66666666-6666-4666-8666-000000000001"
INVOICE_A = "aaaaaaaa-aaaa-4aaa-8aaa-000000000001"
INVOICE_B = "aaaaaaaa-aaaa-4aaa-8aaa-000000000002"
INVOICE_C = "aaaaaaaa-aaaa-4aaa-8aaa-000000000003"
INVOICE_D = "aaaaaaaa-aaaa-4aaa-8aaa-000000000004"
MANUAL_LINE_A = "b0000000-bbbb-4bbb-8bbb-000000000099"

VALIDATION_VERSION = "review-validation-v1"
T0 = datetime(2026, 9, 6, 9, 0, tzinfo=timezone.utc)


def sha(value: object) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def event_id(number: int) -> str:
    return f"e1000000-0000-4000-8000-{number:012d}"


def change_id(number: int) -> str:
    return f"c1000000-0000-4000-8000-{number:012d}"


def run_id(number: int) -> str:
    return f"a1000000-0000-4000-8000-{number:012d}"


def result_id(number: int) -> str:
    return f"d1000000-0000-4000-8000-{number:012d}"


def idem_id(number: int) -> str:
    return f"f1000000-0000-4000-8000-{number:012d}"


def fixture_payload() -> dict:
    definitions = [
        (DOC_A, ADMIN_A, "field_edited", "pending_review", "pending_review", None, "Corrected supplier and line order"),
        (DOC_A, ADMIN_A, "approved", "pending_review", "approved", None, "Verified against source"),
        (DOC_A, ADMIN_A, "reopened", "approved", "pending_review", "Supplier correction required", None),
        (DOC_A, OPERATOR_A, "field_edited", "pending_review", "pending_review", None, "Corrected quantity"),
        (DOC_A, ADMIN_A, "approved", "pending_review", "approved", None, "Final approval"),
        (DOC_B, OPERATOR_A, "rejected", "pending_review", "rejected", "Required invoice number is absent", None),
        (DOC_C, OPERATOR_B, "field_edited", "pending_review", "pending_review", None, "Corrected currency"),
        (DOC_C, OPERATOR_B, "approved", "pending_review", "approved", None, "Tenant B approval"),
        (DOC_D, ADMIN_A, "field_edited", "pending_review", "pending_review", None, "Verified export boundary source"),
        (DOC_D, ADMIN_A, "approved", "pending_review", "approved", None, "Export boundary approval"),
    ]
    revisions = {DOC_A: 0, DOC_B: 0, DOC_C: 0, DOC_D: 0}
    events = []
    for number, (document, actor, action, from_status, to_status, reason, note) in enumerate(definitions, 1):
        revisions[document] += 1
        request = {
            "document_id": document,
            "actor_user_id": actor,
            "action": action,
            "review_revision": revisions[document],
        }
        events.append(
            dict(
                id=event_id(number),
                document_id=document,
                actor_user_id=actor,
                action=action,
                from_status=from_status,
                to_status=to_status,
                review_revision=revisions[document],
                reason=reason,
                note=note,
                request_id=f"fixture-review-{number:02d}",
                payload_hash=sha(request),
                created_at=(T0 + timedelta(minutes=number)).isoformat(),
            )
        )

    changes = [
        dict(id=change_id(1), audit_event_id=event_id(1), field_path="invoice.supplier_name",
             change_kind="set", old_value="Synthetic Supplier", new_value="Synthetic Supplier Ltd"),
        dict(id=change_id(2), audit_event_id=event_id(1), field_path=f"line_items.{MANUAL_LINE_A}",
             change_kind="add", old_value=None,
             new_value={"description": "Review fee", "quantity": "1.0000", "unit_price": "5.0000",
                        "tax_amount": "0.00", "total_price": "5.00", "line_order": 4}),
        dict(id=change_id(3), audit_event_id=event_id(1), field_path="document.status",
             change_kind="set", old_value="pending_review", new_value="pending_review"),
        dict(id=change_id(4), audit_event_id=event_id(4),
             field_path="invoice.grand_total", change_kind="set", old_value="126.00", new_value="131.00"),
        dict(id=change_id(5), audit_event_id=event_id(7),
             field_path="invoice.currency", change_kind="set", old_value="BDT", new_value="USD"),
        dict(id=change_id(6), audit_event_id=event_id(9),
             field_path="invoice.supplier_name", change_kind="set",
             old_value="Synthetic Export Supplier", new_value="Synthetic Export Supplier Ltd"),
    ]
    # A no-op set is invalid; use a real deterministic reorder for the third change.
    changes[2] = dict(
        id=change_id(3), audit_event_id=event_id(1), field_path="line_items." + MANUAL_LINE_A + ".line_order",
        change_kind="set", old_value=3, new_value=4,
    )

    validated_events = [1, 2, 4, 5, 7, 8, 9, 10]
    runs = []
    results = []
    result_number = 0
    for number, event_number in enumerate(validated_events, 1):
        event = events[event_number - 1]
        eligible = event_number not in {4}
        math_valid = event_number not in {4}
        run = dict(
            id=run_id(number), audit_event_id=event["id"], document_id=event["document_id"],
            review_revision=event["review_revision"], validation_version=VALIDATION_VERSION,
            candidate_hash=sha({"document_id": event["document_id"], "event": event_number}),
            is_math_valid=math_valid, approval_eligible=eligible, created_at=event["created_at"],
        )
        runs.append(run)
        states = [
            ("BR-02-REQUIRED", "document", "passed", "REQUIRED_FIELDS_PRESENT", False, None, None),
            ("BR-03-TOTAL", "document", "passed" if math_valid else "failed",
             "TOTAL_RECONCILED" if math_valid else "TOTAL_MISMATCH", not math_valid,
             "0.000000" if math_valid else "5.000000", "0.050000"),
        ]
        for rule, scope, status, message, blocks, difference, epsilon in states:
            result_number += 1
            results.append(
                dict(
                    id=result_id(result_number), review_validation_run_id=run["id"], rule_id=rule,
                    scope_key=scope, status=status, observed_value="131.00", expected_value="131.00",
                    difference=difference, epsilon=epsilon, message_code=message,
                    blocks_approval=blocks, created_at=event["created_at"],
                )
            )
    results.extend([
        dict(id=result_id(result_number + 1), review_validation_run_id=run_id(1),
             rule_id="BR-02-TAX-ID", scope_key="invoice.supplier_tax_id", status="missing",
             observed_value=None, expected_value=None, difference=None, epsilon=None,
             message_code="FIELD_NOT_PRESENT", blocks_approval=False, created_at=events[0]["created_at"]),
        dict(id=result_id(result_number + 2), review_validation_run_id=run_id(1),
             rule_id="BR-02-DUE-DATE", scope_key="invoice.due_date", status="not_applicable",
             observed_value=None, expected_value=None, difference=None, epsilon=None,
             message_code="RULE_NOT_APPLICABLE", blocks_approval=False, created_at=events[0]["created_at"]),
    ])

    owners = {
        DOC_A: (TENANT_A, ADMIN_A),
        DOC_B: (TENANT_A, OPERATOR_A),
        DOC_C: (TENANT_B, OPERATOR_B),
        DOC_D: (TENANT_A, ADMIN_A),
    }
    idempotency = []
    for number, event in enumerate(events, 1):
        tenant, _ = owners[event["document_id"]]
        idempotency.append(
            dict(
                id=idem_id(number), company_id=tenant, actor_user_id=event["actor_user_id"],
                document_id=event["document_id"], idempotency_key=f"fixture-key-{number:02d}",
                request_hash=event["payload_hash"], audit_event_id=event["id"], response_status=200,
                response_body={"audit_event_id": event["id"], "review_revision": event["review_revision"],
                               "status": event["to_status"]},
                created_at=event["created_at"], updated_at=event["created_at"],
                expires_at=(datetime.fromisoformat(event["created_at"]) + timedelta(hours=24)).isoformat(),
            )
        )

    return {
        "scope": "DATABASE_ONLY",
        "version": 1,
        "required_parents": [
            {"company_id": TENANT_A, "actor_user_id": ADMIN_A, "document_id": DOC_A, "invoice_id": INVOICE_A},
            {"company_id": TENANT_A, "actor_user_id": OPERATOR_A, "document_id": DOC_B, "invoice_id": INVOICE_B},
            {"company_id": TENANT_B, "actor_user_id": OPERATOR_B, "document_id": DOC_C, "invoice_id": INVOICE_C},
            {"company_id": TENANT_A, "actor_user_id": ADMIN_A, "document_id": DOC_D, "invoice_id": INVOICE_D},
        ],
        "document_final": [
            {"document_id": DOC_A, "status": "approved", "review_revision": 5,
             "last_reviewed_by": ADMIN_A, "last_reviewed_at": events[4]["created_at"]},
            {"document_id": DOC_B, "status": "rejected", "review_revision": 1,
             "last_reviewed_by": OPERATOR_A, "last_reviewed_at": events[5]["created_at"]},
            {"document_id": DOC_C, "status": "approved", "review_revision": 2,
             "last_reviewed_by": OPERATOR_B, "last_reviewed_at": events[7]["created_at"]},
            {"document_id": DOC_D, "status": "approved", "review_revision": 2,
             "last_reviewed_by": ADMIN_A, "last_reviewed_at": events[9]["created_at"]},
        ],
        "current_mutations": {
            "invoice_updates": [
                {"invoice_id": INVOICE_A, "event_id": event_id(1), "supplier_name": "Synthetic Supplier Ltd"},
                {"invoice_id": INVOICE_A, "event_id": event_id(4), "grand_total": "131.00"},
                {"invoice_id": INVOICE_C, "event_id": event_id(7), "currency": "USD"},
                {"invoice_id": INVOICE_D, "event_id": event_id(9),
                 "supplier_name": "Synthetic Export Supplier Ltd"},
            ],
            "manual_lines": [
                {"id": MANUAL_LINE_A, "invoice_id": INVOICE_A, "event_id": event_id(1),
                 "source_row_key": f"manual:{MANUAL_LINE_A}", "line_order": 4,
                 "description": "Review fee", "hs_code": None, "quantity": "1.0000",
                 "unit_price": "5.0000", "tax_amount": "0.00", "total_price": "5.00",
                 "created_at": events[0]["created_at"], "updated_at": events[0]["created_at"],
                 "origin": "reviewer_added"}
            ],
        },
        "events": events,
        "changes": changes,
        "validation_runs": runs,
        "validation_results": results,
        "idempotency": idempotency,
    }


