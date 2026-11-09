"""SQLAlchemy mappings for the verified document-ingestion schema.

This module intentionally reuses ``Base`` and the auth tables from the sibling
``models.py`` handoff. Consumers must load that module first; no duplicate
metadata registry or parent mappings are created here.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..auth.models import Base


class Document(Base):
    """Accepted private-object metadata and tenant-scoped processing state."""

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False,
    )
    uploaded_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    s3_url: Mapped[str] = mapped_column(Text, nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(127), nullable=False)
    doc_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="commercial_invoice",
        server_default="commercial_invoice",
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="queued", server_default="queued",
    )
    overall_confidence: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=func.now(), server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=func.now(), onupdate=func.now(),
        server_default=func.now(),
    )

    company = relationship("Company")
    uploader = relationship("User", foreign_keys=[uploaded_by])
    processing_job: Mapped[Optional["ProcessingJob"]] = relationship(
        "ProcessingJob", back_populates="document", uselist=False, passive_deletes=True,
    )

    __table_args__ = (
        CheckConstraint(
            "length(btrim(file_name)) > 0 AND file_name NOT IN ('.', '..') "
            "AND position('/' in file_name) = 0 AND position(chr(92) in file_name) = 0 "
            "AND file_name !~ '[[:cntrl:]]'",
            name="chk_documents_file_name",
        ),
        CheckConstraint(
            "s3_url ~ ('^s3://[a-z0-9][a-z0-9.-]*/' || company_id::text || '/' || "
            "id::text || '/[^/?#]+$') AND s3_url !~ '[[:cntrl:]]' "
            "AND position(chr(92) in s3_url) = 0",
            name="chk_documents_s3_url",
        ),
        CheckConstraint("file_size_bytes BETWEEN 1 AND 10485760", name="chk_documents_file_size"),
        CheckConstraint("file_hash ~ '^[0-9a-f]{64}$'", name="chk_documents_file_hash"),
        CheckConstraint(
            "mime_type IN ('application/pdf', 'image/png', 'image/jpeg')",
            name="chk_documents_mime_type",
        ),
        CheckConstraint(
            "doc_type IN ('commercial_invoice', 'purchase_order', 'packing_list')",
            name="chk_documents_doc_type",
        ),
        CheckConstraint(
            "status IN ('queued', 'partitioning', 'chunking', 'vectorizing', 'extracting', "
            "'pending_review', 'approved', 'rejected', 'failed')",
            name="chk_documents_status",
        ),
        CheckConstraint(
            "overall_confidence IS NULL OR (overall_confidence <> 'NaN'::numeric "
            "AND overall_confidence BETWEEN 0.00 AND 100.00)",
            name="chk_documents_confidence",
        ),
        Index("idx_documents_company_id", "company_id"),
        Index("idx_documents_uploaded_by", "uploaded_by"),
        Index("idx_documents_status", "status"),
        Index("idx_documents_file_hash", "company_id", "file_hash"),
        Index("idx_documents_company_created", "company_id", text("created_at DESC"), text("id DESC")),
        Index(
            "idx_documents_company_status_created", "company_id", "status",
            text("created_at DESC"), text("id DESC"),
        ),
    )


class ProcessingJob(Base):
    """Durable one-per-document processing checkpoint and retry lease."""

    __tablename__ = "processing_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued", server_default="queued")
    current_stage: Mapped[str] = mapped_column(
        String(30), nullable=False, default="upload", server_default="upload",
    )
    progress_percentage: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default="0",
    )
    attempt_count: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default="0",
    )
    next_attempt_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=func.now(), server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=func.now(), onupdate=func.now(),
        server_default=func.now(),
    )

    document: Mapped[Document] = relationship("Document", back_populates="processing_job")

    __table_args__ = (
        UniqueConstraint("document_id", name="uq_processing_jobs_document_id"),
        CheckConstraint("status IN ('queued', 'processing', 'completed', 'failed')", name="chk_processing_jobs_status"),
        CheckConstraint(
            "current_stage IN ('upload', 'partitioning', 'chunking', 'vectorizing', 'extracting')",
            name="chk_processing_jobs_stage",
        ),
        CheckConstraint("progress_percentage BETWEEN 0 AND 100", name="chk_processing_jobs_progress"),
        CheckConstraint("attempt_count BETWEEN 0 AND 4", name="chk_processing_jobs_attempts"),
        CheckConstraint(
            "status <> 'completed' OR (progress_percentage = 100 AND finished_at IS NOT NULL)",
            name="chk_processing_jobs_completion",
        ),
        CheckConstraint(
            "status <> 'failed' OR (finished_at IS NOT NULL AND error_code IS NOT NULL "
            "AND length(btrim(error_code)) > 0)",
            name="chk_processing_jobs_failure",
        ),
        CheckConstraint(
            "status IN ('completed', 'failed') OR finished_at IS NULL",
            name="chk_processing_jobs_nonterminal_finish",
        ),
        CheckConstraint(
            "status NOT IN ('completed', 'failed') OR "
            "(lease_expires_at IS NULL AND next_attempt_at IS NULL)",
            name="chk_processing_jobs_terminal_cleanup",
        ),
        Index(
            "idx_processing_jobs_dispatch", "status",
            text("next_attempt_at ASC NULLS FIRST"), "created_at",
        ),
        Index("idx_processing_jobs_lease", "status", "lease_expires_at"),
    )


__all__ = ["Base", "Document", "ProcessingJob"]
