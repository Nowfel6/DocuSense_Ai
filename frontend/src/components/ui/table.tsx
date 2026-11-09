import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from "lucide-react";
import type { ReactNode } from "react";

import { IconButton } from "./button";
import { Skeleton } from "./feedback";

export function TableFrame({
  caption,
  headers,
  children,
  state = "ready",
  stateContent,
}: {
  caption: string;
  headers: ReactNode[];
  children: ReactNode;
  state?: "ready" | "loading" | "empty" | "error";
  stateContent?: ReactNode;
}) {
  const content = state === "loading"
    ? Array.from({ length: 3 }, (_, index) => (
      <tr key={index}>
        <td colSpan={headers.length}><Skeleton shape="row" /></td>
      </tr>
    ))
    : state === "ready"
      ? children
      : <tr><td colSpan={headers.length} className="ds-table-state">{stateContent}</td></tr>;

  return (
    <div className="ds-table-frame">
      <div className="ds-table-scroll" tabIndex={0} aria-label={`${caption} table region`}>
        <table className="ds-table">
          <caption>{caption}</caption>
          <thead><tr>{headers.map((header, index) => <th key={index} scope="col">{header}</th>)}</tr></thead>
          <tbody>{content}</tbody>
        </table>
      </div>
    </div>
  );
}

export function Pagination({
  page,
  totalPages,
  onFirst,
  onPrevious,
  onNext,
  onLast,
}: {
  page: number;
  totalPages: number;
  onFirst: () => void;
  onPrevious: () => void;
  onNext: () => void;
  onLast: () => void;
}) {
  return (
    <nav className="ds-pagination" aria-label="Pagination">
      <IconButton
        label="First page"
        icon={<ChevronsLeft aria-hidden="true" size={18} />}
        onClick={onFirst}
        disabled={page <= 1}
      />
      <IconButton
        label="Previous page"
        icon={<ChevronLeft aria-hidden="true" size={18} />}
        onClick={onPrevious}
        disabled={page <= 1}
      />
      <span className="ds-pagination-status" aria-live="polite">Page {page} of {Math.max(totalPages, 1)}</span>
      <IconButton
        label="Next page"
        icon={<ChevronRight aria-hidden="true" size={18} />}
        onClick={onNext}
        disabled={page >= totalPages}
      />
      <IconButton
        label="Last page"
        icon={<ChevronsRight aria-hidden="true" size={18} />}
        onClick={onLast}
        disabled={page >= totalPages}
      />
    </nav>
  );
}
