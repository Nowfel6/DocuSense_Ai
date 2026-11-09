import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Pagination, TableFrame } from "@/components/ui";

describe("table and pagination patterns", () => {
  it("renders an explicit table empty state", () => {
    render(
      <TableFrame caption="Documents" headers={["Name", "Status"]} state="empty" stateContent="No documents yet.">
        <tr><td>Unused ready row</td></tr>
      </TableFrame>,
    );
    expect(screen.getByRole("table", { name: "Documents" })).toHaveTextContent("No documents yet.");
    expect(screen.queryByText("Unused ready row")).not.toBeInTheDocument();
  });

  it("renders structural skeleton rows while loading", () => {
    const { container } = render(
      <TableFrame caption="Documents" headers={["Name", "Status"]} state="loading">
        <tr><td>Unused ready row</td></tr>
      </TableFrame>,
    );
    expect(container.querySelectorAll(".ds-skeleton")).toHaveLength(3);
  });

  it("exposes first, previous, next, and last controls", async () => {
    const onNext = vi.fn();
    const onLast = vi.fn();
    const user = userEvent.setup();
    render(
      <Pagination
        page={1}
        totalPages={4}
        onFirst={vi.fn()}
        onPrevious={vi.fn()}
        onNext={onNext}
        onLast={onLast}
      />,
    );
    expect(screen.getByRole("button", { name: "First page" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Previous page" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Next page" }));
    await user.click(screen.getByRole("button", { name: "Last page" }));
    expect(onNext).toHaveBeenCalledOnce();
    expect(onLast).toHaveBeenCalledOnce();
  });
});
