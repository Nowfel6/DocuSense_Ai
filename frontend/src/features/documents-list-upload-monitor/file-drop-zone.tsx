"use client";

import { FileUp, X } from "lucide-react";
import { useRef, useState, type DragEvent } from "react";

import { IconButton } from "@/components/ui/button";
import { formatFileSize } from "@/lib/formatting/format";

import styles from "./documents-list-upload-monitor.module.css";

export function FileDropZone({
  file,
  disabled,
  error,
  onFiles,
  onClear,
}: {
  file: File | null;
  disabled: boolean;
  error?: string;
  onFiles: (files: File[]) => void;
  onClear: () => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  function drop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    if (!disabled) onFiles(Array.from(event.dataTransfer.files));
  }

  return (
    <div className={styles.dropField}>
      <div
        className={styles.dropZone}
        data-dragging={dragging || undefined}
        onDragEnter={(event) => { event.preventDefault(); if (!disabled) setDragging(true); }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={() => setDragging(false)}
        onDrop={drop}
      >
        <FileUp aria-hidden="true" size={34} />
        <p className={styles.dropTitle}>Drop a PDF, PNG, JPG, or JPEG here</p>
        <p>One file per upload. Maximum 10 MiB.</p>
        <button type="button" className="ds-button" data-variant="secondary" disabled={disabled} onClick={() => inputRef.current?.click()}>
          {file ? "Replace file" : "Choose file"}
        </button>
        <input
          ref={inputRef}
          className={styles.visuallyHidden}
          type="file"
          accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg"
          disabled={disabled}
          aria-label="Choose document file"
          aria-describedby={error ? "upload-file-error" : undefined}
          onChange={(event) => {
            onFiles(Array.from(event.target.files ?? []));
            event.target.value = "";
          }}
        />
      </div>
      {file ? (
        <div className={styles.selectedFile}>
          <div><strong title={file.name}>{file.name}</strong><span>{formatFileSize(file.size)}</span></div>
          <IconButton label="Clear selected file" icon={<X aria-hidden="true" size={18} />} variant="subtle" disabled={disabled} onClick={onClear} />
        </div>
      ) : null}
      {error ? <p id="upload-file-error" className="ds-field-message" data-tone="error" role="alert">{error}</p> : null}
    </div>
  );
}
