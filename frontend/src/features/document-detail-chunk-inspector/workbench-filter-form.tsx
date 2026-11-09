"use client";

import { useRef, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { SelectField, TextField } from "@/components/ui/fields";

import type { ChunkType, RetrievalRole, ValidationState, WorkbenchQuery } from "./types";
import styles from "./document-detail-chunk-inspector.module.css";

const FIELD_PATH = /^[a-z][a-z0-9_]*(?:\.[A-Za-z0-9_-]+)+$/;
const CONFIDENCE = /^(?:0|[1-9]\d?|100)(?:\.\d{1,2})?$/;

export function WorkbenchFilterForm({
  query,
  onApply,
  onClear,
}: {
  query: WorkbenchQuery;
  onApply: (query: WorkbenchQuery) => void;
  onClear: () => void;
}) {
  const [chunkType, setChunkType] = useState(query.mode === "chunks" ? query.chunkType ?? "" : "");
  const [pageNumber, setPageNumber] = useState(query.mode === "chunks" ? String(query.pageNumber ?? "") : "");
  const [retrievalRole, setRetrievalRole] = useState(query.mode === "chunks" ? query.retrievalRole ?? "" : "");
  const [section, setSection] = useState(query.mode === "chunks" ? query.section ?? "" : "");
  const [order, setOrder] = useState(query.mode === "chunks" ? query.order : "asc");
  const [fieldPath, setFieldPath] = useState(query.mode === "evidence" ? query.fieldPath ?? "" : "");
  const [validationState, setValidationState] = useState(query.mode === "evidence" ? query.validationState ?? "" : "");
  const [minConfidence, setMinConfidence] = useState(query.mode === "evidence" ? query.minConfidence ?? "" : "");
  const [selectedPageSize, setSelectedPageSize] = useState(String(query.pageSize));
  const [errors, setErrors] = useState<Record<string, string>>({});
  const firstChunkRef = useRef<HTMLInputElement>(null);
  const firstEvidenceRef = useRef<HTMLInputElement>(null);

  function submit(event: FormEvent) {
    event.preventDefault();
    const nextErrors: Record<string, string> = {};
    const pageSize = Number(selectedPageSize) as 20 | 50 | 100;

    if (query.mode === "chunks") {
      const trimmedSection = section.normalize("NFC").trim();
      const parsedPage = pageNumber ? Number(pageNumber) : undefined;
      if (pageNumber && (!/^[1-9]\d*$/.test(pageNumber) || !Number.isSafeInteger(parsedPage))) nextErrors.pageNumber = "Enter a whole page number of 1 or greater.";
      if (trimmedSection.length > 255) nextErrors.section = "Section must be 255 characters or fewer.";
      if (Object.keys(nextErrors).length) {
        setErrors(nextErrors);
        firstChunkRef.current?.focus();
        return;
      }
      setErrors({});
      onApply({
        mode: "chunks", page: 1, pageSize,
        chunkType: chunkType ? chunkType as ChunkType : undefined,
        pageNumber: parsedPage,
        retrievalRole: retrievalRole ? retrievalRole as RetrievalRole : undefined,
        section: trimmedSection || undefined,
        order: order as "asc" | "desc",
      });
      return;
    }

    if (fieldPath && (fieldPath.length > 255 || !FIELD_PATH.test(fieldPath))) nextErrors.fieldPath = "Use a canonical field path such as invoice.grand_total.";
    if (minConfidence && (!CONFIDENCE.test(minConfidence) || Number(minConfidence) > 100)) nextErrors.minConfidence = "Enter a value from 0 to 100 with up to two decimal places.";
    if (Object.keys(nextErrors).length) {
      setErrors(nextErrors);
      firstEvidenceRef.current?.focus();
      return;
    }
    setErrors({});
    onApply({
      mode: "evidence", page: 1, pageSize,
      fieldPath: fieldPath || undefined,
      validationState: validationState ? validationState as ValidationState : undefined,
      minConfidence: minConfidence || undefined,
    });
  }

  return (
    <form className={styles.filterPanel} aria-label={`${query.mode === "chunks" ? "Chunk" : "Evidence"} filters`} onSubmit={submit}>
      {query.mode === "chunks" ? (
        <>
          <SelectField label="Chunk type" value={chunkType} onChange={(event) => setChunkType(event.target.value)}>
            <option value="">All types</option>
            <option value="text">Text</option><option value="table">Table</option><option value="header">Header</option>
            <option value="list">List</option><option value="image">Image</option><option value="unknown">Unknown</option>
          </SelectField>
          <TextField ref={firstChunkRef} label="Source page" inputMode="numeric" value={pageNumber} error={errors.pageNumber} onChange={(event) => setPageNumber(event.target.value)} />
          <SelectField label="Retrieval role" value={retrievalRole} onChange={(event) => setRetrievalRole(event.target.value)}>
            <option value="">All roles</option><option value="parent">Parent</option><option value="child">Child</option><option value="both">Both</option>
          </SelectField>
          <TextField label="Section" value={section} maxLength={256} error={errors.section} onChange={(event) => setSection(event.target.value)} />
          <SelectField label="Order" value={order} onChange={(event) => setOrder(event.target.value === "desc" ? "desc" : "asc")}>
            <option value="asc">Ascending ordinal</option><option value="desc">Descending ordinal</option>
          </SelectField>
        </>
      ) : (
        <>
          <TextField ref={firstEvidenceRef} label="Field path" placeholder="invoice.grand_total" value={fieldPath} maxLength={255} error={errors.fieldPath} onChange={(event) => setFieldPath(event.target.value)} />
          <SelectField label="Validation" value={validationState} onChange={(event) => setValidationState(event.target.value)}>
            <option value="">All states</option><option value="valid">Valid</option><option value="invalid">Invalid</option>
            <option value="missing">Missing</option><option value="ambiguous">Ambiguous</option><option value="unsupported">Unsupported</option>
          </SelectField>
          <TextField label="Minimum confidence" inputMode="decimal" placeholder="0–100" value={minConfidence} error={errors.minConfidence} onChange={(event) => setMinConfidence(event.target.value)} />
        </>
      )}
      <SelectField label="Results per page" value={selectedPageSize} onChange={(event) => setSelectedPageSize(event.target.value)}>
        <option value="20">20</option><option value="50">50</option><option value="100">100</option>
      </SelectField>
      <div className={styles.filterActions}>
        <Button type="submit" variant="primary">Apply filters</Button>
        <Button type="button" variant="subtle" onClick={onClear}>Clear filters</Button>
      </div>
    </form>
  );
}
