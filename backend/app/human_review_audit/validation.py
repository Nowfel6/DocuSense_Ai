"""Deterministic BR-02/BR-03 review validation using Decimal only."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from .diff import candidate_hash
from .schemas import (
    InvoiceCandidate,
    PreviewLineItem,
    ResolvedCandidate,
    ResolvedLineCandidate,
    RuleResult,
    ValidationBundle,
    ValidationSummary,
)

EPSILON = Decimal("0.050000")


class UnsupportedCurrencyError(ValueError):
    """Raised only when a supplied currency is outside the configured allow-list."""


def _safe(value: Decimal | date | str | int | bool | None) -> str | int | bool | None:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, date):
        return value.isoformat()
    return value


def _result(rule_id: str, scope: str, status: str, observed: object,
            expected: object, *, blocks: bool, difference: Decimal | None = None,
            epsilon: Decimal | None = None) -> RuleResult:
    return RuleResult(
        rule_id=rule_id,
        scope_key=scope,
        status=status,
        observed_value=_safe(observed),
        expected_value=_safe(expected),
        difference=difference,
        epsilon=epsilon,
        message_code=f"{rule_id}.{status.upper()}",
        blocks_approval=blocks,
    )


def _present(rule_id: str, scope: str, value: object) -> RuleResult:
    present = value is not None
    return _result(rule_id, scope, "passed" if present else "missing", value,
                   "present", blocks=True)


def _compare(rule_id: str, scope: str, observed: Decimal | None,
             expected: Decimal | None) -> RuleResult:
    if observed is None or expected is None:
        return _result(rule_id, scope, "missing", observed, expected,
                       blocks=True, difference=None, epsilon=None)
    difference = abs(observed - expected)
    status = "passed" if difference <= EPSILON else "failed"
    return _result(rule_id, scope, status, observed, expected, blocks=True,
                   difference=difference, epsilon=EPSILON)


def compare_amounts(observed: Decimal | None, expected: Decimal | None) -> RuleResult:
    """Expose the exact inclusive-epsilon comparison for focused contract tests."""
    return _compare("BR-03.TEST.v1", "document", observed, expected)


def _line_scope(line: ResolvedLineCandidate, persisted: bool) -> str:
    if not persisted and line.client_correlation_key is not None:
        return f"client:{line.client_correlation_key}"
    return f"line_items.{line.line_item_id}"


def calculate(candidate: ResolvedCandidate) -> tuple[tuple[Decimal | None, ...],
                                                       Decimal | None, Decimal | None]:
    line_totals = tuple(
        None if line.quantity is None or line.unit_price is None
        else line.quantity * line.unit_price
        for line in candidate.line_items
    )
    subtotal = None
    if candidate.line_items and all(line.total_price is not None for line in candidate.line_items):
        subtotal = sum((line.total_price for line in candidate.line_items
                        if line.total_price is not None), Decimal("0"))
    invoice = candidate.invoice
    grand_total = None
    if invoice.subtotal is not None and invoice.tax_amount is not None and invoice.discount_amount is not None:
        grand_total = invoice.subtotal + invoice.tax_amount - invoice.discount_amount
    return line_totals, subtotal, grand_total


def validate_candidate(candidate: ResolvedCandidate,
                       supported_currencies: frozenset[str], *,
                       persisted: bool = True) -> ValidationBundle:
    invoice = candidate.invoice
    results: list[RuleResult] = [
        _present("BR-02.INVOICE_NUMBER.v1", "invoice.invoice_number", invoice.invoice_number),
        _present("BR-02.SUPPLIER_NAME.v1", "invoice.supplier_name", invoice.supplier_name),
        _present("BR-02.DATE_ISSUED.v1", "invoice.date_issued", invoice.date_issued),
        _present("BR-02.GRAND_TOTAL.v1", "invoice.grand_total", invoice.grand_total),
    ]
    if invoice.currency is None:
        results.append(_result("BR-02.CURRENCY.v1", "invoice.currency",
                               "not_applicable", None, None, blocks=False))
    else:
        if invoice.currency not in supported_currencies:
            raise UnsupportedCurrencyError("Unsupported currency")
        results.append(_result("BR-02.CURRENCY.v1", "invoice.currency",
                               "passed", invoice.currency,
                               "supported ISO 4217", blocks=False))

    line_calculated, subtotal_calculated, total_calculated = calculate(candidate)
    valid_lines = 0
    for line, calculated in zip(candidate.line_items, line_calculated):
        complete = all(value is not None for value in (
            line.description, line.quantity, line.unit_price, line.total_price,
        ))
        if complete:
            valid_lines += 1
        scope = _line_scope(line, persisted)
        results.append(_result("BR-02.LINE_REQUIRED.v1", scope,
                               "passed" if complete else "missing",
                               "complete" if complete else "incomplete", "complete",
                               blocks=True))
        results.append(_compare("BR-03.LINE_TOTAL.v1", f"{scope}.total_price",
                                line.total_price, calculated))

    results.append(_result("BR-02.LINE_PRESENT.v1", "document",
                           "passed" if valid_lines > 0 else "missing",
                           valid_lines, ">=1", blocks=True))
    results.append(_compare("BR-03.SUBTOTAL.v1", "invoice.subtotal",
                            invoice.subtotal, subtotal_calculated))
    results.append(_compare("BR-03.GRAND_TOTAL.v1", "invoice.grand_total",
                            invoice.grand_total, total_calculated))
    results.sort(key=lambda row: (row.rule_id, row.scope_key))

    financial = [row for row in results if row.rule_id.startswith("BR-03.")]
    is_math_valid = bool(financial) and all(row.status == "passed" for row in financial)
    blocking = tuple(row.message_code for row in results
                     if row.blocks_approval and row.status in ("failed", "missing"))
    counts = {status: sum(row.status == status for row in results)
              for status in ("passed", "failed", "missing", "not_applicable")}
    return ValidationBundle(
        candidate_hash=candidate_hash(candidate),
        is_math_valid=is_math_valid,
        approval_eligible=not blocking and is_math_valid,
        summary=ValidationSummary(**counts),
        results=tuple(results),
        blocking_reasons=blocking,
    )


def preview_lines(candidate: ResolvedCandidate) -> tuple[PreviewLineItem, ...]:
    calculated, _, _ = calculate(candidate)
    return tuple(PreviewLineItem(
        line_item_id=line.line_item_id if line.client_correlation_key is None else None,
        client_correlation_key=line.client_correlation_key,
        origin=line.origin,
        line_order=line.line_order,
        description=line.description,
        hs_code=line.hs_code,
        quantity=line.quantity,
        unit_price=line.unit_price,
        tax_amount=line.tax_amount,
        total_price=line.total_price,
        calculated_total_price=None if value is None else value.quantize(Decimal("0.01")),
    ) for line, value in zip(candidate.line_items, calculated))


def preview_candidate(invoice: InvoiceCandidate, lines: tuple[ResolvedLineCandidate, ...],
                      revision: int, supported_currencies: frozenset[str]):
    from .schemas import PreviewData

    candidate = ResolvedCandidate(invoice=invoice, line_items=lines)
    _, subtotal, grand_total = calculate(candidate)
    return PreviewData(
        review_revision=revision,
        invoice=invoice,
        line_items=preview_lines(candidate),
        calculated_subtotal=None if subtotal is None else subtotal.quantize(Decimal("0.01")),
        calculated_grand_total=None if grand_total is None else grand_total.quantize(Decimal("0.01")),
        validation=validate_candidate(candidate, supported_currencies, persisted=False).public(),
    )
