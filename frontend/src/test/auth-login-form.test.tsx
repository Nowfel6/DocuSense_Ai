import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LoginForm } from "@/features/auth-login/login-form";
import { jsonResponse, loginSuccess } from "@/test/fixtures/auth-login";

const replace = vi.hoisted(() => vi.fn());
const refresh = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, refresh }),
}));

describe("auth login form", () => {
  beforeEach(() => {
    replace.mockReset();
    refresh.mockReset();
    vi.restoreAllMocks();
  });

  it("validates locally, associates errors, and focuses the first invalid field", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const user = userEvent.setup();
    render(<LoginForm returnTo="/dashboard" />);

    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(fetchSpy).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Email")).toHaveFocus();
    expect(screen.getByLabelText("Email")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByText("Enter a valid email address.")).toBeInTheDocument();
    expect(screen.getByText("Enter your password.")).toBeInTheDocument();
  });

  it("toggles password visibility without changing the value", async () => {
    const user = userEvent.setup();
    render(<LoginForm returnTo="/dashboard" />);
    const password = screen.getByLabelText("Password");
    await user.type(password, "preserved secret");
    await user.click(screen.getByRole("button", { name: "Show password" }));
    expect(password).toHaveAttribute("type", "text");
    expect(password).toHaveValue("preserved secret");
    expect(screen.getByRole("button", { name: "Hide password" })).toHaveAttribute("aria-pressed", "true");
  });

  it("clears and focuses password after invalid credentials", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({
      success: false,
      error: { code: "INVALID_CREDENTIALS", message: "raw backend text" },
      request_id: "req_login_401",
    }, 401));
    const user = userEvent.setup();
    render(<LoginForm returnTo="/dashboard" />);
    await user.type(screen.getByLabelText("Email"), " operator@example.test ");
    await user.type(screen.getByLabelText("Password"), "wrong password");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByText("Sign in failed")).toBeInTheDocument();
    expect(screen.getByText("The email or password is incorrect.")).toBeInTheDocument();
    expect(screen.queryByText("raw backend text")).not.toBeInTheDocument();
    expect(screen.getByText("Request ID: req_login_401")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByLabelText("Password")).toHaveFocus());
    expect(screen.getByLabelText("Password")).toHaveValue("");
  });

  it("submits once while pending and replaces with the safe destination on success", async () => {
    let resolveRequest: ((response: Response) => void) | undefined;
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation(() => new Promise((resolve) => {
      resolveRequest = resolve;
    }));
    const user = userEvent.setup();
    render(<LoginForm returnTo="/dashboard" />);
    await user.type(screen.getByLabelText("Email"), "operator@example.test");
    await user.type(screen.getByLabelText("Password"), "correct password");
    const submit = screen.getByRole("button", { name: "Sign in" });
    await user.click(submit);
    await user.click(screen.getByRole("button", { name: "Signing in…" }));
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "Signing in…" })).toBeDisabled();

    resolveRequest?.(jsonResponse(loginSuccess));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/dashboard"));
    expect(refresh).toHaveBeenCalledOnce();
  });
});
