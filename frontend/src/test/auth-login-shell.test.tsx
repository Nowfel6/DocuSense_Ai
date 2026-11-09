import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AppShell } from "@/components/shell";
import { PublicShell } from "@/components/shell/public-shell";
import { authProfile } from "@/test/fixtures/auth-login";

const replace = vi.hoisted(() => vi.fn());
const refresh = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({
  usePathname: () => "/dashboard",
  useRouter: () => ({ replace, refresh }),
}));

describe("authenticated shell rollout behavior", () => {
  beforeEach(() => {
    replace.mockReset();
    refresh.mockReset();
    window.localStorage.clear();
    vi.restoreAllMocks();
  });

  it("shows released document navigation and no placeholder notifications", () => {
    render(<AppShell profile={authProfile}><h1>Workspace ready</h1></AppShell>);
    expect(screen.getAllByRole("link", { name: "Dashboard" })).toHaveLength(1);
    expect(screen.getByRole("link", { name: "All documents" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Upload" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Notifications" })).not.toBeInTheDocument();
  });

  it("prevents duplicate logout and returns with a signed-out notice", async () => {
    let resolveLogout: ((response: Response) => void) | undefined;
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation(() => new Promise((resolve) => {
      resolveLogout = resolve;
    }));
    const user = userEvent.setup();
    render(<AppShell profile={authProfile}><h1>Workspace ready</h1></AppShell>);
    await user.click(screen.getByLabelText("Account menu for Example Operator"));
    const signOut = screen.getByRole("button", { name: "Sign out" });
    await user.click(signOut);
    await user.click(signOut);
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(signOut).toBeDisabled();
    resolveLogout?.(jsonResponse({ success: true }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login?signedOut=1"));
    expect(refresh).toHaveBeenCalledOnce();
  });

  it("adds the expiry reason and encodes the return path", () => {
    render(<AppShell profile={authProfile}><h1>Workspace ready</h1></AppShell>);
    window.dispatchEvent(new CustomEvent("docusense:session-expired", {
      detail: { returnTo: "/dashboard?tab=ready" },
    }));
    expect(replace).toHaveBeenCalledWith(
      "/login?reason=session-expired&returnTo=%2Fdashboard%3Ftab%3Dready",
    );
  });

  it("keeps the Login public shell and links its wordmark home", () => {
    render(<PublicShell><h1>Sign in to your workspace</h1></PublicShell>);
    expect(screen.getByRole("banner")).toBeInTheDocument();
    expect(screen.getByRole("main")).toContainElement(
      screen.getByRole("heading", { name: "Sign in to your workspace" }),
    );
    expect(screen.getByRole("link", { name: "DocuSense home" })).toHaveAttribute("href", "/");
  });
});

function jsonResponse(payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    headers: { "content-type": "application/json" },
  });
}
