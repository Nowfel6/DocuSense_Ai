"""Concrete SQLAlchemy repositories over the verified PostgreSQL schema."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..document_ingestion.errors import CommitUncertain, IngestionError, duplicate
from ..document_ingestion.repository import (
    AcceptanceCommand, AcceptanceReceipt, DocumentPage, Resolution,
)
from ..document_ingestion.schemas import (
    Caller, DocumentRecord, DocumentSummary, JobSnapshot, ListQuery,
)

if TYPE_CHECKING:
    from ..document_ingestion.dispatcher import DispatchCandidate


class IngestionSqlRepository:
    """Pair-atomic ingestion writes and tenant-filtered reads."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def has_duplicate(self, company_id: UUID, file_hash: str) -> bool:
        async with self._sessions() as session:
            result = await session.execute(text(
                "SELECT EXISTS(SELECT 1 FROM documents WHERE company_id=:company_id AND file_hash=:file_hash)"
            ), {"company_id": company_id, "file_hash": file_hash})
            return bool(result.scalar_one())

    async def accept(self, command: AcceptanceCommand) -> AcceptanceReceipt:
        committed = False
        try:
            async with self._sessions() as session:
                async with session.begin():
                    await session.execute(text(
                        "SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"
                    ), {"lock_key": f"{command.company_id}:{command.file_hash}"})
                    exists = bool((await session.execute(text(
                        "SELECT EXISTS(SELECT 1 FROM documents WHERE company_id=:company_id AND file_hash=:file_hash)"
                    ), {"company_id": command.company_id, "file_hash": command.file_hash})).scalar_one())
                    if exists and not command.confirm_duplicate:
                        raise duplicate()
                    await session.execute(text(
                        """INSERT INTO documents
                           (id,company_id,uploaded_by,file_name,s3_url,file_size_bytes,file_hash,mime_type,doc_type,status)
                           VALUES (:id,:company_id,:uploaded_by,:file_name,:reference,:size,:hash,:mime,:doc_type,'queued')"""
                    ), {
                        "id": command.document_id, "company_id": command.company_id,
                        "uploaded_by": command.uploaded_by, "file_name": command.file_name,
                        "reference": command.private_reference, "size": command.file_size_bytes,
                        "hash": command.file_hash, "mime": command.mime_type,
                        "doc_type": command.doc_type,
                    })
                    await session.execute(text(
                        """INSERT INTO processing_jobs
                           (id,document_id,status,current_stage,progress_percentage,attempt_count)
                           VALUES (:job_id,:document_id,'queued','upload',0,0)"""
                    ), {"job_id": command.job_id, "document_id": command.document_id})
                committed = True
            return AcceptanceReceipt(command.document_id, command.job_id, exists)
        except IngestionError:
            raise
        except (DBAPIError, SQLAlchemyError) as exc:
            if committed or getattr(exc, "connection_invalidated", False):
                raise CommitUncertain() from exc
            raise IngestionError("DATABASE_UNAVAILABLE") from exc

    async def resolve_acceptance(self, command: AcceptanceCommand) -> Resolution:
        try:
            async with self._sessions() as session:
                result = await session.execute(text(
                    """SELECT d.id AS document_id,j.id AS job_id,d.company_id,d.s3_url,
                              d.file_hash,d.file_size_bytes,
                              EXISTS(SELECT 1 FROM documents other
                                     WHERE other.company_id=d.company_id
                                       AND other.file_hash=d.file_hash
                                       AND other.id<>d.id) AS was_duplicate
                       FROM documents d LEFT JOIN processing_jobs j ON j.document_id=d.id
                       WHERE d.id=:document_id OR j.id=:job_id"""
                ), {"document_id": command.document_id, "job_id": command.job_id})
                rows = result.mappings().all()
        except SQLAlchemyError:
            return Resolution("unknown")
        if not rows:
            return Resolution("unknown")
        if len(rows) == 1:
            row = rows[0]
            exact = (
                row["document_id"] == command.document_id and row["job_id"] == command.job_id
                and row["company_id"] == command.company_id
                and row["s3_url"] == command.private_reference
                and row["file_hash"] == command.file_hash
                and row["file_size_bytes"] == command.file_size_bytes
            )
            if exact:
                return Resolution("committed", AcceptanceReceipt(
                    command.document_id, command.job_id, bool(row["was_duplicate"]),
                ))
        return Resolution("unknown")

    async def safe_to_remove(self, command: AcceptanceCommand) -> bool:
        try:
            async with self._sessions() as session:
                async with session.begin():
                    await session.execute(text(
                        "SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"
                    ), {"lock_key": f"{command.company_id}:{command.file_hash}"})
                    referenced = bool((await session.execute(text(
                        """SELECT EXISTS(
                               SELECT 1 FROM documents d
                               LEFT JOIN processing_jobs j ON j.document_id=d.id
                               WHERE d.id=:document_id OR j.id=:job_id OR d.s3_url=:reference
                           )"""
                    ), {
                        "document_id": command.document_id, "job_id": command.job_id,
                        "reference": command.private_reference,
                    })).scalar_one())
            return not referenced
        except SQLAlchemyError:
            return False

    async def due_page(
        self, after: "DispatchCandidate | None", limit: int,
    ) -> tuple["DispatchCandidate", ...]:
        """Return DB-time eligible queued or expired-lease work in stable order."""
        from ..document_ingestion.dispatcher import DispatchCandidate

        if not 1 <= limit <= 1000:
            raise ValueError("Dispatch limit must be 1..1000")
        values: dict[str, object] = {"limit": limit}
        cursor = ""
        if after is not None:
            values.update({
                "after_next": after.next_attempt_at,
                "after_created": after.created_at,
                "after_id": after.job_id,
            })
            cursor = """
              AND (
                COALESCE(j.next_attempt_at, '-infinity'::timestamptz),
                j.created_at,
                j.id
              ) > (
                COALESCE(CAST(:after_next AS timestamptz), '-infinity'::timestamptz),
                CAST(:after_created AS timestamptz),
                CAST(:after_id AS uuid)
              )
            """
        async with self._sessions() as session:
            rows = (await session.execute(text(f"""
                SELECT d.id AS document_id,j.id AS job_id,j.next_attempt_at,j.created_at
                FROM processing_jobs j
                JOIN documents d ON d.id=j.document_id
                WHERE j.attempt_count < 4
                  AND (
                    (j.status='queued' AND
                     (j.next_attempt_at IS NULL OR j.next_attempt_at<=clock_timestamp()))
                    OR
                    (j.status='processing' AND j.lease_expires_at IS NOT NULL
                     AND j.lease_expires_at<=clock_timestamp())
                  )
                  {cursor}
                ORDER BY j.next_attempt_at ASC NULLS FIRST,j.created_at ASC,j.id ASC
                LIMIT :limit
            """), values)).mappings().all()
        return tuple(DispatchCandidate(**dict(row)) for row in rows)

    @staticmethod
    def _summary(row: dict[str, object]) -> DocumentSummary:
        return DocumentSummary(
            document_id=row["document_id"], file_name=row["file_name"],
            file_size_bytes=row["file_size_bytes"], mime_type=row["mime_type"],
            doc_type=row["doc_type"], status=row["document_status"],
            overall_confidence=row["overall_confidence"],
            created_at=row["created_at"], updated_at=row["updated_at"],
        )

    async def list_documents(self, caller: Caller, query: ListQuery) -> DocumentPage:
        filters = ["company_id=:company_id"]
        values: dict[str, object] = {"company_id": caller.company_id}
        if caller.user_id is not None and caller.role == "viewer":
            filters.append("status='approved'")
        if query.status:
            filters.append("status=:status")
            values["status"] = query.status
        if query.doc_type:
            filters.append("doc_type=:doc_type")
            values["doc_type"] = query.doc_type
        if query.from_date:
            filters.append("created_at>=:from_date")
            values["from_date"] = query.from_date
        if query.to_date:
            filters.append("created_at<(:to_date + INTERVAL '1 day')")
            values["to_date"] = query.to_date
        where = " AND ".join(filters)
        sort = {"created_at": "created_at", "updated_at": "updated_at", "file_name": "file_name"}[query.sort_by]
        direction = "ASC" if query.order == "asc" else "DESC"
        values.update({"limit": query.page_size, "offset": (query.page - 1) * query.page_size})
        async with self._sessions() as session:
            async with session.begin():
                await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
                total = int((await session.execute(text(
                    f"SELECT count(*) FROM documents WHERE {where}"
                ), values)).scalar_one())
                rows = (await session.execute(text(
                    f"""SELECT id AS document_id,file_name,file_size_bytes,mime_type,doc_type,
                                status AS document_status,overall_confidence,created_at,updated_at
                         FROM documents WHERE {where}
                         ORDER BY {sort} {direction}, id {direction}
                         LIMIT :limit OFFSET :offset"""
                ), values)).mappings().all()
        return DocumentPage(tuple(self._summary(dict(row)) for row in rows), total)

    async def get_document(self, caller: Caller, document_id: UUID) -> DocumentRecord | None:
        visibility = "AND d.status='approved'" if caller.user_id is not None and caller.role == "viewer" else ""
        async with self._sessions() as session:
            row = (await session.execute(text(
                f"""SELECT d.id AS document_id,d.company_id,d.uploaded_by,d.s3_url,d.file_name,
                            d.file_size_bytes,d.mime_type,d.doc_type,d.status AS document_status,
                            d.overall_confidence,d.created_at,d.updated_at,
                            j.id AS job_id,j.status AS job_status,j.current_stage,j.progress_percentage,
                            j.attempt_count,j.lease_expires_at,j.next_attempt_at,j.started_at,
                            j.finished_at,j.error_code,j.error_message
                     FROM documents d LEFT JOIN processing_jobs j ON j.document_id=d.id
                     WHERE d.id=:document_id AND d.company_id=:company_id {visibility}"""
            ), {"document_id": document_id, "company_id": caller.company_id})).mappings().one_or_none()
        if row is None:
            return None
        data = dict(row)
        job = None if data["job_id"] is None else JobSnapshot(
            id=data["job_id"], document_id=data["document_id"], status=data["job_status"],
            current_stage=data["current_stage"], progress_percentage=data["progress_percentage"],
            attempt_count=data["attempt_count"], lease_expires_at=data["lease_expires_at"],
            next_attempt_at=data["next_attempt_at"], started_at=data["started_at"],
            finished_at=data["finished_at"], error_code=data["error_code"],
            error_message=data["error_message"],
        )
        return DocumentRecord(
            company_id=data["company_id"], summary=self._summary(data),
            uploaded_by=data["uploaded_by"], private_reference=data["s3_url"], job=job,
        )


__all__ = ["IngestionSqlRepository"]


