import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AppShell } from "@/components/shell";
import { operatorProfile } from "@/test/fixtures/foundation-shell";

vi.mock("next/navigation", () => ({
  usePathname: () => "/dashboard",
  useRouter: () => ({ replace: vi.fn() }),
}));

describe("application shell", () => {
  beforeEach(() => window.localStorage.clear());

  it("renders landmarks and role-filtered navigation", () => {
    render(<AppShell profile={operatorProfile}><h1>Dashboard</h1></AppShell>);
    expect(screen.getByRole("navigation", { name: "Primary navigation" })).toBeInTheDocument();
    expect(screen.getByRole("main")).toContainElement(screen.getByRole("heading", { name: "Dashboard" }));
    expect(screen.queryByRole("link", { name: /API & integrations/ })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "All documents" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Upload" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Dashboard" })).toHaveAttribute("aria-current", "page");
    expect(screen.queryByRole("button", { name: "Notifications" })).not.toBeInTheDocument();
  });

  it("persists only the visual collapse preference", async () => {
    const user = userEvent.setup();
    render(<AppShell profile={operatorProfile}><h1>Dashboard</h1></AppShell>);
    await user.click(screen.getByRole("button", { name: "Collapse navigation" }));
    await waitFor(() => expect(window.localStorage.getItem("docusense.sidebar.collapsed")).toBe("true"));
    expect(Object.keys(window.localStorage)).toEqual(["docusense.sidebar.collapsed"]);
  });
});
