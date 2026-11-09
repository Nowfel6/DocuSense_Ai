"""Shared-Base SQLAlchemy mappings for human review and immutable audit.

The canonical ingestion and RAG feature packages supply the already-mapped
Document and LineItem classes. This module extends them without redeclaring
their tables or creating another Base.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..document_ingestion.models import Document
from ..document_processing_rag.models import Base, LineItem


uuid_pk = dict(primary_key=True, default=uuid.uuid4, server_default=sa.func.gen_random_uuid())
created = dict(nullable=False, default=sa.func.now(), server_default=sa.func.now())
updated = dict(
    nullable=False,
    default=sa.func.now(),
    onupdate=sa.func.now(),
    server_default=sa.func.now(),
)


def _extend_parent_models() -> None:
    documents = Document.__table__
    if "review_revision" not in documents.c:
        revision = sa.Column(
            "review_revision", sa.BigInteger, nullable=False, server_default=sa.text("0")
        )
        reviewer = sa.Column(
            "last_reviewed_by",
            UUID(as_uuid=True),
            sa.ForeignKey(
                "users.id",
                name="fk_documents_last_reviewed_by_users",
                ondelete="SET NULL",
            ),
            nullable=True,
        )
        reviewed_at = sa.Column("last_reviewed_at", sa.DateTime(timezone=True), nullable=True)
        documents.append_column(revision)
        documents.append_column(reviewer)
        documents.append_column(reviewed_at)
        documents.append_constraint(
            sa.CheckConstraint(
                "review_revision >= 0", name="chk_documents_review_revision"
            )
        )
        documents.append_constraint(
            sa.CheckConstraint(
                "(last_reviewed_by IS NULL) = (last_reviewed_at IS NULL)",
                name="chk_documents_review_summary_pair",
            )
        )
        sa.Index(
            "idx_documents_company_review_state",
            documents.c.company_id,
            documents.c.status,
            documents.c.review_revision,
            documents.c.updated_at,
            documents.c.id,
        )
        sa.Index("idx_documents_last_reviewed_by", documents.c.last_reviewed_by)
        mapper = sa.inspect(Document)
        mapper.add_property("review_revision", documents.c.review_revision)
        mapper.add_property("last_reviewed_by", documents.c.last_reviewed_by)
        mapper.add_property("last_reviewed_at", documents.c.last_reviewed_at)

    lines = LineItem.__table__
    if "origin" not in lines.c:
        origin = sa.Column(
            "origin", sa.String(20), nullable=False, server_default="extracted"
        )
        lines.append_column(origin)
        lines.append_constraint(
            sa.CheckConstraint(
                "origin IN ('extracted','reviewer_added')",
                name="chk_line_items_origin",
            )
        )
        lines.append_constraint(
            sa.CheckConstraint(
                "(origin='reviewer_added' AND source_row_key='manual:'||id::text) "
                "OR (origin='extracted' AND source_row_key NOT LIKE 'manual:%')",
                name="chk_line_items_manual_source",
            )
        )
        sa.inspect(LineItem).add_property("origin", lines.c.origin)


_extend_parent_models()


class ReviewAuditEvent(Base):
    __tablename__ = "review_audit_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **uuid_pk)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("documents.id", name="fk_review_audit_events_document", ondelete="RESTRICT"), nullable=False
    )
    actor_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id", name="fk_review_audit_events_actor", ondelete="RESTRICT"), nullable=False
    )
    action: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    from_status: Mapped[str] = mapped_column(sa.String(30), nullable=False)
    to_status: Mapped[str] = mapped_column(sa.String(30), nullable=False)
    review_revision: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(sa.String(1000))
    note: Mapped[Optional[str]] = mapped_column(sa.String(1000))
    request_id: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    payload_hash: Mapped[str] = mapped_column(sa.CHAR(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), **created)

    changes: Mapped[list["ReviewAuditChange"]] = relationship(
        back_populates="event", passive_deletes=True
    )
    validation_run: Mapped[Optional["ReviewValidationRun"]] = relationship(
        back_populates="event", passive_deletes=True, uselist=False
    )

    __table_args__ = (
        sa.UniqueConstraint(
            "document_id", "review_revision", name="uq_review_audit_event_revision"
        ),
        sa.CheckConstraint(
            "action IN ('field_edited','approved','rejected','reopened')",
            name="chk_review_audit_events_action",
        ),
        sa.CheckConstraint("review_revision > 0", name="chk_review_audit_events_revision"),
        sa.CheckConstraint(
            "payload_hash ~ '^[0-9a-f]{64}$'", name="chk_review_audit_events_hash"
        ),
        sa.CheckConstraint(
            "request_id=btrim(request_id) AND request_id ~ '^[!-~]+$'",
            name="chk_review_audit_events_request_id",
        ),
        sa.CheckConstraint(
            "(action='field_edited' AND from_status='pending_review' AND to_status='pending_review' "
            "AND reason IS NULL AND (note IS NULL OR (note=btrim(note) AND length(note)>0))) OR "
            "(action='approved' AND from_status='pending_review' AND to_status='approved' "
            "AND reason IS NULL AND (note IS NULL OR (note=btrim(note) AND length(note)>0))) OR "
            "(action='rejected' AND from_status='pending_review' AND to_status='rejected' "
            "AND reason=btrim(reason) AND length(reason)>0 AND note IS NULL) OR "
            "(action='reopened' AND from_status='approved' AND to_status='pending_review' "
            "AND reason=btrim(reason) AND length(reason)>0 AND note IS NULL)",
            name="chk_review_audit_events_reason_note",
        ),
        sa.Index(
            "idx_review_audit_document_created",
            "document_id",
            sa.text("created_at DESC"),
            sa.text("id DESC"),
        ),
        sa.Index(
            "idx_review_audit_actor_created",
            "actor_user_id",
            sa.text("created_at DESC"),
            sa.text("id DESC"),
        ),
        sa.Index(
            "idx_review_audit_document_action",
            "document_id",
            "action",
            sa.text("created_at DESC"),
            sa.text("id DESC"),
        ),
    )


class ReviewAuditChange(Base):
    __tablename__ = "review_audit_changes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **uuid_pk)
    audit_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("review_audit_events.id", name="fk_review_audit_changes_event", ondelete="CASCADE"),
        nullable=False,
    )
    field_path: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    change_kind: Mapped[str] = mapped_column(sa.String(10), nullable=False)
    old_value: Mapped[Optional[Any]] = mapped_column(JSONB)
    new_value: Mapped[Optional[Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), **created)

    event: Mapped[ReviewAuditEvent] = relationship(back_populates="changes")

    __table_args__ = (
        sa.UniqueConstraint(
            "audit_event_id", "field_path", name="uq_review_audit_change_path"
        ),
        sa.CheckConstraint(
            "change_kind IN ('set','add','remove','reorder')",
            name="chk_review_audit_changes_kind",
        ),
        sa.CheckConstraint(
            "field_path ~ '^(invoice\\.(invoice_number|supplier_name|supplier_tax_id|buyer_name|date_issued|due_date|currency|subtotal|tax_amount|discount_amount|grand_total)|line_items\\.[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}(\\.(description|hs_code|quantity|unit_price|tax_amount|total_price|line_order))?|document\\.status)$'",
            name="chk_review_audit_changes_path",
        ),
        sa.CheckConstraint(
            "(change_kind='set' AND old_value IS DISTINCT FROM new_value) OR "
            "(change_kind='add' AND old_value IS NULL AND new_value IS NOT NULL) OR "
            "(change_kind='remove' AND old_value IS NOT NULL AND new_value IS NULL) OR "
            "(change_kind='reorder' AND jsonb_typeof(old_value)='array' "
            "AND jsonb_typeof(new_value)='array' AND old_value IS DISTINCT FROM new_value)",
            name="chk_review_audit_changes_values",
        ),
        sa.CheckConstraint(
            "(old_value IS NULL OR octet_length(old_value::text)<=65536) AND "
            "(new_value IS NULL OR octet_length(new_value::text)<=65536)",
            name="chk_review_audit_changes_size",
        ),
    )


class ReviewValidationRun(Base):
    __tablename__ = "review_validation_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **uuid_pk)
    audit_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("review_audit_events.id", name="fk_review_validation_runs_event", ondelete="CASCADE"),
        nullable=False,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("documents.id", name="fk_review_validation_runs_document", ondelete="RESTRICT"), nullable=False
    )
    review_revision: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    validation_version: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    candidate_hash: Mapped[str] = mapped_column(sa.CHAR(64), nullable=False)
    is_math_valid: Mapped[bool] = mapped_column(sa.Boolean, nullable=False)
    approval_eligible: Mapped[bool] = mapped_column(sa.Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), **created)

    event: Mapped[ReviewAuditEvent] = relationship(back_populates="validation_run")
    results: Mapped[list["ReviewValidationResult"]] = relationship(
        back_populates="run", passive_deletes=True
    )

    __table_args__ = (
        sa.UniqueConstraint("audit_event_id", name="uq_review_validation_event"),
        sa.UniqueConstraint(
            "document_id", "review_revision", name="uq_review_validation_revision"
        ),
        sa.CheckConstraint(
            "review_revision>0", name="chk_review_validation_runs_revision"
        ),
        sa.CheckConstraint(
            "validation_version=btrim(validation_version) AND length(validation_version)>0",
            name="chk_review_validation_runs_version",
        ),
        sa.CheckConstraint(
            "candidate_hash ~ '^[0-9a-f]{64}$'", name="chk_review_validation_runs_hash"
        ),
    )


class ReviewValidationResult(Base):
    __tablename__ = "review_validation_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **uuid_pk)
    review_validation_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("review_validation_runs.id", name="fk_review_validation_results_run", ondelete="CASCADE"),
        nullable=False,
    )
    rule_id: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    scope_key: Mapped[str] = mapped_column(
        sa.String(255), nullable=False, server_default="document"
    )
    status: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    observed_value: Mapped[Optional[Any]] = mapped_column(JSONB)
    expected_value: Mapped[Optional[Any]] = mapped_column(JSONB)
    difference: Mapped[Optional[Decimal]] = mapped_column(sa.Numeric(18, 6))
    epsilon: Mapped[Optional[Decimal]] = mapped_column(sa.Numeric(8, 6))
    message_code: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    blocks_approval: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.false()
    )
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), **created)

    run: Mapped[ReviewValidationRun] = relationship(back_populates="results")

    __table_args__ = (
        sa.UniqueConstraint(
            "review_validation_run_id",
            "rule_id",
            "scope_key",
            name="uq_review_validation_rule",
        ),
        sa.CheckConstraint(
            "rule_id=btrim(rule_id) AND length(rule_id)>0 AND "
            "scope_key=btrim(scope_key) AND length(scope_key)>0 AND "
            "message_code=btrim(message_code) AND length(message_code)>0",
            name="chk_review_validation_results_strings",
        ),
        sa.CheckConstraint(
            "status IN ('passed','failed','missing','not_applicable')",
            name="chk_review_validation_results_status",
        ),
        sa.CheckConstraint(
            "(difference IS NULL OR (difference<>'NaN'::numeric AND difference>=0)) "
            "AND (epsilon IS NULL OR (epsilon<>'NaN'::numeric AND epsilon>=0))",
            name="chk_review_validation_results_nonnegative",
        ),
        sa.CheckConstraint(
            "rule_id NOT LIKE 'BR-03%' "
            "OR status IN ('missing','not_applicable') "
            "OR epsilon=0.050000",
            name="chk_review_validation_results_financial_epsilon",
        ),
        sa.CheckConstraint(
            "(status IN ('missing','not_applicable') AND difference IS NULL AND epsilon IS NULL) "
            "OR status NOT IN ('missing','not_applicable')",
            name="chk_review_validation_results_comparison",
        ),
        sa.CheckConstraint(
            "difference IS NULL OR epsilon IS NULL OR status NOT IN ('passed','failed') OR "
            "(status='passed' AND difference<=epsilon) OR "
            "(status='failed' AND difference>epsilon)",
            name="chk_review_validation_results_pass_fail",
        ),
    )


class ReviewIdempotencyKey(Base):
    __tablename__ = "review_idempotency_keys"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **uuid_pk)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("companies.id", name="fk_review_idempotency_company", ondelete="RESTRICT"), nullable=False
    )
    actor_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id", name="fk_review_idempotency_actor", ondelete="RESTRICT"), nullable=False
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("documents.id", name="fk_review_idempotency_document", ondelete="RESTRICT"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(sa.CHAR(64), nullable=False)
    audit_event_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("review_audit_events.id", name="fk_review_idempotency_event", ondelete="RESTRICT"),
    )
    response_status: Mapped[Optional[int]] = mapped_column(sa.SmallInteger)
    response_body: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), **created)
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), **updated)
    expires_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)

    __table_args__ = (
        sa.UniqueConstraint(
            "company_id",
            "actor_user_id",
            "document_id",
            "idempotency_key",
            name="uq_review_idempotency_scope",
        ),
        sa.UniqueConstraint(
            "audit_event_id", name="uq_review_idempotency_audit_event"
        ),
        sa.CheckConstraint(
            "idempotency_key=btrim(idempotency_key) AND idempotency_key ~ '^[!-~]+$'",
            name="chk_review_idempotency_key",
        ),
        sa.CheckConstraint(
            "request_hash ~ '^[0-9a-f]{64}$'", name="chk_review_idempotency_hash"
        ),
        sa.CheckConstraint(
            "expires_at>=created_at+INTERVAL '24 hours'",
            name="chk_review_idempotency_expiry",
        ),
        sa.CheckConstraint(
            "(audit_event_id IS NULL AND response_status IS NULL AND response_body IS NULL) OR "
            "(audit_event_id IS NOT NULL AND response_status BETWEEN 200 AND 299 "
            "AND jsonb_typeof(response_body)='object' "
            "AND octet_length(response_body::text)<=65536)",
            name="chk_review_idempotency_response",
        ),
        sa.Index("idx_review_idempotency_actor", "actor_user_id", sa.text("created_at DESC")),
        sa.Index("idx_review_idempotency_document", "document_id", sa.text("created_at DESC")),
        sa.Index("idx_review_idempotency_expiry", "expires_at", "id"),
    )


__all__ = [
    "Base",
    "Document",
    "LineItem",
    "ReviewAuditEvent",
    "ReviewAuditChange",
    "ReviewValidationRun",
    "ReviewValidationResult",
    "ReviewIdempotencyKey",
]
