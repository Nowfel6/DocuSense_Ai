import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import SettingsApiPage from "@/app/(authenticated)/settings/api/page";
import { breadcrumbsForPathname, navigationForRole } from "@/components/shell/navigation";
import { SettingsApiPlaceholderView } from "@/features/settings-api-placeholder/settings-api-placeholder-view";
import type { SessionProfile } from "@/lib/auth/session-types";

const sessionState = vi.hoisted(() => ({ current: null as SessionProfile | null }));

vi.mock("@/lib/auth/session", () => ({
  readSession: vi.fn(async () => sessionState.current),
}));

const baseSession: SessionProfile = {
  userId: "test-user",
  email: "user@example.invalid",
  displayName: "Test User",
  role: "admin",
  organizationId: "test-organization",
  organizationName: "Test Organization",
};

describe("settings API placeholder", () => {
  it("exposes navigation and breadcrumbs only as approved", () => {
    expect(navigationForRole("admin").map((item) => item.href)).toContain("/settings/api");
    expect(navigationForRole("operator").map((item) => item.href)).not.toContain("/settings/api");
    expect(navigationForRole("viewer").map((item) => item.href)).not.toContain("/settings/api");
    expect(breadcrumbsForPathname("/settings/api")).toEqual([
      { label: "Settings" },
      { label: "API & Integrations" },
    ]);
  });

  it("renders the approved static content without a feature request or management controls", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<SettingsApiPlaceholderView />);

    expect(screen.getByRole("heading", { level: 1, name: "API & Integrations" })).toBeInTheDocument();
    expect(screen.getByText("Not enabled in this release")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Developer access is coming later" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Return to dashboard" })).toHaveAttribute("href", "/dashboard");
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(fetchSpy).not.toHaveBeenCalled();

    fetchSpy.mockRestore();
  });

  it("allows an administrator through the server route", async () => {
    sessionState.current = baseSession;
    render(await SettingsApiPage());

    expect(screen.getByRole("heading", { level: 1, name: "API & Integrations" })).toBeInTheDocument();
    expect(screen.queryByText("This area is restricted to administrators.")).not.toBeInTheDocument();
  });

  it("denies non-admin roles and returns no feature content without a session", async () => {
    for (const role of ["operator", "viewer"] as const) {
      sessionState.current = { ...baseSession, role };
      const { unmount } = render(await SettingsApiPage());
      expect(screen.getByRole("heading", { name: "API & integrations unavailable" })).toBeInTheDocument();
      expect(screen.queryByText("Developer access is coming later")).not.toBeInTheDocument();
      unmount();
    }

    sessionState.current = null;
    expect(await SettingsApiPage()).toBeNull();
  });
});

