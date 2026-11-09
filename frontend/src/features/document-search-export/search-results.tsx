import Link from "next/link";
import type { Route } from "next";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/fields";
import { EmptyState, StatusBadge } from "@/components/ui/feedback";
import { Pagination, TableFrame } from "@/components/ui/table";

import { formatMoneyString, formatSimilarity } from "./format";
import type { SearchEnvelope, SearchResult } from "./types";

function ResultIdentity({ item }: { item: SearchResult }) {
  return <div className="seh-identity"><strong title={item.file_name}>{item.file_name}</strong><span>{item.supplier_name ?? "Supplier not available"}{item.invoice_number ? ` · ${item.invoice_number}` : ""}</span></div>;
}

function ResultActions({ item }: { item: SearchResult }) {
  return <div className="seh-row-actions"><Link className="ds-button" data-variant="subtle" href={item.document_url as Route}>Open</Link>{item.review_url ? <Link className="ds-button" data-variant="subtle" href={item.review_url as Route}>Review</Link> : null}</div>;
}

function Match({ item, semantic }: { item: SearchResult; semantic: boolean }) {
  if (!semantic) return <span>Structured match</span>;
  return <div className="seh-match"><span>Similarity {formatSimilarity(item.relevance_score)}</span>{item.matching_excerpt ? <span title={item.matching_excerpt}>{item.matching_excerpt}</span> : null}{item.matching_page_start ? <span>Page {item.matching_page_start}{item.matching_page_end && item.matching_page_end !== item.matching_page_start ? `–${item.matching_page_end}` : ""}</span> : null}</div>;
}

export function SearchResults({ envelope, semantic, canExport, selected, onToggle, onTogglePage, onPage }: {
  envelope: SearchEnvelope;
  semantic: boolean;
  canExport: boolean;
  selected: Set<string>;
  onToggle: (id: string, checked: boolean) => void;
  onTogglePage: (checked: boolean) => void;
  onPage: (page: number) => void;
}) {
  const eligible = envelope.data.filter((item) => item.export_eligible);
  const selectedEligible = eligible.filter((item) => selected.has(item.document_id)).length;
  if (!envelope.data.length) return <EmptyState title="No matching documents" message="Adjust the search text or filters and try again." />;
  const selectHeader = canExport ? <Checkbox label="Select eligible documents on this page" checked={eligible.length > 0 && selectedEligible === eligible.length} indeterminate={selectedEligible > 0 && selectedEligible < eligible.length} disabled={!eligible.length} onChange={(event) => onTogglePage(event.target.checked)} /> : null;
  return (
    <>
      <div className="seh-table-view">
        <TableFrame caption="Document search results" headers={[selectHeader, "Document", "Type / date", "Amount", "Status", "Match", "Actions"]}>
          {envelope.data.map((item) => <tr key={item.document_id}>
            <td>{canExport ? item.export_eligible ? <Checkbox label={`Select ${item.file_name}`} checked={selected.has(item.document_id)} onChange={(event) => onToggle(item.document_id, event.target.checked)} /> : <span className="seh-ineligible">Not exportable</span> : null}</td>
            <td><ResultIdentity item={item} /></td>
            <td><span>{item.document_type.replaceAll("_", " ")}</span><br /><span>{item.date_issued ?? "Date not available"}</span></td>
            <td className="seh-number">{formatMoneyString(item.grand_total, item.currency)}</td>
            <td><StatusBadge status={item.status} /></td>
            <td><Match item={item} semantic={semantic} /></td>
            <td><ResultActions item={item} /></td>
          </tr>)}
        </TableFrame>
      </div>
      <ul className="seh-card-list" aria-label="Document search results">
        {envelope.data.map((item) => <li className="seh-result-card" key={item.document_id}>
          <div className="seh-card-head">{canExport && item.export_eligible ? <Checkbox label={`Select ${item.file_name}`} checked={selected.has(item.document_id)} onChange={(event) => onToggle(item.document_id, event.target.checked)} /> : null}<StatusBadge status={item.status} /></div>
          <ResultIdentity item={item} /><dl><div><dt>Amount</dt><dd>{formatMoneyString(item.grand_total, item.currency)}</dd></div><div><dt>Date</dt><dd>{item.date_issued ?? "Not available"}</dd></div><div><dt>Type</dt><dd>{item.document_type.replaceAll("_", " ")}</dd></div></dl><Match item={item} semantic={semantic} />{canExport && !item.export_eligible ? <span className="seh-ineligible">Not exportable</span> : null}<ResultActions item={item} />
        </li>)}
      </ul>
      <Pagination page={envelope.pagination.page} totalPages={envelope.pagination.total_pages} onFirst={() => onPage(1)} onPrevious={() => onPage(envelope.pagination.page - 1)} onNext={() => onPage(envelope.pagination.page + 1)} onLast={() => onPage(envelope.pagination.total_pages)} />
    </>
  );
}

export function ResultSummary({ envelope, refreshing, onRetry }: { envelope: SearchEnvelope; refreshing: boolean; onRetry?: () => void }) {
  const start = envelope.pagination.total_records ? (envelope.pagination.page - 1) * envelope.pagination.page_size + 1 : 0;
  const end = start ? start + envelope.data.length - 1 : 0;
  return <div className="seh-result-summary" aria-live="polite"><span>{start}–{end} of {envelope.pagination.total_records} visible results{refreshing ? " · Refreshing" : ""}</span>{onRetry ? <Button size="compact" onClick={onRetry}>Retry</Button> : null}</div>;
}
