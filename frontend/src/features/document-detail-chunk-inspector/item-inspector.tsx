"use client";

import { X } from "lucide-react";
import type { RefObject } from "react";

import { IconButton } from "@/components/ui/button";
import { Badge } from "@/components/ui/feedback";
import { Drawer } from "@/components/ui/overlays";
import { formatDateTime } from "@/lib/formatting/format";

import { SourceViewAction } from "./source-view-action";
import { StructuredTableView } from "./structured-table-view";
import type { EvidenceResponse, SelectedWorkbenchItem, SourceView } from "./types";
import styles from "./document-detail-chunk-inspector.module.css";

function display(value: string | number | boolean | null | undefined) {
  if (value === null || value === undefined || value === "") return "Not available";
  return typeof value === "boolean" ? (value ? "True" : "False") : String(value);
}

function InspectorContent({
  selected,
  source,
  evidence,
  sourceBlocked,
  sourceRefreshing,
  onRefreshSource,
}: {
  selected: SelectedWorkbenchItem;
  source: SourceView;
  evidence?: EvidenceResponse;
  sourceBlocked: boolean;
  sourceRefreshing: boolean;
  onRefreshSource: () => void;
}) {
  if (selected.mode === "chunks") {
    const item = selected.item;
    return (
      <div className={styles.inspectorStack}>
        <div className={styles.inspectorBadges}><Badge tone="technical">{item.chunk_type}</Badge><Badge>{item.retrieval_role}</Badge><Badge tone={item.embedding_status === "completed" ? "success" : item.embedding_status === "failed" ? "danger" : "neutral"}>{item.embedding_status.replaceAll("_", " ")}</Badge></div>
        <dl className={styles.inspectorFacts}>
          <div><dt>Chunk ID</dt><dd className={styles.identifier}>{item.chunk_id}</dd></div>
          <div><dt>Parent chunk</dt><dd className={styles.identifier}>{item.parent_chunk_id ?? "Not available"}</dd></div>
          <div><dt>Ordinal</dt><dd>{item.ordinal}</dd></div>
          <div><dt>Page range</dt><dd>{item.page_start === item.page_end ? item.page_start : `${item.page_start}–${item.page_end}`}</dd></div>
          <div><dt>Section</dt><dd>{display(item.section)}</dd></div>
          <div><dt>Token count</dt><dd>{item.token_count}</dd></div>
          <div><dt>Has embedding</dt><dd>{item.has_embedding ? "Yes" : "No"}</dd></div>
        </dl>
        {item.summary ? <section><h3>Summary</h3><p>{item.summary}</p></section> : null}
        <section><h3>Chunk content</h3><pre className={styles.rawContent}>{item.raw_content}</pre></section>
        {item.structured_content ? <StructuredTableView table={item.structured_content} /> : null}
        <section>
          <h3>Source provenance</h3>
          <p>Source elements: {item.source_element_ids.length ? item.source_element_ids.join(", ") : "Not available"}</p>
          <p>Bounding regions: {item.bounding_boxes.length ? item.bounding_boxes.map((box) => `page ${box.page_number} (${box.x0}, ${box.y0})–(${box.x1}, ${box.y1})`).join("; ") : "Not available"}</p>
        </section>
        <SourceViewAction source={source} page={item.page_start} blocked={sourceBlocked} refreshing={sourceRefreshing} onRefresh={onRefreshSource} />
      </div>
    );
  }

  const item = selected.item;
  const run = evidence?.data.extraction_run;
  return (
    <div className={styles.inspectorStack}>
      <div className={styles.inspectorBadges}><Badge tone={item.validation_state === "valid" ? "success" : item.validation_state === "invalid" ? "danger" : item.validation_state === "ambiguous" ? "warning" : "neutral"}>{item.validation_state}</Badge></div>
      <dl className={styles.inspectorFacts}>
        <div><dt>Field path</dt><dd className={styles.identifier}>{item.field_path}</dd></div>
        <div><dt>Source value</dt><dd>{display(item.source_value)}</dd></div>
        <div><dt>Normalized value</dt><dd>{display(item.normalized_value)}</dd></div>
        <div><dt>Primary chunk ID</dt><dd className={styles.identifier}>{display(item.primary_chunk_id)}</dd></div>
        <div><dt>Source page</dt><dd>{display(item.source_page)}</dd></div>
        <div><dt>Field confidence</dt><dd>{item.confidence_score}%</dd></div>
        <div><dt>Retrieval rank</dt><dd>{display(item.retrieval_rank)}</dd></div>
        <div><dt>Retrieval score</dt><dd>{display(item.retrieval_score)}</dd></div>
      </dl>
      <p className={styles.scoreNote}>Retrieval rank and score describe persisted evidence selection. They are not correctness probabilities.</p>
      <section><h3>Evidence excerpt</h3><p className={styles.rawContent}>{display(item.evidence_excerpt)}</p></section>
      <section><h3>Confidence reasons</h3><p>{item.confidence_reason_codes.length ? item.confidence_reason_codes.join(", ") : "No reason codes returned."}</p></section>
      {item.bounding_box ? <section><h3>Source region</h3><p>Page {item.bounding_box.page_number}: ({item.bounding_box.x0}, {item.bounding_box.y0})–({item.bounding_box.x1}, {item.bounding_box.y1})</p></section> : null}
      {run ? (
        <section>
          <h3>Extraction run</h3>
          <dl className={styles.inspectorFacts}>
            <div><dt>Run ID</dt><dd className={styles.identifier}>{run.extraction_run_id}</dd></div>
            <div><dt>Pipeline</dt><dd>{run.pipeline_version}</dd></div>
            <div><dt>Parser</dt><dd>{run.parser_name} {run.parser_version}</dd></div>
            <div><dt>Embedding model</dt><dd>{run.embedding_model}</dd></div>
            <div><dt>LLM</dt><dd>{run.llm_provider} / {run.llm_model}</dd></div>
            <div><dt>Completed</dt><dd>{formatDateTime(run.completed_at)}</dd></div>
          </dl>
        </section>
      ) : null}
      {evidence ? <section><h3>Validation rules</h3><p>{evidence.data.validation_summary.passed} passed, {evidence.data.validation_summary.failed} failed, {evidence.data.validation_summary.missing} missing, {evidence.data.validation_summary.not_applicable} not applicable.</p><ul className={styles.ruleList}>{evidence.data.rule_results.map((rule) => <li key={`${rule.rule_id}-${rule.scope_key}`}><strong>{rule.rule_id}</strong>: {rule.status} · {rule.message_code}</li>)}</ul></section> : null}
      <SourceViewAction source={source} page={item.source_page ?? undefined} blocked={sourceBlocked} refreshing={sourceRefreshing} onRefresh={onRefreshSource} />
    </div>
  );
}

export function ItemInspector({
  selected,
  evidence,
  source,
  wide,
  sourceBlocked,
  sourceRefreshing,
  onRefreshSource,
  onClose,
  returnFocusRef,
}: {
  selected: SelectedWorkbenchItem | null;
  evidence?: EvidenceResponse;
  source: SourceView;
  wide: boolean;
  sourceBlocked: boolean;
  sourceRefreshing: boolean;
  onRefreshSource: () => void;
  onClose: () => void;
  returnFocusRef: RefObject<HTMLElement | null>;
}) {
  if (!selected) {
    return wide ? <aside className={styles.inspectorEmpty} aria-label="Selected item inspector"><h2>Nothing selected</h2><p>Select a result to inspect its content and provenance.</p></aside> : null;
  }

  const title = selected.mode === "chunks" ? `Chunk #${selected.item.ordinal}` : selected.item.field_path;
  const content = <InspectorContent selected={selected} source={source} evidence={evidence} sourceBlocked={sourceBlocked} sourceRefreshing={sourceRefreshing} onRefreshSource={onRefreshSource} />;

  if (!wide) {
    return <Drawer open title={title} description="Selected document evidence" cancelLabel="Close" onClose={onClose} returnFocusRef={returnFocusRef}>{content}</Drawer>;
  }

  return (
    <aside className={styles.inspector} aria-labelledby="item-inspector-title">
      <div className={styles.inspectorHeading}><h2 id="item-inspector-title">{title}</h2><IconButton label="Close inspector" variant="subtle" icon={<X aria-hidden="true" size={18} />} onClick={onClose} /></div>
      {content}
    </aside>
  );
}

