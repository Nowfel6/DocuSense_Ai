"""Shared-Base SQLAlchemy mappings for document search/export provenance.

Load the auth, ingestion, RAG, and review mapping modules under their stable
verification aliases before this module. No predecessor table is redeclared.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..auth.models import Company, User
from ..document_ingestion.models import Document
from ..human_review_audit.models import Base


uuid_pk = dict(primary_key=True, default=uuid.uuid4, server_default=sa.func.gen_random_uuid())
created = dict(nullable=False, default=sa.func.now(), server_default=sa.func.now())
updated = dict(
    nullable=False,
    default=sa.func.now(),
    onupdate=sa.func.now(),
    server_default=sa.func.now(),
)


class ExportJob(Base):
    __tablename__ = "export_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **uuid_pk)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("companies.id", name="fk_export_jobs_company", ondelete="RESTRICT"),
        nullable=False,
    )
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey(
            "users.id", name="fk_export_jobs_requested_by_user", ondelete="RESTRICT"
        ),
        nullable=False,
    )
    format: Mapped[str] = mapped_column(sa.String(8), nullable=False)
    mode: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    status: Mapped[str] = mapped_column(sa.String(16), nullable=False, server_default="queued")
    current_stage: Mapped[str] = mapped_column(sa.String(16), nullable=False, server_default="accepted")
    progress_percentage: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False, server_default="0")
    selection_type: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    schema_version: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    criteria_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
    )
    criteria_hash: Mapped[str] = mapped_column(sa.CHAR(64), nullable=False)
    request_hash: Mapped[str] = mapped_column(sa.CHAR(64), nullable=False)
    idempotency_key_hash: Mapped[Optional[str]] = mapped_column(sa.CHAR(64))
    selected_document_count: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    exported_document_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")
    row_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")
    artifact_object_key: Mapped[Optional[str]] = mapped_column(sa.Text)
    artifact_file_name: Mapped[Optional[str]] = mapped_column(sa.String(255))
    artifact_content_type: Mapped[Optional[str]] = mapped_column(sa.String(127))
    artifact_size_bytes: Mapped[Optional[int]] = mapped_column(sa.BigInteger)
    artifact_sha256: Mapped[Optional[str]] = mapped_column(sa.CHAR(64))
    artifact_expires_at: Mapped[Optional[datetime]] = mapped_column(sa.DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False, server_default="0")
    next_attempt_at: Mapped[Optional[datetime]] = mapped_column(sa.DateTime(timezone=True))
    lease_token: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))
    lease_expires_at: Mapped[Optional[datetime]] = mapped_column(sa.DateTime(timezone=True))
    error_code: Mapped[Optional[str]] = mapped_column(sa.String(100))
    error_message: Mapped[Optional[str]] = mapped_column(sa.String(1000))
    request_id: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(sa.DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(sa.DateTime(timezone=True))
    failed_at: Mapped[Optional[datetime]] = mapped_column(sa.DateTime(timezone=True))
    expired_at: Mapped[Optional[datetime]] = mapped_column(sa.DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), **created)
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), **updated)

    company: Mapped[Company] = relationship(foreign_keys=[company_id], passive_deletes=True)
    requested_by_user: Mapped[User] = relationship(
        foreign_keys=[requested_by_user_id], passive_deletes=True
    )
    documents: Mapped[list["ExportJobDocument"]] = relationship(
        back_populates="job", passive_deletes=True, order_by="ExportJobDocument.ordinal"
    )

    __table_args__ = (
        sa.CheckConstraint("format IN ('csv','xlsx','json')", name="chk_export_jobs_format"),
        sa.CheckConstraint("mode IN ('synchronous','asynchronous')", name="chk_export_jobs_mode"),
        sa.CheckConstraint("status IN ('queued','processing','completed','failed','expired')", name="chk_export_jobs_status"),
        sa.CheckConstraint("current_stage IN ('accepted','generating','packaging','storing','completed')", name="chk_export_jobs_stage"),
        sa.CheckConstraint("selection_type IN ('document_ids','criteria')", name="chk_export_jobs_selection_type"),
        sa.CheckConstraint("schema_version='docusense-approved-invoice-export-v1'", name="chk_export_jobs_schema_version"),
        sa.CheckConstraint("public.validate_export_criteria_json(criteria_json) AND (NOT criteria_json ? 'selection_type' OR criteria_json->>'selection_type'=selection_type)", name="chk_export_jobs_criteria_object_size"),
        sa.CheckConstraint("criteria_hash ~ '^[0-9a-f]{64}$' AND request_hash ~ '^[0-9a-f]{64}$'", name="chk_export_jobs_hashes"),
        sa.CheckConstraint("idempotency_key_hash IS NULL OR idempotency_key_hash ~ '^[0-9a-f]{64}$'", name="chk_export_jobs_idempotency_hash"),
        sa.CheckConstraint("selected_document_count BETWEEN 1 AND 50000 AND exported_document_count BETWEEN 0 AND selected_document_count AND row_count BETWEEN 0 AND 1000000", name="chk_export_jobs_counts"),
        sa.CheckConstraint("progress_percentage BETWEEN 0 AND 100", name="chk_export_jobs_progress"),
        sa.CheckConstraint("attempt_count BETWEEN 0 AND 4 AND (mode='asynchronous' OR attempt_count=0)", name="chk_export_jobs_attempt_count"),
        sa.CheckConstraint("artifact_sha256 IS NULL OR artifact_sha256 ~ '^[0-9a-f]{64}$'", name="chk_export_jobs_artifact_hash"),
        sa.CheckConstraint("request_id=btrim(request_id) AND length(request_id) BETWEEN 1 AND 128 AND request_id ~ '^[!-~]+$'", name="chk_export_jobs_request_id"),
        sa.CheckConstraint("artifact_file_name IS NULL OR (artifact_file_name=btrim(artifact_file_name) AND length(artifact_file_name)>0 AND artifact_file_name NOT IN ('.','..') AND position('/' in artifact_file_name)=0 AND position(E'\\\\' in artifact_file_name)=0 AND artifact_file_name !~ '[[:cntrl:]]')", name="chk_export_jobs_artifact_file_name"),
        sa.CheckConstraint("artifact_content_type IS NULL OR artifact_content_type IN ('text/csv; charset=utf-8','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','application/json','application/zip')", name="chk_export_jobs_content_type"),
        sa.CheckConstraint("updated_at>=created_at AND (started_at IS NULL OR started_at>=created_at) AND (completed_at IS NULL OR completed_at>=COALESCE(started_at,created_at)) AND (failed_at IS NULL OR failed_at>=COALESCE(started_at,created_at)) AND (artifact_expires_at IS NULL OR (completed_at IS NOT NULL AND artifact_expires_at>completed_at AND artifact_expires_at<=completed_at+INTERVAL '7 days')) AND (expired_at IS NULL OR (artifact_expires_at IS NOT NULL AND expired_at>=artifact_expires_at))", name="chk_export_jobs_timestamps"),
        sa.CheckConstraint(
            "(status='queued' AND mode='asynchronous' AND current_stage='accepted' AND progress_percentage=0 AND exported_document_count=0 AND row_count=0 AND completed_at IS NULL AND failed_at IS NULL AND expired_at IS NULL AND lease_token IS NULL AND lease_expires_at IS NULL AND artifact_object_key IS NULL AND artifact_file_name IS NULL AND artifact_content_type IS NULL AND artifact_size_bytes IS NULL AND artifact_sha256 IS NULL AND artifact_expires_at IS NULL) OR (status='processing' AND started_at IS NOT NULL AND current_stage IN ('generating','packaging','storing') AND progress_percentage<100 AND completed_at IS NULL AND failed_at IS NULL AND expired_at IS NULL AND next_attempt_at IS NULL AND error_code IS NULL AND error_message IS NULL AND artifact_object_key IS NULL AND lease_expires_at IS NOT NULL = (mode='asynchronous')) OR (status='completed' AND current_stage='completed' AND progress_percentage=100 AND exported_document_count=selected_document_count AND row_count>0 AND started_at IS NOT NULL AND completed_at IS NOT NULL AND artifact_object_key IS NOT NULL AND artifact_file_name IS NOT NULL AND artifact_content_type IS NOT NULL AND artifact_size_bytes>0 AND artifact_sha256 IS NOT NULL AND artifact_expires_at IS NOT NULL AND failed_at IS NULL AND expired_at IS NULL) OR (status='failed' AND current_stage<>'completed' AND progress_percentage<100 AND exported_document_count=0 AND failed_at IS NOT NULL AND error_code IS NOT NULL AND error_message IS NOT NULL AND completed_at IS NULL AND artifact_object_key IS NULL) OR (status='expired' AND current_stage='completed' AND progress_percentage=100 AND exported_document_count=selected_document_count AND row_count>0 AND completed_at IS NOT NULL AND artifact_object_key IS NULL AND artifact_file_name IS NOT NULL AND artifact_sha256 IS NOT NULL AND expired_at IS NOT NULL)",
            name="chk_export_jobs_state_shape",
        ),
        sa.Index("idx_export_jobs_company_created", "company_id", sa.desc("created_at"), sa.desc("id")),
        sa.Index("idx_export_jobs_requester_created", "requested_by_user_id", sa.desc("created_at"), sa.desc("id")),
        sa.Index("uq_export_jobs_idempotency", "company_id", "requested_by_user_id", "idempotency_key_hash", unique=True, postgresql_where=sa.text("idempotency_key_hash IS NOT NULL")),
        sa.Index("idx_export_jobs_dispatch", "next_attempt_at", "created_at", "id", postgresql_where=sa.text("status='queued' AND mode='asynchronous'")),
        sa.Index("idx_export_jobs_lease", "lease_expires_at", "id", postgresql_where=sa.text("status='processing' AND mode='asynchronous'")),
        sa.Index("idx_export_jobs_expiry", "artifact_expires_at", "id", postgresql_where=sa.text("status='completed'")),
    )


class ExportJobDocument(Base):
    __tablename__ = "export_job_documents"

    export_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("export_jobs.id", name="fk_export_job_documents_job", ondelete="CASCADE"),
        primary_key=True,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("documents.id", name="fk_export_job_documents_document", ondelete="RESTRICT"),
        primary_key=True,
    )
    review_revision: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    ordinal: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    source_value_hash: Mapped[str] = mapped_column(sa.CHAR(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), **created)

    job: Mapped[ExportJob] = relationship(back_populates="documents", passive_deletes=True)
    document: Mapped[Document] = relationship(passive_deletes=True)

    __table_args__ = (
        sa.UniqueConstraint("export_job_id", "ordinal", name="uq_export_job_documents_ordinal"),
        sa.CheckConstraint("review_revision>0", name="chk_export_job_documents_review_revision"),
        sa.CheckConstraint("ordinal>=0", name="chk_export_job_documents_ordinal"),
        sa.CheckConstraint("source_value_hash ~ '^[0-9a-f]{64}$'", name="chk_export_job_documents_source_hash"),
        sa.Index("idx_export_job_documents_document", "document_id", "export_job_id"),
    )


__all__ = ["Base", "ExportJob", "ExportJobDocument"]


