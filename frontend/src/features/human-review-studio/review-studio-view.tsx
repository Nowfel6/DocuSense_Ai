"use client";

import { ArrowLeft, Calculator, Check, RotateCcw, Save, XCircle } from "lucide-react";
import type { Route } from "next";
import { useEffect, useMemo, useRef, useState, type CSSProperties, type PointerEvent as ReactPointerEvent } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Alert, Badge, RouteState, Skeleton, StatusBadge } from "@/components/ui/feedback";
import { Dialog } from "@/components/ui/overlays";
import { PageHeader } from "@/components/ui/page-header";
import { readDocumentDetail } from "@/features/document-detail-chunk-inspector/api";
import type { DocumentDetail } from "@/features/document-detail-chunk-inspector/types";
import { ApiError, normalizeApiError } from "@/lib/api/errors";

import { AuditHistory } from "./audit-history";
import { candidateHash, draftFromInvoice, draftFromPreview, serializeDraft, validateDraft } from "./candidate";
import { InvoiceFields } from "./invoice-fields";
import { LineItemsEditor } from "./line-items-editor";
import { mutateReview, previewReview } from "./api";
import { SourceEvidencePane } from "./source-evidence-pane";
import type { CurrentPreview, MutationBody, ReviewDraft } from "./types";
import { ValidationPanel } from "./validation-panel";
import styles from "./human-review-studio.module.css";

type ReviewTab = "source" | "fields" | "items" | "validation" | "history";
type ConfirmAction = "approve" | "reject" | "reopen" | "leave";

const TABS: Array<{ id: ReviewTab; label: string }> = [
  { id: "source", label: "Source" },
  { id: "fields", label: "Fields" },
  { id: "items", label: "Items" },
  { id: "validation", label: "Validation" },
  { id: "history", label: "History" },
];

function focusError(path?: string) {
  if (!path) return;
  const invoice = path.match(/^invoice\.(.+)$/)?.[1];
  if (invoice) document.getElementById(`review-invoice-${invoice}`)?.focus();
  const line = path.match(/^line_items\.([^.]+)\.(.+)$/);
  if (line) document.getElementById(`review-line-${line[1]}-${line[2].replace("hs_code", "hs")}`)?.focus();
}

function applyMutation(detail: DocumentDetail, data: Awaited<ReturnType<typeof mutateReview>>["data"]): DocumentDetail {
  return {
    ...detail,
    status: data.status,
    review_revision: data.review_revision,
    invoice: data.invoice,
    latest_review_validation: data.latest_review_validation,
    permitted_actions: data.permitted_actions,
  };
}

export function HumanReviewStudio({ documentId }: { documentId: string }) {
  const router = useRouter();
  const [detail, setDetail] = useState<DocumentDetail>();
  const [draft, setDraft] = useState<ReviewDraft>();
  const [baselineHash, setBaselineHash] = useState("");
  const [preview, setPreview] = useState<CurrentPreview>();
  const [activeTab, setActiveTab] = useState<ReviewTab>("fields");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError>();
  const [actionError, setActionError] = useState<ApiError>();
  const [pending, setPending] = useState<"preview" | "save" | "approve" | "reject" | "reopen">();
  const [confirmAction, setConfirmAction] = useState<ConfirmAction>();
  const [reason, setReason] = useState("");
  const [announcement, setAnnouncement] = useState("");
  const [conflict, setConflict] = useState(false);
  const [sourceBlocked, setSourceBlocked] = useState(false);
  const [sourceRefreshing, setSourceRefreshing] = useState(false);
  const [auditRefresh, setAuditRefresh] = useState(0);
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const [retryIntent, setRetryIntent] = useState<{ signature: string; key: string }>();
  const [split, setSplit] = useState(40);
  const previewController = useRef<AbortController | undefined>(undefined);
  const previewSequence = useRef(0);
  const draftVersion = useRef(0);
  const leaveTarget = useRef("/documents");

  const hash = useMemo(() => draft ? candidateHash(draft) : "", [draft]);
  const dirty = Boolean(draft && baselineHash && hash !== baselineHash);
  const localValidation = useMemo(() => draft ? validateDraft(draft) : { errors: {} }, [draft]);
  const previewStale = Boolean(preview && preview.candidateHash !== hash);
  const previewEligible = Boolean(preview && !previewStale && preview.data.validation.approval_eligible);
  const readOnly = detail?.status !== "pending_review";
  const anyPending = Boolean(pending);

  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      setLoading(true);
      setError(undefined);
      try {
        const response = await readDocumentDetail(documentId, controller.signal);
        const next = response.data;
        setDetail(next);
        if (next.invoice && next.review_revision !== null) {
          const nextDraft = draftFromInvoice(next.invoice, next.review_revision);
          setDraft(nextDraft);
          setBaselineHash(candidateHash(nextDraft));
        }
      } catch (cause) {
        const next = normalizeApiError(cause);
        if (next.code !== "REQUEST_ABORTED") setError(next);
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }
    void load();
    return () => controller.abort();
  }, [documentId]);

  useEffect(() => {
    if (!dirty) return;
    const guard = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", guard);
    return () => window.removeEventListener("beforeunload", guard);
  }, [dirty]);

  useEffect(() => {
    if (!dirty) return;
    const guardLinks = (event: MouseEvent) => {
      if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      const anchor = (event.target as Element | null)?.closest("a");
      if (!anchor || anchor.target || anchor.hasAttribute("download")) return;
      const target = new URL(anchor.href, window.location.href);
      if (target.origin !== window.location.origin || target.href === window.location.href) return;
      event.preventDefault();
      leaveTarget.current = `${target.pathname}${target.search}${target.hash}`;
      setConfirmAction("leave");
    };
    document.addEventListener("click", guardLinks, true);
    return () => document.removeEventListener("click", guardLinks, true);
  }, [dirty]);

  function updateDraft(next: ReviewDraft) {
    draftVersion.current += 1;
    if (pending === "preview") {
      previewController.current?.abort();
      previewSequence.current += 1;
      setPending(undefined);
    }
    setDraft(next);
    setActionError(undefined);
    setAnnouncement(preview ? "Validation preview is now out of date." : "");
    setRetryIntent(undefined);
  }

  async function recalculate() {
    if (!draft || anyPending || conflict) return;
    if (Object.keys(localValidation.errors).length) {
      setActionError(new ApiError("Correct the highlighted fields before recalculating.", { code: "LOCAL_VALIDATION" }));
      focusError(localValidation.firstPath);
      return;
    }
    previewController.current?.abort();
    const controller = new AbortController();
    previewController.current = controller;
    const sequence = ++previewSequence.current;
    const submittedVersion = draftVersion.current;
    setPending("preview");
    setActionError(undefined);
    try {
      const response = await previewReview(documentId, serializeDraft(draft), controller.signal);
      if (sequence !== previewSequence.current || draftVersion.current !== submittedVersion) return;
      const normalizedDraft = draftFromPreview(draft, response.data);
      const normalizedHash = candidateHash(normalizedDraft);
      setDraft(normalizedDraft);
      setPreview({ data: response.data, candidateHash: normalizedHash, receivedAt: Date.now() });
      setAnnouncement(response.data.validation.approval_eligible ? "Validation complete. This candidate is eligible for approval." : "Validation complete. Approval blockers remain.");
      setActiveTab("validation");
    } catch (cause) {
      const next = normalizeApiError(cause);
      if (next.code === "REVIEW_CONFLICT") setConflict(true);
      if (next.code !== "REQUEST_ABORTED") setActionError(next);
    } finally {
      if (sequence === previewSequence.current) setPending(undefined);
    }
  }

  function mutationBody(action: "save" | "approve" | "reject" | "reopen"): MutationBody | null {
    if (!draft) return null;
    if (action === "reject" || action === "reopen") return { action, expected_review_revision: draft.expected_review_revision, reason: reason.trim() };
    return { ...serializeDraft(draft), action, note: action === "approve" ? reason.trim() || null : null };
  }

  async function runMutation(action: "save" | "approve" | "reject" | "reopen", retry = false) {
    if (!draft || !detail || anyPending || conflict) return;
    if ((action === "reject" || action === "reopen") && (!reason.trim() || reason.trim().length > 1000)) {
      setActionError(new ApiError("Enter a reason between 1 and 1,000 characters.", { code: "LOCAL_VALIDATION" }));
      return;
    }
    if ((action === "save" || action === "approve") && Object.keys(localValidation.errors).length) {
      setActionError(new ApiError("Correct the highlighted fields before continuing.", { code: "LOCAL_VALIDATION" }));
      focusError(localValidation.firstPath);
      return;
    }
    const body = mutationBody(action);
    if (!body) return;
    const signature = JSON.stringify(body);
    const key = retry && retryIntent?.signature === signature ? retryIntent.key : crypto.randomUUID();
    setRetryIntent({ signature, key });
    setPending(action);
    setActionError(undefined);
    try {
      const response = await mutateReview(documentId, body, key);
      const nextDetail = applyMutation(detail, response.data);
      const nextDraft = draftFromInvoice(response.data.invoice, response.data.review_revision);
      setDetail(nextDetail);
      setDraft(nextDraft);
      setBaselineHash(candidateHash(nextDraft));
      setPreview(undefined);
      setConflict(false);
      setConfirmAction(undefined);
      setReason("");
      setAuditRefresh((value) => value + 1);
      setAnnouncement(action === "save" ? "Review draft saved." : `Document ${response.data.status.replaceAll("_", " ")}.`);
      setRetryIntent(undefined);
    } catch (cause) {
      const next = normalizeApiError(cause);
      if (next.code === "REVIEW_CONFLICT") setConflict(true);
      if (next.code === "IDEMPOTENCY_KEY_REUSED") setRetryIntent(undefined);
      setActionError(next);
    } finally {
      setPending(undefined);
    }
  }

  async function reloadLatest(forceDiscard = false) {
    if (dirty && !forceDiscard && !window.confirm("Discard your local review draft and load the latest server revision?")) return;
    setLoading(true);
    setActionError(undefined);
    try {
      const response = await readDocumentDetail(documentId);
      const next = response.data;
      if (!next.invoice || next.review_revision === null) throw new ApiError("This document no longer has reviewable data.", { code: "NOT_REVIEWABLE" });
      const nextDraft = draftFromInvoice(next.invoice, next.review_revision);
      setDetail(next);
      setDraft(nextDraft);
      setBaselineHash(candidateHash(nextDraft));
      setPreview(undefined);
      setConflict(false);
      setSourceBlocked(false);
      setAnnouncement("Latest server revision loaded.");
    } catch (cause) {
      setActionError(normalizeApiError(cause));
    } finally {
      setLoading(false);
    }
  }

  async function refreshSource() {
    if (!detail || sourceRefreshing) return;
    setSourceBlocked(true);
    setSourceRefreshing(true);
    try {
      const response = await readDocumentDetail(documentId);
      if (response.data.review_revision !== detail.review_revision) {
        setConflict(true);
        setActionError(new ApiError("A newer review revision is available. Your local draft is preserved.", { code: "REVIEW_CONFLICT" }));
      } else {
        setDetail((current) => current ? { ...current, source_view: response.data.source_view, field_evidence: response.data.field_evidence } : current);
        setSourceBlocked(false);
        setAnnouncement("Source link refreshed.");
      }
    } catch (cause) {
      setActionError(normalizeApiError(cause));
    } finally {
      setSourceRefreshing(false);
    }
  }

  function requestLeave(target = "/documents") {
    if (!dirty) { router.push(target as Route); return; }
    leaveTarget.current = target;
    setConfirmAction("leave");
  }

  function resizeFromPointer(event: ReactPointerEvent<HTMLDivElement>) {
    const track = event.currentTarget.parentElement;
    if (!track) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    const bounds = track.getBoundingClientRect();
    const move = (pointer: PointerEvent) => setSplit(Math.min(55, Math.max(32, ((pointer.clientX - bounds.left) / bounds.width) * 100)));
    const done = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", done); };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", done);
  }

  if (loading && !detail) return <div className={styles.pageStack} aria-label="Loading review studio"><Skeleton shape="text" width="45%" /><Skeleton shape="panel" height="34rem" /></div>;
  if (!detail || !draft) {
    const unavailable = error?.status === 403 || error?.status === 404;
    return <RouteState kind={unavailable ? "not-found" : "error"} title={unavailable ? "Review unavailable" : "Review couldn’t be loaded"} message={unavailable ? "This review is unavailable or you do not have access." : "Try again from the document page."} requestId={error?.requestId} actionLabel="Back to documents" href="/documents" />;
  }

  const can = (action: "save" | "approve" | "reject" | "reopen") => detail.permitted_actions.includes(action);
  const retryable = actionError?.code === "NETWORK_ERROR" && retryIntent;

  return (
    <div className={styles.pageStack}>
      <PageHeader
        title={detail.file_name}
        description={`Human review · revision ${detail.review_revision ?? "unavailable"}`}
        actions={<><StatusBadge status={detail.status} />{dirty ? <Badge tone="warning">Unsaved changes</Badge> : <Badge>Saved</Badge>}<Button variant="subtle" onClick={() => requestLeave(`/documents/${documentId}`)}><ArrowLeft aria-hidden="true" size={16} /> Back to document</Button></>}
      />
      {readOnly ? <Alert tone="info" title="Read-only review" message="This terminal review can be inspected with its validation and audit history. Only a returned reopen action can make it editable." /> : null}
      {conflict ? <Alert tone="warning" title="A newer revision is available" message="Your local draft is preserved. Reload latest only when you are ready to discard it." action={<Button onClick={() => void reloadLatest()}>Reload latest</Button>} /> : null}
      {actionError ? <Alert tone="error" title={actionError.code === "LOCAL_VALIDATION" ? "Check the review" : "The action couldn’t be completed"} message={`${actionError.message}${actionError.requestId ? ` Request ID: ${actionError.requestId}` : ""}`} action={retryable && pending === undefined ? <Button onClick={() => void runMutation((JSON.parse(retryIntent.signature) as MutationBody).action as "save" | "approve" | "reject" | "reopen", true)}>Retry same request</Button> : undefined} /> : null}
      <p className={styles.visuallyHidden} aria-live="polite">{announcement}</p>

      <div className={styles.tabs} role="tablist" aria-label="Review sections">
        {TABS.map((tab) => <button key={tab.id} type="button" role="tab" aria-selected={activeTab === tab.id} aria-controls={`review-panel-${tab.id}`} className={styles.tab} data-selected={activeTab === tab.id || undefined} onClick={() => { setActiveTab(tab.id); if (tab.id === "history") setHistoryLoaded(true); }}>{tab.label}</button>)}
      </div>

      <div className={styles.workspace} style={{ "--review-source-percent": `${split}%` } as CSSProperties}>
        <div id="review-panel-source" role="tabpanel" aria-label="Source and evidence" className={styles.sourceRegion} data-mobile-active={activeTab === "source" || undefined}>
          <SourceEvidencePane detail={detail} sourceBlocked={sourceBlocked} sourceRefreshing={sourceRefreshing} onRefreshSource={() => void refreshSource()} />
        </div>
        <div
          className={styles.separator}
          role="separator"
          aria-label="Resize source and review panes"
          aria-orientation="vertical"
          aria-valuemin={32}
          aria-valuemax={55}
          aria-valuenow={Math.round(split)}
          tabIndex={0}
          onDoubleClick={() => setSplit(40)}
          onPointerDown={resizeFromPointer}
          onKeyDown={(event) => {
            const step = event.shiftKey ? 8 : 2;
            if (event.key === "ArrowLeft") setSplit((value) => Math.max(32, value - step));
            else if (event.key === "ArrowRight") setSplit((value) => Math.min(55, value + step));
            else if (event.key === "Home") setSplit(32);
            else if (event.key === "End") setSplit(55);
            else return;
            event.preventDefault();
          }}
        />
        <div className={styles.reviewRegion} data-mobile-active={activeTab !== "source" || undefined}>
          <div id="review-panel-fields" role="tabpanel" hidden={activeTab !== "fields"}><InvoiceFields value={draft.invoice} errors={localValidation.errors} readOnly={readOnly} onChange={(invoice) => updateDraft({ ...draft, invoice })} /></div>
          <div id="review-panel-items" role="tabpanel" hidden={activeTab !== "items"}><LineItemsEditor value={draft.line_items} errors={localValidation.errors} readOnly={readOnly} onChange={(line_items) => updateDraft({ ...draft, line_items })} onAnnounce={setAnnouncement} /></div>
          <div id="review-panel-validation" role="tabpanel" hidden={activeTab !== "validation"}><ValidationPanel preview={preview} stale={previewStale} /></div>
          <div id="review-panel-history" role="tabpanel" hidden={activeTab !== "history"}>{historyLoaded ? <AuditHistory documentId={documentId} refreshToken={auditRefresh} /> : null}</div>
        </div>
      </div>

      <div className={styles.actionBar} aria-label="Review actions">
        {!readOnly && can("save") ? <Button variant="secondary" disabled={!dirty || anyPending || conflict} isPending={pending === "save"} onClick={() => void runMutation("save")}><Save aria-hidden="true" size={16} /> Save draft</Button> : null}
        {!readOnly ? <Button variant="secondary" disabled={anyPending || conflict} isPending={pending === "preview"} pendingLabel="Recalculating…" onClick={() => void recalculate()}><Calculator aria-hidden="true" size={16} /> Recalculate</Button> : null}
        {!readOnly && can("reject") ? <Button variant="destructive" disabled={anyPending || conflict} onClick={() => { setReason(""); setConfirmAction("reject"); }}><XCircle aria-hidden="true" size={16} /> Reject</Button> : null}
        {!readOnly && can("approve") ? <Button variant="primary" disabled={!previewEligible || anyPending || conflict} title={!previewEligible ? "Run an eligible, current validation preview first." : undefined} onClick={() => { setReason(""); setConfirmAction("approve"); }}><Check aria-hidden="true" size={16} /> Confirm & approve</Button> : null}
        {readOnly && can("reopen") ? <Button variant="primary" disabled={anyPending} onClick={() => { setReason(""); setConfirmAction("reopen"); }}><RotateCcw aria-hidden="true" size={16} /> Reopen review</Button> : null}
      </div>

      <Dialog
        open={Boolean(confirmAction)}
        title={confirmAction === "approve" ? "Approve this document?" : confirmAction === "reject" ? "Reject this document?" : confirmAction === "reopen" ? "Reopen this review?" : "Discard unsaved changes?"}
        description={confirmAction === "reject" ? "Unsaved field edits are not included in rejection." : confirmAction === "leave" ? "Your local changes will be lost." : "The server will verify the current revision before applying this action."}
        confirmLabel={confirmAction === "leave" ? "Discard and leave" : confirmAction ? `${confirmAction[0].toUpperCase()}${confirmAction.slice(1)}` : undefined}
        pending={Boolean(pending)}
        initialFocus="cancel"
        error={actionError?.code === "LOCAL_VALIDATION" ? actionError.message : undefined}
        onClose={() => { if (!pending) { setConfirmAction(undefined); setReason(""); } }}
        onConfirm={() => {
          if (confirmAction === "leave") { setBaselineHash(hash); router.push(leaveTarget.current as Route); }
          else if (confirmAction) void runMutation(confirmAction);
        }}
      >
        {confirmAction && confirmAction !== "leave" ? (
          <div className="ds-field"><label className="ds-label" htmlFor="review-action-reason">{confirmAction === "approve" ? "Approval note (optional)" : "Reason"}</label><textarea id="review-action-reason" className="ds-input" rows={4} maxLength={1000} value={reason} onChange={(event) => setReason(event.currentTarget.value)} /></div>
        ) : null}
      </Dialog>
    </div>
  );
}
