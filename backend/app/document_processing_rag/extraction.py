"""Strict LLM boundary plus evidence-preserving value normalization."""
from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal, InvalidOperation
import json
import re
import unicodedata
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError, model_validator
from typing_extensions import Annotated

from .errors import ProcessingError
from .schemas import CandidateEvidence, InvoiceCandidate, InvoiceLineCandidate


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RawLine(StrictModel):
    source_row_key: str = Field(min_length=1, max_length=128)
    line_order: int = Field(strict=True, ge=1)
    description: str | None = Field(default=None, max_length=32768)
    hs_code: str | None = Field(default=None, max_length=50)
    quantity: str | None = None
    unit_price: str | None = None
    tax_amount: str | None = None
    total_price: str | None = None


FIELD_PATH_PATTERN = r"^[a-z][a-z0-9_]*(?:\.[A-Za-z0-9_-]+)+$"


class RawEvidence(StrictModel):
    field_path: Annotated[str, StringConstraints(
        min_length=1, max_length=255, pattern=FIELD_PATH_PATTERN,
    )]
    source_value: str | None = Field(default=None, max_length=2000)
    primary_chunk_id: str | None = None
    source_page: int | None = Field(default=None, ge=1)
    evidence_excerpt: str | None = Field(default=None, max_length=1000)
    retrieval_rank: int | None = Field(default=None, ge=1)
    retrieval_score: Decimal | None = Field(default=None, ge=-1, le=1, allow_inf_nan=False)
    exact_match: bool = False


class RawInvoice(StrictModel):
    invoice_number: str | None = Field(default=None, max_length=100)
    supplier_name: str | None = Field(default=None, max_length=255)
    supplier_tax_id: str | None = Field(default=None, max_length=100)
    buyer_name: str | None = Field(default=None, max_length=255)
    date_issued: str | None = Field(default=None, max_length=10)
    due_date: str | None = Field(default=None, max_length=10)
    currency: str | None = Field(default=None, max_length=3)
    subtotal: str | None = Field(default=None, max_length=64)
    tax_amount: str | None = Field(default=None, max_length=64)
    discount_amount: str | None = Field(default=None, max_length=64)
    grand_total: str | None = Field(default=None, max_length=64)
    line_items: tuple[RawLine, ...] = Field(max_length=2000)
    evidence: tuple[RawEvidence, ...] = Field(max_length=4096)

    @model_validator(mode="after")
    def unique_rows_and_paths(self) -> "RawInvoice":
        row_keys = [line.source_row_key for line in self.line_items]
        orders = [line.line_order for line in self.line_items]
        paths = [item.field_path for item in self.evidence]
        if len(row_keys) != len(set(row_keys)) or len(orders) != len(set(orders)) or len(paths) != len(set(paths)):
            raise ValueError("Line identities and evidence paths must be unique")
        return self


class LLMProvider(Protocol):
    async def extract(self, evidence: str, schema_version: str, corrective: bool) -> str:
        """Return schema-only JSON; evidence is untrusted content, never instructions."""
        ...


def _text(value: str | None, maximum: int) -> str | None:
    if value is None:
        return None
    cleaned = unicodedata.normalize("NFC", value).strip()
    if not cleaned or cleaned.casefold() in {"n/a", "none", "null", "unknown", "-"}:
        return None
    if len(cleaned) > maximum:
        raise ValueError("Text exceeds field limit")
    return cleaned


def _date(value: str | None) -> date | None:
    cleaned = _text(value, 10)
    if cleaned is None:
        return None
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", cleaned):
        raise ValueError("Date must be ISO-8601")
    return date.fromisoformat(cleaned)


def _decimal(value: str | None, scale: int) -> Decimal | None:
    cleaned = _text(value, 64)
    if cleaned is None:
        return None
    normalized = cleaned.replace(",", "").replace(" ", "")
    normalized = re.sub(r"^[\$€£]", "", normalized)
    if not re.fullmatch(rf"\+?[0-9]+(?:\.[0-9]{{1,{scale}}})?", normalized):
        raise ValueError("Unsupported or negative decimal")
    try:
        number = Decimal(normalized.lstrip("+"))
    except InvalidOperation as exc:
        raise ValueError("Invalid decimal") from exc
    if not number.is_finite() or number < 0:
        raise ValueError("Decimal must be finite and non-negative")
    return number


_INVOICE_TOP_LEVEL = frozenset({
    "invoice_number", "supplier_name", "supplier_tax_id", "buyer_name",
    "date_issued", "due_date", "currency", "subtotal", "tax_amount",
    "discount_amount", "grand_total",
})
_LINE_FIELDS = frozenset({
    "description", "hs_code", "quantity", "unit_price",
    "tax_amount", "total_price",
})
_DOTTED_PATH = re.compile(r"^[a-z][a-z0-9_]*(?:\.[A-Za-z0-9_-]+)+$")


def _normalize_field_paths(response: str) -> str:
    """Repair bare or malformed evidence.field_path values before strict validation.

    The LLM is told the regex `^[a-z][a-z0-9_]*(?:\\.[A-Za-z0-9_-]+)+$` but
    occasionally emits bare names like 'invoice_number' or 'subtotal'. Rather
    than invalidate the entire response, we prefix them with the canonical
    parent namespace ('invoice.' for top-level fields, 'line_items.<order>.'
    for line items). Mixed-case keys and whitespace are tolerated. Any path
    that already matches the regex is left untouched.

    Raises ValueError when the payload cannot be decoded or contains a path
    that cannot be salvaged (unknown bare name, missing parent, etc.).
    """
    try:
        payload = json.loads(response)
    except json.JSONDecodeError as exc:
        raise ValueError("Response is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("Response must be an object")
    evidence = payload.get("evidence")
    if not isinstance(evidence, list):
        raise ValueError("Response is missing the evidence array")
    line_orders = sorted({
        int(item.get("line_order"))
        for item in payload.get("line_items") or []
        if isinstance(item, dict) and isinstance(item.get("line_order"), int)
            and item.get("line_order", 0) >= 1
    })
    for item in evidence:
        if not isinstance(item, dict):
            raise ValueError("Evidence entries must be objects")
        path = item.get("field_path")
        if not isinstance(path, str) or not path.strip():
            raise ValueError("Evidence entries must carry a string field_path")
        path = unicodedata.normalize("NFC", path).strip()
        if _DOTTED_PATH.fullmatch(path):
            item["field_path"] = path
            continue
        # Strip stray whitespace around dots and try once more
        collapsed = re.sub(r"\s*\.\s*", ".", path)
        if _DOTTED_PATH.fullmatch(collapsed):
            item["field_path"] = collapsed
            continue
        # Bare top-level field name → 'invoice.<bare>'
        bare = collapsed.lower()
        if bare in _INVOICE_TOP_LEVEL:
            item["field_path"] = f"invoice.{bare}"
            continue
        # 'line_items.N' or 'line_items.<N>.<field>' with missing parent
        line_match = re.fullmatch(r"line_items(?:\.([A-Za-z0-9_-]+))?(?:\.([A-Za-z0-9_-]+))?", collapsed)
        if line_match:
            order_raw, leaf = line_match.group(1), line_match.group(2)
            try:
                order = int(order_raw) if order_raw is not None else (line_orders[0] if len(line_orders) == 1 else 0)
            except ValueError:
                order = 0
            if order >= 1 and leaf and leaf.lower() in _LINE_FIELDS:
                item["field_path"] = f"line_items.{order}.{leaf.lower()}"
                continue
        raise ValueError(f"Cannot repair unsupported field_path '{path}'")
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


class ExtractionService:
    def __init__(self, provider: LLMProvider, supported_currencies: frozenset[str],
                 request_timeout_seconds: float = 120) -> None:
        if not supported_currencies or any(not re.fullmatch(r"[A-Z]{3}", code) for code in supported_currencies):
            raise ValueError("Supported currencies must be explicit ISO-style codes")
        self.provider = provider
        self.supported_currencies = supported_currencies
        if request_timeout_seconds <= 0:
            raise ValueError("LLM timeout must be positive")
        self.request_timeout_seconds = request_timeout_seconds

    async def extract(self, evidence: str) -> InvoiceCandidate:
        if not evidence or len(evidence) > 120_000:
            raise ProcessingError("INSUFFICIENT_EXTRACTION_EVIDENCE")
        for corrective in (False, True):
            try:
                response = await asyncio.wait_for(
                    self.provider.extract(evidence, "commercial-invoice-v1", corrective),
                    timeout=self.request_timeout_seconds,
                )
            except asyncio.TimeoutError as exc:
                raise ProcessingError("PROCESSING_TIMEOUT") from exc
            if len(response.encode("utf-8")) > 1_048_576:
                continue
            try:
                repaired = _normalize_field_paths(response)
            except ValueError:
                continue
            try:
                return self._normalize(RawInvoice.model_validate_json(repaired))
            except (ValidationError, ValueError, InvalidOperation):
                continue
        raise ProcessingError("INVALID_STRUCTURED_OUTPUT")

    def _normalize(self, raw: RawInvoice) -> InvoiceCandidate:
        currency = _text(raw.currency, 3)
        if currency is not None:
            currency = currency.upper()
            if currency not in self.supported_currencies:
                raise ValueError("Unsupported currency")
        lines = tuple(InvoiceLineCandidate(
            source_row_key=_text(line.source_row_key, 128),
            line_order=line.line_order,
            description=_text(line.description, 32768), hs_code=_text(line.hs_code, 50),
            quantity=_decimal(line.quantity, 4), unit_price=_decimal(line.unit_price, 4),
            tax_amount=_decimal(line.tax_amount, 2), total_price=_decimal(line.total_price, 2),
        ) for line in sorted(raw.line_items, key=lambda row: row.line_order))
        evidence = tuple(CandidateEvidence(
            field_path=item.field_path, source_value=_text(item.source_value, 2000),
            primary_chunk_id=item.primary_chunk_id, source_page=item.source_page,
            evidence_excerpt=_text(item.evidence_excerpt, 1000), retrieval_rank=item.retrieval_rank,
            retrieval_score=item.retrieval_score, exact_match=item.exact_match,
        ) for item in raw.evidence)
        return InvoiceCandidate(
            invoice_number=_text(raw.invoice_number, 100), supplier_name=_text(raw.supplier_name, 255),
            supplier_tax_id=_text(raw.supplier_tax_id, 100), buyer_name=_text(raw.buyer_name, 255),
            date_issued=_date(raw.date_issued), due_date=_date(raw.due_date), currency=currency,
            subtotal=_decimal(raw.subtotal, 2), tax_amount=_decimal(raw.tax_amount, 2),
            discount_amount=_decimal(raw.discount_amount, 2), grand_total=_decimal(raw.grand_total, 2),
            line_items=lines, evidence=evidence,
        )
