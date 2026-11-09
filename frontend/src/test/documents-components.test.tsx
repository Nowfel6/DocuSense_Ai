import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { DocumentCollection } from "@/features/documents-list-upload-monitor/document-collection";
import { ProcessingStageRail } from "@/features/documents-list-upload-monitor/processing-stage-rail";
import { UploadComposer } from "@/features/documents-list-upload-monitor/upload-composer";
import { ApiError } from "@/lib/api/errors";

import { documentListFixture, uploadAcceptedFixture } from "./fixtures/documents-list-upload-monitor";

const uploadDocument = vi.hoisted(() => vi.fn());
vi.mock("@/features/documents-list-upload-monitor/upload-transport", () => ({ uploadDocument }));

describe("documents essential interactions", () => {
  it("renders document semantics without viewer monitor actions", () => {
    render(<DocumentCollection envelope={documentListFixture} role="viewer" onPage={vi.fn()} />);
    expect(screen.getAllByText("northstar-invoice-2026-0042.pdf").length).toBeGreaterThan(0);
    expect(screen.queryByRole("link", { name: "Monitor" })).not.toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "View details" })).toHaveLength(2);
  });

  it("renders exactly the five persisted processing stages", () => {
    render(<ProcessingStageRail stages={{ upload: "completed", partitioning: "completed", chunking: "completed", vectorizing: "in_progress", extracting: "pending" }} />);
    expect(screen.getAllByRole("listitem")).toHaveLength(5);
    expect(screen.getByText("Extraction & validation")).toBeInTheDocument();
    expect(screen.queryByText("Validation", { exact: true })).not.toBeInTheDocument();
  });

  it("requires explicit duplicate confirmation and focuses Cancel", async () => {
    const user = userEvent.setup();
    const accepted = vi.fn();
    uploadDocument
      .mockRejectedValueOnce(new ApiError("duplicate", { code: "DUPLICATE_FILE_DETECTED", status: 409 }))
      .mockResolvedValueOnce(uploadAcceptedFixture.data);
    render(<UploadComposer onAccepted={accepted} />);

    await user.upload(screen.getByLabelText("Choose document file"), new File(["pdf"], "invoice.pdf", { type: "application/pdf" }));
    await user.click(screen.getByRole("button", { name: "Upload document" }));
    const cancel = await screen.findByRole("button", { name: "Cancel" });
    await waitFor(() => expect(cancel).toHaveFocus());
    expect(uploadDocument).toHaveBeenLastCalledWith(expect.objectContaining({ confirmDuplicate: false }));

    await user.click(screen.getByRole("button", { name: "Upload another copy" }));
    await waitFor(() => expect(accepted).toHaveBeenCalledWith(uploadAcceptedFixture.data));
    expect(uploadDocument).toHaveBeenLastCalledWith(expect.objectContaining({ confirmDuplicate: true }));
  });
});
