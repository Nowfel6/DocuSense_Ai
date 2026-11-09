import type { StructuredTable } from "./types";
import styles from "./document-detail-chunk-inspector.module.css";

export function StructuredTableView({ table }: { table: StructuredTable }) {
  return (
    <div className={styles.structuredTableScroll} tabIndex={0} aria-label="Structured chunk table region">
      <table className={styles.structuredTable}>
        <caption>Structured content extracted from this chunk</caption>
        {table.headers.length ? (
          <thead>
            <tr>{table.headers.map((header, index) => <th key={`${index}-${header}`} scope="col">{header || `Column ${index + 1}`}</th>)}</tr>
          </thead>
        ) : null}
        <tbody>
          {table.rows.map((row) => (
            <tr key={row.row_index}>
              {row.cells.map((cell) => (
                <td key={`${cell.row}-${cell.column}`} rowSpan={cell.row_span} colSpan={cell.column_span}>{cell.text}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

