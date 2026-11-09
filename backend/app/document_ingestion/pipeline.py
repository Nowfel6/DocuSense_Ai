"""Pure checkpoint/lease policy; persistence and worker execution remain gated."""
from datetime import datetime, timedelta
import hashlib
from uuid import UUID

from .errors import IngestionError, StaleClaim
from .schemas import (
    DocumentProgress, DocumentRecord, FailureCode, JobSnapshot, ProcessingError,
    Stage, StageState, StageStates,
)

STAGES: tuple[Stage, ...] = ("upload", "partitioning", "chunking", "vectorizing", "extracting")
FAILURES: dict[FailureCode, str] = {
    "PDF_ENCRYPTED_OR_CORRUPT": "The PDF is encrypted or corrupt.",
    "PROCESSING_UNAVAILABLE": "Document processing is unavailable.",
    "PROCESSING_FAILED": "Document processing failed.",
}


def duplicate_lock_key(company_id: UUID, file_hash: str) -> int:
    """Derive the database spec's stable signed 64-bit advisory-lock key."""
    if len(file_hash) != 64 or any(c not in "0123456789abcdef" for c in file_hash):
        raise ValueError("Expected lowercase SHA-256")
    material = f"document-ingestion:{company_id}:{file_hash}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(material).digest()[:8], "big", signed=True)


def retry_at(attempt: int, database_wall_time: datetime) -> datetime | None:
    """Apply only after the repository locks/fences a failed or expired claim."""
    if database_wall_time.tzinfo is None or type(attempt) is not int or attempt not in (1, 2, 3, 4):
        raise ValueError("A claimed attempt and timezone-aware database wall time are required")
    return None if attempt == 4 else database_wall_time + timedelta(seconds=(5, 10, 20)[attempt - 1])


def require_live_claim(job: JobSnapshot, attempt: int, database_wall_time: datetime) -> None:
    """Pure check, not an atomic lock. Caller must read wall time after pair locks."""
    if database_wall_time.tzinfo is None:
        raise ValueError("Database wall time must be timezone-aware")
    if job.status != "processing" or job.attempt_count != attempt or job.lease_expires_at is None or job.lease_expires_at <= database_wall_time:
        raise StaleClaim()


def project_progress(record: DocumentRecord) -> DocumentProgress:
    """Validate a consistent persisted pair and derive only the documented stages."""
    job = record.job
    if job is None or job.document_id != record.summary.document_id:
        raise IngestionError("INTERNAL_ERROR")
    index = STAGES.index(job.current_stage)
    terminal = job.status in ("completed", "failed")
    expected_progress = 100 if job.status == "completed" else index * 20
    valid = job.progress_percentage == expected_progress
    valid &= (job.finished_at is not None) == terminal
    if terminal:
        valid &= job.lease_expires_at is None and job.next_attempt_at is None
    elif job.status == "processing":
        valid &= job.lease_expires_at is not None and job.attempt_count >= 1 and job.started_at is not None and job.next_attempt_at is None
    else:
        valid &= job.lease_expires_at is None and job.attempt_count < 4
    if job.attempt_count == 0:
        valid &= job.current_stage == "upload" and job.started_at is None
    else:
        valid &= job.started_at is not None
    if job.status == "completed":
        valid &= job.current_stage == "extracting" and record.summary.status in ("pending_review", "approved", "rejected")
        valid &= job.error_code is None and job.error_message is None
    elif job.status == "failed":
        valid &= record.summary.status == "failed" and bool(job.error_code and job.error_code.strip())
    else:
        valid &= record.summary.status == ("queued" if index == 0 else job.current_stage)
    if not valid:
        raise IngestionError("INTERNAL_ERROR")
    states: dict[str, StageState] = {stage: "pending" for stage in STAGES}
    states["upload"] = "completed"
    if job.status == "completed":
        states = {stage: "completed" for stage in STAGES}
    else:
        for earlier in STAGES[1:index]:
            states[earlier] = "completed"
        if index:
            states[job.current_stage] = {"processing": "in_progress", "queued": "pending", "failed": "failed"}[job.status]
    error = None
    if job.status == "failed":
        # Never echo arbitrary persisted provider text. Unknown codes use the safe fallback.
        code: FailureCode = "PROCESSING_FAILED"
        for known in FAILURES:
            if known == job.error_code:
                code = known
        error = ProcessingError(code=code, message=FAILURES[code])
    return DocumentProgress(document_id=record.summary.document_id, job_id=job.id,
                            status=record.summary.status, job_status=job.status,
                            current_stage=job.current_stage, progress_percentage=job.progress_percentage,
                            stages=StageStates.model_validate(states), error=error)
