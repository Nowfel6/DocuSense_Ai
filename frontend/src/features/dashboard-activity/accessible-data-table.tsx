import { TableFrame } from "@/components/ui/table";

export function AccessibleDataTable({ caption, headers, rows }: { caption: string; headers: string[]; rows: (string | number)[][] }) {
  return (
    <details className="dba-data-details">
      <summary>View exact data</summary>
      <TableFrame caption={caption} headers={headers}>
        {rows.map((row, rowIndex) => <tr key={`${caption}-${rowIndex}`}>{row.map((cell, index) => <td key={index}>{cell}</td>)}</tr>)}
      </TableFrame>
    </details>
  );
}

