"""Canonical JSON hashing and null-aware human-review diffs."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import hashlib
import json
from typing import TypeAlias
from uuid import UUID

from pydantic import BaseModel

from .schemas import (
    AuditChange,
    CandidatePayload,
    ResolvedCandidate,
    ReviewInvoice,
    ReviewLineItem,
)

Canonical: TypeAlias = str | int | bool | None | list["Canonical"] | dict[str, "Canonical"]
INVOICE_FIELDS = (
    "invoice_number", "supplier_name", "supplier_tax_id", "buyer_name",
    "date_issued", "due_date", "currency", "subtotal", "tax_amount",
    "discount_amount", "grand_total",
)
LINE_FIELDS = (
    "description", "hs_code", "quantity", "unit_price", "tax_amount",
    "total_price", "line_order",
)


def canonical_value(value: object) -> Canonical:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value).lower()
    if isinstance(value, BaseModel):
        return canonical_value(value.model_dump(mode="python", exclude_none=False))
    if isinstance(value, tuple):
        return [canonical_value(item) for item in value]
    if isinstance(value, list):
        return [canonical_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): canonical_value(value[key]) for key in sorted(value)}
    raise TypeError(f"Unsupported canonical value type: {type(value).__name__}")


def canonical_json(value: object) -> str:
    return json.dumps(canonical_value(value), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)


def sha256(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def request_hash(request: object) -> str:
    return sha256(request)


def candidate_hash(candidate: ResolvedCandidate) -> str:
    return sha256({
        "invoice": candidate.invoice,
        "line_items": [{
            "line_item_id": line.line_item_id,
            "origin": line.origin,
            **{field: getattr(line, field) for field in LINE_FIELDS},
        } for line in candidate.line_items],
    })


def _line_value(line: ReviewLineItem | object, field: str) -> Canonical:
    return canonical_value(getattr(line, field))


def _whole_line(line: ReviewLineItem | object) -> dict[str, Canonical]:
    return {
        "line_item_id": canonical_value(getattr(line, "line_item_id")),
        "origin": canonical_value(getattr(line, "origin")),
        **{field: _line_value(line, field) for field in LINE_FIELDS},
    }


def build_changes(current: ReviewInvoice, candidate: ResolvedCandidate) -> tuple[AuditChange, ...]:
    changes: list[AuditChange] = []
    for field in INVOICE_FIELDS:
        old = canonical_value(getattr(current, field))
        new = canonical_value(getattr(candidate.invoice, field))
        if old != new:
            changes.append(AuditChange(field_path=f"invoice.{field}", change_kind="set",
                                       old_value=old, new_value=new))

    old_lines = {line.line_item_id: line for line in current.line_items}
    new_lines = {line.line_item_id: line for line in candidate.line_items}
    for line_id in sorted(old_lines.keys() - new_lines.keys(), key=str):
        changes.append(AuditChange(field_path=f"line_items.{line_id}", change_kind="remove",
                                   old_value=_whole_line(old_lines[line_id]), new_value=None))
    for line_id in sorted(new_lines.keys() - old_lines.keys(), key=str):
        changes.append(AuditChange(field_path=f"line_items.{line_id}", change_kind="add",
                                   old_value=None, new_value=_whole_line(new_lines[line_id])))
    for line_id in sorted(old_lines.keys() & new_lines.keys(), key=str):
        old_line, new_line = old_lines[line_id], new_lines[line_id]
        for field in LINE_FIELDS:
            old = _line_value(old_line, field)
            new = _line_value(new_line, field)
            if old != new:
                changes.append(AuditChange(
                    field_path=f"line_items.{line_id}.{field}", change_kind="set",
                    old_value=old, new_value=new,
                ))
    return tuple(sorted(changes, key=lambda row: (row.field_path, row.change_kind)))


def client_request_payload(action: str, expected_revision: int,
                           candidate: CandidatePayload | None, note: str | None,
                           reason: str | None) -> dict[str, Canonical]:
    return {
        "action": action,
        "candidate": canonical_value(candidate),
        "expected_review_revision": expected_revision,
        "note": note,
        "reason": reason,
    }
