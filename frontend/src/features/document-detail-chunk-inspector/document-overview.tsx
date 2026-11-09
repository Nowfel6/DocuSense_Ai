import { Alert, Badge, StatusBadge } from "@/components/ui/feedback";
import { ProcessingStageRail } from "@/features/documents-list-upload-monitor/processing-stage-rail";
import type { DocumentProgress } from "@/features/documents-list-upload-monitor/types";
import { formatDateTime, formatFileSize } from "@/lib/formatting/format";
import type { ApiError } from "@/lib/api/errors";

import { LineItemSummary } from "./line-item-summary";
import type { DocumentDetail, ReviewInvoice, ValidationSummary } from "./types";
import styles from "./document-detail-chunk-inspector.module.css";

const TYPE_LABELS = {
  commercial_invoice: "Commercial invoice",
  purchase_order: "Purchase order",
  packing_list: "Packing list",
};

function display(value: string | null | undefined) {
  return value === null || value === undefined || value === "" ? "Not available" : value;
}

function money(value: string | null, currency: string | null) {
  return value === null ? "Not available" : `${currency ? `${currency} ` : ""}${value}`;
}

function ValidationCounts({ summary }: { summary: ValidationSummary }) {
  return (
    <dl className={styles.metricGrid}>
      <div><dt>Passed</dt><dd>{summary.passed}</dd></div>
      <div><dt>Failed</dt><dd>{summary.failed}</dd></div>
      <div><dt>Missing</dt><dd>{summary.missing}</dd></div>
      <div><dt>Not applicable</dt><dd>{summary.not_applicable}</dd></div>
    </dl>
  );
}

function ExtractionSummary({ invoice }: { invoice: ReviewInvoice }) {
  return (
    <section className={styles.surfaceSection} aria-labelledby="extraction-title">
      <div className={styles.sectionHeading}>
        <div><h2 id="extraction-title">Extraction summary</h2><p>Read-only values returned by the completed extraction.</p></div>
        <Badge tone={invoice.is_math_valid ? "success" : "warning"}>{invoice.is_math_valid ? "Math valid" : "Math check failed"}</Badge>
      </div>
      <dl className={styles.detailGrid}>
        <div><dt>Supplier</dt><dd>{display(invoice.supplier_name)}</dd></div>
        <div><dt>Invoice number</dt><dd>{display(invoice.invoice_number)}</dd></div>
        <div><dt>Supplier tax ID</dt><dd>{display(invoice.supplier_tax_id)}</dd></div>
        <div><dt>Buyer</dt><dd>{display(invoice.buyer_name)}</dd></div>
        <div><dt>Date issued</dt><dd>{display(invoice.date_issued)}</dd></div>
        <div><dt>Due date</dt><dd>{display(invoice.due_date)}</dd></div>
        <div><dt>Subtotal</dt><dd>{money(invoice.subtotal, invoice.currency)}</dd></div>
        <div><dt>Tax</dt><dd>{money(invoice.tax_amount, invoice.currency)}</dd></div>
        <div><dt>Discount</dt><dd>{money(invoice.discount_amount, invoice.currency)}</dd></div>
        <div><dt>Grand total</dt><dd>{money(invoice.grand_total, invoice.currency)}</dd></div>
      </dl>
    </section>
  );
}

export function DocumentOverview({
  detail,
  progress,
  statusError,
  statusStale,
  statusPaused,
  onRefreshStatus,
}: {
  detail: DocumentDetail;
  progress?: DocumentProgress;
  statusError?: ApiError;
  statusStale: boolean;
  statusPaused: boolean;
  onRefreshStatus: () => void;
}) {
  const validation = detail.extraction_validation ?? detail.latest_review_validation?.summary ?? null;

  return (
    <div className={styles.overviewGrid}>
      <section className={`${styles.surfaceSection} ${styles.fileFacts}`} aria-labelledby="file-details-title">
        <h2 id="file-details-title">File details</h2>
        <dl className={styles.detailGrid}>
          <div><dt>Document type</dt><dd>{TYPE_LABELS[detail.doc_type]}</dd></div>
          <div><dt>MIME type</dt><dd>{detail.mime_type}</dd></div>
          <div><dt>File size</dt><dd>{formatFileSize(detail.file_size_bytes)}</dd></div>
          <div><dt>Pages</dt><dd>{detail.source_view.page_count ?? "Not available"}</dd></div>
          <div><dt>Uploaded</dt><dd>{formatDateTime(detail.created_at)}</dd></div>
          <div><dt>Last updated</dt><dd>{formatDateTime(detail.updated_at)}</dd></div>
          <div><dt>Document ID</dt><dd className={styles.identifier}>{detail.document_id}</dd></div>
          <div><dt>Job ID</dt><dd className={styles.identifier}>{detail.job_id}</dd></div>
        </dl>
      </section>

      <section className={`${styles.surfaceSection} ${styles.reviewFacts}`} aria-labelledby="review-state-title">
        <h2 id="review-state-title">Review state</h2>
        <StatusBadge status={detail.status} />
        <p>Review editing and approval will be available in the Review Studio.</p>
        <p className={styles.muted}>Review actions returned by the API are intentionally not enabled in this read-only feature.</p>
      </section>

      <section className={`${styles.surfaceSection} ${styles.processingSection}`} aria-labelledby="processing-title">
        <div className={styles.sectionHeading}>
          <div><h2 id="processing-title">Current processing state</h2><p>Persisted backend state, not an estimated timeline.</p></div>
          {progress ? <Badge tone={progress.job_status === "failed" ? "danger" : progress.job_status === "completed" ? "success" : "technical"}>{progress.job_status.replaceAll("_", " ")}</Badge> : null}
        </div>
        {progress ? (
          <>
            <div className={styles.persistedProgress}>
              <span>{progress.progress_percentage}% persisted progress</span>
              <progress max="100" value={progress.progress_percentage}>{progress.progress_percentage}%</progress>
            </div>
            <ProcessingStageRail stages={progress.stages} />
            {progress.error ? <Alert tone="error" title="Processing failed" message={progress.error.message} /> : null}
          </>
        ) : <p className={styles.unavailable}>Current processing state is not available.</p>}
        {statusPaused ? <Alert tone="warning" title="Status updates paused" message="Updates resume when this page is visible and online." /> : null}
        {statusStale ? <Alert tone="warning" title="Processing status may be out of date" message="The last validated status remains visible while DocuSense retries." /> : null}
        {statusError && !statusStale ? (
          <Alert tone="error" title="Processing status couldn’t be loaded" message={`The document details remain available.${statusError.requestId ? ` Request ID: ${statusError.requestId}` : ""}`} action={<button type="button" className="ds-button" data-variant="secondary" onClick={onRefreshStatus}>Refresh status</button>} />
        ) : null}
      </section>

      {detail.invoice ? <ExtractionSummary invoice={detail.invoice} /> : (
        <section className={styles.surfaceSection} aria-labelledby="extraction-title">
          <h2 id="extraction-title">{detail.doc_type === "commercial_invoice" ? "Extraction not available yet" : "Structured invoice data does not apply"}</h2>
          <p>{detail.doc_type === "commercial_invoice" ? "Extraction details will appear after processing completes." : "This document type does not use the commercial-invoice summary."}</p>
        </section>
      )}

      <section className={styles.surfaceSection} aria-labelledby="validation-title">
        <h2 id="validation-title">Validation summary</h2>
        <div className={styles.overallConfidence}>
          <span>Overall document confidence</span>
          <strong>{detail.overall_confidence === null ? "Not available" : `${detail.overall_confidence}%`}</strong>
        </div>
        {validation ? <ValidationCounts summary={validation} /> : <p className={styles.unavailable}>Validation results are not available yet.</p>}
      </section>

      {detail.invoice ? <div className={styles.lineItemsRegion}><LineItemSummary items={detail.invoice.line_items} currency={detail.invoice.currency} /></div> : null}
    </div>
  );
}

