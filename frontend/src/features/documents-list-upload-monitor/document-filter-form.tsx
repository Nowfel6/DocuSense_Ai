"use client";

import { useRef, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { SelectField, TextField } from "@/components/ui/fields";

import { DOCUMENT_TYPE_OPTIONS } from "./capabilities";
import { DEFAULT_DOCUMENT_QUERY } from "./list-query";
import type { DocumentListQuery } from "./types";
import styles from "./documents-list-upload-monitor.module.css";

const STATUS_OPTIONS = [
  ["queued", "Queued"], ["partitioning", "Partitioning"], ["chunking", "Chunking"],
  ["vectorizing", "Vectorizing"], ["extracting", "Extracting"],
  ["pending_review", "Pending review"], ["approved", "Approved"],
  ["rejected", "Rejected"], ["failed", "Failed"],
] as const;

export function DocumentFilterForm({
  query,
  viewer,
  onApply,
  onClear,
}: {
  query: DocumentListQuery;
  viewer: boolean;
  onApply: (query: DocumentListQuery) => void;
  onClear: () => void;
}) {
  const [draft, setDraft] = useState(query);
  const [dateError, setDateError] = useState<string>();
  const fromRef = useRef<HTMLInputElement>(null);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (draft.fromDate && draft.toDate && draft.fromDate > draft.toDate) {
      setDateError("Uploaded from must not be after Uploaded through.");
      fromRef.current?.focus();
      return;
    }
    setDateError(undefined);
    onApply({ ...draft, page: 1, status: viewer ? undefined : draft.status });
  }

  const directionLabels = draft.sortBy === "file_name"
    ? { asc: "A–Z", desc: "Z–A" }
    : { asc: "Oldest first", desc: "Newest first" };

  return (
    <section className={styles.filterPanel} aria-labelledby="document-filter-title">
      <h2 id="document-filter-title">Filter documents</h2>
      <form className={styles.filterGrid} onSubmit={submit}>
        {!viewer ? (
          <SelectField label="Status" value={draft.status ?? ""} onChange={(event) => setDraft({ ...draft, status: event.target.value as DocumentListQuery["status"] || undefined })}>
            <option value="">All statuses</option>
            {STATUS_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </SelectField>
        ) : null}
        <SelectField label="Document type" value={draft.documentType ?? ""} onChange={(event) => setDraft({ ...draft, documentType: event.target.value as DocumentListQuery["documentType"] || undefined })}>
          <option value="">All types</option>
          {DOCUMENT_TYPE_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
        </SelectField>
        <TextField ref={fromRef} label="Uploaded from" type="date" value={draft.fromDate ?? ""} error={dateError} onChange={(event) => setDraft({ ...draft, fromDate: event.target.value || undefined })} />
        <TextField label="Uploaded through" type="date" value={draft.toDate ?? ""} error={dateError} onChange={(event) => setDraft({ ...draft, toDate: event.target.value || undefined })} />
        <SelectField label="Sort by" value={draft.sortBy} onChange={(event) => setDraft({ ...draft, sortBy: event.target.value as DocumentListQuery["sortBy"] })}>
          <option value="created_at">Uploaded</option>
          <option value="updated_at">Updated</option>
          <option value="file_name">File name</option>
        </SelectField>
        <SelectField label="Order" value={draft.order} onChange={(event) => setDraft({ ...draft, order: event.target.value as DocumentListQuery["order"] })}>
          <option value="desc">{directionLabels.desc}</option>
          <option value="asc">{directionLabels.asc}</option>
        </SelectField>
        <SelectField label="Rows per page" value={draft.pageSize} onChange={(event) => setDraft({ ...draft, pageSize: Number(event.target.value) as 20 | 50 | 100 })}>
          <option value="20">20</option><option value="50">50</option><option value="100">100</option>
        </SelectField>
        <div className={styles.filterActions}>
          <Button type="submit" variant="primary">Apply filters</Button>
          <Button variant="subtle" onClick={() => { setDateError(undefined); setDraft(DEFAULT_DOCUMENT_QUERY); onClear(); }}>Clear filters</Button>
        </div>
      </form>
    </section>
  );
}
