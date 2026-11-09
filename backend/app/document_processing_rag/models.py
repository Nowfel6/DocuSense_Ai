"""SQLAlchemy mappings for document processing, RAG, and invoice extraction.

Load the sibling auth and ingestion mappings first so this module extends their
single shared ``Base``. Vectors are internal persistence fields and should not be
serialized by API response models.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

import sqlalchemy as sa
from pgvector.sqlalchemy import VECTOR
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..auth.models import Base


uuid_pk = dict(primary_key=True, default=uuid.uuid4, server_default=sa.func.gen_random_uuid())
created = dict(nullable=False, default=sa.func.now(), server_default=sa.func.now())
updated = dict(nullable=False, default=sa.func.now(), onupdate=sa.func.now(), server_default=sa.func.now())


class DocumentPartition(Base):
    __tablename__ = "document_partitions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **uuid_pk)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), sa.ForeignKey("processing_jobs.id", ondelete="CASCADE"), nullable=False)
    created_attempt: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False)
    pipeline_version: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    configuration_hash: Mapped[str] = mapped_column(sa.CHAR(64), nullable=False)
    parser_name: Mapped[str] = mapped_column(sa.String(100), nullable=False, server_default="docling")
    parser_version: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    ocr_policy_version: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    canonical_document: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    content_hash: Mapped[str] = mapped_column(sa.CHAR(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), **created)

    __table_args__ = (
        sa.UniqueConstraint("document_id", name="uq_document_partitions_document_id"),
        sa.UniqueConstraint("job_id", name="uq_document_partitions_job_id"),
        sa.CheckConstraint("created_attempt BETWEEN 1 AND 4", name="chk_document_partitions_attempt"),
        sa.CheckConstraint("length(btrim(pipeline_version))>0 AND parser_name='docling' AND length(btrim(parser_version))>0 AND length(btrim(ocr_policy_version))>0", name="chk_document_partitions_versions"),
        sa.CheckConstraint("configuration_hash ~ '^[0-9a-f]{64}$'", name="chk_document_partitions_configuration_hash"),
        sa.CheckConstraint("content_hash ~ '^[0-9a-f]{64}$'", name="chk_document_partitions_content_hash"),
        sa.CheckConstraint("octet_length(canonical_document::text)<=16777216", name="chk_document_partitions_size"),
        sa.CheckConstraint(
            "jsonb_typeof(canonical_document)='object' AND canonical_document->>'document_id'=document_id::text "
            "AND canonical_document->>'pipeline_version'=pipeline_version AND canonical_document->>'parser_name'=parser_name "
            "AND canonical_document->>'parser_version'=parser_version AND canonical_document->>'ocr_policy_version'=ocr_policy_version "
            "AND CASE WHEN jsonb_typeof(canonical_document->'pages')='array' THEN jsonb_array_length(canonical_document->'pages') BETWEEN 1 AND 500 ELSE FALSE END "
            "AND jsonb_typeof(canonical_document->'warning_codes')='array'",
            name="chk_document_partitions_shape",
        ),
        sa.Index("idx_document_partitions_company_id", "company_id"),
    )


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **uuid_pk)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    parent_chunk_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    pipeline_version: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    ordinal: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    page_start: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    page_end: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    section: Mapped[Optional[str]] = mapped_column(sa.String(255))
    chunk_type: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    retrieval_role: Mapped[str] = mapped_column(sa.String(10), nullable=False)
    raw_content: Mapped[str] = mapped_column(sa.Text, nullable=False)
    structured_content: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)
    summary: Mapped[Optional[str]] = mapped_column(sa.Text)
    token_count: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    source_element_ids: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, server_default=sa.text("'[]'::jsonb"))
    bounding_boxes: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, server_default=sa.text("'[]'::jsonb"))
    content_hash: Mapped[str] = mapped_column(sa.CHAR(64), nullable=False)
    embedding: Mapped[Optional[list[float]]] = mapped_column(VECTOR(384))
    embedding_model: Mapped[Optional[str]] = mapped_column(sa.String(255))
    embedding_revision: Mapped[Optional[str]] = mapped_column(sa.String(255))
    embedding_status: Mapped[str] = mapped_column(sa.String(12), nullable=False, server_default="pending")
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), **created)
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), **updated)
    parent: Mapped[Optional["DocumentChunk"]] = relationship(remote_side="DocumentChunk.id", foreign_keys=[parent_chunk_id])

    __table_args__ = (
        sa.UniqueConstraint("document_id", "pipeline_version", "ordinal", name="uq_document_chunks_version_ordinal"),
        sa.UniqueConstraint("id", "document_id", "pipeline_version", name="uq_document_chunks_identity_owner"),
        sa.ForeignKeyConstraint(
            ["parent_chunk_id", "document_id", "pipeline_version"],
            ["document_chunks.id", "document_chunks.document_id", "document_chunks.pipeline_version"],
            name="fk_document_chunks_parent_owner", ondelete="CASCADE",
        ),
        sa.CheckConstraint("length(btrim(pipeline_version)) > 0", name="chk_document_chunks_pipeline_version"),
        sa.CheckConstraint("ordinal >= 0", name="chk_document_chunks_ordinal"),
        sa.CheckConstraint("page_start >= 1 AND page_end >= page_start", name="chk_document_chunks_pages"),
        sa.CheckConstraint("chunk_type IN ('text','table','header','list','image','unknown')", name="chk_document_chunks_type"),
        sa.CheckConstraint("retrieval_role IN ('parent','child','both')", name="chk_document_chunks_retrieval_role"),
        sa.CheckConstraint("length(btrim(raw_content)) > 0", name="chk_document_chunks_content"),
        sa.CheckConstraint("token_count > 0", name="chk_document_chunks_token_count"),
        sa.CheckConstraint("jsonb_typeof(source_element_ids)='array'", name="chk_document_chunks_source_ids_array"),
        sa.CheckConstraint("jsonb_typeof(bounding_boxes)='array'", name="chk_document_chunks_boxes_array"),
        sa.CheckConstraint("content_hash ~ '^[0-9a-f]{64}$'", name="chk_document_chunks_content_hash"),
        sa.CheckConstraint("embedding_status IN ('pending','completed','failed','not_required')", name="chk_document_chunks_embedding_status"),
        sa.CheckConstraint(
            "(embedding_status='completed' AND embedding IS NOT NULL AND embedding_model='sentence-transformers/all-MiniLM-L6-v2' "
            "AND embedding_revision IS NOT NULL AND length(btrim(embedding_revision))>0 AND abs(vector_norm(embedding)-1.0)<=0.0001) "
            "OR (embedding_status IN ('pending','failed') AND embedding IS NULL AND embedding_model IS NULL AND embedding_revision IS NULL) "
            "OR (embedding_status='not_required' AND retrieval_role='parent' AND embedding IS NULL AND embedding_model IS NULL AND embedding_revision IS NULL)",
            name="chk_document_chunks_embedding_consistency",
        ),
        sa.CheckConstraint("parent_chunk_id IS NULL OR parent_chunk_id <> id", name="chk_document_chunks_parent_not_self"),
        sa.Index("idx_document_chunks_document_type_page", "document_id", "chunk_type", "page_start", "ordinal"),
        sa.Index("idx_document_chunks_parent", "parent_chunk_id", "ordinal"),
        sa.Index("idx_document_chunks_embedding_ready", "document_id", "ordinal", postgresql_where=sa.text("embedding_status='completed' AND embedding IS NOT NULL")),
    )


class ExtractionRun(Base):
    __tablename__ = "extraction_runs"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **uuid_pk)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), sa.ForeignKey("processing_jobs.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(sa.String(12), nullable=False, server_default="running")
    pipeline_version: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    configuration_hash: Mapped[str] = mapped_column(sa.CHAR(64), nullable=False)
    parser_name: Mapped[str] = mapped_column(sa.String(100), nullable=False, server_default="docling")
    parser_version: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    ocr_policy_version: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    embedding_model: Mapped[str] = mapped_column(sa.String(255), nullable=False, server_default="sentence-transformers/all-MiniLM-L6-v2")
    embedding_revision: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    embedding_dimension: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False, server_default="384")
    llm_provider: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    llm_model: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    prompt_version: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    schema_version: Mapped[str] = mapped_column(sa.String(64), nullable=False, server_default="commercial-invoice-v1")
    retrieval_config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    warning_codes: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, server_default=sa.text("'[]'::jsonb"))
    input_tokens: Mapped[Optional[int]] = mapped_column(sa.Integer)
    output_tokens: Mapped[Optional[int]] = mapped_column(sa.Integer)
    estimated_cost: Mapped[Optional[Decimal]] = mapped_column(sa.Numeric(14, 6))
    started_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), **created)
    finished_at: Mapped[Optional[datetime]] = mapped_column(sa.DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), **created)
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), **updated)

    __table_args__ = (
        sa.UniqueConstraint("document_id", name="uq_extraction_runs_document_id"),
        sa.UniqueConstraint("job_id", name="uq_extraction_runs_job_id"),
        sa.CheckConstraint("status IN ('running','completed','failed')", name="chk_extraction_runs_status"),
        sa.CheckConstraint("(status='running' AND finished_at IS NULL) OR (status IN ('completed','failed') AND finished_at IS NOT NULL AND finished_at>=started_at)", name="chk_extraction_runs_terminal_time"),
        sa.CheckConstraint("configuration_hash ~ '^[0-9a-f]{64}$'", name="chk_extraction_runs_configuration_hash"),
        sa.CheckConstraint("embedding_model='sentence-transformers/all-MiniLM-L6-v2' AND embedding_dimension=384 AND length(btrim(embedding_revision))>0", name="chk_extraction_runs_embedding"),
        sa.CheckConstraint("parser_name='docling' AND schema_version='commercial-invoice-v1' AND length(btrim(pipeline_version))>0 AND length(btrim(parser_version))>0 AND length(btrim(ocr_policy_version))>0 AND length(btrim(llm_provider))>0 AND length(btrim(llm_model))>0 AND length(btrim(prompt_version))>0", name="chk_extraction_runs_versions"),
        sa.CheckConstraint("jsonb_typeof(retrieval_config)='object'", name="chk_extraction_runs_retrieval_config"),
        sa.CheckConstraint("jsonb_typeof(warning_codes)='array'", name="chk_extraction_runs_warning_codes"),
        sa.CheckConstraint("(input_tokens IS NULL OR input_tokens>=0) AND (output_tokens IS NULL OR output_tokens>=0) AND (estimated_cost IS NULL OR (estimated_cost <> 'NaN'::numeric AND estimated_cost>=0))", name="chk_extraction_runs_usage"),
    )


class Invoice(Base):
    __tablename__ = "invoices"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **uuid_pk)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    extraction_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), sa.ForeignKey("extraction_runs.id", ondelete="CASCADE"), nullable=False)
    invoice_number: Mapped[Optional[str]] = mapped_column(sa.String(100))
    supplier_name: Mapped[Optional[str]] = mapped_column(sa.String(255))
    supplier_tax_id: Mapped[Optional[str]] = mapped_column(sa.String(100))
    buyer_name: Mapped[Optional[str]] = mapped_column(sa.String(255))
    date_issued: Mapped[Optional[date]] = mapped_column(sa.Date)
    due_date: Mapped[Optional[date]] = mapped_column(sa.Date)
    currency: Mapped[Optional[str]] = mapped_column(sa.CHAR(3))
    subtotal: Mapped[Optional[Decimal]] = mapped_column(sa.Numeric(14, 2))
    tax_amount: Mapped[Optional[Decimal]] = mapped_column(sa.Numeric(14, 2))
    discount_amount: Mapped[Optional[Decimal]] = mapped_column(sa.Numeric(14, 2))
    grand_total: Mapped[Optional[Decimal]] = mapped_column(sa.Numeric(14, 2))
    is_math_valid: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.false())
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), **created)
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), **updated)
    line_items: Mapped[list["LineItem"]] = relationship(passive_deletes=True)
    __table_args__ = (
        sa.UniqueConstraint("document_id", name="uq_invoices_document_id"),
        sa.UniqueConstraint("extraction_run_id", name="uq_invoices_extraction_run_id"),
        sa.CheckConstraint("(invoice_number IS NULL OR (length(btrim(invoice_number))>0 AND lower(btrim(invoice_number)) NOT IN ('n/a','none','null'))) AND (supplier_name IS NULL OR length(btrim(supplier_name))>0) AND (supplier_tax_id IS NULL OR length(btrim(supplier_tax_id))>0) AND (buyer_name IS NULL OR length(btrim(buyer_name))>0)", name="chk_invoices_normalized_strings"),
        sa.CheckConstraint("currency IS NULL OR currency ~ '^[A-Z]{3}$'", name="chk_invoices_currency"),
        sa.CheckConstraint("(subtotal IS NULL OR (subtotal <> 'NaN'::numeric AND subtotal>=0)) AND (tax_amount IS NULL OR (tax_amount <> 'NaN'::numeric AND tax_amount>=0)) AND (discount_amount IS NULL OR (discount_amount <> 'NaN'::numeric AND discount_amount>=0)) AND (grand_total IS NULL OR (grand_total <> 'NaN'::numeric AND grand_total>=0))", name="chk_invoices_nonnegative_amounts"),
        sa.Index("idx_invoices_number", "invoice_number", postgresql_where=sa.text("invoice_number IS NOT NULL")),
    )


class LineItem(Base):
    __tablename__ = "line_items"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **uuid_pk)
    invoice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), sa.ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False)
    source_row_key: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    line_order: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(sa.Text)
    hs_code: Mapped[Optional[str]] = mapped_column(sa.String(50))
    quantity: Mapped[Optional[Decimal]] = mapped_column(sa.Numeric(18, 4))
    unit_price: Mapped[Optional[Decimal]] = mapped_column(sa.Numeric(14, 4))
    tax_amount: Mapped[Optional[Decimal]] = mapped_column(sa.Numeric(14, 2))
    total_price: Mapped[Optional[Decimal]] = mapped_column(sa.Numeric(14, 2))
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), **created)
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), **updated)
    __table_args__ = (
        sa.UniqueConstraint("invoice_id", "source_row_key", name="uq_line_items_invoice_source"),
        sa.UniqueConstraint("invoice_id", "line_order", name="uq_line_items_invoice_order"),
        sa.CheckConstraint("length(btrim(source_row_key))>0", name="chk_line_items_source"),
        sa.CheckConstraint("line_order>0", name="chk_line_items_order"),
        sa.CheckConstraint("(description IS NULL OR length(btrim(description))>0) AND (hs_code IS NULL OR length(btrim(hs_code))>0)", name="chk_line_items_strings"),
        sa.CheckConstraint("(quantity IS NULL OR (quantity <> 'NaN'::numeric AND quantity>=0)) AND (unit_price IS NULL OR (unit_price <> 'NaN'::numeric AND unit_price>=0)) AND (tax_amount IS NULL OR (tax_amount <> 'NaN'::numeric AND tax_amount>=0)) AND (total_price IS NULL OR (total_price <> 'NaN'::numeric AND total_price>=0))", name="chk_line_items_nonnegative"),
    )


class FieldEvidence(Base):
    __tablename__ = "field_evidence"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **uuid_pk)
    extraction_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), sa.ForeignKey("extraction_runs.id", ondelete="CASCADE"), nullable=False)
    field_path: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    source_value: Mapped[Optional[str]] = mapped_column(sa.Text)
    normalized_value: Mapped[Optional[Any]] = mapped_column(JSONB)
    primary_chunk_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), sa.ForeignKey("document_chunks.id", ondelete="SET NULL"))
    source_page: Mapped[Optional[int]] = mapped_column(sa.Integer)
    bounding_box: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)
    evidence_excerpt: Mapped[Optional[str]] = mapped_column(sa.String(1000))
    retrieval_rank: Mapped[Optional[int]] = mapped_column(sa.SmallInteger)
    retrieval_score: Mapped[Optional[Decimal]] = mapped_column(sa.Numeric(8, 6))
    exact_match: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.false())
    confidence_score: Mapped[Decimal] = mapped_column(sa.Numeric(5, 2), nullable=False, server_default="0.00")
    reason_codes: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, server_default=sa.text("'[]'::jsonb"))
    validation_state: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), **created)
    __table_args__ = (
        sa.UniqueConstraint("extraction_run_id", "field_path", name="uq_field_evidence_run_path"),
        sa.CheckConstraint("length(btrim(field_path))>0", name="chk_field_evidence_path"),
        sa.CheckConstraint("(source_page IS NULL OR source_page>0) AND (retrieval_rank IS NULL OR retrieval_rank>0)", name="chk_field_evidence_positions"),
        sa.CheckConstraint("confidence_score <> 'NaN'::numeric AND confidence_score BETWEEN 0 AND 100", name="chk_field_evidence_confidence"),
        sa.CheckConstraint("retrieval_score IS NULL OR (retrieval_score <> 'NaN'::numeric AND retrieval_score BETWEEN -1 AND 1)", name="chk_field_evidence_retrieval"),
        sa.CheckConstraint("bounding_box IS NULL OR jsonb_typeof(bounding_box)='object'", name="chk_field_evidence_box"),
        sa.CheckConstraint("jsonb_typeof(reason_codes)='array'", name="chk_field_evidence_reason_codes"),
        sa.CheckConstraint("validation_state IN ('valid','invalid','missing','ambiguous','unsupported')", name="chk_field_evidence_state"),
        sa.CheckConstraint("(validation_state='valid' AND primary_chunk_id IS NOT NULL) OR (validation_state IN ('missing','unsupported') AND source_value IS NULL AND normalized_value IS NULL AND primary_chunk_id IS NULL AND source_page IS NULL AND bounding_box IS NULL AND evidence_excerpt IS NULL AND exact_match=FALSE AND confidence_score=0) OR validation_state IN ('invalid','ambiguous')", name="chk_field_evidence_state_consistency"),
        sa.Index("idx_field_evidence_primary_chunk", "primary_chunk_id", postgresql_where=sa.text("primary_chunk_id IS NOT NULL")),
        sa.Index("idx_field_evidence_state", "extraction_run_id", "validation_state", "confidence_score"),
    )


class ValidationResult(Base):
    __tablename__ = "validation_results"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **uuid_pk)
    extraction_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), sa.ForeignKey("extraction_runs.id", ondelete="CASCADE"), nullable=False)
    rule_id: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    scope_key: Mapped[str] = mapped_column(sa.String(255), nullable=False, server_default="document")
    status: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    observed_value: Mapped[Optional[Any]] = mapped_column(JSONB)
    expected_value: Mapped[Optional[Any]] = mapped_column(JSONB)
    difference: Mapped[Optional[Decimal]] = mapped_column(sa.Numeric(18, 6))
    epsilon: Mapped[Optional[Decimal]] = mapped_column(sa.Numeric(8, 6))
    message_code: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), **created)
    __table_args__ = (
        sa.UniqueConstraint("extraction_run_id", "rule_id", "scope_key", name="uq_validation_results_run_rule_scope"),
        sa.CheckConstraint("length(btrim(rule_id))>0 AND length(btrim(scope_key))>0 AND length(btrim(message_code))>0", name="chk_validation_results_strings"),
        sa.CheckConstraint("status IN ('passed','failed','missing','not_applicable')", name="chk_validation_results_status"),
        sa.CheckConstraint("(difference IS NULL OR (difference <> 'NaN'::numeric AND difference>=0)) AND (epsilon IS NULL OR (epsilon <> 'NaN'::numeric AND epsilon>=0))", name="chk_validation_results_nonnegative"),
        sa.CheckConstraint("rule_id NOT LIKE 'BR-03%' OR epsilon=0.050000", name="chk_validation_results_financial_epsilon"),
        sa.CheckConstraint("difference IS NULL OR epsilon IS NULL OR status NOT IN ('passed','failed') OR (status='passed' AND difference<=epsilon) OR (status='failed' AND difference>epsilon)", name="chk_validation_results_comparison"),
    )


__all__ = ["Base", "DocumentPartition", "DocumentChunk", "ExtractionRun", "Invoice", "LineItem", "FieldEvidence", "ValidationResult"]
