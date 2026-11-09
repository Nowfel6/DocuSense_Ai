"""Concrete tenant-safe human-review repository over the verified schema."""

from __future__ import annotations

import json
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..human_review_audit.errors import ReviewError
from ..human_review_audit.repository import (
    CommandOutcome, PreparedAction, ReviewSnapshot,
)
from ..human_review_audit.schemas import (
    AuditChange, AuditEvent, AuditQuery, Caller, EvidenceSummary, MutationData,
    ReviewInvoice, ReviewLineItem, RuleResult, ValidationReport,
    ValidationSummary,
)


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _summary(rows: tuple[RuleResult, ...]) -> ValidationSummary:
    return ValidationSummary(**{
        status: sum(row.status == status for row in rows)
        for status in ("passed", "failed", "missing", "not_applicable")
    })


class ReviewSqlRepository:
    """Implements review reads, mutation fencing, audit, and replay atomically."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    @staticmethod
    def _invoice(invoice: dict[str, object], lines: list[dict[str, object]]) -> ReviewInvoice:
        return ReviewInvoice(
            invoice_id=invoice["id"], invoice_number=invoice["invoice_number"],
            supplier_name=invoice["supplier_name"], supplier_tax_id=invoice["supplier_tax_id"],
            buyer_name=invoice["buyer_name"], date_issued=invoice["date_issued"],
            due_date=invoice["due_date"], currency=invoice["currency"],
            subtotal=invoice["subtotal"], tax_amount=invoice["tax_amount"],
            discount_amount=invoice["discount_amount"], grand_total=invoice["grand_total"],
            is_math_valid=invoice["is_math_valid"],
            line_items=tuple(ReviewLineItem(
                line_item_id=row["id"], origin=row["origin"], line_order=row["line_order"],
                description=row["description"], hs_code=row["hs_code"], quantity=row["quantity"],
                unit_price=row["unit_price"], tax_amount=row["tax_amount"],
                total_price=row["total_price"],
            ) for row in lines),
        )

    @staticmethod
    def _rule(row: dict[str, object]) -> RuleResult:
        return RuleResult(
            rule_id=row["rule_id"], scope_key=row["scope_key"], status=row["status"],
            observed_value=row["observed_value"], expected_value=row["expected_value"],
            difference=row["difference"], epsilon=row["epsilon"],
            message_code=row["message_code"], blocks_approval=row["blocks_approval"],
        )

    @classmethod
    async def _review_validation(cls, session: AsyncSession, document_id: UUID,
                                 revision: int) -> ValidationReport | None:
        run = (await session.execute(text(
            """SELECT * FROM review_validation_runs
               WHERE document_id=:document_id AND review_revision=:revision"""
        ), {"document_id": document_id, "revision": revision})).mappings().one_or_none()
        if run is None:
            return None
        raw = (await session.execute(text(
            """SELECT * FROM review_validation_results
               WHERE review_validation_run_id=:run_id ORDER BY rule_id,scope_key,id"""
        ), {"run_id": run["id"]})).mappings().all()
        rules = tuple(cls._rule(dict(row)) for row in raw)
        blockers = tuple(row.message_code for row in rules
                         if row.blocks_approval and row.status in ("failed", "missing"))
        return ValidationReport(
            validation_version=run["validation_version"], is_math_valid=run["is_math_valid"],
            approval_eligible=run["approval_eligible"], summary=_summary(rules), results=rules,
            blocking_reasons=blockers,
        )

    @classmethod
    async def _snapshot(cls, session: AsyncSession, caller: Caller, document_id: UUID,
                        *, lock: bool = False) -> ReviewSnapshot | None:
        if lock:
            visible = (await session.execute(text(
                """SELECT d.id FROM documents d
                   JOIN processing_jobs j ON j.document_id=d.id
                   WHERE d.id=:document_id AND d.company_id=:company_id
                   FOR UPDATE OF d,j"""
            ), {"document_id": document_id,
                "company_id": caller.company_id})).scalar_one_or_none()
            if visible is None:
                return None
        owner = (await session.execute(text(
            """SELECT d.id AS document_id,d.company_id,d.file_name,d.file_size_bytes,
                      d.mime_type,d.doc_type,d.status,d.overall_confidence,d.created_at,d.updated_at,
                      d.uploaded_by,d.s3_url,d.review_revision,j.id AS job_id,j.status AS job_status,
                      j.progress_percentage,r.id AS run_id,r.status AS run_status,
                      r.finished_at AS run_finished_at,i.id AS invoice_id,
                      COALESCE(jsonb_array_length(p.canonical_document->'pages'),0) AS page_count
               FROM documents d JOIN processing_jobs j ON j.document_id=d.id
               LEFT JOIN extraction_runs r ON r.document_id=d.id
               LEFT JOIN invoices i ON i.document_id=d.id AND i.extraction_run_id=r.id
               LEFT JOIN document_partitions p ON p.document_id=d.id
               WHERE d.id=:document_id AND d.company_id=:company_id"""
        ), {"document_id": document_id, "company_id": caller.company_id})).mappings().one_or_none()
        if owner is None:
            return None
        invoice = None
        extraction_summary = None
        evidence: tuple[EvidenceSummary, ...] = ()
        if lock and owner["run_id"] is not None:
            await session.execute(text(
                "SELECT id FROM extraction_runs WHERE id=:run_id FOR UPDATE"
            ), {"run_id": owner["run_id"]})
        if owner["invoice_id"] is not None:
            invoice_row = (await session.execute(text(
                "SELECT * FROM invoices WHERE id=:invoice_id" + (" FOR UPDATE" if lock else "")
            ), {"invoice_id": owner["invoice_id"]})).mappings().one()
            lines = (await session.execute(text(
                "SELECT * FROM line_items WHERE invoice_id=:invoice_id ORDER BY line_order,id" +
                (" FOR UPDATE" if lock else "")
            ), {"invoice_id": owner["invoice_id"]})).mappings().all()
            invoice = cls._invoice(dict(invoice_row), [dict(row) for row in lines])
        if owner["run_id"] is not None:
            counts = dict((await session.execute(text(
                """SELECT status,count(*) FROM validation_results
                   WHERE extraction_run_id=:run_id GROUP BY status"""
            ), {"run_id": owner["run_id"]})).all())
            extraction_summary = ValidationSummary(**{
                status: int(counts.get(status, 0))
                for status in ("passed", "failed", "missing", "not_applicable")
            })
            evidence_rows = (await session.execute(text(
                """SELECT field_path,source_page,evidence_excerpt,confidence_score,validation_state
                   FROM field_evidence WHERE extraction_run_id=:run_id ORDER BY field_path,id"""
            ), {"run_id": owner["run_id"]})).mappings().all()
            evidence = tuple(EvidenceSummary(**dict(row)) for row in evidence_rows)
        latest = await cls._review_validation(
            session, document_id, int(owner["review_revision"])
        ) if owner["review_revision"] else None
        return ReviewSnapshot(
            document_id=owner["document_id"], company_id=owner["company_id"],
            file_name=owner["file_name"], file_size_bytes=owner["file_size_bytes"],
            mime_type=owner["mime_type"], doc_type=owner["doc_type"], status=owner["status"],
            overall_confidence=owner["overall_confidence"], created_at=owner["created_at"],
            updated_at=owner["updated_at"], uploaded_by=owner["uploaded_by"],
            job_id=owner["job_id"], job_status=owner["job_status"],
            progress_percentage=owner["progress_percentage"], run_status=owner["run_status"],
            run_finished_at=owner["run_finished_at"], review_revision=owner["review_revision"],
            invoice=invoice, extraction_validation=extraction_summary, field_evidence=evidence,
            latest_review_validation=latest, private_reference=owner["s3_url"],
            page_count=owner["page_count"] or None,
        )

    async def get_snapshot(self, caller: Caller, document_id: UUID) -> ReviewSnapshot | None:
        async with self._sessions() as session:
            async with session.begin():
                await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
                return await self._snapshot(session, caller, document_id)

    async def list_audit(self, caller: Caller, document_id: UUID,
                         query: AuditQuery) -> tuple[tuple[AuditEvent, ...], int] | None:
        async with self._sessions() as session:
            async with session.begin():
                await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
                visible = (await session.execute(text(
                    "SELECT 1 FROM documents WHERE id=:document_id AND company_id=:company_id"
                ), {"document_id": document_id, "company_id": caller.company_id})).scalar_one_or_none()
                if visible is None:
                    return None
                action_sql = " AND e.action=:action" if query.action else ""
                values: dict[str, object] = {
                    "document_id": document_id, "action": query.action,
                    "limit": query.page_size, "offset": (query.page - 1) * query.page_size,
                }
                total = int((await session.execute(text(
                    "SELECT count(*) FROM review_audit_events e WHERE e.document_id=:document_id" + action_sql
                ), values)).scalar_one())
                events = (await session.execute(text(
                    """SELECT e.*,u.full_name AS actor_display_name FROM review_audit_events e
                       LEFT JOIN users u ON u.id=e.actor_user_id
                       WHERE e.document_id=:document_id""" + action_sql +
                    " ORDER BY e.created_at DESC,e.id DESC LIMIT :limit OFFSET :offset"
                ), values)).mappings().all()
                ids = [row["id"] for row in events]
                changes_by_event: dict[UUID, list[AuditChange]] = {event_id: [] for event_id in ids}
                if ids:
                    changes = (await session.execute(text(
                        """SELECT * FROM review_audit_changes WHERE audit_event_id=ANY(:ids)
                           ORDER BY audit_event_id,field_path,id"""
                    ), {"ids": ids})).mappings().all()
                    for row in changes:
                        changes_by_event[row["audit_event_id"]].append(AuditChange(
                            field_path=row["field_path"], change_kind=row["change_kind"],
                            old_value=row["old_value"], new_value=row["new_value"],
                        ))
        return tuple(AuditEvent(
            audit_event_id=row["id"], actor_user_id=row["actor_user_id"],
            actor_display_name=row["actor_display_name"], action=row["action"],
            from_status=row["from_status"], to_status=row["to_status"],
            review_revision=row["review_revision"], reason=row["reason"], note=row["note"],
            request_id=row["request_id"], created_at=row["created_at"],
            changes=tuple(changes_by_event[row["id"]]),
        ) for row in events), total

    @staticmethod
    async def _reserve(session: AsyncSession, caller: Caller, document_id: UUID,
                       key: str, request_hash: str) -> tuple[bool, dict[str, object]]:
        inserted = (await session.execute(text(
            """INSERT INTO review_idempotency_keys
               (id,company_id,actor_user_id,document_id,idempotency_key,request_hash,expires_at)
               VALUES (:id,:company_id,:actor_id,:document_id,:key,:request_hash,
                       clock_timestamp()+interval '25 hours')
               ON CONFLICT (company_id,actor_user_id,document_id,idempotency_key)
               DO NOTHING RETURNING id"""
        ), {"id": uuid4(), "company_id": caller.company_id, "actor_id": caller.user_id,
            "document_id": document_id, "key": key, "request_hash": request_hash})).scalar_one_or_none()
        row = (await session.execute(text(
            """SELECT * FROM review_idempotency_keys
               WHERE company_id=:company_id AND actor_user_id=:actor_id
                 AND document_id=:document_id AND idempotency_key=:key FOR UPDATE"""
        ), {"company_id": caller.company_id, "actor_id": caller.user_id,
            "document_id": document_id, "key": key})).mappings().one()
        return inserted is not None, dict(row)

    @staticmethod
    async def _persist_validation(session: AsyncSession, document_id: UUID,
                                  action: PreparedAction) -> None:
        if action.validation is None:
            return
        run_id = uuid4()
        validation = action.validation
        await session.execute(text(
            """INSERT INTO review_validation_runs
               (id,audit_event_id,document_id,review_revision,validation_version,
                candidate_hash,is_math_valid,approval_eligible)
               VALUES (:id,:event_id,:document_id,:revision,:version,:candidate_hash,
                       :is_math_valid,:approval_eligible)"""
        ), {"id": run_id, "event_id": action.event_id, "document_id": document_id,
            "revision": action.resulting_revision, "version": validation.validation_version,
            "candidate_hash": validation.candidate_hash,
            "is_math_valid": validation.is_math_valid,
            "approval_eligible": validation.approval_eligible})
        for rule in validation.results:
            await session.execute(text(
                """INSERT INTO review_validation_results
                   (id,review_validation_run_id,rule_id,scope_key,status,observed_value,
                    expected_value,difference,epsilon,message_code,blocks_approval)
                   VALUES (:id,:run_id,:rule_id,:scope_key,:status,CAST(:observed AS jsonb),
                    CAST(:expected AS jsonb),:difference,:epsilon,:message_code,:blocks_approval)"""
            ), {"id": uuid4(), "run_id": run_id, "rule_id": rule.rule_id,
                "scope_key": rule.scope_key, "status": rule.status,
                "observed": _json(rule.observed_value), "expected": _json(rule.expected_value),
                "difference": rule.difference, "epsilon": rule.epsilon,
                "message_code": rule.message_code, "blocks_approval": rule.blocks_approval})

    @staticmethod
    async def _apply_candidate(session: AsyncSession, invoice_id: UUID,
                               action: PreparedAction) -> ReviewInvoice | None:
        if action.candidate is None:
            return None
        candidate = action.candidate
        validation = action.validation
        assert validation is not None
        await session.execute(text(
            """UPDATE invoices SET invoice_number=:invoice_number,supplier_name=:supplier_name,
                      supplier_tax_id=:supplier_tax_id,buyer_name=:buyer_name,date_issued=:date_issued,
                      due_date=:due_date,currency=:currency,subtotal=:subtotal,tax_amount=:tax_amount,
                      discount_amount=:discount_amount,grand_total=:grand_total,is_math_valid=:is_math_valid
               WHERE id=:invoice_id"""
        ), {"invoice_id": invoice_id, **candidate.invoice.model_dump(),
            "is_math_valid": validation.is_math_valid})
        current = (await session.execute(text(
            "SELECT id,line_order FROM line_items WHERE invoice_id=:invoice_id ORDER BY id FOR UPDATE"
        ), {"invoice_id": invoice_id})).mappings().all()
        desired = {row.line_item_id: row for row in candidate.line_items}
        current_ids = {row["id"] for row in current}
        changed_order = {
            row["id"] for row in current
            if row["id"] in desired and row["line_order"] != desired[row["id"]].line_order
        }
        for row in current:
            if row["id"] in changed_order:
                await session.execute(text(
                    "UPDATE line_items SET line_order=:temporary WHERE id=:id"
                ), {"temporary": 1_000_000 + int(row["line_order"]), "id": row["id"]})
        for line_id in current_ids - desired.keys():
            await session.execute(text("DELETE FROM line_items WHERE id=:id"), {"id": line_id})
        for line in candidate.line_items:
            values = {"id": line.line_item_id, "invoice_id": invoice_id,
                      "source_row_key": f"manual:{line.line_item_id}", **line.model_dump()}
            values.pop("client_correlation_key", None)
            values.pop("origin", None)
            if line.line_item_id in current_ids:
                await session.execute(text(
                    """UPDATE line_items SET line_order=:line_order,description=:description,
                              hs_code=:hs_code,quantity=:quantity,unit_price=:unit_price,
                              tax_amount=:tax_amount,total_price=:total_price WHERE id=:id"""
                ), values)
            else:
                await session.execute(text(
                    """INSERT INTO line_items
                       (id,invoice_id,source_row_key,line_order,origin,description,hs_code,
                        quantity,unit_price,tax_amount,total_price)
                       VALUES (:id,:invoice_id,:source_row_key,:line_order,'reviewer_added',
                        :description,:hs_code,:quantity,:unit_price,:tax_amount,:total_price)"""
                ), values)
        return ReviewInvoice(
            invoice_id=invoice_id, **candidate.invoice.model_dump(),
            is_math_valid=validation.is_math_valid,
            line_items=tuple(ReviewLineItem(
                line_item_id=row.line_item_id, origin=row.origin, line_order=row.line_order,
                description=row.description, hs_code=row.hs_code, quantity=row.quantity,
                unit_price=row.unit_price, tax_amount=row.tax_amount, total_price=row.total_price,
            ) for row in candidate.line_items),
        )

    async def execute(self, caller: Caller, document_id: UUID,
                      idempotency_key: str | None, request_hash: str,
                      prepare) -> CommandOutcome:
        if caller.user_id is None:
            raise ReviewError("FORBIDDEN")
        async with self._sessions() as session:
            async with session.begin():
                reservation_id = None
                if idempotency_key is not None:
                    created, reservation = await self._reserve(
                        session, caller, document_id, idempotency_key, request_hash
                    )
                    if reservation["request_hash"] != request_hash:
                        raise ReviewError("IDEMPOTENCY_KEY_REUSED")
                    if not created:
                        if (reservation["audit_event_id"] is None
                                or reservation["response_status"] is None
                                or reservation["response_body"] is None):
                            raise ReviewError("REVIEW_DATA_INTEGRITY_ERROR")
                        return CommandOutcome(
                            MutationData.model_validate(reservation["response_body"]), replayed=True
                        )
                    reservation_id = reservation["id"]
                snapshot = await self._snapshot(session, caller, document_id, lock=True)
                if snapshot is None:
                    raise ReviewError("DOCUMENT_NOT_FOUND")
                action: PreparedAction = prepare(snapshot)
                if snapshot.invoice is None:
                    raise ReviewError("REVIEW_DATA_INTEGRITY_ERROR")
                event_created = (await session.execute(text(
                    """INSERT INTO review_audit_events
                       (id,document_id,actor_user_id,action,from_status,to_status,review_revision,
                        reason,note,request_id,payload_hash)
                       VALUES (:id,:document_id,:actor_id,:action,:from_status,:to_status,:revision,
                        :reason,:note,:request_id,:payload_hash) RETURNING created_at"""
                ), {"id": action.event_id, "document_id": document_id,
                    "actor_id": caller.user_id, "action": action.event_action,
                    "from_status": action.from_status, "to_status": action.to_status,
                    "revision": action.resulting_revision, "reason": action.reason,
                    "note": action.note, "request_id": action.request_id,
                    "payload_hash": action.payload_hash})).scalar_one()
                for change in action.changes:
                    await session.execute(text(
                        """INSERT INTO review_audit_changes
                           (id,audit_event_id,field_path,change_kind,old_value,new_value)
                           VALUES (:id,:event_id,:path,:kind,CAST(:old AS jsonb),CAST(:new AS jsonb))"""
                    ), {"id": uuid4(), "event_id": action.event_id,
                        "path": change.field_path, "kind": change.change_kind,
                        "old": _json(change.old_value), "new": _json(change.new_value)})
                await session.execute(text(
                    "SELECT set_config('docusense.review_event_id',CAST(:event_id AS text),true)"
                ), {"event_id": action.event_id})
                invoice = await self._apply_candidate(session, snapshot.invoice.invoice_id, action)
                await self._persist_validation(session, document_id, action)
                decision = action.event_action in ("approved", "rejected")
                result = await session.execute(text(
                    """UPDATE documents SET status=:status,review_revision=:new_revision,
                              last_reviewed_by=CASE WHEN :decision THEN CAST(:actor_id AS uuid)
                                                   ELSE last_reviewed_by END,
                              last_reviewed_at=CASE WHEN :decision THEN :reviewed_at
                                                   ELSE last_reviewed_at END
                       WHERE id=:document_id AND company_id=:company_id
                         AND review_revision=:old_revision"""
                ), {"status": action.to_status, "new_revision": action.resulting_revision,
                    "decision": decision, "actor_id": caller.user_id, "reviewed_at": event_created,
                    "document_id": document_id, "company_id": caller.company_id,
                    "old_revision": snapshot.review_revision})
                if result.rowcount != 1:
                    raise ReviewError("REVIEW_CONFLICT")
                if invoice is None:
                    invoice = snapshot.invoice
                from ..human_review_audit.service import permitted_actions
                data = MutationData(
                    document_id=document_id, status=action.to_status,
                    review_revision=action.resulting_revision, invoice=invoice,
                    latest_review_validation=(
                        action.validation.public() if action.validation is not None else None
                    ), audit_event_id=action.event_id,
                    permitted_actions=permitted_actions(action.to_status, caller.role),
                )
                if reservation_id is not None:
                    await session.execute(text(
                        """UPDATE review_idempotency_keys SET audit_event_id=:event_id,
                                  response_status=200,response_body=CAST(:body AS jsonb)
                           WHERE id=:id"""
                    ), {"event_id": action.event_id,
                        "body": data.model_dump_json(), "id": reservation_id})
                await session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
        return CommandOutcome(data)


__all__ = ["ReviewSqlRepository"]


