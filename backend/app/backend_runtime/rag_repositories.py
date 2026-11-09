"""Concrete RAG processing, technical-read, and exact-vector repositories."""

from __future__ import annotations

import json
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..document_processing_rag.errors import FenceLost, ProcessingError
from ..document_processing_rag.repository import (
    ChunkPage, EvidenceSnapshot, RankedChunk, TechnicalDocument,
)
from ..document_processing_rag.schemas import (
    CallerContext, CanonicalDocument, ChunkDraft, ChunkItem, ChunkQuery,
    EmbeddedChunk, EvidenceItem, EvidenceQuery, ExtractionRunInfo,
    FieldEvidenceDraft, InvoiceLineResult, InvoiceResult, JobClaim,
    ProcessingIdentity, ValidationBundle, ValidationRuleSummary,
    ValidationSummary,
)


MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def _fence(job_id: UUID, attempt: int) -> UUID:
    """Stable claim token; database authorization remains job+attempt+live lease."""
    return uuid5(NAMESPACE_URL, f"docusense-processing:{job_id}:{attempt}")


def _json(value: object) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def _vector(value: tuple[float, ...]) -> str:
    return "[" + ",".join(format(item, ".17g") for item in value) + "]"


class RagSqlRepository:
    """All PostgreSQL-owned RAG operations with attempt/lease fencing."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    @staticmethod
    def _check_fence(claim: JobClaim) -> None:
        if claim.fence != _fence(claim.job_id, claim.attempt):
            raise FenceLost()

    @staticmethod
    async def _lock_claim(session: AsyncSession, claim: JobClaim) -> dict[str, object]:
        RagSqlRepository._check_fence(claim)
        row = (await session.execute(text(
            """SELECT d.company_id,d.s3_url,d.doc_type,j.status,j.current_stage,
                      j.progress_percentage,j.attempt_count,j.lease_expires_at
               FROM documents d JOIN processing_jobs j ON j.document_id=d.id
               WHERE d.id=:document_id AND j.id=:job_id
               FOR UPDATE OF d,j"""
        ), {"document_id": claim.document_id, "job_id": claim.job_id})).mappings().one_or_none()
        if (row is None or row["status"] != "processing"
                or row["attempt_count"] != claim.attempt
                or row["lease_expires_at"] is None
                or not bool((await session.execute(text(
                    "SELECT :lease_expires_at > clock_timestamp()"
                ), {"lease_expires_at": row["lease_expires_at"]})).scalar_one())):
            raise FenceLost()
        return dict(row)

    async def claim(self, document_id: UUID, job_id: UUID, identity: ProcessingIdentity,
                    lease_seconds: float) -> JobClaim | None:
        if lease_seconds <= 0 or lease_seconds > 3600:
            raise ValueError("lease_seconds must be between 0 and 3600")
        async with self._sessions() as session:
            async with session.begin():
                row = (await session.execute(text(
                    """SELECT d.company_id,d.s3_url,d.doc_type,d.status AS document_status,
                              j.status,j.current_stage,j.progress_percentage,j.attempt_count,
                              j.next_attempt_at,j.lease_expires_at
                       FROM documents d JOIN processing_jobs j ON j.document_id=d.id
                       WHERE d.id=:document_id AND j.id=:job_id FOR UPDATE OF d,j"""
                ), {"document_id": document_id, "job_id": job_id})).mappings().one_or_none()
                if row is None or row["doc_type"] != "commercial_invoice":
                    return None
                database_now = (await session.execute(text("SELECT clock_timestamp()"))).scalar_one()
                due = row["next_attempt_at"] is None or row["next_attempt_at"] <= database_now
                expired = row["lease_expires_at"] is not None and row["lease_expires_at"] <= database_now
                eligible = row["status"] == "queued" and due
                eligible = eligible or (row["status"] == "processing" and expired)
                if not eligible or row["attempt_count"] >= 4:
                    return None
                attempt = int(row["attempt_count"]) + 1
                lease = (await session.execute(text(
                    """UPDATE processing_jobs SET status='processing',current_stage='partitioning',
                              progress_percentage=GREATEST(progress_percentage,20),attempt_count=:attempt,
                              next_attempt_at=NULL,lease_expires_at=clock_timestamp()+(:lease_seconds*interval '1 second'),
                              error_code=NULL,error_message=NULL,started_at=COALESCE(started_at,clock_timestamp()),
                              finished_at=NULL
                       WHERE id=:job_id RETURNING lease_expires_at"""
                ), {"attempt": attempt, "lease_seconds": lease_seconds, "job_id": job_id})).scalar_one()
                await session.execute(text(
                    "UPDATE documents SET status='partitioning',overall_confidence=NULL WHERE id=:document_id"
                ), {"document_id": document_id})
                run = (await session.execute(text(
                    "SELECT * FROM extraction_runs WHERE document_id=:document_id FOR UPDATE"
                ), {"document_id": document_id})).mappings().one_or_none()
                expected = {
                    "pipeline_version": identity.pipeline_version,
                    "configuration_hash": identity.configuration_hash,
                    "parser_name": "docling", "parser_version": identity.parser_version,
                    "ocr_policy_version": identity.ocr_policy_version,
                    "embedding_model": MODEL, "embedding_revision": identity.embedding_revision,
                    "embedding_dimension": 384, "llm_provider": identity.llm_provider,
                    "llm_model": identity.llm_model, "prompt_version": identity.prompt_version,
                    "schema_version": identity.schema_version,
                }
                if run is None:
                    await session.execute(text(
                        """INSERT INTO extraction_runs
                           (id,document_id,job_id,status,pipeline_version,configuration_hash,
                            parser_name,parser_version,ocr_policy_version,embedding_model,
                            embedding_revision,embedding_dimension,llm_provider,llm_model,
                            prompt_version,schema_version,retrieval_config)
                           VALUES (:id,:document_id,:job_id,'running',:pipeline_version,
                            :configuration_hash,'docling',:parser_version,:ocr_policy_version,
                            :embedding_model,:embedding_revision,384,:llm_provider,:llm_model,
                            :prompt_version,:schema_version,CAST(:retrieval_config AS jsonb))"""
                    ), {"id": uuid5(NAMESPACE_URL, f"docusense-run:{document_id}"),
                        "document_id": document_id, "job_id": job_id,
                        **expected, "retrieval_config": _json({"mode": "exact_cosine", "top_k": 24, "selected_limit": 12, "context_tokens": 8000})})
                elif run["status"] != "running" or any(run[key] != value for key, value in expected.items()):
                    raise ProcessingError("PROCESSING_CONFIGURATION_CHANGED")
        return JobClaim(
            document_id=document_id, job_id=job_id, attempt=attempt,
            fence=_fence(job_id, attempt), lease_expires_at=lease,
            private_reference=row["s3_url"], doc_type="commercial_invoice", identity=identity,
        )

    async def heartbeat(self, claim: JobClaim, lease_seconds: float) -> JobClaim:
        self._check_fence(claim)
        async with self._sessions() as session:
            async with session.begin():
                lease = (await session.execute(text(
                    """UPDATE processing_jobs
                       SET lease_expires_at=clock_timestamp()+(:seconds*interval '1 second')
                       WHERE id=:job_id AND document_id=:document_id AND status='processing'
                         AND attempt_count=:attempt AND lease_expires_at>clock_timestamp()
                       RETURNING lease_expires_at"""
                ), {"seconds": lease_seconds, "job_id": claim.job_id,
                    "document_id": claim.document_id, "attempt": claim.attempt})).scalar_one_or_none()
                if lease is None:
                    raise FenceLost()
        return claim.model_copy(update={"lease_expires_at": lease})

    async def load_partition(self, claim: JobClaim) -> CanonicalDocument | None:
        async with self._sessions() as session:
            async with session.begin():
                await self._lock_claim(session, claim)
                row = (await session.execute(text(
                    """SELECT canonical_document,pipeline_version,configuration_hash,
                              parser_version,ocr_policy_version
                       FROM document_partitions
                       WHERE document_id=:document_id AND job_id=:job_id"""
                ), {"document_id": claim.document_id, "job_id": claim.job_id})).mappings().one_or_none()
                if row is None:
                    return None
                if (row["pipeline_version"] != claim.identity.pipeline_version
                        or row["configuration_hash"] != claim.identity.configuration_hash
                        or row["parser_version"] != claim.identity.parser_version
                        or row["ocr_policy_version"] != claim.identity.ocr_policy_version):
                    raise ProcessingError("PROCESSING_CONFIGURATION_CHANGED")
                return CanonicalDocument.model_validate(row["canonical_document"])

    async def persist_partition(self, claim: JobClaim, document: CanonicalDocument) -> None:
        if document.document_id != claim.document_id:
            raise ProcessingError("PROCESSING_DATA_INTEGRITY_ERROR")
        async with self._sessions() as session:
            async with session.begin():
                owner = await self._lock_claim(session, claim)
                await session.execute(text(
                    """INSERT INTO document_partitions
                       (company_id,document_id,job_id,created_attempt,pipeline_version,
                        configuration_hash,parser_name,parser_version,ocr_policy_version,
                        canonical_document)
                       VALUES (:company_id,:document_id,:job_id,:attempt,:pipeline_version,
                        :configuration_hash,'docling',:parser_version,:ocr_policy_version,
                        CAST(:canonical AS jsonb))
                       ON CONFLICT (document_id) DO UPDATE SET
                         company_id=EXCLUDED.company_id,job_id=EXCLUDED.job_id,
                         created_attempt=document_partitions.created_attempt,
                         pipeline_version=EXCLUDED.pipeline_version,
                         configuration_hash=EXCLUDED.configuration_hash,
                         parser_name=EXCLUDED.parser_name,parser_version=EXCLUDED.parser_version,
                         ocr_policy_version=EXCLUDED.ocr_policy_version,
                         canonical_document=EXCLUDED.canonical_document"""
                ), {
                    "company_id": owner["company_id"], "document_id": claim.document_id,
                    "job_id": claim.job_id, "attempt": claim.attempt,
                    "pipeline_version": claim.identity.pipeline_version,
                    "configuration_hash": claim.identity.configuration_hash,
                    "parser_version": claim.identity.parser_version,
                    "ocr_policy_version": claim.identity.ocr_policy_version,
                    "canonical": document.model_dump_json(),
                })
                await session.execute(text(
                    """UPDATE processing_jobs SET current_stage='partitioning',progress_percentage=20
                       WHERE id=:job_id"""
                ), {"job_id": claim.job_id})

    @staticmethod
    def _chunk(row: dict[str, object]) -> ChunkDraft:
        return ChunkDraft(
            chunk_id=row["id"], parent_chunk_id=row["parent_chunk_id"],
            ordinal=row["ordinal"], page_start=row["page_start"], page_end=row["page_end"],
            section=row["section"], chunk_type=row["chunk_type"],
            retrieval_role=row["retrieval_role"], raw_content=row["raw_content"],
            structured_content=row["structured_content"], summary=row["summary"],
            token_count=row["token_count"], source_element_ids=tuple(row["source_element_ids"]),
            bounding_boxes=tuple(row["bounding_boxes"]), content_hash=row["content_hash"],
        )

    async def load_chunks(self, claim: JobClaim) -> tuple[ChunkDraft, ...]:
        async with self._sessions() as session:
            async with session.begin():
                await self._lock_claim(session, claim)
                rows = (await session.execute(text(
                    """SELECT * FROM document_chunks WHERE document_id=:document_id
                         AND pipeline_version=:pipeline_version ORDER BY ordinal,id"""
                ), {"document_id": claim.document_id,
                    "pipeline_version": claim.identity.pipeline_version})).mappings().all()
        return tuple(self._chunk(dict(row)) for row in rows)

    async def persist_chunks(self, claim: JobClaim, chunks: tuple[ChunkDraft, ...]) -> None:
        if not chunks or len({row.chunk_id for row in chunks}) != len(chunks):
            raise ProcessingError("CHUNKING_FAILED")
        async with self._sessions() as session:
            async with session.begin():
                await self._lock_claim(session, claim)
                for chunk in sorted(chunks, key=lambda item: (item.parent_chunk_id is not None, item.ordinal)):
                    await session.execute(text(
                        """INSERT INTO document_chunks
                           (id,document_id,parent_chunk_id,pipeline_version,ordinal,page_start,page_end,
                            section,chunk_type,retrieval_role,raw_content,structured_content,summary,
                            token_count,source_element_ids,bounding_boxes,content_hash)
                           VALUES (:id,:document_id,:parent_id,:pipeline_version,:ordinal,:page_start,:page_end,
                            :section,:chunk_type,:retrieval_role,:raw_content,CAST(:structured AS jsonb),:summary,
                            :token_count,CAST(:source_ids AS jsonb),CAST(:boxes AS jsonb),:content_hash)
                           ON CONFLICT (document_id,pipeline_version,ordinal) DO UPDATE SET
                            raw_content=EXCLUDED.raw_content,content_hash=EXCLUDED.content_hash"""
                    ), {
                        "id": chunk.chunk_id, "document_id": claim.document_id,
                        "parent_id": chunk.parent_chunk_id,
                        "pipeline_version": claim.identity.pipeline_version,
                        "ordinal": chunk.ordinal, "page_start": chunk.page_start,
                        "page_end": chunk.page_end, "section": chunk.section,
                        "chunk_type": chunk.chunk_type, "retrieval_role": chunk.retrieval_role,
                        "raw_content": chunk.raw_content,
                        "structured": _json(chunk.structured_content.model_dump(mode="json")) if chunk.structured_content else None,
                        "summary": chunk.summary, "token_count": chunk.token_count,
                        "source_ids": _json(chunk.source_element_ids),
                        "boxes": _json([box.model_dump(mode="json") for box in chunk.bounding_boxes]),
                        "content_hash": chunk.content_hash,
                    })
                await session.execute(text(
                    "UPDATE processing_jobs SET current_stage='chunking',progress_percentage=40 WHERE id=:job_id"
                ), {"job_id": claim.job_id})
                await session.execute(text(
                    "UPDATE documents SET status='chunking' WHERE id=:document_id"
                ), {"document_id": claim.document_id})

    async def pending_embeddings(self, claim: JobClaim) -> tuple[ChunkDraft, ...]:
        async with self._sessions() as session:
            async with session.begin():
                await self._lock_claim(session, claim)
                rows = (await session.execute(text(
                    """SELECT * FROM document_chunks WHERE document_id=:document_id
                         AND pipeline_version=:pipeline_version
                         AND (retrieval_role IN ('child','both')
                              OR chunk_type='table')
                         AND embedding_status IN ('pending','failed') ORDER BY ordinal,id"""
                ), {"document_id": claim.document_id,
                    "pipeline_version": claim.identity.pipeline_version})).mappings().all()
        return tuple(self._chunk(dict(row)) for row in rows)

    async def persist_embeddings(self, claim: JobClaim,
                                 rows: tuple[EmbeddedChunk, ...], complete: bool) -> None:
        async with self._sessions() as session:
            async with session.begin():
                await self._lock_claim(session, claim)
                for row in rows:
                    result = await session.execute(text(
                        """UPDATE document_chunks SET embedding=CAST(:vector AS vector),
                                  embedding_model=:model,embedding_revision=:revision,
                                  embedding_status='completed'
                           WHERE id=:chunk_id AND document_id=:document_id
                             AND pipeline_version=:pipeline_version
                             AND embedding_status IN ('pending','failed')"""
                    ), {"vector": _vector(row.vector), "model": row.model,
                        "revision": row.revision, "chunk_id": row.chunk_id,
                        "document_id": claim.document_id,
                        "pipeline_version": claim.identity.pipeline_version})
                    if result.rowcount != 1 or row.model != MODEL or row.revision != claim.identity.embedding_revision:
                        raise ProcessingError("EMBEDDING_CONFIGURATION_MISMATCH")
                if complete:
                    pending = (await session.execute(text(
                        """SELECT count(*) FROM document_chunks WHERE document_id=:document_id
                           AND pipeline_version=:pipeline_version AND retrieval_role IN ('child','both')
                           AND embedding_status<>'completed'"""
                    ), {"document_id": claim.document_id,
                        "pipeline_version": claim.identity.pipeline_version})).scalar_one()
                    if pending:
                        raise ProcessingError("VECTOR_INDEXING_FAILED")
                    await session.execute(text(
                        "UPDATE processing_jobs SET current_stage='vectorizing',progress_percentage=60 WHERE id=:job_id"
                    ), {"job_id": claim.job_id})
                    await session.execute(text(
                        "UPDATE documents SET status='vectorizing' WHERE id=:document_id"
                    ), {"document_id": claim.document_id})

    async def mark_extracting(self, claim: JobClaim) -> None:
        async with self._sessions() as session:
            async with session.begin():
                await self._lock_claim(session, claim)
                await session.execute(text(
                    "UPDATE processing_jobs SET current_stage='extracting',progress_percentage=80 WHERE id=:job_id"
                ), {"job_id": claim.job_id})
                await session.execute(text(
                    "UPDATE documents SET status='extracting' WHERE id=:document_id"
                ), {"document_id": claim.document_id})

    async def complete(self, claim: JobClaim, bundle: ValidationBundle) -> None:
        async with self._sessions() as session:
            async with session.begin():
                await self._lock_claim(session, claim)
                run_id = (await session.execute(text(
                    "SELECT id FROM extraction_runs WHERE document_id=:document_id FOR UPDATE"
                ), {"document_id": claim.document_id})).scalar_one()
                invoice_id = uuid5(NAMESPACE_URL, f"docusense-invoice:{run_id}")
                invoice = bundle.invoice
                await session.execute(text(
                    """INSERT INTO invoices
                       (id,document_id,extraction_run_id,invoice_number,supplier_name,supplier_tax_id,
                        buyer_name,date_issued,due_date,currency,subtotal,tax_amount,discount_amount,
                        grand_total,is_math_valid)
                       VALUES (:id,:document_id,:run_id,:invoice_number,:supplier_name,:supplier_tax_id,
                        :buyer_name,:date_issued,:due_date,:currency,:subtotal,:tax_amount,:discount_amount,
                        :grand_total,:is_math_valid)"""
                ), {"id": invoice_id, "document_id": claim.document_id, "run_id": run_id,
                    **invoice.model_dump(exclude={"line_items", "evidence"}),
                    "is_math_valid": bundle.is_math_valid})
                for item in invoice.line_items:
                    await session.execute(text(
                        """INSERT INTO line_items
                           (id,invoice_id,source_row_key,line_order,description,hs_code,quantity,
                            unit_price,tax_amount,total_price)
                           VALUES (:id,:invoice_id,:source_row_key,:line_order,:description,:hs_code,
                            :quantity,:unit_price,:tax_amount,:total_price)"""
                    ), {"id": uuid5(NAMESPACE_URL, f"docusense-line:{invoice_id}:{item.source_row_key}"),
                        "invoice_id": invoice_id, **item.model_dump()})
                for evidence in bundle.evidence:
                    await self._insert_evidence(session, run_id, evidence)
                for rule in bundle.rules:
                    values = rule.model_dump()
                    values.update({
                        "id": uuid5(NAMESPACE_URL, f"docusense-rule:{run_id}:{rule.rule_id}:{rule.scope_key}"),
                        "run_id": run_id,
                        "observed": _json(rule.observed_value) if rule.observed_value is not None else None,
                        "expected": _json(rule.expected_value) if rule.expected_value is not None else None,
                    })
                    await session.execute(text(
                        """INSERT INTO validation_results
                           (id,extraction_run_id,rule_id,scope_key,status,observed_value,
                            expected_value,difference,epsilon,message_code)
                           VALUES (:id,:run_id,:rule_id,:scope_key,:status,CAST(:observed AS jsonb),
                            CAST(:expected AS jsonb),:difference,:epsilon,:message_code)"""
                    ), values)
                await session.execute(text(
                    "UPDATE extraction_runs SET status='completed',finished_at=clock_timestamp() WHERE id=:run_id"
                ), {"run_id": run_id})
                await session.execute(text(
                    """UPDATE documents SET status='pending_review',overall_confidence=:confidence
                       WHERE id=:document_id"""
                ), {"confidence": bundle.document_confidence, "document_id": claim.document_id})
                await session.execute(text(
                    """UPDATE processing_jobs SET status='completed',current_stage='extracting',
                              progress_percentage=100,next_attempt_at=NULL,lease_expires_at=NULL,
                              error_code=NULL,error_message=NULL,finished_at=clock_timestamp()
                       WHERE id=:job_id"""
                ), {"job_id": claim.job_id})

    @staticmethod
    async def _insert_evidence(session: AsyncSession, run_id: UUID,
                               evidence: FieldEvidenceDraft) -> None:
        values = evidence.model_dump()
        values.update({
            "id": uuid5(NAMESPACE_URL, f"docusense-evidence:{run_id}:{evidence.field_path}"),
            "run_id": run_id,
            "normalized": _json(evidence.normalized_value) if evidence.normalized_value is not None else None,
            "box": _json(evidence.bounding_box.model_dump(mode="json")) if evidence.bounding_box else None,
            "reasons": _json(evidence.reason_codes),
        })
        await session.execute(text(
            """INSERT INTO field_evidence
               (id,extraction_run_id,field_path,source_value,normalized_value,primary_chunk_id,
                source_page,bounding_box,evidence_excerpt,retrieval_rank,retrieval_score,exact_match,
                confidence_score,reason_codes,validation_state)
               VALUES (:id,:run_id,:field_path,:source_value,CAST(:normalized AS jsonb),:primary_chunk_id,
                :source_page,CAST(:box AS jsonb),:evidence_excerpt,:retrieval_rank,:retrieval_score,
                :exact_match,:confidence_score,CAST(:reasons AS jsonb),:validation_state)"""
        ), values)

    async def schedule_retry(self, claim: JobClaim, code: str, delay_seconds: int) -> None:
        async with self._sessions() as session:
            async with session.begin():
                await self._lock_claim(session, claim)
                await session.execute(text(
                    """UPDATE processing_jobs SET status='queued',next_attempt_at=clock_timestamp()+(:delay*interval '1 second'),
                              lease_expires_at=NULL,error_code=CAST(:code AS varchar(100)),
                              error_message=CAST(:code AS text),finished_at=NULL
                       WHERE id=:job_id"""
                ), {"delay": delay_seconds, "code": code, "job_id": claim.job_id})

    async def fail(self, claim: JobClaim, code: str) -> None:
        async with self._sessions() as session:
            async with session.begin():
                await self._lock_claim(session, claim)
                await session.execute(text(
                    """UPDATE extraction_runs SET status='failed',finished_at=clock_timestamp()
                       WHERE document_id=:document_id AND status='running'"""
                ), {"document_id": claim.document_id})
                await session.execute(text(
                    "UPDATE documents SET status='failed',overall_confidence=NULL WHERE id=:document_id"
                ), {"document_id": claim.document_id})
                await session.execute(text(
                    """UPDATE processing_jobs SET status='failed',next_attempt_at=NULL,
                              lease_expires_at=NULL,error_code=CAST(:code AS varchar(100)),
                              error_message=CAST(:code AS text),
                              finished_at=clock_timestamp() WHERE id=:job_id"""
                ), {"code": code, "job_id": claim.job_id})

    @staticmethod
    def _technical(row: dict[str, object]) -> TechnicalDocument:
        return TechnicalDocument(
            document_id=row["document_id"], company_id=row["company_id"],
            job_status=row["job_status"], current_stage=row["current_stage"],
            progress_percentage=row["progress_percentage"], run_status=row.get("run_status"),
            pipeline_version=row.get("pipeline_version"),
        )

    async def list_chunks(self, caller: CallerContext, document_id: UUID,
                          query: ChunkQuery) -> ChunkPage | None:
        filters = ["c.document_id=:document_id"]
        values: dict[str, object] = {"document_id": document_id, "company_id": caller.company_id,
                                    "limit": query.page_size, "offset": (query.page - 1) * query.page_size}
        if query.chunk_type:
            filters.append("c.chunk_type=:chunk_type"); values["chunk_type"] = query.chunk_type
        if query.page_number:
            filters.append(":page_number BETWEEN c.page_start AND c.page_end"); values["page_number"] = query.page_number
        if query.retrieval_role:
            filters.append("c.retrieval_role=:retrieval_role"); values["retrieval_role"] = query.retrieval_role
        if query.section:
            filters.append("c.section=:section"); values["section"] = query.section
        where = " AND ".join(filters)
        direction = "ASC" if query.order == "asc" else "DESC"
        async with self._sessions() as session:
            async with session.begin():
                await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
                owner = (await session.execute(text(
                    """SELECT d.id AS document_id,d.company_id,j.status AS job_status,j.current_stage,
                              j.progress_percentage,r.status AS run_status,r.pipeline_version
                       FROM documents d JOIN processing_jobs j ON j.document_id=d.id
                       LEFT JOIN extraction_runs r ON r.document_id=d.id
                       WHERE d.id=:document_id AND d.company_id=:company_id"""
                ), values)).mappings().one_or_none()
                if owner is None:
                    return None
                total = int((await session.execute(text(f"SELECT count(*) FROM document_chunks c WHERE {where}"), values)).scalar_one())
                rows = (await session.execute(text(
                    f"""SELECT c.* FROM document_chunks c WHERE {where}
                         ORDER BY c.ordinal {direction},c.id {direction} LIMIT :limit OFFSET :offset"""
                ), values)).mappings().all()
        items = tuple(ChunkItem(
            chunk_id=row["id"], parent_chunk_id=row["parent_chunk_id"], ordinal=row["ordinal"],
            page_start=row["page_start"], page_end=row["page_end"], section=row["section"],
            chunk_type=row["chunk_type"], retrieval_role=row["retrieval_role"], token_count=row["token_count"],
            raw_content=row["raw_content"], structured_content=row["structured_content"], summary=row["summary"],
            source_element_ids=tuple(row["source_element_ids"]), bounding_boxes=tuple(row["bounding_boxes"]),
            embedding_status=row["embedding_status"], has_embedding=row["embedding"] is not None,
        ) for row in rows)
        return ChunkPage(self._technical(dict(owner)), items, total)

    async def search(self, document_id: UUID, pipeline_version: str, model: str,
                     revision: str, vector: tuple[float, ...], objective: str,
                     limit: int) -> tuple[RankedChunk, ...]:
        if model != MODEL or len(vector) != 384 or not 1 <= limit <= 24:
            raise ProcessingError("EMBEDDING_CONFIGURATION_MISMATCH")
        async with self._sessions() as session:
            rows = (await session.execute(text(
                """SELECT c.*,1-(c.embedding <=> CAST(:vector AS vector)) AS score
                   FROM document_chunks c WHERE c.document_id=:document_id
                     AND c.pipeline_version=:pipeline_version AND c.embedding_status='completed'
                     AND c.embedding_model=:model AND c.embedding_revision=:revision
                     AND (c.retrieval_role IN ('child','both') OR c.chunk_type='table')
                   ORDER BY c.embedding <=> CAST(:vector AS vector),c.ordinal,c.id LIMIT :limit"""
            ), {"vector": _vector(vector), "document_id": document_id,
                "pipeline_version": pipeline_version, "model": model,
                "revision": revision, "limit": limit})).mappings().all()
        return tuple(RankedChunk(self._chunk(dict(row)), float(row["score"]), rank)
                     for rank, row in enumerate(rows, 1))

    async def get_evidence(self, caller: CallerContext, document_id: UUID,
                           query: EvidenceQuery) -> EvidenceSnapshot | None:
        filters = ["e.extraction_run_id=r.id"]
        values: dict[str, object] = {"document_id": document_id, "company_id": caller.company_id,
                                    "limit": query.page_size, "offset": (query.page - 1) * query.page_size}
        if query.field_path:
            filters.append("e.field_path=:field_path"); values["field_path"] = query.field_path
        if query.validation_state:
            filters.append("e.validation_state=:validation_state"); values["validation_state"] = query.validation_state
        if query.min_confidence is not None:
            filters.append("e.confidence_score>=:confidence"); values["confidence"] = query.min_confidence
        where = " AND ".join(filters)
        async with self._sessions() as session:
            async with session.begin():
                await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
                owner = (await session.execute(text(
                    """SELECT d.id AS document_id,d.company_id,j.status AS job_status,j.current_stage,
                              j.progress_percentage,r.id AS run_id,r.status AS run_status,r.*
                       FROM documents d JOIN processing_jobs j ON j.document_id=d.id
                       LEFT JOIN extraction_runs r ON r.document_id=d.id
                       WHERE d.id=:document_id AND d.company_id=:company_id"""
                ), values)).mappings().one_or_none()
                if owner is None:
                    return None
                if owner["run_id"] is None or owner["run_status"] != "completed":
                    return EvidenceSnapshot(self._technical(dict(owner)), None, (), 0, None, ())
                total = int((await session.execute(text(f"SELECT count(*) FROM field_evidence e, extraction_runs r WHERE r.id=:run_id AND {where}"), {**values, "run_id": owner["run_id"]})).scalar_one())
                evidence = (await session.execute(text(
                    f"""SELECT e.* FROM field_evidence e,extraction_runs r
                         WHERE r.id=:run_id AND {where} ORDER BY e.field_path,e.id LIMIT :limit OFFSET :offset"""
                ), {**values, "run_id": owner["run_id"]})).mappings().all()
                rules = (await session.execute(text(
                    "SELECT * FROM validation_results WHERE extraction_run_id=:run_id ORDER BY rule_id,scope_key,id"
                ), {"run_id": owner["run_id"]})).mappings().all()
        info = ExtractionRunInfo(
            extraction_run_id=owner["run_id"], status="completed", pipeline_version=owner["pipeline_version"],
            parser_name=owner["parser_name"], parser_version=owner["parser_version"],
            ocr_policy_version=owner["ocr_policy_version"], embedding_model=owner["embedding_model"],
            embedding_revision=owner["embedding_revision"], embedding_dimension=owner["embedding_dimension"],
            llm_provider=owner["llm_provider"], llm_model=owner["llm_model"],
            prompt_version=owner["prompt_version"], schema_version=owner["schema_version"],
            warning_codes=tuple(owner["warning_codes"]), started_at=owner["started_at"], completed_at=owner["finished_at"],
        )
        items = tuple(EvidenceItem(
            field_path=row["field_path"], source_value=row["source_value"],
            normalized_value=row["normalized_value"], primary_chunk_id=row["primary_chunk_id"],
            source_page=row["source_page"], bounding_box=row["bounding_box"],
            evidence_excerpt=row["evidence_excerpt"], retrieval_rank=row["retrieval_rank"],
            retrieval_score=row["retrieval_score"], confidence_score=row["confidence_score"],
            confidence_reason_codes=tuple(row["reason_codes"]), validation_state=row["validation_state"],
        ) for row in evidence)
        summaries = tuple(ValidationRuleSummary(
            rule_id=row["rule_id"], scope_key=row["scope_key"], status=row["status"],
            message_code=row["message_code"], observed_value=row["observed_value"],
            expected_value=row["expected_value"],
            difference=None if row["difference"] is None else str(row["difference"]),
            epsilon=None if row["epsilon"] is None else str(row["epsilon"]),
        ) for row in rules)
        counts = {name: sum(row.status == name for row in summaries)
                  for name in ("passed", "failed", "missing", "not_applicable")}
        return EvidenceSnapshot(self._technical(dict(owner)), info, items, total,
                                ValidationSummary(**counts), summaries)

    async def get_invoice(self, caller: CallerContext, document_id: UUID) -> InvoiceResult | None:
        async with self._sessions() as session:
            invoice = (await session.execute(text(
                """SELECT i.*,r.schema_version,r.finished_at,r.id AS run_id
                   FROM documents d JOIN extraction_runs r ON r.document_id=d.id AND r.status='completed'
                   JOIN invoices i ON i.extraction_run_id=r.id AND i.document_id=d.id
                   WHERE d.id=:document_id AND d.company_id=:company_id"""
            ), {"document_id": document_id, "company_id": caller.company_id})).mappings().one_or_none()
            if invoice is None:
                return None
            lines = (await session.execute(text(
                "SELECT * FROM line_items WHERE invoice_id=:invoice_id ORDER BY line_order,id"
            ), {"invoice_id": invoice["id"]})).mappings().all()
            counts = dict((await session.execute(text(
                "SELECT status,count(*) FROM validation_results WHERE extraction_run_id=:run_id GROUP BY status"
            ), {"run_id": invoice["run_id"]})).all())
        return InvoiceResult(
            invoice_id=invoice["id"], invoice_number=invoice["invoice_number"],
            supplier_name=invoice["supplier_name"], supplier_tax_id=invoice["supplier_tax_id"],
            buyer_name=invoice["buyer_name"], date_issued=invoice["date_issued"], due_date=invoice["due_date"],
            currency=invoice["currency"], subtotal=invoice["subtotal"], tax_amount=invoice["tax_amount"],
            discount_amount=invoice["discount_amount"], grand_total=invoice["grand_total"],
            is_math_valid=invoice["is_math_valid"],
            line_items=tuple(InvoiceLineResult(
                line_item_id=row["id"], line_order=row["line_order"], description=row["description"],
                hs_code=row["hs_code"], quantity=row["quantity"], unit_price=row["unit_price"],
                tax_amount=row["tax_amount"], total_price=row["total_price"],
            ) for row in lines),
            validation_summary=ValidationSummary(**{
                name: int(counts.get(name, 0)) for name in ("passed", "failed", "missing", "not_applicable")
            }), extraction_run_id=invoice["run_id"], schema_version=invoice["schema_version"],
            completed_at=invoice["finished_at"],
        )


__all__ = ["RagSqlRepository"]


