import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createRef, useState } from "react";
import { describe, expect, it } from "vitest";

import { Button, Dialog, Tabs } from "@/components/ui";

describe("tabs and dialogs", () => {
  it("moves tab focus with arrow keys and activates on click", async () => {
    const user = userEvent.setup();
    function Harness() {
      const [selected, setSelected] = useState("one");
      return <Tabs label="Test tabs" selectedId={selected} onSelect={setSelected} items={[
        { id: "one", label: "One", panel: "First panel" },
        { id: "two", label: "Two", panel: "Second panel" },
      ]} />;
    }
    render(<Harness />);
    const first = screen.getByRole("tab", { name: "One" });
    const second = screen.getByRole("tab", { name: "Two" });
    first.focus();
    await user.keyboard("{ArrowRight}");
    expect(second).toHaveFocus();
    await user.click(second);
    expect(second).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel")).toHaveTextContent("Second panel");
  });

  it("returns focus to its trigger when closed", async () => {
    const user = userEvent.setup();
    const trigger = createRef<HTMLButtonElement>();
    function Harness() {
      const [open, setOpen] = useState(false);
      return <><Button ref={trigger} onClick={() => setOpen(true)}>Open</Button><Dialog open={open} title="Example" onClose={() => setOpen(false)} returnFocusRef={trigger} /></>;
    }
    render(<Harness />);
    await user.click(screen.getByRole("button", { name: "Open" }));
    await user.click(screen.getByRole("button", { name: "Close dialog" }));
    expect(screen.getByRole("button", { name: "Open" })).toHaveFocus();
  });
});
