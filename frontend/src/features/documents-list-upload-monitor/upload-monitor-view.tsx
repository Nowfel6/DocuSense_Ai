"use client";

import type { Route } from "next";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { RouteState } from "@/components/ui/feedback";
import { PageHeader } from "@/components/ui/page-header";

import { UUID_PATTERN } from "./api";
import { ProcessingMonitor } from "./processing-monitor";
import type { UploadAccepted } from "./types";
import { UploadComposer } from "./upload-composer";
import styles from "./documents-list-upload-monitor.module.css";

export function UploadMonitorView() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const documentValues = searchParams.getAll("document");
  const candidate = documentValues.length === 1 ? documentValues[0] : undefined;
  const invalidDocument = documentValues.length > 0 && (!candidate || !UUID_PATTERN.test(candidate));
  const documentId = candidate && UUID_PATTERN.test(candidate) ? candidate : undefined;
  const [accepted, setAccepted] = useState<UploadAccepted>();

  useEffect(() => {
    if ([...searchParams.keys()].some((key) => key !== "document")) {
      router.replace((documentId ? `/documents/upload?document=${encodeURIComponent(documentId)}` : "/documents/upload") as Route);
    }
  }, [documentId, router, searchParams]);

  if (invalidDocument) {
    return <RouteState kind="error" title="Invalid monitor link" message="This processing link is not valid. No status request was sent." actionLabel="Start a new upload" href="/documents/upload" />;
  }

  return (
    <div className={styles.pageStack}>
      <PageHeader title="Upload document" description="Add one supported document and monitor its processing status." />
      {documentId ? (
        <ProcessingMonitor documentId={documentId} accepted={accepted?.document_id === documentId ? accepted : undefined} onUploadAnother={() => { setAccepted(undefined); router.replace("/documents/upload"); }} />
      ) : (
        <UploadComposer onAccepted={(next) => { setAccepted(next); router.replace(`/documents/upload?document=${encodeURIComponent(next.document_id)}` as Route); }} />
      )}
    </div>
  );
}
