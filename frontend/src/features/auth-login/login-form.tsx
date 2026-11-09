"use client";

import type { Route } from "next";
import { useRouter } from "next/navigation";
import {
  useEffect,
  useReducer,
  useRef,
  type FormEvent,
} from "react";

import { Button } from "@/components/ui/button";
import { Alert } from "@/components/ui/feedback";
import { TextField } from "@/components/ui/fields";

import { PasswordField } from "./password-field";
import { createLoginSession, LoginError, type LoginErrorCode } from "./session-client";

interface FormError {
  title: string;
  message: string;
  requestId?: string;
}

interface LoginState {
  email: string;
  password: string;
  passwordVisible: boolean;
  hydrated: boolean;
  fieldErrors: { email?: string; password?: string };
  submission: "idle" | "submitting" | "failed";
  formError?: FormError;
}

type LoginAction =
  | { type: "email"; value: string }
  | { type: "password"; value: string }
  | { type: "visibility"; value: boolean }
  | { type: "hydrated" }
  | { type: "submitting"; email: string }
  | { type: "validation"; errors: LoginState["fieldErrors"] }
  | { type: "failure"; error: FormError; clearPassword: boolean };

const initialState: LoginState = {
  email: "",
  password: "",
  passwordVisible: false,
  hydrated: false,
  fieldErrors: {},
  submission: "idle",
};

function reducer(state: LoginState, action: LoginAction): LoginState {
  switch (action.type) {
    case "email":
      return {
        ...state,
        email: action.value,
        fieldErrors: { ...state.fieldErrors, email: undefined },
        formError: undefined,
        submission: "idle",
      };
    case "password":
      return {
        ...state,
        password: action.value,
        fieldErrors: { ...state.fieldErrors, password: undefined },
        formError: undefined,
        submission: "idle",
      };
    case "visibility":
      return { ...state, passwordVisible: action.value };
    case "hydrated":
      return { ...state, hydrated: true };
    case "submitting":
      return {
        ...state,
        email: action.email,
        submission: "submitting",
        fieldErrors: {},
        formError: undefined,
      };
    case "validation":
      return { ...state, submission: "failed", fieldErrors: action.errors, formError: undefined };
    case "failure":
      return {
        ...state,
        password: action.clearPassword ? "" : state.password,
        submission: "failed",
        formError: action.error,
      };
  }
}

function errorCopy(code: LoginErrorCode, requestId?: string): FormError {
  switch (code) {
    case "INVALID_CREDENTIALS":
      return { title: "Sign in failed", message: "The email or password is incorrect.", requestId };
    case "INVALID_REQUEST":
    case "REQUEST_TOO_LARGE":
      return { title: "Check your details", message: "Enter a valid email and password, then try again.", requestId };
    case "RATE_LIMITED":
      return { title: "Too many attempts", message: "Wait a moment before trying to sign in again.", requestId };
    case "NETWORK_OFFLINE":
      return { title: "Can’t reach DocuSense", message: "Check your connection and try again.", requestId };
    case "AUTH_SERVICE_UNAVAILABLE":
      return { title: "Sign in unavailable", message: "The sign-in service could not be reached. Try again.", requestId };
    case "SESSION_UNAVAILABLE":
    case "AUTH_CONTRACT_INVALID":
      return { title: "Sign in unavailable", message: "Contact your administrator if this continues.", requestId };
    case "INVALID_ORIGIN":
      return { title: "Sign in could not continue", message: "Refresh the page and try again.", requestId };
    case "AUTH_RESPONSE_INVALID":
      return {
        title: "Sign in could not be completed",
        message: "Try again. If this continues, share the request ID with support.",
        requestId,
      };
    default:
      return { title: "Sign in could not be completed", message: "Try again.", requestId };
  }
}

function validEmail(value: string): boolean {
  return /^[^\s@]+@[^\s@]+$/.test(value);
}

export function LoginForm({ returnTo }: { returnTo: string }) {
  const [state, dispatch] = useReducer(reducer, initialState);
  const router = useRouter();
  const emailRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);
  const errorRef = useRef<HTMLDivElement>(null);
  const requestRef = useRef<AbortController | null>(null);
  const submittingRef = useRef(false);

  useEffect(() => {
    dispatch({ type: "hydrated" });
    return () => requestRef.current?.abort();
  }, []);

  useEffect(() => {
    if (
      state.formError &&
      state.formError.title !== "Sign in failed" &&
      state.formError.title !== "Check your details"
    ) {
      errorRef.current?.focus();
    }
  }, [state.formError]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submittingRef.current) return;

    const submitted = new FormData(event.currentTarget);
    const rawEmail = submitted.get("email");
    const rawPassword = submitted.get("password");
    const email = typeof rawEmail === "string" ? rawEmail.trim() : "";
    const password = typeof rawPassword === "string" ? rawPassword : "";
    const fieldErrors: LoginState["fieldErrors"] = {};
    if (!email || !validEmail(email)) fieldErrors.email = "Enter a valid email address.";
    if (!password) fieldErrors.password = "Enter your password.";
    if (fieldErrors.email || fieldErrors.password) {
      dispatch({ type: "validation", errors: fieldErrors });
      if (fieldErrors.email) emailRef.current?.focus();
      else passwordRef.current?.focus();
      return;
    }

    submittingRef.current = true;
    const controller = new AbortController();
    requestRef.current = controller;
    dispatch({ type: "submitting", email });
    try {
      await createLoginSession({ email, password }, controller.signal);
      router.replace(returnTo as Route);
      router.refresh();
    } catch (error) {
      if (controller.signal.aborted) return;
      const loginError = error instanceof LoginError ? error : new LoginError("UNKNOWN");
      const clearPassword = loginError.code === "INVALID_CREDENTIALS" ||
        loginError.code === "AUTH_RESPONSE_INVALID";
      dispatch({ type: "failure", error: errorCopy(loginError.code, loginError.requestId), clearPassword });
      if (loginError.code === "INVALID_CREDENTIALS") {
        window.requestAnimationFrame(() => passwordRef.current?.focus());
      } else if (loginError.code === "INVALID_REQUEST" || loginError.code === "REQUEST_TOO_LARGE") {
        window.requestAnimationFrame(() => emailRef.current?.focus());
      }
    } finally {
      submittingRef.current = false;
      requestRef.current = null;
    }
  }

  const pending = state.submission === "submitting";
  return (
    <form className="ds-login-form" data-hydrated={state.hydrated} noValidate onSubmit={handleSubmit}>
      <TextField
        ref={emailRef}
        label="Email"
        name="email"
        type="email"
        inputMode="email"
        autoComplete="email"
        autoCapitalize="none"
        autoCorrect="off"
        spellCheck={false}
        required
        disabled={pending}
        value={state.email}
        error={state.fieldErrors.email}
        onChange={(event) => dispatch({ type: "email", value: event.target.value })}
      />
      <PasswordField
        ref={passwordRef}
        name="password"
        autoComplete="current-password"
        required
        disabled={pending}
        value={state.password}
        error={state.fieldErrors.password}
        visible={state.passwordVisible}
        onVisibleChange={(value) => dispatch({ type: "visibility", value })}
        onChange={(event) => dispatch({ type: "password", value: event.target.value })}
      />
      {state.formError ? (
        <div ref={errorRef} tabIndex={-1} className="ds-login-error-summary">
          <Alert tone="error" title={state.formError.title} message={state.formError.message} />
          {state.formError.requestId ? (
            <p className="ds-login-request-id">Request ID: {state.formError.requestId}</p>
          ) : null}
        </div>
      ) : null}
      <Button type="submit" variant="primary" isPending={pending} pendingLabel="Signing in…">
        Sign in
      </Button>
      <details className="ds-login-demo-hint">
        <summary>Demo accounts</summary>
        <p>
          DocuSense ships pre-seeded demo accounts for local development only.
          Run <code>python backend/scripts/reset_demo_passwords.py</code> if sign in fails.
        </p>
        <dl>
          <dt>admin@acme.com</dt>
          <dd><code>AdminPassword123!</code></dd>
          <dt>operator@acme.com</dt>
          <dd><code>OperatorPassword123!</code></dd>
          <dt>viewer@acme.com</dt>
          <dd><code>ViewerPassword123!</code></dd>
        </dl>
      </details>
    </form>
  );
}
