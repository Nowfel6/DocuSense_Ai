import { useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { SelectField, TextField } from "@/components/ui/fields";

import { draftFromQuery, serializeReport } from "./api";
import type { DashboardQuery, ReportDraft, ReportErrors } from "./types";

export function ReportControls({ query, pending, onApply, onReset }: {
  query: DashboardQuery;
  pending: boolean;
  onApply: (query: DashboardQuery) => void;
  onReset: () => void;
}) {
  const [draft, setDraft] = useState<ReportDraft>(() => draftFromQuery(query));
  const [errors, setErrors] = useState<ReportErrors>({});
  const fromRef = useRef<HTMLInputElement>(null);
  const toRef = useRef<HTMLInputElement>(null);

  function apply() {
    const result = serializeReport(draft);
    setErrors(result.errors);
    if (!result.query) {
      if (result.errors.from || result.errors.range) fromRef.current?.focus();
      else toRef.current?.focus();
      return;
    }
    onApply(result.query);
  }

  function update(patch: Partial<ReportDraft>) {
    setDraft((current) => ({ ...current, ...patch }));
    setErrors({});
  }

  return (
    <section className="dba-controls" aria-labelledby="dba-controls-title">
      <div className="dba-section-heading">
        <div><h2 id="dba-controls-title">Report period</h2><p>UTC boundaries use an exclusive end time.</p></div>
      </div>
      <div className="dba-control-grid">
        <SelectField label="Range" value={draft.mode} disabled={pending} onChange={(event) => update({ mode: event.target.value as ReportDraft["mode"] })}>
          <option value="default">Server default (last 30 days)</option>
          <option value="custom">Custom range</option>
        </SelectField>
        <TextField ref={fromRef} label="From (UTC)" type="datetime-local" value={draft.from} disabled={pending || draft.mode !== "custom"} error={errors.from} onChange={(event) => update({ from: event.target.value })} />
        <TextField ref={toRef} label="To (UTC, exclusive)" type="datetime-local" value={draft.to} disabled={pending || draft.mode !== "custom"} error={errors.to} onChange={(event) => update({ to: event.target.value })} />
        <SelectField label="Bucket" value={draft.bucket} disabled={pending} onChange={(event) => update({ bucket: event.target.value as ReportDraft["bucket"] })}>
          <option value="day">Day</option><option value="week">Week</option><option value="month">Month</option>
        </SelectField>
      </div>
      {errors.range ? <p className="dba-control-error" role="alert">{errors.range}</p> : null}
      <div className="dba-control-actions">
        <Button variant="primary" isPending={pending} pendingLabel="Applying…" onClick={apply}>Apply</Button>
        <Button disabled={pending} onClick={() => { setErrors({}); onReset(); }}>Reset</Button>
      </div>
    </section>
  );
}
