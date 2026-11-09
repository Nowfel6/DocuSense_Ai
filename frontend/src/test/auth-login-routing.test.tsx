import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LoginView } from "@/features/auth-login/login-view";
import { safeReturnPath } from "@/lib/auth/return-path";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn() }),
}));

describe("auth login routing and query states", () => {
  it.each([
    ["/dashboard", "/dashboard"],
    ["/dashboard?tab=ready#main", "/dashboard?tab=ready#main"],
    ["/documents", "/documents"],
    ["/documents/upload", "/documents/upload"],
    ["https://evil.invalid/steal", "/dashboard"],
    ["//evil.invalid/steal", "/dashboard"],
    ["/login?reason=session-expired", "/dashboard"],
    ["/api/session/logout", "/dashboard"],
  ])("normalizes %s to %s", (candidate, expected) => {
    expect(safeReturnPath(candidate)).toBe(expected);
  });

  it("renders only recognized notice copy", () => {
    const { rerender } = render(<LoginView returnTo="/dashboard" notice="signed-out" />);
    expect(screen.getByText("You’re signed out")).toBeInTheDocument();
    rerender(<LoginView returnTo="/dashboard" notice="session-expired" />);
    expect(screen.getByText("Your session ended")).toBeInTheDocument();
    expect(screen.queryByText("You’re signed out")).not.toBeInTheDocument();
    rerender(<LoginView returnTo="/dashboard" notice={null} />);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});
