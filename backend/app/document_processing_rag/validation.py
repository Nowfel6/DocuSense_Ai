"""Deterministic invoice rules using exact Decimal arithmetic."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from .schemas import (
    CandidateEvidence, FieldEvidenceDraft, InvoiceCandidate, RuleResult,
)

EPSILON = Decimal("0.050000")
HEADER_PATHS = (
    "invoice.invoice_number", "invoice.supplier_name", "invoice.supplier_tax_id",
    "invoice.buyer_name", "invoice.date_issued", "invoice.due_date",
    "invoice.currency", "invoice.subtotal", "invoice.tax_amount",
    "invoice.discount_amount", "invoice.grand_total",
)


def _safe(value: Decimal | date | str | int | bool | None) -> str | int | bool | None:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, date):
        return value.isoformat()
    return value


def _comparison(rule_id: str, scope: str, observed: Decimal | None,
                expected: Decimal | None, message: str) -> RuleResult:
    if observed is None or expected is None:
        return RuleResult(rule_id=rule_id, scope_key=scope, status="missing",
                          observed_value=_safe(observed), expected_value=_safe(expected),
                          difference=None, epsilon=EPSILON, message_code=f"{message}_MISSING")
    difference = abs(observed - expected)
    passed = difference <= EPSILON
    return RuleResult(rule_id=rule_id, scope_key=scope,
                      status="passed" if passed else "failed",
                      observed_value=_safe(observed), expected_value=_safe(expected),
                      difference=difference, epsilon=EPSILON,
                      message_code=f"{message}_{'PASSED' if passed else 'FAILED'}")


def validate_rules(invoice: InvoiceCandidate) -> tuple[tuple[RuleResult, ...], bool]:
    results: list[RuleResult] = []
    financial: list[RuleResult] = []
    for line in invoice.line_items:
        expected = None if line.quantity is None or line.unit_price is None else line.quantity * line.unit_price
        result = _comparison("BR-03-LINE", f"line_items.{line.source_row_key}",
                             line.total_price, expected, "LINE_TOTAL")
        results.append(result)
        financial.append(result)

    expected_subtotal = None
    if invoice.line_items and all(line.total_price is not None for line in invoice.line_items):
        expected_subtotal = sum((line.total_price for line in invoice.line_items if line.total_price is not None), Decimal("0"))
    subtotal = _comparison("BR-03-SUBTOTAL", "invoice.subtotal", invoice.subtotal,
                           expected_subtotal, "SUBTOTAL")
    results.append(subtotal)
    financial.append(subtotal)

    expected_total = None
    if invoice.subtotal is not None and invoice.tax_amount is not None and invoice.discount_amount is not None:
        expected_total = invoice.subtotal + invoice.tax_amount - invoice.discount_amount
    total = _comparison("BR-03-GRAND-TOTAL", "invoice.grand_total",
                        invoice.grand_total, expected_total, "GRAND_TOTAL")
    results.append(total)
    financial.append(total)

    required = {
        "invoice.invoice_number": invoice.invoice_number,
        "invoice.supplier_name": invoice.supplier_name,
        "invoice.date_issued": invoice.date_issued,
        "invoice.grand_total": invoice.grand_total,
    }
    for path, value in required.items():
        present = value is not None
        results.append(RuleResult(
            rule_id="BR-02-REQUIRED", scope_key=path,
            status="passed" if present else "missing", observed_value=_safe(value),
            expected_value="present", difference=None, epsilon=None,
            message_code="REQUIRED_PRESENT" if present else "REQUIRED_MISSING",
        ))

    supplied = {item.field_path: item for item in invoice.evidence}
    critical = {
        "invoice.invoice_number": invoice.invoice_number,
        "invoice.supplier_name": invoice.supplier_name,
        "invoice.date_issued": invoice.date_issued,
        "invoice.currency": invoice.currency,
        "invoice.subtotal": invoice.subtotal,
        "invoice.tax_amount": invoice.tax_amount,
        "invoice.discount_amount": invoice.discount_amount,
        "invoice.grand_total": invoice.grand_total,
    }
    for path, value in critical.items():
        source = supplied.get(path)
        if value is None:
            status = "not_applicable"
            code = "EVIDENCE_NOT_APPLICABLE"
        elif source is not None and source.primary_chunk_id is not None:
            status = "passed"
            code = "EVIDENCE_LINKED"
        else:
            status = "failed"
            code = "EVIDENCE_MISSING"
        results.append(RuleResult(rule_id="BR-04-EVIDENCE", scope_key=path,
                                  status=status, observed_value=_safe(value),
                                  expected_value="source_reference", difference=None,
                                  epsilon=None, message_code=code))

    is_math_valid = bool(financial) and all(result.status == "passed" for result in financial)
    return tuple(results), is_math_valid


def build_evidence(invoice: InvoiceCandidate) -> tuple[FieldEvidenceDraft, ...]:
    supplied = {item.field_path: item for item in invoice.evidence}
    values: dict[str, Decimal | date | str | None] = {
        "invoice.invoice_number": invoice.invoice_number,
        "invoice.supplier_name": invoice.supplier_name,
        "invoice.supplier_tax_id": invoice.supplier_tax_id,
        "invoice.buyer_name": invoice.buyer_name,
        "invoice.date_issued": invoice.date_issued,
        "invoice.due_date": invoice.due_date,
        "invoice.currency": invoice.currency,
        "invoice.subtotal": invoice.subtotal,
        "invoice.tax_amount": invoice.tax_amount,
        "invoice.discount_amount": invoice.discount_amount,
        "invoice.grand_total": invoice.grand_total,
    }
    for line in invoice.line_items:
        # Canonical line-items paths use the 1-based ordinal (`line_items.1.description`,
        # not `line_items.row-1.description`) so the LLM's emitted paths line up with
        # the values we cross-check here.
        prefix = f"line_items.{line.line_order}"
        values.update({
            f"{prefix}.description": line.description,
            f"{prefix}.hs_code": line.hs_code,
            f"{prefix}.quantity": line.quantity,
            f"{prefix}.unit_price": line.unit_price,
            f"{prefix}.tax_amount": line.tax_amount,
            f"{prefix}.total_price": line.total_price,
        })
    unknown = set(supplied).difference(values)
    if unknown:
        raise ValueError("Evidence contains an unknown canonical field path")
    rows: list[FieldEvidenceDraft] = []
    for path, value in values.items():
        source: CandidateEvidence | None = supplied.get(path)
        normalized = _safe(value)
        if value is None:
            state = "missing"
            # Missing canonical values must not retain misleading source support.
            source = None
        elif source is None or source.primary_chunk_id is None:
            state = "invalid"
        else:
            state = "valid"
        rows.append(FieldEvidenceDraft(
            field_path=path,
            source_value=None if source is None else source.source_value,
            normalized_value=normalized,
            primary_chunk_id=None if source is None else source.primary_chunk_id,
            source_page=None if source is None else source.source_page,
            bounding_box=None if source is None else source.bounding_box,
            evidence_excerpt=None if source is None else source.evidence_excerpt,
            retrieval_rank=None if source is None else source.retrieval_rank,
            retrieval_score=None if source is None else source.retrieval_score,
            exact_match=False if source is None else source.exact_match,
            confidence_score=Decimal("0"), reason_codes=(), validation_state=state,
        ))
    return tuple(rows)
