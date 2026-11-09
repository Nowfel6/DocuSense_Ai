import { SlidersHorizontal } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Checkbox, SelectField, TextField } from "@/components/ui/fields";
import { Alert } from "@/components/ui/feedback";
import { Drawer } from "@/components/ui/overlays";

import type { FieldErrors, SearchDocumentStatus, SearchDraft } from "./types";

const STATUS_OPTIONS: Array<[SearchDocumentStatus, string]> = [
  ["pending_review", "Pending review"],
  ["approved", "Approved"],
  ["rejected", "Rejected"],
];

function FilterFields({
  draft,
  errors,
  idPrefix,
  viewer,
  onChange,
}: {
  draft: SearchDraft;
  errors: FieldErrors;
  idPrefix: string;
  viewer: boolean;
  onChange: (patch: Partial<SearchDraft>) => void;
}) {
  function toggleStatus(status: SearchDocumentStatus, checked: boolean) {
    onChange({ document_statuses: checked ? [...draft.document_statuses, status] : draft.document_statuses.filter((item) => item !== status) });
  }
  return (
    <div className="seh-filter-grid">
      {!viewer ? (
        <fieldset className="seh-status-fieldset">
          <legend>Document status</legend>
          <div className="seh-check-row">
            {STATUS_OPTIONS.map(([value, label]) => <Checkbox key={value} id={`${idPrefix}-${value}`} label={label} checked={draft.document_statuses.includes(value)} onChange={(event) => toggleStatus(value, event.target.checked)} />)}
          </div>
        </fieldset>
      ) : <p className="seh-viewer-note">Viewer searches are restricted to approved documents.</p>}
      <SelectField id={`${idPrefix}-type`} label="Document type" value={draft.document_type} onChange={(event) => onChange({ document_type: event.target.value as SearchDraft["document_type"] })}>
        <option value="">Any type</option><option value="commercial_invoice">Commercial invoice</option><option value="purchase_order">Purchase order</option><option value="packing_list">Packing list</option>
      </SelectField>
      <TextField id={`${idPrefix}-supplier`} label="Supplier" value={draft.supplier} maxLength={255} error={errors.supplier} onChange={(event) => onChange({ supplier: event.target.value })} />
      <TextField id={`${idPrefix}-currency`} label="Currency" value={draft.currency} maxLength={3} placeholder="USD" error={errors.currency} onChange={(event) => onChange({ currency: event.target.value.toUpperCase() })} />
      <TextField id={`${idPrefix}-invoice-from`} label="Invoice date from" type="date" value={draft.invoice_date_from} error={errors.invoice_date_from} onChange={(event) => onChange({ invoice_date_from: event.target.value })} />
      <TextField id={`${idPrefix}-invoice-to`} label="Invoice date to" type="date" value={draft.invoice_date_to} error={errors.invoice_date_to} onChange={(event) => onChange({ invoice_date_to: event.target.value })} />
      <TextField id={`${idPrefix}-uploaded-from`} label="Uploaded from (UTC)" type="datetime-local" value={draft.uploaded_from} error={errors.uploaded_from} onChange={(event) => onChange({ uploaded_from: event.target.value })} />
      <TextField id={`${idPrefix}-uploaded-to`} label="Uploaded to (UTC)" type="datetime-local" value={draft.uploaded_to} error={errors.uploaded_to} onChange={(event) => onChange({ uploaded_to: event.target.value })} />
      <TextField id={`${idPrefix}-min-total`} label="Minimum total" inputMode="decimal" value={draft.min_total} error={errors.min_total} onChange={(event) => onChange({ min_total: event.target.value })} />
      <TextField id={`${idPrefix}-max-total`} label="Maximum total" inputMode="decimal" value={draft.max_total} error={errors.max_total} onChange={(event) => onChange({ max_total: event.target.value })} />
      <SelectField id={`${idPrefix}-sort`} label="Sort by" value={draft.sort_by} error={errors.sort_by} onChange={(event) => onChange({ sort_by: event.target.value as SearchDraft["sort_by"] })}>
        <option value="created_at">Uploaded</option><option value="date_issued">Invoice date</option><option value="grand_total">Total</option><option value="relevance">Similarity</option>
      </SelectField>
      <SelectField id={`${idPrefix}-order`} label="Order" value={draft.order} onChange={(event) => onChange({ order: event.target.value as SearchDraft["order"] })}>
        <option value="desc">Descending</option><option value="asc">Ascending</option>
      </SelectField>
      <SelectField id={`${idPrefix}-page-size`} label="Results per page" value={draft.page_size} onChange={(event) => onChange({ page_size: Number(event.target.value) as SearchDraft["page_size"] })}>
        <option value={20}>20</option><option value={50}>50</option><option value={100}>100</option>
      </SelectField>
    </div>
  );
}

export function SearchComposer({ draft, errors, viewer, pending, filtersOpen, onFiltersOpen, onChange, onSubmit, onReset }: {
  draft: SearchDraft;
  errors: FieldErrors;
  viewer: boolean;
  pending: boolean;
  filtersOpen: boolean;
  onFiltersOpen: (open: boolean) => void;
  onChange: (patch: Partial<SearchDraft>) => void;
  onSubmit: () => void;
  onReset: () => void;
}) {
  return (
    <form className="seh-search" onSubmit={(event) => { event.preventDefault(); onSubmit(); }} noValidate>
      {errors.criteria ? <Alert tone="error" title="Add search criteria" message={errors.criteria} /> : null}
      <div className="seh-search-primary">
        <TextField id="seh-query" label="Search document content" helpText="3–500 characters. Search text is never added to the URL or browser storage." value={draft.query} maxLength={500} error={errors.query} onChange={(event) => onChange({ query: event.target.value })} />
        <div className="seh-search-actions">
          <Button type="submit" variant="primary" isPending={pending} pendingLabel="Searching…">Search</Button>
          <Button className="seh-filter-trigger" onClick={() => onFiltersOpen(true)}><SlidersHorizontal aria-hidden="true" size={17} /> Filters</Button>
          <Button variant="subtle" onClick={onReset} disabled={pending}>Reset</Button>
        </div>
      </div>
      <div className="seh-desktop-filters" aria-label="Structured filters"><FilterFields draft={draft} errors={errors} idPrefix="desktop" viewer={viewer} onChange={onChange} /></div>
      {filtersOpen ? <Drawer open title="Search filters" description="Apply structured filters to the next search." placement="right" onClose={() => onFiltersOpen(false)}><FilterFields draft={draft} errors={errors} idPrefix="drawer" viewer={viewer} onChange={onChange} /><div className="seh-drawer-actions"><Button variant="primary" onClick={() => { onFiltersOpen(false); onSubmit(); }}>Apply and search</Button></div></Drawer> : null}
    </form>
  );
}
