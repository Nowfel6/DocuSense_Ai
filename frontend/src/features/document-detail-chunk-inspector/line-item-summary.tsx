"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { TableFrame } from "@/components/ui/table";

import type { ReviewLineItem } from "./types";
import styles from "./document-detail-chunk-inspector.module.css";

const PAGE_SIZE = 20;

function value(item: string | null, currency?: string | null) {
  if (item === null) return "Not available";
  return currency ? `${currency} ${item}` : item;
}

export function LineItemSummary({ items, currency }: { items: ReviewLineItem[]; currency: string | null }) {
  const [visible, setVisible] = useState(PAGE_SIZE);
  const shown = items.slice(0, visible);

  return (
    <section aria-labelledby="line-items-title" className={styles.sectionStack}>
      <div className={styles.sectionHeading}>
        <div>
          <h2 id="line-items-title">Line items</h2>
          <p>Showing {shown.length} of {items.length} extracted line items.</p>
        </div>
      </div>
      {items.length ? (
        <>
          <div className={styles.lineItemTable}>
            <TableFrame caption="Extracted invoice line items" headers={["Line", "Description", "HS code", "Quantity", "Unit price", "Tax", "Total"]}>
              {shown.map((item) => (
                <tr key={item.line_item_id}>
                  <th scope="row">{item.line_order}</th>
                  <td>{item.description ?? "Not available"}</td>
                  <td>{item.hs_code ?? "Not available"}</td>
                  <td className={styles.numeric}>{value(item.quantity)}</td>
                  <td className={styles.numeric}>{value(item.unit_price, currency)}</td>
                  <td className={styles.numeric}>{value(item.tax_amount, currency)}</td>
                  <td className={styles.numeric}>{value(item.total_price, currency)}</td>
                </tr>
              ))}
            </TableFrame>
          </div>
          <ul className={styles.lineItemCards} aria-label="Extracted invoice line items">
            {shown.map((item) => (
              <li key={item.line_item_id}>
                <h3>Line {item.line_order}: {item.description ?? "Description unavailable"}</h3>
                <dl>
                  <div><dt>HS code</dt><dd>{item.hs_code ?? "Not available"}</dd></div>
                  <div><dt>Quantity</dt><dd>{value(item.quantity)}</dd></div>
                  <div><dt>Unit price</dt><dd>{value(item.unit_price, currency)}</dd></div>
                  <div><dt>Tax</dt><dd>{value(item.tax_amount, currency)}</dd></div>
                  <div><dt>Total</dt><dd>{value(item.total_price, currency)}</dd></div>
                </dl>
              </li>
            ))}
          </ul>
          {shown.length < items.length ? (
            <Button variant="subtle" onClick={() => setVisible((count) => Math.min(items.length, count + PAGE_SIZE))}>
              Show {Math.min(PAGE_SIZE, items.length - shown.length)} more
            </Button>
          ) : null}
          <p className={styles.visuallyHidden} aria-live="polite">{shown.length} line items visible.</p>
        </>
      ) : <p className={styles.unavailable}>No line items were returned.</p>}
    </section>
  );
}

