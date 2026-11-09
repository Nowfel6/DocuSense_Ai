"""Approved ingestion wire types and internal DTOs; no ORM mappings."""
from datetime import date, datetime, timezone
from decimal import Decimal
import re
from typing import Annotated, Generic, Literal, TypeVar
from uuid import UUID

from pydantic import (
    AfterValidator, AwareDatetime, BaseModel, BeforeValidator, ConfigDict,
    Field, PlainSerializer, field_validator, model_validator,
)
from ..document_processing_rag.schemas import InvoiceResult

MAX_FILE_BYTES = 10_485_760
DocType = Literal["commercial_invoice", "purchase_order", "packing_list"]
DocumentStatus = Literal["queued", "partitioning", "chunking", "vectorizing",
                         "extracting", "pending_review", "approved", "rejected", "failed"]
JobStatus = Literal["queued", "processing", "completed", "failed"]
Stage = Literal["upload", "partitioning", "chunking", "vectorizing", "extracting"]
StageState = Literal["pending", "in_progress", "completed", "failed"]
MimeType = Literal["application/pdf", "image/png", "image/jpeg"]
Role = Literal["admin", "operator", "viewer"]
FailureCode = Literal["PDF_ENCRYPTED_OR_CORRUPT", "PROCESSING_UNAVAILABLE", "PROCESSING_FAILED"]


def utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc)


UtcDatetime = Annotated[AwareDatetime, AfterValidator(utc)]
Confidence = Annotated[
    Decimal, Field(ge=0, le=100, allow_inf_nan=False),
    PlainSerializer(float, return_type=float, when_used="json"),
]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class UploadForm(Model):
    doc_type_hint: DocType = "commercial_invoice"
    confirm_duplicate: bool = False

    @field_validator("doc_type_hint", mode="before")
    @classmethod
    def aliases(cls, value: object) -> object:
        if value == "invoice":
            return "commercial_invoice"
        if value == "po":
            return "purchase_order"
        return value


def integer_query(value: object) -> int:
    if type(value) is int:
        return value
    if isinstance(value, str) and re.fullmatch(r"[0-9]+", value):
        try:
            return int(value)
        except ValueError:
            pass
    raise ValueError("Expected a base-10 integer")


def date_query(value: object) -> date | None:
    if value is None or type(value) is date:
        return value
    if isinstance(value, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        return date.fromisoformat(value)
    raise ValueError("Expected YYYY-MM-DD")


class ListQuery(Model):
    page: Annotated[int, BeforeValidator(integer_query), Field(ge=1)] = 1
    page_size: Annotated[int, BeforeValidator(integer_query), Field(ge=1, le=100)] = 20
    status: DocumentStatus | None = None
    doc_type: DocType | None = None
    sort_by: Literal["created_at", "updated_at", "file_name"] = "created_at"
    order: Literal["asc", "desc"] = "desc"
    from_date: Annotated[date | None, BeforeValidator(date_query)] = None
    to_date: Annotated[date | None, BeforeValidator(date_query)] = None

    @model_validator(mode="after")
    def ordered_dates(self) -> "ListQuery":
        if self.from_date and self.to_date and self.from_date > self.to_date:
            raise ValueError("from_date must not follow to_date")
        return self


class DocumentPath(Model):
    document_id: UUID


class Caller(Model):
    """Only a trusted shared auth resolver may construct this internal DTO."""
    company_id: UUID
    user_id: UUID | None = None
    role: Role | None = None
    api_key_id: UUID | None = None

    @model_validator(mode="after")
    def identity(self) -> "Caller":
        human = self.user_id is not None and self.role is not None and self.api_key_id is None
        key = self.api_key_id is not None and self.user_id is None and self.role is None
        if not (human or key):
            raise ValueError("Exactly one resolved caller identity is required")
        return self


class Meta(Model):
    timestamp: UtcDatetime
    request_id: Annotated[str, Field(min_length=1)]


class Warning(Model):
    code: Literal["LOW_IMAGE_RESOLUTION", "DUPLICATE_FILE_DETECTED"]
    message: str


class ErrorDetail(Model):
    field: str
    issue: str


class ErrorBody(Model):
    code: str
    message: str
    details: list[ErrorDetail] = Field(default_factory=list)


class ErrorEnvelope(Model):
    success: Literal[False] = False
    error: ErrorBody
    meta: Meta


class UploadAccepted(Model):
    document_id: UUID
    job_id: UUID
    file_name: Annotated[str, Field(min_length=1, max_length=255)]
    file_size_bytes: Annotated[int, Field(strict=True, ge=1, le=MAX_FILE_BYTES)]
    status: Literal["queued"] = "queued"
    status_url: str
    warnings: list[Warning] = Field(default_factory=list)

    @model_validator(mode="after")
    def status_location(self) -> "UploadAccepted":
        if self.status_url != f"/api/v1/documents/{self.document_id}/status":
            raise ValueError("Invalid status URL")
        return self


class DocumentSummary(Model):
    document_id: UUID
    file_name: Annotated[str, Field(min_length=1, max_length=255)]
    file_size_bytes: Annotated[int, Field(strict=True, ge=1, le=MAX_FILE_BYTES)]
    mime_type: MimeType
    doc_type: DocType
    status: DocumentStatus
    overall_confidence: Confidence | None
    created_at: UtcDatetime
    updated_at: UtcDatetime


class DocumentDetail(DocumentSummary):
    job_id: UUID
    uploaded_by: UUID | None
    s3_url: str
    invoice: InvoiceResult | None = None


class ProcessingError(Model):
    code: FailureCode
    message: str


class StageStates(Model):
    upload: StageState
    partitioning: StageState
    chunking: StageState
    vectorizing: StageState
    extracting: StageState


class DocumentProgress(Model):
    document_id: UUID
    job_id: UUID
    status: DocumentStatus
    job_status: JobStatus
    current_stage: Stage
    progress_percentage: Annotated[int, Field(strict=True, ge=0, le=100)]
    stages: StageStates
    error: ProcessingError | None


class Pagination(Model):
    page: Annotated[int, Field(strict=True, ge=1)]
    page_size: Annotated[int, Field(strict=True, ge=1, le=100)]
    total_records: Annotated[int, Field(strict=True, ge=0)]
    total_pages: Annotated[int, Field(strict=True, ge=0)]
    has_next: bool
    has_prev: bool

    @classmethod
    def for_query(cls, query: ListQuery, total: int) -> "Pagination":
        pages = (total + query.page_size - 1) // query.page_size
        return cls(page=query.page, page_size=query.page_size, total_records=total,
                   total_pages=pages, has_next=query.page < pages,
                   has_prev=query.page > 1 and total > 0)


DataT = TypeVar("DataT")


class Success(Model, Generic[DataT]):
    success: Literal[True] = True
    data: DataT
    message: str
    meta: Meta


class DocumentList(Success[list[DocumentSummary]]):
    pagination: Pagination


class JobSnapshot(Model):
    """Internal one-snapshot repository projection, not a replacement DB model."""
    id: UUID
    document_id: UUID
    status: JobStatus
    current_stage: Stage
    progress_percentage: Annotated[int, Field(strict=True, ge=0, le=100)]
    attempt_count: Annotated[int, Field(strict=True, ge=0, le=4)]
    lease_expires_at: UtcDatetime | None = None
    next_attempt_at: UtcDatetime | None = None
    started_at: UtcDatetime | None = None
    finished_at: UtcDatetime | None = None
    error_code: str | None = None
    error_message: str | None = None


class DocumentRecord(Model):
    """Authorized repository projection. Private fields never go straight to JSON."""
    company_id: UUID
    summary: DocumentSummary
    uploaded_by: UUID | None
    private_reference: str
    job: JobSnapshot | None
