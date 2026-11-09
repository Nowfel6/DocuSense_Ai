"""Typed wire/domain models for the document-processing RAG build.

This module deliberately contains no ORM mappings and no provider-native values.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
import json
import math
import re
import unicodedata
from typing import Annotated, Generic, Literal, TypeVar
from uuid import UUID

from pydantic import (
    AfterValidator, AwareDatetime, BaseModel, BeforeValidator, ConfigDict, Field,
    PlainSerializer, field_validator, model_validator,
)

ChunkType = Literal["text", "table", "header", "list", "image", "unknown"]
RetrievalRole = Literal["parent", "child", "both"]
EmbeddingStatus = Literal["pending", "completed", "failed", "not_required"]
ValidationState = Literal["valid", "invalid", "missing", "ambiguous", "unsupported"]
RuleStatus = Literal["passed", "failed", "missing", "not_applicable"]
RunStatus = Literal["running", "completed", "failed"]
Role = Literal["admin", "operator", "viewer"]
ElementType = Literal["heading", "paragraph", "list", "table", "image", "header", "footer", "unknown"]


def _utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc)


def _query_int(value: object) -> int:
    if type(value) is int:
        return value
    if isinstance(value, str) and re.fullmatch(r"[0-9]+", value):
        return int(value)
    raise ValueError("Expected a base-10 integer")


def _query_decimal(value: object) -> Decimal | None:
    if value is None or isinstance(value, Decimal):
        return value
    if isinstance(value, str) and re.fullmatch(r"(?:0|[1-9][0-9]{0,2})(?:\.[0-9]{1,2})?", value):
        result = Decimal(value)
        if result.is_finite():
            return result
    raise ValueError("Expected a finite decimal with at most two fractional digits")


def _nfc(value: str) -> str:
    return unicodedata.normalize("NFC", value).strip()


UtcDatetime = Annotated[AwareDatetime, AfterValidator(_utc)]
QueryInt = Annotated[int, BeforeValidator(_query_int)]
QueryDecimal = Annotated[Decimal | None, BeforeValidator(_query_decimal)]
Confidence = Annotated[
    Decimal,
    Field(ge=0, le=100, allow_inf_nan=False, max_digits=5, decimal_places=2),
    PlainSerializer(float, return_type=float, when_used="json"),
]
Score = Annotated[
    Decimal,
    Field(ge=-1, le=1, allow_inf_nan=False, max_digits=8, decimal_places=6),
    PlainSerializer(float, return_type=float, when_used="json"),
]
MoneyString = Annotated[
    Decimal,
    Field(ge=0, allow_inf_nan=False, max_digits=14, decimal_places=2),
    PlainSerializer(lambda value: format(value, ".2f"), return_type=str, when_used="json"),
]
QuantityString = Annotated[
    Decimal,
    Field(ge=0, allow_inf_nan=False, max_digits=18, decimal_places=4),
    PlainSerializer(lambda value: format(value, ".4f"), return_type=str, when_used="json"),
]
NonNegativeDecimal = Annotated[Decimal, Field(ge=0, allow_inf_nan=False)]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CallerContext(Model):
    company_id: UUID
    user_id: UUID | None = None
    role: Role | None = None
    api_key_id: UUID | None = None

    @model_validator(mode="after")
    def one_identity(self) -> "CallerContext":
        human = self.user_id is not None and self.role is not None and self.api_key_id is None
        key = self.api_key_id is not None and self.user_id is None and self.role is None
        if not (human or key):
            raise ValueError("Exactly one trusted caller identity is required")
        return self


class BoundingBox(Model):
    version: Literal["bbox-v1"] = "bbox-v1"
    page_number: Annotated[int, Field(strict=True, ge=1)]
    x0: Annotated[float, Field(strict=True, ge=0, le=1, allow_inf_nan=False)]
    y0: Annotated[float, Field(strict=True, ge=0, le=1, allow_inf_nan=False)]
    x1: Annotated[float, Field(strict=True, ge=0, le=1, allow_inf_nan=False)]
    y1: Annotated[float, Field(strict=True, ge=0, le=1, allow_inf_nan=False)]
    rotation: Literal[0, 90, 180, 270] = 0

    @model_validator(mode="after")
    def ordered(self) -> "BoundingBox":
        if self.x0 >= self.x1 or self.y0 >= self.y1:
            raise ValueError("Bounding-box coordinates must be ordered")
        return self


class TableCell(Model):
    row: Annotated[int, Field(strict=True, ge=0)]
    column: Annotated[int, Field(strict=True, ge=0)]
    text: Annotated[str, Field(max_length=4096)]
    row_span: Annotated[int, Field(strict=True, ge=1)] = 1
    column_span: Annotated[int, Field(strict=True, ge=1)] = 1
    source_element_id: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    bounding_box: BoundingBox | None = None


class TableRow(Model):
    row_index: Annotated[int, Field(strict=True, ge=0)]
    cells: tuple[TableCell, ...] = Field(max_length=200)


class StructuredTable(Model):
    version: Literal["table-v1"] = "table-v1"
    headers: tuple[Annotated[str, Field(max_length=4096)], ...] = Field(max_length=200)
    rows: tuple[TableRow, ...] = Field(max_length=2000)

    @model_validator(mode="after")
    def bounded_cells(self) -> "StructuredTable":
        if sum(len(row.cells) for row in self.rows) > 50_000:
            raise ValueError("Table exceeds the cell limit")
        return self


class CanonicalElement(Model):
    source_id: Annotated[str, Field(min_length=1, max_length=128)]
    element_type: ElementType
    original_text: str = Field(max_length=32768)
    normalized_text: str | None = Field(default=None, max_length=32768)
    page_number: Annotated[int, Field(strict=True, ge=1)]
    bounding_box: BoundingBox | None = None
    table: StructuredTable | None = None
    section: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def element_shape(self) -> "CanonicalElement":
        if self.bounding_box and self.bounding_box.page_number != self.page_number:
            raise ValueError("Element box must belong to its page")
        if self.element_type == "table" and self.table is None:
            raise ValueError("Table elements require typed table content")
        if self.element_type != "table" and self.table is not None:
            raise ValueError("Only table elements may carry table content")
        return self

    @property
    def text(self) -> str:
        return self.normalized_text if self.normalized_text is not None else self.original_text


class CanonicalPage(Model):
    page_number: Annotated[int, Field(strict=True, ge=1)]
    width: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    height: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    rotation: Literal[0, 90, 180, 270] = 0
    ocr_used: bool = False
    ocr_language: Literal["eng"] | None = None
    elements: tuple[CanonicalElement, ...] = Field(max_length=2000)

    @model_validator(mode="after")
    def page_ownership(self) -> "CanonicalPage":
        if any(element.page_number != self.page_number for element in self.elements):
            raise ValueError("Every element must belong to its containing page")
        if self.ocr_used and self.ocr_language != "eng":
            raise ValueError("OCR pages require the approved English language")
        return self


class CanonicalDocument(Model):
    document_id: UUID
    pipeline_version: Annotated[str, Field(min_length=1, max_length=64)]
    parser_name: Literal["docling"] = "docling"
    parser_version: Annotated[str, Field(min_length=1, max_length=100)]
    ocr_policy_version: Annotated[str, Field(min_length=1, max_length=64)]
    warning_codes: tuple[Annotated[str, Field(min_length=1, max_length=100)], ...] = Field(max_length=64)
    pages: tuple[CanonicalPage, ...] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def document_shape(self) -> "CanonicalDocument":
        numbers = [page.page_number for page in self.pages]
        if numbers != list(range(1, len(numbers) + 1)):
            raise ValueError("Pages must be consecutive and 1-based")
        ids = [element.source_id for page in self.pages for element in page.elements]
        if len(ids) > 20_000 or len(ids) != len(set(ids)):
            raise ValueError("Element IDs must be unique and within the document limit")
        encoded = self.model_dump_json().encode("utf-8")
        if len(encoded) > 16 * 1024 * 1024:
            raise ValueError("Canonical document exceeds the serialized limit")
        return self


class ChunkDraft(Model):
    chunk_id: UUID
    parent_chunk_id: UUID | None = None
    ordinal: Annotated[int, Field(strict=True, ge=0)]
    page_start: Annotated[int, Field(strict=True, ge=1)]
    page_end: Annotated[int, Field(strict=True, ge=1)]
    section: str | None = Field(default=None, max_length=255)
    chunk_type: ChunkType
    retrieval_role: RetrievalRole
    raw_content: Annotated[str, Field(min_length=1, max_length=32768)]
    structured_content: StructuredTable | None = None
    summary: str | None = Field(default=None, max_length=4096)
    token_count: Annotated[int, Field(strict=True, gt=0)]
    source_element_ids: tuple[Annotated[str, Field(min_length=1, max_length=128)], ...] = Field(max_length=256)
    bounding_boxes: tuple[BoundingBox, ...] = Field(max_length=256)
    content_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]

    @model_validator(mode="after")
    def pages_and_parent(self) -> "ChunkDraft":
        if self.page_end < self.page_start or self.parent_chunk_id == self.chunk_id:
            raise ValueError("Invalid chunk page range or hierarchy")
        if any(not self.page_start <= box.page_number <= self.page_end for box in self.bounding_boxes):
            raise ValueError("Chunk boxes must belong to its page range")
        if len(self.raw_content.encode("utf-8")) > 32768:
            raise ValueError("Chunk content exceeds UTF-8 byte limit")
        if self.summary and len(self.summary.encode("utf-8")) > 4096:
            raise ValueError("Summary exceeds UTF-8 byte limit")
        if self.structured_content:
            size = len(json.dumps(self.structured_content.model_dump(mode="json"), separators=(",", ":")).encode("utf-8"))
            if size > 65536:
                raise ValueError("Structured chunk content exceeds byte limit")
        return self


class ChunkQuery(Model):
    page: Annotated[QueryInt, Field(ge=1)] = 1
    page_size: Annotated[QueryInt, Field(ge=1, le=100)] = 50
    chunk_type: ChunkType | None = None
    page_number: Annotated[QueryInt | None, Field(ge=1)] = None
    retrieval_role: RetrievalRole | None = None
    section: str | None = Field(default=None, min_length=1, max_length=255)
    sort_by: Literal["ordinal"] = "ordinal"
    order: Literal["asc", "desc"] = "asc"

    @field_validator("section")
    @classmethod
    def section_nfc(cls, value: str | None) -> str | None:
        if value is None:
            return None
        result = _nfc(value)
        if not result:
            raise ValueError("Section cannot be blank")
        return result


class EvidenceQuery(Model):
    page: Annotated[QueryInt, Field(ge=1)] = 1
    page_size: Annotated[QueryInt, Field(ge=1, le=100)] = 50
    field_path: str | None = Field(default=None, min_length=1, max_length=255)
    validation_state: ValidationState | None = None
    min_confidence: Annotated[QueryDecimal, Field(ge=0, le=100)] = None

    @field_validator("field_path")
    @classmethod
    def canonical_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        result = _nfc(value)
        if not re.fullmatch(r"[a-z][a-z0-9_]*(?:\.[A-Za-z0-9_-]+)+", result):
            raise ValueError("Invalid canonical field path")
        return result


class Pagination(Model):
    page: Annotated[int, Field(strict=True, ge=1)]
    page_size: Annotated[int, Field(strict=True, ge=1, le=100)]
    total_records: Annotated[int, Field(strict=True, ge=0)]
    total_pages: Annotated[int, Field(strict=True, ge=0)]
    has_next: bool
    has_prev: bool

    @classmethod
    def create(cls, page: int, page_size: int, total: int) -> "Pagination":
        pages = (total + page_size - 1) // page_size
        return cls(page=page, page_size=page_size, total_records=total, total_pages=pages,
                   has_next=page < pages, has_prev=page > 1 and total > 0)


class ChunkItem(Model):
    chunk_id: UUID
    parent_chunk_id: UUID | None
    ordinal: Annotated[int, Field(strict=True, ge=0)]
    page_start: Annotated[int, Field(strict=True, ge=1)]
    page_end: Annotated[int, Field(strict=True, ge=1)]
    section: str | None
    chunk_type: ChunkType
    retrieval_role: RetrievalRole
    token_count: Annotated[int, Field(strict=True, gt=0)]
    raw_content: str = Field(min_length=1, max_length=32768)
    structured_content: StructuredTable | None
    summary: str | None = Field(default=None, max_length=4096)
    source_element_ids: tuple[str, ...] = Field(max_length=256)
    bounding_boxes: tuple[BoundingBox, ...] = Field(max_length=256)
    embedding_status: EmbeddingStatus
    has_embedding: bool

    @model_validator(mode="after")
    def embedding_projection(self) -> "ChunkItem":
        if self.has_embedding != (self.embedding_status == "completed"):
            raise ValueError("Embedding projection is inconsistent")
        return self


class CandidateEvidence(Model):
    field_path: Annotated[str, Field(min_length=1, max_length=255, pattern=r"^[a-z][a-z0-9_]*(?:\.[A-Za-z0-9_-]+)+$")]
    source_value: str | None = Field(default=None, max_length=2000)
    primary_chunk_id: UUID | None = None
    source_page: Annotated[int | None, Field(ge=1)] = None
    bounding_box: BoundingBox | None = None
    evidence_excerpt: str | None = Field(default=None, max_length=1000)
    retrieval_rank: Annotated[int | None, Field(ge=1)] = None
    retrieval_score: Score | None = None
    exact_match: bool = False


class InvoiceLineCandidate(Model):
    source_row_key: Annotated[str, Field(min_length=1, max_length=128)]
    line_order: Annotated[int, Field(strict=True, ge=1)]
    description: str | None = Field(default=None, max_length=32768)
    hs_code: str | None = Field(default=None, max_length=50)
    quantity: NonNegativeDecimal | None = None
    unit_price: NonNegativeDecimal | None = None
    tax_amount: NonNegativeDecimal | None = None
    total_price: NonNegativeDecimal | None = None


class InvoiceCandidate(Model):
    invoice_number: str | None = Field(default=None, max_length=100)
    supplier_name: str | None = Field(default=None, max_length=255)
    supplier_tax_id: str | None = Field(default=None, max_length=100)
    buyer_name: str | None = Field(default=None, max_length=255)
    date_issued: date | None = None
    due_date: date | None = None
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    subtotal: NonNegativeDecimal | None = None
    tax_amount: NonNegativeDecimal | None = None
    discount_amount: NonNegativeDecimal | None = None
    grand_total: NonNegativeDecimal | None = None
    line_items: tuple[InvoiceLineCandidate, ...] = Field(max_length=2000)
    evidence: tuple[CandidateEvidence, ...] = Field(max_length=4096)

    @model_validator(mode="after")
    def deterministic_identities(self) -> "InvoiceCandidate":
        keys = [row.source_row_key for row in self.line_items]
        orders = [row.line_order for row in self.line_items]
        paths = [row.field_path for row in self.evidence]
        if len(keys) != len(set(keys)) or len(orders) != len(set(orders)) or len(paths) != len(set(paths)):
            raise ValueError("Line identities and evidence paths must be unique")
        return self


class RuleResult(Model):
    rule_id: Annotated[str, Field(min_length=1, max_length=64)]
    scope_key: Annotated[str, Field(min_length=1, max_length=255)]
    status: RuleStatus
    observed_value: str | int | bool | None = None
    expected_value: str | int | bool | None = None
    difference: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    epsilon: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    message_code: Annotated[str, Field(min_length=1, max_length=100)]


class FieldEvidenceDraft(Model):
    field_path: Annotated[str, Field(min_length=1, max_length=255)]
    source_value: str | None = Field(default=None, max_length=2000)
    normalized_value: str | int | bool | None = None
    primary_chunk_id: UUID | None = None
    source_page: Annotated[int | None, Field(ge=1)] = None
    bounding_box: BoundingBox | None = None
    evidence_excerpt: str | None = Field(default=None, max_length=1000)
    retrieval_rank: Annotated[int | None, Field(ge=1)] = None
    retrieval_score: Score | None = None
    exact_match: bool = False
    confidence_score: Confidence = Decimal("0")
    reason_codes: tuple[Annotated[str, Field(min_length=1, max_length=100)], ...] = Field(max_length=64)
    validation_state: ValidationState

    @model_validator(mode="after")
    def state_shape(self) -> "FieldEvidenceDraft":
        empty = all(value is None for value in (
            self.source_value, self.normalized_value, self.primary_chunk_id,
            self.source_page, self.bounding_box, self.evidence_excerpt,
            self.retrieval_rank, self.retrieval_score,
        ))
        if self.validation_state == "valid" and self.primary_chunk_id is None:
            raise ValueError("Valid evidence requires a primary chunk")
        if self.validation_state in ("missing", "unsupported") and (not empty or self.exact_match or self.confidence_score != 0):
            raise ValueError("Missing/unsupported evidence must be empty with zero confidence")
        return self


class InvoiceLineResult(Model):
    line_item_id: UUID
    line_order: Annotated[int, Field(strict=True, ge=1)]
    description: str | None
    hs_code: str | None
    quantity: QuantityString | None
    unit_price: QuantityString | None
    tax_amount: MoneyString | None
    total_price: MoneyString | None


class ValidationSummary(Model):
    passed: Annotated[int, Field(strict=True, ge=0)]
    failed: Annotated[int, Field(strict=True, ge=0)]
    missing: Annotated[int, Field(strict=True, ge=0)]
    not_applicable: Annotated[int, Field(strict=True, ge=0)]


class InvoiceResult(Model):
    invoice_id: UUID
    invoice_number: str | None
    supplier_name: str | None
    supplier_tax_id: str | None
    buyer_name: str | None
    date_issued: date | None
    due_date: date | None
    currency: str | None
    subtotal: MoneyString | None
    tax_amount: MoneyString | None
    discount_amount: MoneyString | None
    grand_total: MoneyString | None
    is_math_valid: bool
    line_items: tuple[InvoiceLineResult, ...]
    validation_summary: ValidationSummary
    extraction_run_id: UUID
    schema_version: Literal["commercial-invoice-v1"]
    completed_at: UtcDatetime


class ExtractionRunInfo(Model):
    extraction_run_id: UUID
    status: Literal["completed"]
    pipeline_version: str
    parser_name: Literal["docling"]
    parser_version: str
    ocr_policy_version: str
    embedding_model: Literal["sentence-transformers/all-MiniLM-L6-v2"]
    embedding_revision: str
    embedding_dimension: Literal[384]
    llm_provider: str
    llm_model: str
    prompt_version: str
    schema_version: Literal["commercial-invoice-v1"]
    warning_codes: tuple[str, ...] = Field(max_length=64)
    started_at: UtcDatetime
    completed_at: UtcDatetime


class EvidenceItem(Model):
    field_path: str
    source_value: str | None
    normalized_value: str | int | bool | None
    primary_chunk_id: UUID | None
    source_page: int | None
    bounding_box: BoundingBox | None
    evidence_excerpt: str | None
    retrieval_rank: int | None
    retrieval_score: Score | None
    confidence_score: Confidence
    confidence_reason_codes: tuple[str, ...] = Field(max_length=64)
    validation_state: ValidationState


class ValidationRuleSummary(Model):
    rule_id: str
    scope_key: str
    status: RuleStatus
    message_code: str
    observed_value: str | int | bool | None
    expected_value: str | int | bool | None
    difference: str | None
    epsilon: str | None


class ExtractionEvidenceData(Model):
    extraction_run: ExtractionRunInfo
    items: tuple[EvidenceItem, ...]
    validation_summary: ValidationSummary
    rule_results: tuple[ValidationRuleSummary, ...]


DataT = TypeVar("DataT")


class ErrorDetail(Model):
    field: str
    issue: str


class ErrorBody(Model):
    code: str
    message: str
    details: tuple[ErrorDetail, ...] = ()


class ErrorEnvelope(Model):
    success: Literal[False] = False
    error: ErrorBody
    meta: dict[str, str]


class Success(Model, Generic[DataT]):
    success: Literal[True] = True
    data: DataT
    message: str
    meta: dict[str, str]


class ChunkList(Success[tuple[ChunkItem, ...]]):
    pagination: Pagination


class EvidenceResponse(Success[ExtractionEvidenceData]):
    pagination: Pagination


class RetrievalCandidate(Model):
    chunk: ChunkDraft
    rank: Annotated[int, Field(strict=True, ge=1)]
    score: Annotated[float, Field(ge=-1, le=1, allow_inf_nan=False)]
    objective: Annotated[str, Field(min_length=1, max_length=64)]
    parent: ChunkDraft | None = None


class EmbeddedChunk(Model):
    chunk_id: UUID
    vector: tuple[float, ...]
    model: Literal["sentence-transformers/all-MiniLM-L6-v2"]
    revision: Annotated[str, Field(min_length=1, max_length=255)]

    @field_validator("vector")
    @classmethod
    def vector_shape(cls, value: tuple[float, ...]) -> tuple[float, ...]:
        if len(value) != 384 or any(not math.isfinite(item) for item in value):
            raise ValueError("Embedding must contain 384 finite values")
        norm = math.sqrt(sum(item * item for item in value))
        if abs(norm - 1.0) > 1e-5:
            raise ValueError("Embedding must be normalized")
        return value


class ProcessingIdentity(Model):
    pipeline_version: Annotated[str, Field(min_length=1, max_length=64)]
    configuration_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    parser_version: Annotated[str, Field(min_length=1, max_length=100)]
    ocr_policy_version: Annotated[str, Field(min_length=1, max_length=64)]
    embedding_revision: Annotated[str, Field(min_length=1, max_length=255)]
    llm_provider: Annotated[str, Field(min_length=1, max_length=100)]
    llm_model: Annotated[str, Field(min_length=1, max_length=255)]
    prompt_version: Annotated[str, Field(min_length=1, max_length=64)]
    schema_version: Literal["commercial-invoice-v1"] = "commercial-invoice-v1"


class JobClaim(Model):
    document_id: UUID
    job_id: UUID
    attempt: Annotated[int, Field(strict=True, ge=1, le=4)]
    fence: UUID
    lease_expires_at: UtcDatetime
    private_reference: Annotated[str, Field(min_length=1)]
    doc_type: Literal["commercial_invoice"]
    identity: ProcessingIdentity


class ValidationBundle(Model):
    invoice: InvoiceCandidate
    rules: tuple[RuleResult, ...]
    evidence: tuple[FieldEvidenceDraft, ...]
    document_confidence: Confidence
    is_math_valid: bool


__all__ = [name for name in globals() if not name.startswith("_")]
