import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Button, Checkbox, SelectField, TextField } from "@/components/ui";

describe("foundation controls", () => {
  it("blocks duplicate presses while pending", async () => {
    const onClick = vi.fn();
    const user = userEvent.setup();
    render(<Button isPending onClick={onClick}>Save</Button>);
    const button = screen.getByRole("button", { name: "Working…" });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");
    await user.click(button);
    expect(onClick).not.toHaveBeenCalled();
  });

  it("associates labels, guidance, and errors with fields", () => {
    render(<TextField label="Reference" helpText="Use the source reference." error="Reference is required." />);
    const field = screen.getByRole("textbox", { name: "Reference" });
    expect(field).toHaveAccessibleDescription("Use the source reference. Reference is required.");
    expect(field).toHaveAttribute("aria-invalid", "true");
  });

  it("uses native accessible checkbox and select controls", () => {
    render(<><Checkbox label="Include tables" /><SelectField label="Priority"><option>Normal</option></SelectField></>);
    expect(screen.getByRole("checkbox", { name: "Include tables" })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Priority" })).toBeInTheDocument();
  });
});
