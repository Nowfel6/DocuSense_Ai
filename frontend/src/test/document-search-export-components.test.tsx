import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ExportStatusPanel } from "@/features/document-search-export/export-status-panel";
import { SearchResults } from "@/features/document-search-export/search-results";

import { documentId, exportId, exportResource, searchEnvelope } from "./fixtures/document-search-export";

describe("document search/export components", () => {
  it("selects only backend-eligible rows on the visible page", async () => {
    const user = userEvent.setup();
    const onTogglePage = vi.fn();
    render(<SearchResults envelope={searchEnvelope()} semantic canExport selected={new Set()} onToggle={vi.fn()} onTogglePage={onTogglePage} onPage={vi.fn()} />);
    await user.click(screen.getByRole("checkbox", { name: "Select eligible documents on this page" }));
    expect(onTogglePage).toHaveBeenCalledWith(true);
    expect(screen.getAllByText("Similarity 0.875").length).toBeGreaterThan(0);
    expect(screen.getAllByRole("link", { name: "Open" })[0]).toHaveAttribute("href", `/documents/${documentId}`);
  });

  it("does not render selection when export is unavailable", () => {
    render(<SearchResults envelope={searchEnvelope()} semantic canExport={false} selected={new Set()} onToggle={vi.fn()} onTogglePage={vi.fn()} onPage={vi.fn()} />);
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });

  it("offers an authorized same-origin download only when complete", () => {
    const { rerender } = render(<ExportStatusPanel resource={exportResource()} stale={false} error={null} onRefresh={vi.fn()} onDismiss={vi.fn()} onNewExport={vi.fn()} />);
    expect(screen.getByRole("link", { name: "Download" })).toHaveAttribute("href", `/api/backend/api/v1/exports/${exportId}/download`);
    rerender(<ExportStatusPanel resource={exportResource({ status: "expired", download_url: null })} stale={false} error={null} onRefresh={vi.fn()} onDismiss={vi.fn()} onNewExport={vi.fn()} />);
    expect(screen.queryByRole("link", { name: "Download" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create new export" })).toBeInTheDocument();
  });
});
