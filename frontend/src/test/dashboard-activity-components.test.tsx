import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DashboardActivityView } from "@/features/dashboard-activity/dashboard-activity-view";

import { activityEnvelope, dashboardEnvelope } from "./fixtures/dashboard-activity";

const { replace, readDashboard, readActivity } = vi.hoisted(() => ({
  replace: vi.fn(),
  readDashboard: vi.fn(),
  readActivity: vi.fn(),
}));

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }) }));
vi.mock("@/features/dashboard-activity/api", async (original) => {
  const actual = await original<typeof import("@/features/dashboard-activity/api")>();
  return { ...actual, readDashboard, readActivity };
});

describe("dashboard/activity view", () => {
  beforeEach(() => {
    replace.mockReset(); readDashboard.mockReset(); readActivity.mockReset();
    readDashboard.mockResolvedValue(dashboardEnvelope());
    readActivity.mockResolvedValue(activityEnvelope("viewer"));
  });

  it("renders current, period, exact-data, and role-safe activity content", async () => {
    render(<DashboardActivityView role="viewer" initialState={{ query: { bucket: "day" } }} />);
    expect(await screen.findByRole("heading", { name: "Current workload" })).toBeInTheDocument();
    expect(screen.getByText("Initial deterministic validation pass rate")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Document volume" })).toBeInTheDocument();
    expect(await screen.findByText("Invoice ACME-1042")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Upload documents" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open document" })).toBeInTheDocument();
  });

  it("applies one explicit UTC range and updates the route", async () => {
    const user = userEvent.setup();
    render(<DashboardActivityView role="viewer" initialState={{ query: { bucket: "day" } }} />);
    await screen.findByRole("heading", { name: "Current workload" });
    await user.selectOptions(screen.getByLabelText("Range"), "custom");
    await user.type(screen.getByLabelText("From (UTC)"), "2026-08-01T00:00");
    await user.type(screen.getByLabelText("To (UTC, exclusive)"), "2026-08-02T00:00");
    await user.click(screen.getByRole("button", { name: "Apply" }));
    expect(replace).toHaveBeenCalledWith(expect.stringContaining("from=2026-08-01T00%3A00%3A00Z"), { scroll: false });
  });
});
