"use client";

import type { Route } from "next";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Alert, EmptyState } from "@/components/ui/feedback";
import { PageHeader } from "@/components/ui/page-header";
import { TableFrame } from "@/components/ui/table";
import { ApiError, normalizeApiError } from "@/lib/api/errors";
import type { UserRole } from "@/lib/auth/session-types";

import { listDocuments } from "./api";
import { DocumentCollection } from "./document-collection";
import { DocumentFilterForm } from "./document-filter-form";
import { documentQueryWithPage, normalizeDocumentQuery, serializeDocumentQuery } from "./list-query";
import type { DocumentListEnvelope, DocumentListQuery } from "./types";
import styles from "./documents-list-upload-monitor.module.css";

function documentsHref(search: string): Route {
  return `/documents${search ? `?${search}` : ""}` as Route;
}

export function DocumentsView({ role }: { role: UserRole }) {
  const viewer = role === "viewer";
  const router = useRouter();
  const searchParams = useSearchParams();
  const sourceQuery = searchParams.toString();
  const normalized = useMemo(() => normalizeDocumentQuery(sourceQuery, viewer), [sourceQuery, viewer]);
  const [envelope, setEnvelope] = useState<DocumentListEnvelope>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError>();
  const [retryKey, setRetryKey] = useState(0);

  useEffect(() => {
    if (normalized.canonical !== sourceQuery) router.replace(documentsHref(normalized.canonical));
  }, [normalized.canonical, router, sourceQuery]);

  useEffect(() => {
    const controller = new AbortController();
    void Promise.resolve().then(() => {
      if (controller.signal.aborted) return;
      setLoading(true);
      setError(undefined);
      return listDocuments(normalized.query, controller.signal);
    }).then((next) => {
      if (!next) return;
      if (next.pagination.total_pages > 0 && normalized.query.page > next.pagination.total_pages) {
        router.replace(documentsHref(documentQueryWithPage(normalized.query, next.pagination.total_pages)));
        return;
      }
      if (next.pagination.total_pages === 0 && normalized.query.page !== 1) {
        router.replace(documentsHref(documentQueryWithPage(normalized.query, 1)));
      }
      setEnvelope(next);
    }).catch((cause) => {
      const nextError = normalizeApiError(cause);
      if (nextError.code !== "REQUEST_ABORTED") setError(nextError);
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false);
    });
    return () => controller.abort();
  }, [normalized.query, retryKey, router]);

  function apply(query: DocumentListQuery) {
    router.push(documentsHref(serializeDocumentQuery(query)));
  }

  const hasFilters = Boolean(normalized.query.status || normalized.query.documentType || normalized.query.fromDate || normalized.query.toDate);
  const noRows = !loading && envelope?.data.length === 0;

  return (
    <div className={styles.pageStack}>
      <PageHeader
        title="Documents"
        description="Browse documents available to your organization."
        actions={!viewer ? <Link className="ds-button" data-variant="primary" href="/documents/upload">Upload document</Link> : null}
      />
      {viewer ? <Alert title="Showing approved documents available to your role." /> : null}
      {normalized.reset ? <Alert tone="warning" title="Some filters were reset" message="Unsupported or invalid filter values were removed." /> : null}
      <DocumentFilterForm key={normalized.canonical} query={normalized.query} viewer={viewer} onApply={apply} onClear={() => router.push("/documents")} />
      {error ? (
        <Alert
          tone="error"
          title="Documents couldn’t be loaded"
          message={`Try again. If the problem continues, share the request ID with support.${error.requestId ? ` Request ID: ${error.requestId}` : ""}`}
          action={<Button onClick={() => setRetryKey((value) => value + 1)}>Try again</Button>}
        />
      ) : null}
      {loading && !envelope ? (
        <TableFrame caption="Loading documents" headers={["File name", "Uploaded", "Type", "Status", "Confidence", "Size", "Action"]} state="loading"><></></TableFrame>
      ) : null}
      {loading && envelope ? <Alert title="Refreshing documents" message="Showing the previous results while the latest page loads." /> : null}
      {noRows ? (
        <EmptyState
          title={hasFilters ? "No documents match these filters" : viewer ? "No approved documents" : "No documents yet"}
          message={hasFilters ? "Try changing or clearing the current filters." : viewer ? "Approved documents will appear here when available." : "Upload a document to start processing."}
          action={hasFilters
            ? <Button onClick={() => router.push("/documents")}>Clear filters</Button>
            : !viewer ? <Link className="ds-button" data-variant="primary" href="/documents/upload">Upload document</Link> : undefined}
        />
      ) : envelope && envelope.data.length ? (
        <DocumentCollection envelope={envelope} role={role} onPage={(page) => router.push(documentsHref(documentQueryWithPage(normalized.query, page)))} />
      ) : null}
    </div>
  );
}
