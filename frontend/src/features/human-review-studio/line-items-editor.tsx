import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react";
import { useRef } from "react";

import { Button, IconButton } from "@/components/ui/button";
import { FormMessage, TextField } from "@/components/ui/fields";

import { newDraftLine } from "./candidate";
import type { ReviewDraftLine } from "./types";
import styles from "./human-review-studio.module.css";

function lineHasContent(line: ReviewDraftLine) {
  return [line.description, line.hs_code, line.quantity, line.unit_price, line.tax_amount, line.total_price]
    .some((value) => Boolean(value?.trim()));
}

export function LineItemsEditor({
  value,
  errors,
  readOnly,
  onChange,
  onAnnounce,
}: {
  value: ReviewDraftLine[];
  errors: Record<string, string>;
  readOnly: boolean;
  onChange: (next: ReviewDraftLine[]) => void;
  onAnnounce: (message: string) => void;
}) {
  const addRef = useRef<HTMLButtonElement>(null);

  function normalize(next: ReviewDraftLine[]) {
    return next.map((line, index) => ({ ...line, line_order: index + 1 }));
  }

  function update(index: number, patch: Partial<ReviewDraftLine>) {
    onChange(value.map((line, lineIndex) => lineIndex === index ? { ...line, ...patch } : line));
  }

  function move(index: number, offset: -1 | 1) {
    const target = index + offset;
    if (target < 0 || target >= value.length) return;
    const next = [...value];
    [next[index], next[target]] = [next[target], next[index]];
    onChange(normalize(next));
    onAnnounce(`Line item moved to position ${target + 1} of ${next.length}.`);
  }

  function remove(index: number) {
    const line = value[index];
    if (lineHasContent(line) && !window.confirm(`Remove line item ${index + 1}?`)) return;
    onChange(normalize(value.filter((_, lineIndex) => lineIndex !== index)));
    onAnnounce(`Line item ${index + 1} removed.`);
    requestAnimationFrame(() => (document.querySelector<HTMLElement>(`[data-line-index="${Math.min(index, value.length - 2)}"] input`) ?? addRef.current)?.focus());
  }

  return (
    <section className={styles.section} aria-labelledby="line-items-heading">
      <div className={styles.sectionHeading}>
        <div>
          <h2 id="line-items-heading">Line items</h2>
          <p>{value.length} of 500 items. Reorder with the named buttons.</p>
        </div>
        {!readOnly ? (
          <Button
            ref={addRef}
            size="compact"
            disabled={value.length >= 500}
            onClick={() => {
              const line = { ...newDraftLine(), line_order: value.length + 1 };
              onChange([...value, line]);
              requestAnimationFrame(() => document.getElementById(`review-line-${line.key}-description`)?.focus());
            }}
          >
            <Plus aria-hidden="true" size={16} /> Add line
          </Button>
        ) : null}
      </div>
      {errors.line_items ? <FormMessage tone="error">{errors.line_items}</FormMessage> : null}
      {value.length === 0 ? <p className={styles.emptyText}>No line items. Add one before recalculating if the invoice requires item detail.</p> : null}
      <ol className={styles.lineList}>
        {value.map((line, index) => {
          const base = `line_items.${line.key}`;
          return (
            <li key={line.key} className={styles.lineCard} data-line-index={index}>
              <fieldset disabled={readOnly}>
                <legend>Line item {index + 1}</legend>
                <div className={styles.lineActions}>
                  <IconButton label={`Move line item ${index + 1} up`} icon={<ArrowUp aria-hidden="true" size={16} />} size="compact" disabled={index === 0} onClick={() => move(index, -1)} />
                  <IconButton label={`Move line item ${index + 1} down`} icon={<ArrowDown aria-hidden="true" size={16} />} size="compact" disabled={index === value.length - 1} onClick={() => move(index, 1)} />
                  <IconButton label={`Remove line item ${index + 1}`} icon={<Trash2 aria-hidden="true" size={16} />} size="compact" variant="destructive" onClick={() => remove(index)} />
                </div>
                <div className={styles.lineGrid}>
                  <div className={styles.descriptionField}>
                    <label className="ds-label" htmlFor={`review-line-${line.key}-description`}>Description</label>
                    <textarea
                      id={`review-line-${line.key}-description`}
                      className="ds-input"
                      rows={2}
                      maxLength={32768}
                      value={line.description ?? ""}
                      aria-invalid={Boolean(errors[`${base}.description`]) || undefined}
                      aria-describedby={errors[`${base}.description`] ? `review-line-${line.key}-description-error` : undefined}
                      onChange={(event) => update(index, { description: event.currentTarget.value })}
                    />
                    {errors[`${base}.description`] ? <FormMessage id={`review-line-${line.key}-description-error`} tone="error">{errors[`${base}.description`]}</FormMessage> : null}
                  </div>
                  <TextField id={`review-line-${line.key}-hs`} label="HS code" maxLength={50} value={line.hs_code ?? ""} error={errors[`${base}.hs_code`]} onChange={(event) => update(index, { hs_code: event.currentTarget.value })} />
                  {(["quantity", "unit_price", "tax_amount", "total_price"] as const).map((field) => (
                    <TextField
                      key={field}
                      id={`review-line-${line.key}-${field}`}
                      label={field.replaceAll("_", " ")}
                      inputMode="decimal"
                      value={line[field] ?? ""}
                      error={errors[`${base}.${field}`]}
                      onChange={(event) => update(index, { [field]: event.currentTarget.value })}
                    />
                  ))}
                </div>
              </fieldset>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
