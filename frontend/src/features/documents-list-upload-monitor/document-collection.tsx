"use client";

import type { Route } from "next";
import Link from "next/link";

import { StatusBadge } from "@/components/ui/feedback";
import { Pagination, TableFrame } from "@/components/ui/table";
import { formatDateTime, formatFileSize } from "@/lib/formatting/format";
import type { UserRole } from "@/lib/auth/session-types";

import type { DocumentListEnvelope, DocumentSummary } from "./types";
import styles from "./documents-list-upload-monitor.module.css";

const TYPE_LABELS = {
  commercial_invoice: "Commercial invoice",
  purchase_order: "Purchase order",
  packing_list: "Packing list",
};
const ACTIVE = new Set(["queued", "partitioning", "chunking", "vectorizing", "extracting"]);

function confidence(value: number | null) {
  return value === null ? "Not available" : `${value.toFixed(value % 1 ? 1 : 0)}%`;
}

function MonitorLink({ document }: { document: DocumentSummary }) {
  if (!ACTIVE.has(document.status)) return null;
  const href = `/documents/upload?document=${encodeURIComponent(document.document_id)}` as Route;
  return <Link className="ds-button" data-variant="subtle" href={href}>Monitor</Link>;
}

function DocumentActions({ document, canMonitor }: { document: DocumentSummary; canMonitor: boolean }) {
  return (
    <div className={styles.actionGroup}>
      <Link className="ds-button" data-variant="secondary" href={`/documents/${document.document_id}` as Route}>View details</Link>
      {canMonitor ? <MonitorLink document={document} /> : null}
    </div>
  );
}

export function DocumentCollection({
  envelope,
  role,
  onPage,
}: {
  envelope: DocumentListEnvelope;
  role: UserRole;
  onPage: (page: number) => void;
}) {
  const canMonitor = role !== "viewer";
  const { pagination } = envelope;
  const first = pagination.total_records === 0 ? 0 : (pagination.page - 1) * pagination.page_size + 1;
  const last = Math.min(pagination.total_records, pagination.page * pagination.page_size);

  return (
    <section aria-labelledby="document-results-title" className={styles.collection}>
      <h2 id="document-results-title" className={styles.resultSummary} tabIndex={-1}>
        Showing {first}–{last} of {pagination.total_records} documents.
      </h2>
      <div className={styles.desktopTable}>
        <TableFrame caption="Documents available to your organization" headers={["File name", "Uploaded", "Type", "Status", "Confidence", "Size", "Action"]}>
          {envelope.data.map((document) => (
            <tr key={document.document_id}>
              <th scope="row"><span className={styles.fileName} title={document.file_name}>{document.file_name}</span></th>
              <td>{formatDateTime(document.created_at)}</td>
              <td>{TYPE_LABELS[document.doc_type]}</td>
              <td><StatusBadge status={document.status} /></td>
              <td className={styles.numeric}>{confidence(document.overall_confidence)}</td>
              <td className={styles.numeric}>{formatFileSize(document.file_size_bytes)}</td>
              <td><DocumentActions document={document} canMonitor={canMonitor} /></td>
            </tr>
          ))}
        </TableFrame>
      </div>
      <ul className={styles.mobileCards} aria-label="Documents available to your organization">
        {envelope.data.map((document) => (
          <li key={document.document_id} className={styles.documentCard}>
            <div className={styles.cardHeading}>
              <h3 title={document.file_name}>{document.file_name}</h3>
              <StatusBadge status={document.status} />
            </div>
            <p>{TYPE_LABELS[document.doc_type]} · {formatDateTime(document.created_at)}</p>
            <dl><div><dt>Confidence</dt><dd>{confidence(document.overall_confidence)}</dd></div><div><dt>Size</dt><dd>{formatFileSize(document.file_size_bytes)}</dd></div></dl>
            <DocumentActions document={document} canMonitor={canMonitor} />
          </li>
        ))}
      </ul>
      {pagination.total_pages > 1 ? (
        <Pagination
          page={pagination.page}
          totalPages={pagination.total_pages}
          onFirst={() => onPage(1)}
          onPrevious={() => onPage(pagination.page - 1)}
          onNext={() => onPage(pagination.page + 1)}
          onLast={() => onPage(pagination.total_pages)}
        />
      ) : null}
    </section>
  );
}
