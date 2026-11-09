"""Authorization-aware review query, preview, and command services."""
from __future__ import annotations

from collections.abc import Callable
from uuid import UUID, uuid4

from .diff import (
    build_changes,
    client_request_payload,
    request_hash as hash_request,
)
from .errors import ReviewError, invalid
from .repository import (
    CommandOutcome,
    PreparedAction,
    ReviewRepository,
    ReviewSnapshot,
    SourceAccessService,
)
from .schemas import (
    ApproveReviewRequest,
    AuditPage,
    AuditQuery,
    Caller,
    CandidatePayload,
    MutationData,
    PreviewData,
    RejectReviewRequest,
    ReopenReviewRequest,
    ResolvedCandidate,
    ResolvedLineCandidate,
    ReviewActionRequest,
    ReviewDetail,
    ReviewValidationRequest,
    SaveReviewRequest,
)
from .validation import (
    UnsupportedCurrencyError,
    preview_candidate,
    validate_candidate,
)


def _human_reviewer(caller: Caller) -> None:
    if caller.api_key_id is not None or caller.user_id is None:
        raise ReviewError("FORBIDDEN")
    if caller.role not in ("admin", "operator"):
        raise ReviewError("FORBIDDEN")


def _human_reader(caller: Caller) -> None:
    if caller.api_key_id is not None or caller.user_id is None:
        raise ReviewError("FORBIDDEN")
    if caller.role not in ("admin", "operator", "viewer"):
        raise ReviewError("FORBIDDEN")


def _assert_detail_snapshot(snapshot: ReviewSnapshot, caller: Caller,
                            document_id: UUID) -> None:
    if snapshot.document_id != document_id or snapshot.company_id != caller.company_id:
        raise ReviewError("REVIEW_DATA_INTEGRITY_ERROR")
    if snapshot.review_revision < 0:
        raise ReviewError("REVIEW_DATA_INTEGRITY_ERROR")
    if caller.role == "viewer" and snapshot.status != "approved":
        # Viewer visibility is deliberately indistinguishable from a missing row.
        raise ReviewError("DOCUMENT_NOT_FOUND")


def _assert_snapshot(snapshot: ReviewSnapshot, caller: Caller, document_id: UUID,
                     *, allow_terminal: bool) -> None:
    if snapshot.document_id != document_id or snapshot.company_id != caller.company_id:
        raise ReviewError("REVIEW_DATA_INTEGRITY_ERROR")
    if snapshot.doc_type != "commercial_invoice":
        raise ReviewError("DOCUMENT_NOT_REVIEWABLE")
    if snapshot.job_status != "completed" or snapshot.progress_percentage != 100:
        raise ReviewError("DOCUMENT_NOT_REVIEWABLE")
    if snapshot.run_status != "completed" or snapshot.run_finished_at is None:
        raise ReviewError("DOCUMENT_NOT_REVIEWABLE")
    if snapshot.invoice is None or snapshot.extraction_validation is None:
        raise ReviewError("REVIEW_DATA_INTEGRITY_ERROR")
    if snapshot.review_revision < 0:
        raise ReviewError("REVIEW_DATA_INTEGRITY_ERROR")
    if allow_terminal:
        if snapshot.status not in ("pending_review", "approved", "rejected"):
            raise ReviewError("DOCUMENT_NOT_REVIEWABLE")
    elif snapshot.status != "pending_review":
        raise ReviewError("DOCUMENT_NOT_REVIEWABLE")


def permitted_actions(status: str, role: str | None) -> tuple[str, ...]:
    if status == "pending_review" and role in ("admin", "operator"):
        return ("save", "approve", "reject")
    if status == "approved" and role == "admin":
        return ("reopen",)
    return ()


def _resolve_candidate(payload: CandidatePayload, snapshot: ReviewSnapshot,
                       uuid_factory: Callable[[], UUID]) -> ResolvedCandidate:
    if snapshot.invoice is None:
        raise ReviewError("REVIEW_DATA_INTEGRITY_ERROR")
    existing = {line.line_item_id: line for line in snapshot.invoice.line_items}
    rows: list[ResolvedLineCandidate] = []
    for line in payload.line_items:
        if line.line_item_id is not None:
            persisted = existing.get(line.line_item_id)
            if persisted is None:
                raise invalid("line_items", "Unknown line identity.")
            line_id = line.line_item_id
            origin = persisted.origin
            correlation = None
        else:
            line_id = uuid_factory()
            origin = "reviewer_added"
            correlation = line.client_correlation_key
        rows.append(ResolvedLineCandidate(
            line_item_id=line_id,
            origin=origin,
            client_correlation_key=correlation,
            description=line.description,
            hs_code=line.hs_code,
            quantity=line.quantity,
            unit_price=line.unit_price,
            tax_amount=line.tax_amount,
            total_price=line.total_price,
            line_order=line.line_order,
        ))
    return ResolvedCandidate(invoice=payload.invoice, line_items=tuple(rows))


class ReviewQueryService:
    def __init__(self, repository: ReviewRepository, source_access: SourceAccessService) -> None:
        if repository is None or source_access is None:
            raise ValueError("Review repository and source access are required")
        self.repository = repository
        self.source_access = source_access

    async def get_review_detail(self, caller: Caller, document_id: UUID) -> ReviewDetail:
        _human_reader(caller)
        snapshot = await self.repository.get_snapshot(caller, document_id)
        if snapshot is None:
            raise ReviewError("DOCUMENT_NOT_FOUND")
        _assert_detail_snapshot(snapshot, caller, document_id)
        has_review_projection = snapshot.status in ("pending_review", "approved", "rejected")
        if has_review_projection:
            _assert_snapshot(snapshot, caller, document_id, allow_terminal=True)
        try:
            source = await self.source_access.issue(
                caller, document_id, snapshot.private_reference,
                snapshot.mime_type, snapshot.page_count,
            )
        except ReviewError:
            raise
        except Exception as exc:
            raise ReviewError("SOURCE_TEMPORARILY_UNAVAILABLE") from exc
        technical_reader = caller.role in ("admin", "operator")
        return ReviewDetail(
            document_id=snapshot.document_id,
            file_name=snapshot.file_name,
            file_size_bytes=snapshot.file_size_bytes,
            mime_type=snapshot.mime_type,
            doc_type=snapshot.doc_type,
            status=snapshot.status,
            overall_confidence=snapshot.overall_confidence,
            created_at=snapshot.created_at,
            updated_at=snapshot.updated_at,
            job_id=snapshot.job_id,
            uploaded_by=snapshot.uploaded_by,
            review_revision=(snapshot.review_revision
                             if has_review_projection and technical_reader else None),
            permitted_actions=(permitted_actions(snapshot.status, caller.role)
                               if has_review_projection and technical_reader else ()),
            invoice=snapshot.invoice if has_review_projection else None,
            extraction_validation=(snapshot.extraction_validation
                                   if has_review_projection else None),
            field_evidence=(snapshot.field_evidence
                            if has_review_projection and technical_reader else ()),
            latest_review_validation=(snapshot.latest_review_validation
                                      if has_review_projection and technical_reader else None),
            source_view=source,
        )

    async def list_audit_logs(self, caller: Caller, document_id: UUID,
                              query: AuditQuery) -> AuditPage:
        _human_reviewer(caller)
        page = await self.repository.list_audit(caller, document_id, query)
        if page is None:
            raise ReviewError("DOCUMENT_NOT_FOUND")
        rows, total = page
        if len(rows) > query.page_size or total < len(rows):
            raise ReviewError("REVIEW_DATA_INTEGRITY_ERROR")
        return AuditPage(rows=rows, pagination=query_pagination(query, total))


def query_pagination(query: AuditQuery, total: int):
    from .schemas import Pagination

    return Pagination.create(query, total)


class ReviewValidationService:
    def __init__(self, repository: ReviewRepository,
                 supported_currencies: frozenset[str],
                 uuid_factory: Callable[[], UUID] = uuid4) -> None:
        if repository is None or not supported_currencies:
            raise ValueError("Repository and supported currency set are required")
        self.repository = repository
        self.supported_currencies = supported_currencies
        self.uuid_factory = uuid_factory

    async def preview(self, caller: Caller, document_id: UUID,
                      request: ReviewValidationRequest) -> PreviewData:
        _human_reviewer(caller)
        snapshot = await self.repository.get_snapshot(caller, document_id)
        if snapshot is None:
            raise ReviewError("DOCUMENT_NOT_FOUND")
        _assert_snapshot(snapshot, caller, document_id, allow_terminal=False)
        if request.expected_review_revision != snapshot.review_revision:
            raise ReviewError("REVIEW_CONFLICT")
        payload = CandidatePayload(invoice=request.invoice, line_items=request.line_items)
        candidate = _resolve_candidate(payload, snapshot, self.uuid_factory)
        try:
            return preview_candidate(request.invoice, candidate.line_items,
                                     snapshot.review_revision, self.supported_currencies)
        except UnsupportedCurrencyError as exc:
            raise invalid("invoice.currency", "Unsupported currency.") from exc


class ReviewCommandService:
    def __init__(self, repository: ReviewRepository,
                 supported_currencies: frozenset[str],
                 uuid_factory: Callable[[], UUID] = uuid4) -> None:
        if repository is None or not supported_currencies:
            raise ValueError("Repository and supported currency set are required")
        self.repository = repository
        self.supported_currencies = supported_currencies
        self.uuid_factory = uuid_factory

    async def execute(self, caller: Caller, document_id: UUID,
                      request: ReviewActionRequest, request_id: str,
                      idempotency_key: str | None) -> CommandOutcome:
        _human_reviewer(caller)
        if request.action == "reopen" and caller.role != "admin":
            raise ReviewError("FORBIDDEN")
        candidate_payload = None
        note = None
        reason = None
        if isinstance(request, (SaveReviewRequest, ApproveReviewRequest)):
            candidate_payload = CandidatePayload(invoice=request.invoice,
                                                 line_items=request.line_items)
            note = request.note
        elif isinstance(request, (RejectReviewRequest, ReopenReviewRequest)):
            reason = request.reason
        canonical_request = client_request_payload(
            request.action, request.expected_review_revision,
            candidate_payload, note, reason,
        )
        request_digest = hash_request(canonical_request)

        def prepare(snapshot: ReviewSnapshot) -> PreparedAction:
            _assert_snapshot(snapshot, caller, document_id, allow_terminal=True)
            if request.expected_review_revision != snapshot.review_revision:
                raise ReviewError("REVIEW_CONFLICT")
            allowed = permitted_actions(snapshot.status, caller.role)
            if request.action not in allowed:
                raise ReviewError("INVALID_REVIEW_TRANSITION")
            resulting_revision = snapshot.review_revision + 1
            resolved = None
            changes = ()
            validation = None
            if candidate_payload is not None:
                resolved = _resolve_candidate(candidate_payload, snapshot, self.uuid_factory)
                try:
                    validation = validate_candidate(
                        resolved, self.supported_currencies, persisted=True,
                    )
                except UnsupportedCurrencyError as exc:
                    raise invalid("invoice.currency", "Unsupported currency.") from exc
                assert snapshot.invoice is not None
                changes = build_changes(snapshot.invoice, resolved)
                if request.action == "save" and not changes:
                    raise ReviewError("NO_REVIEW_CHANGES")
                if request.action == "approve" and not validation.approval_eligible:
                    details = tuple({"field": "candidate", "issue": code}
                                    for code in validation.blocking_reasons[:20])
                    from .schemas import ErrorDetail
                    raise ReviewError("APPROVAL_BLOCKED", tuple(ErrorDetail(**item) for item in details))

            event_action = {
                "save": "field_edited",
                "approve": "approved",
                "reject": "rejected",
                "reopen": "reopened",
            }[request.action]
            to_status = {
                "save": "pending_review",
                "approve": "approved",
                "reject": "rejected",
                "reopen": "pending_review",
            }[request.action]
            return PreparedAction(
                event_id=self.uuid_factory(),
                event_action=event_action,
                from_status=snapshot.status,
                to_status=to_status,
                resulting_revision=resulting_revision,
                reason=reason,
                note=note,
                request_id=request_id,
                payload_hash=request_digest,
                candidate=resolved,
                changes=changes,
                validation=validation,
            )

        return await self.repository.execute(
            caller, document_id, idempotency_key, request_digest, prepare,
        )
