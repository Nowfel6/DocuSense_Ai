import { TextField } from "@/components/ui/fields";

import type { InvoiceCandidate } from "./types";
import styles from "./human-review-studio.module.css";

const FIELDS: Array<{ key: keyof InvoiceCandidate; label: string; type?: string; inputMode?: "decimal"; maxLength?: number }> = [
  { key: "invoice_number", label: "Invoice number", maxLength: 100 },
  { key: "supplier_name", label: "Supplier name", maxLength: 255 },
  { key: "supplier_tax_id", label: "Supplier tax ID", maxLength: 100 },
  { key: "buyer_name", label: "Buyer name", maxLength: 255 },
  { key: "date_issued", label: "Issue date", type: "date" },
  { key: "due_date", label: "Due date", type: "date" },
  { key: "currency", label: "Currency", maxLength: 3 },
  { key: "subtotal", label: "Subtotal", inputMode: "decimal" },
  { key: "tax_amount", label: "Tax amount", inputMode: "decimal" },
  { key: "discount_amount", label: "Discount amount", inputMode: "decimal" },
  { key: "grand_total", label: "Grand total", inputMode: "decimal" },
];

export function InvoiceFields({
  value,
  errors,
  readOnly,
  onChange,
}: {
  value: InvoiceCandidate;
  errors: Record<string, string>;
  readOnly: boolean;
  onChange: (next: InvoiceCandidate) => void;
}) {
  return (
    <section className={styles.section} aria-labelledby="review-fields-heading">
      <div className={styles.sectionHeading}>
        <div>
          <h2 id="review-fields-heading">Invoice fields</h2>
          <p>Correct extracted values. Empty optional values are sent as null.</p>
        </div>
      </div>
      <div className={styles.fieldGrid}>
        {FIELDS.map((field) => (
          <TextField
            key={field.key}
            id={`review-invoice-${field.key}`}
            label={field.label}
            type={field.type}
            inputMode={field.inputMode}
            maxLength={field.maxLength}
            value={value[field.key] ?? ""}
            readOnly={readOnly}
            error={errors[`invoice.${field.key}`]}
            onChange={(event) => onChange({ ...value, [field.key]: event.currentTarget.value })}
          />
        ))}
      </div>
    </section>
  );
}
