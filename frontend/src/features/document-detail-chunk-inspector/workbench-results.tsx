"use client";

import { Badge } from "@/components/ui/feedback";
import { Pagination, TableFrame } from "@/components/ui/table";

import type {
  ChunkItem,
  ChunkListEnvelope,
  EvidenceItem,
  EvidenceResponse,
  SelectedWorkbenchItem,
  WorkbenchEnvelope,
  WorkbenchQuery,
} from "./types";
import styles from "./document-detail-chunk-inspector.module.css";

function excerpt(value: string | null, length = 180) {
  if (!value) return "Not available";
  const collapsed = value.replace(/\s+/g, " ").trim();
  return collapsed.length > length ? `${collapsed.slice(0, length)}…` : collapsed;
}

function pages(item: ChunkItem) {
  return item.page_start === item.page_end ? `Page ${item.page_start}` : `Pages ${item.page_start}–${item.page_end}`;
}

function validationTone(state: EvidenceItem["validation_state"]) {
  if (state === "valid") return "success" as const;
  if (state === "invalid") return "danger" as const;
  if (state === "ambiguous") return "warning" as const;
  return "neutral" as const;
}

export function WorkbenchResults({
  query,
  envelope,
  selectedKey,
  onSelect,
  onPage,
}: {
  query: WorkbenchQuery;
  envelope: WorkbenchEnvelope;
  selectedKey: string | null;
  onSelect: (selected: SelectedWorkbenchItem, trigger: HTMLButtonElement) => void;
  onPage: (page: number) => void;
}) {
  const pagination = envelope.pagination;
  const first = pagination.total_records ? (pagination.page - 1) * pagination.page_size + 1 : 0;
  const last = Math.min(pagination.total_records, pagination.page * pagination.page_size);

  if (query.mode === "chunks") {
    const chunks = (envelope as ChunkListEnvelope).data;
    return (
      <section className={styles.resultsRegion} aria-labelledby="workbench-results-title">
        <h2 id="workbench-results-title" tabIndex={-1}>Showing {first}–{last} of {pagination.total_records} chunks.</h2>
        <div className={styles.resultTable}>
          <TableFrame caption="Persisted document chunks" headers={["Chunk", "Source", "Type", "Role", "Tokens", "Embedding", "Excerpt"]}>
            {chunks.map((item) => (
              <tr key={item.chunk_id} data-selected={selectedKey === item.chunk_id || undefined}>
                <th scope="row"><button type="button" className={styles.resultButton} aria-pressed={selectedKey === item.chunk_id} onClick={(event) => onSelect({ mode: "chunks", item }, event.currentTarget)}>#{item.ordinal} · {item.chunk_id.slice(0, 8)}…</button></th>
                <td>{pages(item)}{item.section ? ` · ${item.section}` : ""}</td>
                <td><Badge tone="technical">{item.chunk_type}</Badge></td>
                <td>{item.retrieval_role}</td>
                <td className={styles.numeric}>{item.token_count}</td>
                <td><Badge tone={item.embedding_status === "completed" ? "success" : item.embedding_status === "failed" ? "danger" : "neutral"}>{item.embedding_status.replaceAll("_", " ")}</Badge></td>
                <td>{excerpt(item.summary ?? item.raw_content)}</td>
              </tr>
            ))}
          </TableFrame>
        </div>
        <ul className={styles.resultCards} aria-label="Persisted document chunks">
          {chunks.map((item) => (
            <li key={item.chunk_id} data-selected={selectedKey === item.chunk_id || undefined}>
              <button type="button" className={styles.cardSelect} aria-pressed={selectedKey === item.chunk_id} onClick={(event) => onSelect({ mode: "chunks", item }, event.currentTarget)}>
                <strong>Chunk #{item.ordinal}</strong><span>{pages(item)} · {item.chunk_type} · {item.retrieval_role}</span><span>{excerpt(item.summary ?? item.raw_content)}</span>
              </button>
            </li>
          ))}
        </ul>
        {pagination.total_pages > 1 ? <Pagination page={pagination.page} totalPages={pagination.total_pages} onFirst={() => onPage(1)} onPrevious={() => onPage(pagination.page - 1)} onNext={() => onPage(pagination.page + 1)} onLast={() => onPage(pagination.total_pages)} /> : null}
      </section>
    );
  }

  const evidence = (envelope as EvidenceResponse).data.items;
  return (
    <section className={styles.resultsRegion} aria-labelledby="workbench-results-title">
      <h2 id="workbench-results-title" tabIndex={-1}>Showing {first}–{last} of {pagination.total_records} evidence records.</h2>
      <div className={styles.resultTable}>
        <TableFrame caption="Persisted extraction evidence" headers={["Field", "Source value", "Page", "Validation", "Field confidence", "Retrieval"]}>
          {evidence.map((item) => (
            <tr key={item.field_path} data-selected={selectedKey === item.field_path || undefined}>
              <th scope="row"><button type="button" className={styles.resultButton} aria-pressed={selectedKey === item.field_path} onClick={(event) => onSelect({ mode: "evidence", item }, event.currentTarget)}>{item.field_path}</button></th>
              <td>{excerpt(item.source_value, 100)}</td>
              <td>{item.source_page ?? "—"}</td>
              <td><Badge tone={validationTone(item.validation_state)}>{item.validation_state}</Badge></td>
              <td className={styles.numeric}>{item.confidence_score}%</td>
              <td className={styles.numeric}>{item.retrieval_rank === null ? "Not available" : `Rank ${item.retrieval_rank}${item.retrieval_score === null ? "" : ` · score ${item.retrieval_score}`}`}</td>
            </tr>
          ))}
        </TableFrame>
      </div>
      <ul className={styles.resultCards} aria-label="Persisted extraction evidence">
        {evidence.map((item) => (
          <li key={item.field_path} data-selected={selectedKey === item.field_path || undefined}>
            <button type="button" className={styles.cardSelect} aria-pressed={selectedKey === item.field_path} onClick={(event) => onSelect({ mode: "evidence", item }, event.currentTarget)}>
              <strong>{item.field_path}</strong><span>{item.validation_state} · Field confidence {item.confidence_score}%</span><span>{excerpt(item.source_value)}</span>
            </button>
          </li>
        ))}
      </ul>
      {pagination.total_pages > 1 ? <Pagination page={pagination.page} totalPages={pagination.total_pages} onFirst={() => onPage(1)} onPrevious={() => onPage(pagination.page - 1)} onNext={() => onPage(pagination.page + 1)} onLast={() => onPage(pagination.total_pages)} /> : null}
    </section>
  );
}

