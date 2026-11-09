"use client";

import Link from "next/link";
import { useRef, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Alert } from "@/components/ui/feedback";
import { SelectField } from "@/components/ui/fields";
import { Dialog } from "@/components/ui/overlays";
import { normalizeApiError } from "@/lib/api/errors";

import { DOCUMENT_TYPE_OPTIONS, validateDocumentFile } from "./capabilities";
import { FileDropZone } from "./file-drop-zone";
import type { DocumentType, UploadAccepted } from "./types";
import { uploadDocument, type UploadProgress } from "./upload-transport";
import styles from "./documents-list-upload-monitor.module.css";

export function UploadComposer({ onAccepted }: { onAccepted: (accepted: UploadAccepted) => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [documentType, setDocumentType] = useState<DocumentType>("commercial_invoice");
  const [fileError, setFileError] = useState<string>();
  const [formError, setFormError] = useState<string>();
  const [requestId, setRequestId] = useState<string>();
  const [progress, setProgress] = useState<UploadProgress>();
  const [duplicateOpen, setDuplicateOpen] = useState(false);
  const [duplicateError, setDuplicateError] = useState<string>();
  const [canceled, setCanceled] = useState(false);
  const controllerRef = useRef<AbortController | undefined>(undefined);
  const uploadButtonRef = useRef<HTMLButtonElement>(null);
  const pending = Boolean(progress);

  function choose(files: File[]) {
    setCanceled(false);
    setFormError(undefined);
    if (files.length !== 1) {
      setFileError("Choose one file at a time.");
      return;
    }
    const error = validateDocumentFile(files[0]);
    setFile(files[0]);
    setFileError(error ?? undefined);
  }

  async function submit(confirmDuplicate: boolean) {
    if (pending) return;
    const validation = validateDocumentFile(file);
    if (validation || !file) {
      setFileError(validation ?? undefined);
      return;
    }

    const controller = new AbortController();
    controllerRef.current = controller;
    setFormError(undefined);
    setDuplicateError(undefined);
    setRequestId(undefined);
    setCanceled(false);
    setProgress({ phase: "transferring" });
    try {
      const accepted = await uploadDocument({ file, documentType, confirmDuplicate, signal: controller.signal, onProgress: setProgress });
      setFile(null);
      setDuplicateOpen(false);
      onAccepted(accepted);
    } catch (cause) {
      const error = normalizeApiError(cause);
      if (error.code === "REQUEST_ABORTED") {
        setCanceled(true);
      } else if (error.code === "DUPLICATE_FILE_DETECTED" && !confirmDuplicate) {
        setDuplicateOpen(true);
      } else {
        const message = error.status === 413 ? "Choose a file no larger than 10 MiB."
          : error.status === 415 ? "The server did not accept this file type. Choose a PDF, PNG, JPG, or JPEG."
          : error.status === 429 ? "Uploads are temporarily limited. Wait, then try again."
          : error.status === 422 ? "The server could not validate this document. Check the file and document type."
          : "The document could not be uploaded. Check Documents before trying again.";
        if (confirmDuplicate) setDuplicateError(message); else setFormError(message);
        setRequestId(error.requestId);
      }
    } finally {
      controllerRef.current = undefined;
      setProgress(undefined);
    }
  }

  return (
    <section className={styles.uploadPanel} aria-labelledby="upload-composer-title">
      <h2 id="upload-composer-title" className={styles.sectionTitle}>Select a document</h2>
      <form className={styles.uploadGrid} onSubmit={(event: FormEvent) => { event.preventDefault(); void submit(false); }}>
        <FileDropZone file={file} disabled={pending} error={fileError} onFiles={choose} onClear={() => { setFile(null); setFileError(undefined); }} />
        <div className={styles.uploadControls}>
          <SelectField label="Document type" value={documentType} disabled={pending} onChange={(event) => setDocumentType(event.target.value as DocumentType)}>
            {DOCUMENT_TYPE_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </SelectField>
          <p className={styles.constraint}>The backend verifies document contents, safety, and duplicates.</p>
          {progress ? (
            <div className={styles.transferStatus} role="status">
              <strong>{progress.phase === "accepting" ? "Accepting document…" : "Uploading document…"}</strong>
              {progress.phase === "transferring" && progress.percentage !== undefined
                ? <><progress max="100" value={progress.percentage}>{progress.percentage}%</progress><span>{progress.percentage}% transferred to DocuSense</span></>
                : <span>{progress.phase === "accepting" ? "Transfer complete. Waiting for the server to accept it." : "Transferring to DocuSense."}</span>}
            </div>
          ) : null}
          {formError ? <Alert tone="error" title="Upload couldn’t be completed" message={`${formError}${requestId ? ` Request ID: ${requestId}` : ""}`} /> : null}
          {canceled ? <Alert tone="warning" title="Upload stopped in this browser" message="The server may still have accepted the file. Check Documents before trying again." /> : null}
          <div className={styles.actionStack}>
            <Button ref={uploadButtonRef} type="submit" variant="primary" isPending={pending} pendingLabel={progress?.phase === "accepting" ? "Accepting document…" : "Uploading document…"}>Upload document</Button>
            {pending ? <Button variant="destructive" onClick={() => controllerRef.current?.abort()}>Cancel upload</Button> : null}
            <Link className="ds-button" data-variant="subtle" href="/documents">Back to documents</Link>
          </div>
        </div>
      </form>
      <Dialog
        open={duplicateOpen}
        title="Upload matching file?"
        description="A matching file already exists in this workspace. Upload another copy?"
        confirmLabel="Upload another copy"
        cancelLabel="Cancel"
        pending={pending}
        error={duplicateError}
        initialFocus="cancel"
        returnFocusRef={uploadButtonRef}
        onConfirm={() => void submit(true)}
        onClose={() => { if (!pending) { setDuplicateOpen(false); setDuplicateError(undefined); } }}
      />
      <p className={styles.visuallyHidden} aria-live="polite">
        {progress?.phase === "accepting" ? "File transfer complete. Document acceptance is pending." : canceled ? "Upload stopped in this browser." : ""}
      </p>
    </section>
  );
}
