"""Deterministic evidence-first field and document confidence scoring."""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from .schemas import (
    FieldEvidenceDraft, InvoiceCandidate, RuleResult, ValidationBundle,
)
from .validation import build_evidence, validate_rules

WEIGHTS: dict[str, Decimal] = {
    "invoice.invoice_number": Decimal("15"),
    "invoice.supplier_name": Decimal("15"),
    "invoice.date_issued": Decimal("10"),
    "invoice.currency": Decimal("10"),
    "invoice.subtotal": Decimal("10"),
    "invoice.tax_amount": Decimal("5"),
    "invoice.discount_amount": Decimal("5"),
    "invoice.grand_total": Decimal("30"),
}


def _field_score(row: FieldEvidenceDraft) -> tuple[Decimal, tuple[str, ...]]:
    if row.validation_state in ("missing", "unsupported"):
        return Decimal("0.00"), ("NO_SUPPORTED_VALUE",)
    reasons: list[str] = []
    score = Decimal("0")
    if row.primary_chunk_id is not None:
        score += 50
        reasons.append("SOURCE_EVIDENCE_LINKED")
    else:
        reasons.append("SOURCE_EVIDENCE_MISSING")
    if row.exact_match:
        score += 25
        reasons.append("EXACT_SOURCE_MATCH")
    if row.retrieval_score is not None:
        score += ((row.retrieval_score + Decimal("1")) / Decimal("2")) * Decimal("15")
        reasons.append("RETRIEVAL_SCORE_APPLIED")
    if row.validation_state == "valid":
        score += 10
        reasons.append("FIELD_VALID")
    else:
        reasons.append("FIELD_INVALID_OR_AMBIGUOUS")
    return min(Decimal("100"), max(Decimal("0"), score)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), tuple(reasons)


def score_invoice(invoice: InvoiceCandidate) -> ValidationBundle:
    rules, math_valid = validate_rules(invoice)
    evidence: list[FieldEvidenceDraft] = []
    scores: dict[str, Decimal] = {}
    for row in build_evidence(invoice):
        score, reasons = _field_score(row)
        evidence.append(row.model_copy(update={"confidence_score": score, "reason_codes": reasons}))
        scores[row.field_path] = score

    weighted = sum((scores.get(path, Decimal("0")) * weight for path, weight in WEIGHTS.items()), Decimal("0")) / Decimal("100")
    penalty = Decimal("0")
    math_failed = any(rule.rule_id.startswith("BR-03") and rule.status == "failed" for rule in rules)
    if math_failed:
        penalty += 35
    if invoice.invoice_number is None:
        penalty += 30
    if invoice.date_issued is None:
        penalty += 20
    if invoice.grand_total is None:
        penalty += 40
    if invoice.supplier_name is None:
        penalty += 15
    document_score = min(Decimal("100"), max(Decimal("0"), weighted - penalty)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    return ValidationBundle(invoice=invoice, rules=rules, evidence=tuple(evidence),
                            document_confidence=document_score, is_math_valid=math_valid)


def summarize_rules(rules: tuple[RuleResult, ...]) -> dict[str, int]:
    counts = {"passed": 0, "failed": 0, "missing": 0, "not_applicable": 0}
    for rule in rules:
        counts[rule.status] += 1
    return counts
