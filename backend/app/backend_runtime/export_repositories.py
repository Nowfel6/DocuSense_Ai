"""Concrete tenant-first search and durable export repository."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
import hashlib
import json
import math
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..document_search_export.errors import SearchExportError, WorkerFailure
from ..document_search_export.repository import (
    AcceptanceOutcome, DownloadRecord, EmbeddingProvider, EmbeddingResult,
    ExportInvoice, ExportLine, GeneratedArtifact, SearchPage, SearchRecord,
    WorkerClaim,
)
from ..document_search_export.schemas import (
    Caller, CreateExportRequest, DirectExportRequest, DocumentSearchRequest,
    ExportResource, ExportStatusResource, SearchCriteria,
)


MODEL = "sentence-transformers/all-MiniLM-L6-v2"
SCHEMA = "docusense-approved-invoice-export-v1"


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _vector(value: tuple[float, ...]) -> str:
    return "[" + ",".join(format(item, ".17g") for item in value) + "]"


def _criteria_metadata(request: CreateExportRequest | DirectExportRequest) -> dict[str, object]:
    if request.document_ids is not None:
        return {"selection_type": "document_ids", "requested_document_count": len(request.document_ids),
                "semantic_query_present": False}
    assert request.criteria is not None
    payload = request.criteria.model_dump(mode="json", exclude_none=True)
    query = payload.pop("query", None)
    payload["selection_type"] = "criteria"
    payload["semantic_query_present"] = query is not None
    if query is not None:
        payload["semantic_query_sha256"] = hashlib.sha256(query.encode()).hexdigest()
    return payload


class SearchExportSqlRepository:
    """One PostgreSQL implementation for Feature 5 search and export ports."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession],
                 embedding: EmbeddingProvider | None = None, *,
                 sync_document_max: int = 500, sync_row_max: int = 50_000,
                 sync_byte_max: int = 64 * 1024 * 1024) -> None:
        if not 0 <= sync_document_max <= 500 or sync_row_max < 1 or sync_byte_max < 1:
            raise ValueError("Invalid synchronous export estimate policy")
        self._sessions = sessions
        self._embedding = embedding
        self._sync_document_max = sync_document_max
        self._sync_row_max = sync_row_max
        self._sync_byte_max = sync_byte_max

    @staticmethod
    def _filters(criteria: SearchCriteria, values: dict[str, object],
                 *, statuses: tuple[str, ...]) -> list[str]:
        filters = ["d.company_id=:company_id", "d.status=ANY(CAST(:statuses AS varchar[]))",
                   "pj.status='completed'", "pj.progress_percentage=100",
                   "er.status='completed'", "i.extraction_run_id=er.id"]
        values["statuses"] = list(statuses)
        if criteria.document_statuses:
            filters.append("d.status=ANY(CAST(:requested_statuses AS varchar[]))")
            values["requested_statuses"] = list(criteria.document_statuses)
        if criteria.document_type:
            filters.append("d.doc_type=:document_type"); values["document_type"] = criteria.document_type
        if criteria.supplier:
            filters.append("i.supplier_name ILIKE :supplier ESCAPE '\\'")
            escaped = criteria.supplier.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            values["supplier"] = f"%{escaped}%"
        for field, column in (("currency", "i.currency"), ("invoice_date_from", "i.date_issued"),
                              ("invoice_date_to", "i.date_issued"), ("uploaded_from", "d.created_at"),
                              ("uploaded_to", "d.created_at"), ("min_total", "i.grand_total"),
                              ("max_total", "i.grand_total")):
            value = getattr(criteria, field)
            if value is None:
                continue
            operator = ">=" if field.endswith("_from") or field.startswith("min_") else "<=" if field.endswith("_to") or field.startswith("max_") else "="
            filters.append(f"{column}{operator}:{field}")
            values[field] = value
        return filters

    @staticmethod
    def _order(criteria: SearchCriteria, semantic: bool) -> str:
        direction = "ASC" if criteria.order == "asc" else "DESC"
        column = {
            "relevance": "similarity", "date_issued": "date_issued",
            "grand_total": "grand_total", "created_at": "created_at",
        }[criteria.sort_by or ("relevance" if semantic else "created_at")]
        nulls = "" if column == "similarity" else " NULLS LAST"
        return f"{column} {direction}{nulls},document_id ASC"

    async def search(self, caller: Caller, request: DocumentSearchRequest,
                     embedding: EmbeddingResult | None,
                     visible_statuses: tuple[str, ...]) -> SearchPage:
        values: dict[str, object] = {"company_id": caller.company_id,
                                    "limit": request.page_size,
                                    "offset": (request.page - 1) * request.page_size}
        filters = self._filters(request, values, statuses=visible_statuses)
        where = " AND ".join(filters)
        semantic = embedding is not None
        if semantic:
            assert embedding is not None
            values.update({"vector": _vector(embedding.vector), "model": embedding.model,
                           "revision": embedding.revision})
            query = f"""WITH candidates AS MATERIALIZED (
                SELECT d.id AS document_id,d.file_name,d.doc_type,d.status,d.created_at,
                       i.id AS invoice_id,i.invoice_number,i.supplier_name,i.date_issued,
                       i.currency,i.grand_total,i.is_math_valid,d.review_revision
                FROM documents d JOIN processing_jobs pj ON pj.document_id=d.id
                JOIN extraction_runs er ON er.document_id=d.id
                JOIN invoices i ON i.document_id=d.id WHERE {where}),
              ranked AS (
                SELECT c.*,dc.id AS matching_chunk_id,dc.raw_content AS matching_excerpt,
                       dc.page_start AS matching_page_start,dc.page_end AS matching_page_end,
                       1-(dc.embedding <=> CAST(:vector AS vector)) AS similarity,
                       row_number() OVER (PARTITION BY c.document_id ORDER BY
                         dc.embedding <=> CAST(:vector AS vector),dc.ordinal,dc.id) AS rn
                FROM candidates c JOIN document_chunks dc ON dc.document_id=c.document_id
                WHERE dc.embedding_status='completed' AND dc.embedding IS NOT NULL
                  AND dc.retrieval_role IN ('child','both')
                  AND dc.embedding_model=:model AND dc.embedding_revision=:revision)
              SELECT *,count(*) OVER() AS total_records FROM ranked WHERE rn=1
              ORDER BY {self._order(request, True)} LIMIT :limit OFFSET :offset"""
        else:
            query = f"""WITH candidates AS MATERIALIZED (
                SELECT d.id AS document_id,d.file_name,d.doc_type,d.status,d.created_at,
                       i.id AS invoice_id,i.invoice_number,i.supplier_name,i.date_issued,
                       i.currency,i.grand_total,i.is_math_valid,d.review_revision,
                       NULL::uuid AS matching_chunk_id,NULL::text AS matching_excerpt,
                       NULL::integer AS matching_page_start,NULL::integer AS matching_page_end,
                       NULL::double precision AS similarity
                FROM documents d JOIN processing_jobs pj ON pj.document_id=d.id
                JOIN extraction_runs er ON er.document_id=d.id
                JOIN invoices i ON i.document_id=d.id WHERE {where})
              SELECT *,count(*) OVER() AS total_records FROM candidates
              ORDER BY {self._order(request, False)} LIMIT :limit OFFSET :offset"""
        async with self._sessions() as session:
            async with session.begin():
                await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
                rows = (await session.execute(text(query), values)).mappings().all()
        total = int(rows[0]["total_records"]) if rows else 0
        return SearchPage(tuple(SearchRecord(
            document_id=row["document_id"], file_name=row["file_name"],
            document_type=row["doc_type"], status=row["status"], created_at=row["created_at"],
            invoice_id=row["invoice_id"], invoice_number=row["invoice_number"],
            supplier_name=row["supplier_name"], date_issued=row["date_issued"],
            currency=row["currency"], grand_total=row["grand_total"],
            is_math_valid=row["is_math_valid"], review_revision=row["review_revision"],
            relevance_score=None if row["similarity"] is None else float(row["similarity"]),
            matching_excerpt=row["matching_excerpt"], matching_chunk_id=row["matching_chunk_id"],
            matching_page_start=row["matching_page_start"], matching_page_end=row["matching_page_end"],
        ) for row in rows), total)

    @staticmethod
    def _resource(row: dict[str, object], *, status: bool = False):
        values = dict(
            export_id=row["id"], format=row["format"], mode=row["mode"], status=row["status"],
            progress_percentage=row["progress_percentage"], current_stage=row["current_stage"],
            selected_document_count=row["selected_document_count"],
            exported_document_count=row["exported_document_count"], row_count=row["row_count"],
            created_at=row["created_at"], started_at=row["started_at"],
            completed_at=row["completed_at"], artifact_expires_at=row["artifact_expires_at"],
            status_url=f"/api/v1/exports/{row['id']}",
            download_url=(f"/api/v1/exports/{row['id']}/download" if row["status"] == "completed" else None),
        )
        if status:
            values.update(error_code=row["error_code"], error_message=row["error_message"])
            return ExportStatusResource(**values)
        return ExportResource(**values)

    async def _criteria_embedding(self, criteria: SearchCriteria | None) -> EmbeddingResult | None:
        if criteria is None or criteria.query is None:
            return None
        if self._embedding is None:
            raise SearchExportError("SEARCH_CONFIGURATION_UNAVAILABLE")
        try:
            result = await self._embedding.embed_query(criteria.query)
        except Exception as exc:
            raise SearchExportError("SEARCH_PROVIDER_UNAVAILABLE") from exc
        if result.model != MODEL or not result.normalized or len(result.vector) != 384:
            raise SearchExportError("SEARCH_PROVIDER_UNAVAILABLE")
        norm = math.sqrt(sum(value * value for value in result.vector))
        if any(not math.isfinite(value) for value in result.vector) or abs(norm - 1.0) > 1e-3:
            raise SearchExportError("SEARCH_PROVIDER_UNAVAILABLE")
        return result

    async def _select(self, session: AsyncSession, caller: Caller,
                      request: CreateExportRequest | DirectExportRequest,
                      embedding: EmbeddingResult | None) -> list[dict[str, object]]:
        if request.document_ids is not None:
            ids = list(request.document_ids)
            visible = int((await session.execute(text(
                "SELECT count(*) FROM documents WHERE company_id=:company_id AND id=ANY(CAST(:ids AS uuid[]))"
            ), {"company_id": caller.company_id, "ids": ids})).scalar_one())
            if visible != len(ids):
                raise SearchExportError("EXPORT_SELECTION_NOT_FOUND")
            rows = (await session.execute(text(
                """WITH requested AS (SELECT id,ordinality-1 AS ordinal
                     FROM unnest(CAST(:ids AS uuid[])) WITH ORDINALITY AS x(id,ordinality))
                   SELECT d.id AS document_id,d.review_revision,
                          compute_export_source_value_hash(d.id) AS source_hash,
                          (SELECT count(*) FROM line_items li WHERE li.invoice_id=i.id) AS line_count,
                          requested.ordinal
                   FROM requested JOIN documents d ON d.id=requested.id
                   JOIN processing_jobs pj ON pj.document_id=d.id
                   JOIN extraction_runs er ON er.document_id=d.id
                   JOIN invoices i ON i.document_id=d.id AND i.extraction_run_id=er.id
                   WHERE d.company_id=:company_id AND d.status='approved'
                     AND d.doc_type='commercial_invoice' AND d.review_revision>0
                     AND pj.status='completed' AND pj.progress_percentage=100
                     AND er.status='completed' ORDER BY requested.ordinal"""
            ), {"company_id": caller.company_id, "ids": ids})).mappings().all()
            if len(rows) != len(ids):
                raise SearchExportError("EXPORT_SELECTION_NOT_ELIGIBLE")
            return [dict(row) for row in rows]
        assert request.criteria is not None
        values: dict[str, object] = {"company_id": caller.company_id}
        filters = self._filters(request.criteria, values, statuses=("approved",))
        where = " AND ".join(filters)
        if embedding is None:
            sql = f"""WITH candidates AS MATERIALIZED (
                     SELECT d.id AS document_id,d.review_revision,i.id AS invoice_id,
                            d.created_at,i.date_issued,i.grand_total
                     FROM documents d JOIN processing_jobs pj ON pj.document_id=d.id
                     JOIN extraction_runs er ON er.document_id=d.id
                     JOIN invoices i ON i.document_id=d.id WHERE {where})
                     SELECT document_id,review_revision,
                       compute_export_source_value_hash(document_id) AS source_hash,
                       (SELECT count(*) FROM line_items li WHERE li.invoice_id=candidates.invoice_id) AS line_count,
                       row_number() OVER (ORDER BY {self._order(request.criteria, False)})-1 AS ordinal
                     FROM candidates ORDER BY {self._order(request.criteria, False)}"""
        else:
            values.update({"vector": _vector(embedding.vector), "model": embedding.model,
                           "revision": embedding.revision})
            sql = f"""WITH candidates AS MATERIALIZED (
                     SELECT d.id AS document_id,d.review_revision,i.id AS invoice_id,
                            d.created_at,i.date_issued,i.grand_total
                     FROM documents d JOIN processing_jobs pj ON pj.document_id=d.id
                     JOIN extraction_runs er ON er.document_id=d.id
                     JOIN invoices i ON i.document_id=d.id WHERE {where}),
                   ranked AS (SELECT c.*,1-(dc.embedding <=> CAST(:vector AS vector)) similarity,
                     row_number() OVER(PARTITION BY c.document_id ORDER BY
                       dc.embedding <=> CAST(:vector AS vector),dc.ordinal,dc.id) rn
                     FROM candidates c JOIN document_chunks dc ON dc.document_id=c.document_id
                     WHERE dc.embedding_status='completed' AND dc.embedding_model=:model
                       AND dc.embedding_revision=:revision AND dc.retrieval_role IN ('child','both'))
                   SELECT document_id,review_revision,compute_export_source_value_hash(document_id) source_hash,
                     (SELECT count(*) FROM line_items li WHERE li.invoice_id=ranked.invoice_id) line_count,
                     row_number() OVER(ORDER BY {self._order(request.criteria, True)})-1 ordinal
                   FROM ranked WHERE rn=1 ORDER BY {self._order(request.criteria, True)}"""
        rows = (await session.execute(text(sql), values)).mappings().all()
        if not rows:
            raise SearchExportError("NO_EXPORTABLE_DOCUMENTS")
        return [dict(row) for row in rows]

    async def accept(self, caller: Caller,
                     request: CreateExportRequest | DirectExportRequest, *,
                     criteria_hash: str, request_hash: str,
                     idempotency_key_hash: str | None, allow_async: bool) -> AcceptanceOutcome:
        embedding = await self._criteria_embedding(request.criteria)
        export_id = uuid4()
        async with self._sessions() as session:
            async with session.begin():
                await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
                if idempotency_key_hash is not None:
                    scope = f"{caller.company_id}:{caller.user_id}:{idempotency_key_hash}"
                    await session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:scope,0))"), {"scope": scope})
                    previous = (await session.execute(text(
                        """SELECT * FROM export_jobs WHERE company_id=:company_id
                           AND requested_by_user_id=:user_id
                           AND idempotency_key_hash=:key FOR UPDATE"""
                    ), {"company_id": caller.company_id, "user_id": caller.user_id,
                        "key": idempotency_key_hash})).mappings().one_or_none()
                    if previous is not None:
                        if previous["request_hash"] != request_hash:
                            raise SearchExportError("IDEMPOTENCY_KEY_REUSED")
                        return AcceptanceOutcome(self._resource(dict(previous)), True, False)
                selected = await self._select(session, caller, request, embedding)
                document_count = len(selected)
                row_count = sum(max(1, int(row["line_count"])) for row in selected)
                if document_count > 50_000 or row_count > 1_000_000:
                    raise SearchExportError("EXPORT_LIMIT_EXCEEDED")
                estimated_bytes = row_count * 4096 + document_count * 1024
                asynchronous = (document_count > self._sync_document_max
                                or row_count > self._sync_row_max
                                or estimated_bytes > self._sync_byte_max)
                if asynchronous and not allow_async:
                    raise SearchExportError("EXPORT_REQUIRES_ASYNC")
                mode = "asynchronous" if asynchronous else "synchronous"
                status = "queued" if asynchronous else "processing"
                if asynchronous:
                    await session.execute(text(
                        "SELECT pg_advisory_xact_lock(hashtextextended(:scope,0))"
                    ), {"scope": f"export-user:{caller.user_id}"})
                    await session.execute(text(
                        "SELECT pg_advisory_xact_lock(hashtextextended(:scope,0))"
                    ), {"scope": f"export-company:{caller.company_id}"})
                    active_user = int((await session.execute(text(
                        """SELECT count(*) FROM export_jobs WHERE requested_by_user_id=:user_id
                           AND mode='asynchronous' AND status IN ('queued','processing')"""
                    ), {"user_id": caller.user_id})).scalar_one())
                    active_company = int((await session.execute(text(
                        """SELECT count(*) FROM export_jobs WHERE company_id=:company_id
                           AND mode='asynchronous' AND status IN ('queued','processing')"""
                    ), {"company_id": caller.company_id})).scalar_one())
                    if active_user >= 3 or active_company >= 10:
                        raise SearchExportError("EXPORT_CONCURRENCY_LIMIT")
                await session.execute(text(
                    """INSERT INTO export_jobs
                       (id,company_id,requested_by_user_id,format,mode,status,current_stage,
                        progress_percentage,selection_type,schema_version,criteria_json,criteria_hash,
                        request_hash,idempotency_key_hash,selected_document_count,request_id,started_at)
                       VALUES (:id,:company_id,:user_id,:format,CAST(:mode AS varchar(16)),:status,:stage,0,:selection_type,
                        :schema,CAST(:criteria AS jsonb),:criteria_hash,:request_hash,:key,:count,
                        :request_id,CASE WHEN CAST(:mode AS varchar(16))='synchronous'
                                         THEN clock_timestamp() ELSE NULL END)"""
                ), {"id": export_id, "company_id": caller.company_id, "user_id": caller.user_id,
                    "format": request.format, "mode": mode, "status": status,
                    "stage": "accepted" if asynchronous else "generating",
                    "selection_type": "document_ids" if request.document_ids is not None else "criteria",
                    "schema": SCHEMA, "criteria": _json(_criteria_metadata(request)),
                    "criteria_hash": criteria_hash, "request_hash": request_hash,
                    "key": idempotency_key_hash, "count": document_count,
                    "request_id": str(export_id)})
                for ordinal, row in enumerate(selected):
                    await session.execute(text(
                        """INSERT INTO export_job_documents
                           (export_job_id,document_id,review_revision,ordinal,source_value_hash)
                           VALUES (:export_id,:document_id,:revision,:ordinal,:source_hash)"""
                    ), {"export_id": export_id, "document_id": row["document_id"],
                        "revision": row["review_revision"], "ordinal": ordinal,
                        "source_hash": row["source_hash"]})
                await session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
                row = (await session.execute(text(
                    "SELECT * FROM export_jobs WHERE id=:id"
                ), {"id": export_id})).mappings().one()
        return AcceptanceOutcome(self._resource(dict(row)), False, asynchronous)

    async def get_status(self, caller: Caller, export_id: UUID) -> ExportStatusResource | None:
        async with self._sessions() as session:
            row = (await session.execute(text(
                "SELECT * FROM export_jobs WHERE id=:id AND company_id=:company_id"
            ), {"id": export_id, "company_id": caller.company_id})).mappings().one_or_none()
        return None if row is None else self._resource(dict(row), status=True)

    async def get_download(self, caller: Caller, export_id: UUID) -> DownloadRecord | None:
        async with self._sessions() as session:
            row = (await session.execute(text(
                "SELECT * FROM export_jobs WHERE id=:id AND company_id=:company_id"
            ), {"id": export_id, "company_id": caller.company_id})).mappings().one_or_none()
        if row is None:
            return None
        return DownloadRecord(self._resource(dict(row), status=True), row["artifact_object_key"],
                              row["artifact_file_name"], row["artifact_content_type"],
                              row["artifact_size_bytes"], row["artifact_sha256"],
                              row["artifact_expires_at"])

    async def claim(self, export_id: UUID, *, lease_seconds: int) -> WorkerClaim | None:
        if not 1 <= lease_seconds <= 3600:
            raise ValueError("lease_seconds must be between 1 and 3600")
        async with self._sessions() as session:
            async with session.begin():
                row = (await session.execute(text(
                    """UPDATE export_jobs SET status='processing',current_stage='generating',
                              progress_percentage=20,attempt_count=attempt_count+1,next_attempt_at=NULL,
                              lease_token=gen_random_uuid(),lease_expires_at=clock_timestamp()+(:lease*interval '1 second'),
                              error_code=NULL,error_message=NULL,started_at=COALESCE(started_at,clock_timestamp())
                       WHERE id=:id AND mode='asynchronous' AND status='queued' AND attempt_count<4
                         AND (next_attempt_at IS NULL OR next_attempt_at<=clock_timestamp())
                       RETURNING id,format,attempt_count,lease_token,started_at"""
                ), {"id": export_id, "lease": lease_seconds})).mappings().one_or_none()
        return None if row is None else WorkerClaim(export_id=row["id"], format=row["format"],
                                                     attempt_count=row["attempt_count"],
                                                     lease_token=row["lease_token"],
                                                     generated_at=row["started_at"])

    async def renew(self, claim: WorkerClaim, *, lease_seconds: int) -> bool:
        if not 1 <= lease_seconds <= 3600:
            raise ValueError("lease_seconds must be between 1 and 3600")
        async with self._sessions() as session:
            async with session.begin():
                result = await session.execute(text(
                    """UPDATE export_jobs SET lease_expires_at=clock_timestamp()+(:lease*interval '1 second')
                       WHERE id=:id AND status='processing' AND attempt_count=:attempt
                         AND lease_token=:token AND lease_expires_at>clock_timestamp()"""
                ), {"lease": lease_seconds, "id": claim.export_id,
                    "attempt": claim.attempt_count, "token": claim.lease_token})
        return result.rowcount == 1

    async def progress(self, claim: WorkerClaim, *, stage: str, percentage: int) -> bool:
        ranges = {"generating": range(20, 70), "packaging": range(70, 80),
                  "storing": range(80, 100)}
        if stage not in ranges or percentage not in ranges[stage]:
            raise ValueError("Invalid export progress milestone")
        async with self._sessions() as session:
            async with session.begin():
                result = await session.execute(text(
                    """UPDATE export_jobs SET current_stage=:stage,progress_percentage=:percentage
                       WHERE id=:id AND status='processing' AND attempt_count=:attempt
                         AND lease_token=:token AND lease_expires_at>clock_timestamp()
                         AND progress_percentage<=:percentage"""
                ), {"stage": stage, "percentage": percentage, "id": claim.export_id,
                    "attempt": claim.attempt_count, "token": claim.lease_token})
        return result.rowcount == 1

    async def source_stream(self, claim: WorkerClaim | UUID) -> AsyncIterator[ExportInvoice]:
        async with self._sessions() as session:
            async with session.begin():
                await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
                values: dict[str, object] = {"id": claim.export_id if isinstance(claim, WorkerClaim) else claim}
                fence = ""
                if isinstance(claim, WorkerClaim):
                    fence = " AND ej.status='processing' AND ej.attempt_count=:attempt AND ej.lease_token=:token AND ej.lease_expires_at>clock_timestamp()"
                    values.update(attempt=claim.attempt_count, token=claim.lease_token)
                else:
                    fence = " AND ej.mode='synchronous' AND ej.status='processing'"
                rows = (await session.execute(text(
                    """SELECT ejd.document_id,ejd.review_revision AS membership_revision,
                              ejd.source_value_hash,d.company_id,d.status AS document_status,
                              d.doc_type,d.review_revision AS current_revision,
                              pj.status AS job_status,pj.progress_percentage,er.status AS run_status,
                              i.id AS invoice_id,i.invoice_number,i.supplier_name,i.date_issued,
                              i.currency,i.subtotal,i.tax_amount,i.grand_total,i.is_math_valid,
                              compute_export_source_value_hash(d.id) AS current_hash
                       FROM export_jobs ej JOIN export_job_documents ejd ON ejd.export_job_id=ej.id
                       JOIN documents d ON d.id=ejd.document_id
                       JOIN processing_jobs pj ON pj.document_id=d.id
                       JOIN extraction_runs er ON er.document_id=d.id
                       JOIN invoices i ON i.document_id=d.id AND i.extraction_run_id=er.id
                       WHERE ej.id=:id""" + fence + " ORDER BY ejd.ordinal"
                ), values)).mappings().all()
                if not rows:
                    raise WorkerFailure("EXPORT_SOURCE_CHANGED", retryable=False)
                for row in rows:
                    if (row["document_status"] != "approved" or row["doc_type"] != "commercial_invoice"
                            or row["membership_revision"] != row["current_revision"]
                            or row["job_status"] != "completed" or row["progress_percentage"] != 100
                            or row["run_status"] != "completed" or row["current_hash"] != row["source_value_hash"]):
                        raise WorkerFailure("EXPORT_SOURCE_CHANGED", retryable=False)
                    lines = (await session.execute(text(
                        "SELECT * FROM line_items WHERE invoice_id=:invoice_id ORDER BY line_order,id"
                    ), {"invoice_id": row["invoice_id"]})).mappings().all()
                    yield ExportInvoice(
                        document_id=row["document_id"], invoice_id=row["invoice_id"],
                        review_revision=row["membership_revision"], invoice_number=row["invoice_number"],
                        supplier_name=row["supplier_name"], date_issued=row["date_issued"],
                        currency=row["currency"], subtotal=row["subtotal"], tax_amount=row["tax_amount"],
                        grand_total=row["grand_total"], is_math_valid=row["is_math_valid"],
                        lines=tuple(ExportLine(
                            line_item_id=line["id"], line_order=line["line_order"],
                            description=line["description"], quantity=line["quantity"],
                            unit_price=line["unit_price"], total_price=line["total_price"],
                        ) for line in lines),
                    )

    @staticmethod
    def _fence(claim: WorkerClaim | UUID, values: dict[str, object]) -> str:
        if isinstance(claim, WorkerClaim):
            values.update(attempt=claim.attempt_count, token=claim.lease_token)
            return " AND mode='asynchronous' AND attempt_count=:attempt AND lease_token=:token AND lease_expires_at>clock_timestamp()"
        return " AND mode='synchronous'"

    async def complete(self, claim: WorkerClaim | UUID, artifact: GeneratedArtifact) -> bool:
        values: dict[str, object] = {"id": claim.export_id if isinstance(claim, WorkerClaim) else claim,
                                    **artifact.__dict__}
        fence = self._fence(claim, values)
        async with self._sessions() as session:
            async with session.begin():
                result = await session.execute(text(
                    """UPDATE export_jobs SET status='completed',current_stage='completed',progress_percentage=100,
                              exported_document_count=:document_count,row_count=:row_count,
                              artifact_object_key=:object_key,artifact_file_name=:file_name,
                              artifact_content_type=:content_type,artifact_size_bytes=:size_bytes,
                              artifact_sha256=:sha256,artifact_expires_at=:expires_at,
                              completed_at=:completed_at,lease_token=NULL,lease_expires_at=NULL,
                              next_attempt_at=NULL,error_code=NULL,error_message=NULL
                       WHERE id=:id AND status='processing'""" + fence
                ), values)
        return result.rowcount == 1

    async def retry(self, claim: WorkerClaim, *, code: str, message: str,
                    due_at: datetime) -> bool:
        values = {"id": claim.export_id, "attempt": claim.attempt_count, "token": claim.lease_token,
                  "code": code, "message": message, "due": due_at}
        async with self._sessions() as session:
            async with session.begin():
                result = await session.execute(text(
                    """UPDATE export_jobs SET status='queued',current_stage='accepted',progress_percentage=0,
                              exported_document_count=0,row_count=0,next_attempt_at=:due,
                              lease_token=NULL,lease_expires_at=NULL,error_code=:code,error_message=:message
                       WHERE id=:id AND status='processing' AND attempt_count=:attempt
                         AND lease_token=:token AND lease_expires_at>clock_timestamp()"""
                ), values)
        return result.rowcount == 1

    async def fail(self, claim: WorkerClaim | UUID, *, code: str, message: str) -> bool:
        values: dict[str, object] = {"id": claim.export_id if isinstance(claim, WorkerClaim) else claim,
                                    "code": code, "message": message}
        fence = self._fence(claim, values)
        async with self._sessions() as session:
            async with session.begin():
                result = await session.execute(text(
                    """UPDATE export_jobs SET status='failed',exported_document_count=0,row_count=0,
                              next_attempt_at=NULL,lease_token=NULL,lease_expires_at=NULL,
                              error_code=:code,error_message=:message,failed_at=clock_timestamp()
                       WHERE id=:id AND status='processing'""" + fence
                ), values)
        return result.rowcount == 1

    async def due_dispatch(self, *, limit: int) -> tuple[UUID, ...]:
        async with self._sessions() as session:
            rows = (await session.execute(text(
                """SELECT id FROM export_jobs WHERE status='queued' AND mode='asynchronous'
                   AND (next_attempt_at IS NULL OR next_attempt_at<=clock_timestamp())
                   ORDER BY next_attempt_at NULLS FIRST,created_at,id LIMIT :limit"""
            ), {"limit": limit})).scalars().all()
        return tuple(rows)

    async def recover_expired_leases(self, *, limit: int) -> tuple[UUID, ...]:
        recovered: list[UUID] = []
        async with self._sessions() as session:
            async with session.begin():
                rows = (await session.execute(text(
                    """SELECT id,attempt_count FROM export_jobs WHERE status='processing'
                       AND mode='asynchronous' AND lease_expires_at<=clock_timestamp()
                       ORDER BY lease_expires_at,id LIMIT :limit FOR UPDATE SKIP LOCKED"""
                ), {"limit": limit})).mappings().all()
                for row in rows:
                    if row["attempt_count"] >= 4:
                        await session.execute(text(
                            """UPDATE export_jobs SET status='failed',exported_document_count=0,row_count=0,
                               lease_token=NULL,lease_expires_at=NULL,error_code='EXPORT_ATTEMPTS_EXHAUSTED',
                               error_message='Export retry attempts were exhausted.',failed_at=clock_timestamp()
                               WHERE id=:id"""
                        ), {"id": row["id"]})
                    else:
                        await session.execute(text(
                            """UPDATE export_jobs SET status='queued',current_stage='accepted',progress_percentage=0,
                               exported_document_count=0,row_count=0,next_attempt_at=clock_timestamp(),
                               lease_token=NULL,lease_expires_at=NULL,error_code='EXPORT_WORKER_INTERRUPTED',
                               error_message='Export worker was interrupted.' WHERE id=:id"""
                        ), {"id": row["id"]})
                        recovered.append(row["id"])
        return tuple(recovered)

    async def due_expiry(self, *, limit: int) -> tuple[UUID, ...]:
        async with self._sessions() as session:
            rows = (await session.execute(text(
                """SELECT id FROM export_jobs WHERE status='completed'
                   AND artifact_expires_at<=clock_timestamp()
                   ORDER BY artifact_expires_at,id LIMIT :limit"""
            ), {"limit": limit})).scalars().all()
        return tuple(rows)

    async def cleanup_key(self, export_id: UUID) -> str | None:
        async with self._sessions() as session:
            async with session.begin():
                await session.execute(text(
                    "SELECT pg_advisory_xact_lock(hashtextextended(CAST(:id AS text),0))"
                ), {"id": export_id})
                return (await session.execute(text(
                    """SELECT artifact_object_key FROM export_jobs WHERE id=:id
                       AND status='completed' AND artifact_expires_at<=clock_timestamp() FOR UPDATE"""
                ), {"id": export_id})).scalar_one_or_none()

    async def expire(self, export_id: UUID, expected_object_key: str) -> bool:
        async with self._sessions() as session:
            async with session.begin():
                result = await session.execute(text(
                    """UPDATE export_jobs SET status='expired',artifact_object_key=NULL,
                              expired_at=GREATEST(clock_timestamp(),artifact_expires_at)
                       WHERE id=:id AND status='completed' AND artifact_object_key=:key
                         AND artifact_expires_at<=clock_timestamp()"""
                ), {"id": export_id, "key": expected_object_key})
        return result.rowcount == 1


__all__ = ["SearchExportSqlRepository"]


