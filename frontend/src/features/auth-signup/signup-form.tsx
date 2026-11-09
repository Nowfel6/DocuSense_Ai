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
import { Checkbox, SelectField, TextField } from "@/components/ui/fields";

import { PasswordField } from "../auth-login/password-field";
import { createSignupAccount, SignupError, type SignupErrorCode } from "./signup-client";

interface FormError {
  title: string;
  message: string;
  requestId?: string;
}

interface SignupState {
  fullName: string;
  organizationName: string;
  businessType: "importer" | "trading" | "logistics" | "";
  country: string;
  email: string;
  password: string;
  passwordVisible: boolean;
  confirmPassword: string;
  confirmPasswordVisible: boolean;
  agreeToTerms: boolean;
  hydrated: boolean;
  fieldErrors: Partial<Record<
    "fullName" | "organizationName" | "businessType" | "country" | "email" | "password" | "confirmPassword" | "agreeToTerms",
    string
  >>;
  submission: "idle" | "submitting" | "failed";
  formError?: FormError;
}

type SignupAction =
  | { type: "full_name"; value: string }
  | { type: "organization_name"; value: string }
  | { type: "business_type"; value: SignupState["businessType"] }
  | { type: "country"; value: string }
  | { type: "email"; value: string }
  | { type: "password"; value: string }
  | { type: "password_visible"; value: boolean }
  | { type: "confirm_password"; value: string }
  | { type: "confirm_password_visible"; value: boolean }
  | { type: "agree_to_terms"; value: boolean }
  | { type: "hydrated" }
  | { type: "submitting" }
  | { type: "validation"; errors: SignupState["fieldErrors"] }
  | { type: "failure"; error: FormError };

const BUSINESS_TYPE_OPTIONS = [
  ["importer", "Importer"],
  ["trading", "Trading company"],
  ["logistics", "Logistics provider"],
] as const;

const COUNTRY_OPTIONS = [
  ["AU", "Australia"], ["BD", "Bangladesh"], ["BR", "Brazil"], ["CA", "Canada"],
  ["CN", "China"], ["DE", "Germany"], ["EG", "Egypt"], ["ES", "Spain"],
  ["FR", "France"], ["GB", "United Kingdom"], ["HK", "Hong Kong SAR"],
  ["ID", "Indonesia"], ["IN", "India"], ["IT", "Italy"], ["JP", "Japan"],
  ["KE", "Kenya"], ["KR", "South Korea"], ["MX", "Mexico"], ["MY", "Malaysia"],
  ["NL", "Netherlands"], ["NZ", "New Zealand"], ["PH", "Philippines"],
  ["PK", "Pakistan"], ["SA", "Saudi Arabia"], ["SG", "Singapore"],
  ["TH", "Thailand"], ["TR", "Türkiye"], ["US", "United States"],
  ["VN", "Vietnam"], ["ZA", "South Africa"],
] as const;

const initialState: SignupState = {
  fullName: "",
  organizationName: "",
  businessType: "",
  country: "BD",
  email: "",
  password: "",
  passwordVisible: false,
  confirmPassword: "",
  confirmPasswordVisible: false,
  agreeToTerms: false,
  hydrated: false,
  fieldErrors: {},
  submission: "idle",
};

function reducer(state: SignupState, action: SignupAction): SignupState {
  switch (action.type) {
    case "full_name":
      return { ...state, fullName: action.value, fieldErrors: { ...state.fieldErrors, fullName: undefined }, formError: undefined, submission: "idle" };
    case "organization_name":
      return { ...state, organizationName: action.value, fieldErrors: { ...state.fieldErrors, organizationName: undefined }, formError: undefined, submission: "idle" };
    case "business_type":
      return { ...state, businessType: action.value, fieldErrors: { ...state.fieldErrors, businessType: undefined }, formError: undefined, submission: "idle" };
    case "country":
      return { ...state, country: action.value, fieldErrors: { ...state.fieldErrors, country: undefined }, formError: undefined, submission: "idle" };
    case "email":
      return { ...state, email: action.value, fieldErrors: { ...state.fieldErrors, email: undefined }, formError: undefined, submission: "idle" };
    case "password":
      return { ...state, password: action.value, fieldErrors: { ...state.fieldErrors, password: undefined, confirmPassword: undefined }, formError: undefined, submission: "idle" };
    case "password_visible":
      return { ...state, passwordVisible: action.value };
    case "confirm_password":
      return { ...state, confirmPassword: action.value, fieldErrors: { ...state.fieldErrors, confirmPassword: undefined }, formError: undefined, submission: "idle" };
    case "confirm_password_visible":
      return { ...state, confirmPasswordVisible: action.value };
    case "agree_to_terms":
      return { ...state, agreeToTerms: action.value, fieldErrors: { ...state.fieldErrors, agreeToTerms: undefined }, formError: undefined, submission: "idle" };
    case "hydrated":
      return { ...state, hydrated: true };
    case "submitting":
      return { ...state, submission: "submitting", fieldErrors: {}, formError: undefined };
    case "validation":
      return { ...state, submission: "failed", fieldErrors: action.errors, formError: undefined };
    case "failure":
      return { ...state, submission: "failed", formError: action.error };
  }
}

function errorCopy(code: SignupErrorCode, requestId?: string): FormError {
  switch (code) {
    case "EMAIL_TAKEN":
      return { title: "Email already in use", message: "An account with this email already exists. Try signing in instead.", requestId };
    case "INVALID_REQUEST":
    case "VALIDATION_ERROR":
    case "REQUEST_TOO_LARGE":
      return { title: "Check your details", message: "Review the highlighted fields and try again.", requestId };
    case "RATE_LIMITED":
      return { title: "Too many attempts", message: "Wait a moment before trying again.", requestId };
    case "NETWORK_OFFLINE":
      return { title: "Can’t reach DocuSense", message: "Check your connection and try again.", requestId };
    case "AUTH_SERVICE_UNAVAILABLE":
      return { title: "Sign up unavailable", message: "The sign-up service could not be reached. Try again.", requestId };
    case "SESSION_UNAVAILABLE":
    case "AUTH_CONTRACT_INVALID":
      return { title: "Sign up unavailable", message: "Contact your administrator if this continues.", requestId };
    case "INVALID_ORIGIN":
      return { title: "Sign up could not continue", message: "Refresh the page and try again.", requestId };
    case "AUTH_RESPONSE_INVALID":
      return {
        title: "Sign up could not be completed",
        message: "Try again. If this continues, share the request ID with support.",
        requestId,
      };
    default:
      return { title: "Sign up could not be completed", message: "Try again.", requestId };
  }
}

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+$/;

interface ClientValidation {
  ok: boolean;
  errors: SignupState["fieldErrors"];
}

function validateClient(state: SignupState): ClientValidation {
  const errors: SignupState["fieldErrors"] = {};
  if (!state.fullName.trim()) errors.fullName = "Enter your full name.";
  else if (state.fullName.trim().length > 100) errors.fullName = "Full name must be 100 characters or fewer.";
  if (!state.organizationName.trim()) errors.organizationName = "Enter your organization name.";
  else if (state.organizationName.trim().length > 255) errors.organizationName = "Organization name must be 255 characters or fewer.";
  if (!state.businessType) errors.businessType = "Pick a business type.";
  if (!/^[A-Z]{2}$/.test(state.country)) errors.country = "Pick a country.";
  if (!state.email.trim()) errors.email = "Enter your work email.";
  else if (!EMAIL_PATTERN.test(state.email.trim()) || state.email.trim().length > 255) errors.email = "Enter a valid email address.";
  if (!state.password) errors.password = "Enter a password.";
  else if (state.password.length < 8 || state.password.length > 128) errors.password = "Password must be 8–128 characters.";
  else if (!/[A-Za-z]/.test(state.password) || !/\d/.test(state.password)) errors.password = "Password must include at least one letter and one number.";
  if (!state.confirmPassword) errors.confirmPassword = "Re-enter your password.";
  else if (state.confirmPassword !== state.password) errors.confirmPassword = "Passwords don’t match.";
  if (!state.agreeToTerms) errors.agreeToTerms = "Accept the terms to continue.";
  return { ok: Object.keys(errors).length === 0, errors };
}

function focusFirstError(fieldErrors: ClientValidation["errors"]) {
  const order: Array<keyof ClientValidation["errors"]> = [
    "fullName", "organizationName", "businessType", "country",
    "email", "password", "confirmPassword", "agreeToTerms",
  ];
  for (const key of order) {
    if (fieldErrors[key]) return key;
  }
  return undefined;
}

export function SignupForm({ returnTo }: { returnTo: string }) {
  const [state, dispatch] = useReducer(reducer, initialState);
  const router = useRouter();
  const refs = {
    fullName: useRef<HTMLInputElement>(null),
    organizationName: useRef<HTMLInputElement>(null),
    businessType: useRef<HTMLSelectElement>(null),
    country: useRef<HTMLSelectElement>(null),
    email: useRef<HTMLInputElement>(null),
    password: useRef<HTMLInputElement>(null),
    confirmPassword: useRef<HTMLInputElement>(null),
    agreeToTerms: useRef<HTMLInputElement>(null),
    error: useRef<HTMLDivElement>(null),
  };
  const requestRef = useRef<AbortController | null>(null);
  const submittingRef = useRef(false);

  useEffect(() => {
    dispatch({ type: "hydrated" });
    return () => requestRef.current?.abort();
  }, []);

  useEffect(() => {
    if (
      state.formError &&
      state.formError.title !== "Check your details"
    ) {
      refs.error.current?.focus();
    }
  }, [state.formError]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submittingRef.current) return;

    const validation = validateClient(state);
    if (!validation.ok) {
      dispatch({ type: "validation", errors: validation.errors });
      const first = focusFirstError(validation.errors);
      if (first === "fullName") refs.fullName.current?.focus();
      else if (first === "organizationName") refs.organizationName.current?.focus();
      else if (first === "businessType") refs.businessType.current?.focus();
      else if (first === "country") refs.country.current?.focus();
      else if (first === "email") refs.email.current?.focus();
      else if (first === "password") refs.password.current?.focus();
      else if (first === "confirmPassword") refs.confirmPassword.current?.focus();
      else if (first === "agreeToTerms") refs.agreeToTerms.current?.focus();
      return;
    }

    submittingRef.current = true;
    const controller = new AbortController();
    requestRef.current = controller;
    dispatch({ type: "submitting" });
    try {
      await createSignupAccount({
        full_name: state.fullName.trim(),
        organization_name: state.organizationName.trim(),
        business_type: state.businessType as "importer" | "trading" | "logistics",
        country: state.country,
        email: state.email.trim(),
        password: state.password,
        agree_to_terms: true,
      }, controller.signal);
      router.replace(returnTo as Route);
      router.refresh();
    } catch (error) {
      if (controller.signal.aborted) return;
      const signupError = error instanceof SignupError ? error : new SignupError("UNKNOWN");
      dispatch({ type: "failure", error: errorCopy(signupError.code, signupError.requestId) });
      if (signupError.code === "EMAIL_TAKEN") {
        window.requestAnimationFrame(() => refs.email.current?.focus());
      } else if (signupError.code === "INVALID_REQUEST" || signupError.code === "VALIDATION_ERROR") {
        window.requestAnimationFrame(() => refs.email.current?.focus());
      }
    } finally {
      submittingRef.current = false;
      requestRef.current = null;
    }
  }

  const pending = state.submission === "submitting";

  return (
    <form className="ds-signup-form" data-hydrated={state.hydrated} noValidate onSubmit={handleSubmit}>
      <TextField
        ref={refs.fullName}
        label="Full name"
        name="full_name"
        type="text"
        autoComplete="name"
        autoCapitalize="words"
        spellCheck={false}
        required
        disabled={pending}
        value={state.fullName}
        error={state.fieldErrors.fullName}
        onChange={(event) => dispatch({ type: "full_name", value: event.target.value })}
      />
      <TextField
        ref={refs.organizationName}
        label="Organization name"
        name="organization_name"
        type="text"
        autoComplete="organization"
        autoCapitalize="words"
        spellCheck={false}
        required
        disabled={pending}
        value={state.organizationName}
        error={state.fieldErrors.organizationName}
        onChange={(event) => dispatch({ type: "organization_name", value: event.target.value })}
      />
      <SelectField
        ref={refs.businessType}
        label="Business type"
        name="business_type"
        required
        disabled={pending}
        value={state.businessType}
        error={state.fieldErrors.businessType}
        onChange={(event) => dispatch({ type: "business_type", value: event.target.value as SignupState["businessType"] })}
      >
        <option value="" disabled>Select a business type</option>
        {BUSINESS_TYPE_OPTIONS.map(([value, label]) => (
          <option key={value} value={value}>{label}</option>
        ))}
      </SelectField>
      <SelectField
        ref={refs.country}
        label="Country"
        name="country"
        required
        disabled={pending}
        value={state.country}
        error={state.fieldErrors.country}
        onChange={(event) => dispatch({ type: "country", value: event.target.value })}
      >
        {COUNTRY_OPTIONS.map(([code, name]) => (
          <option key={code} value={code}>{`${name} (${code})`}</option>
        ))}
      </SelectField>
      <TextField
        ref={refs.email}
        label="Work email"
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
        ref={refs.password}
        name="password"
        autoComplete="new-password"
        required
        disabled={pending}
        value={state.password}
        error={state.fieldErrors.password}
        visible={state.passwordVisible}
        onVisibleChange={(value) => dispatch({ type: "password_visible", value })}
        onChange={(event) => dispatch({ type: "password", value: event.target.value })}
        helpText="8–128 characters, with at least one letter and one number."
      />
      <PasswordField
        ref={refs.confirmPassword}
        name="confirm_password"
        autoComplete="new-password"
        required
        disabled={pending}
        value={state.confirmPassword}
        error={state.fieldErrors.confirmPassword}
        visible={state.confirmPasswordVisible}
        onVisibleChange={(value) => dispatch({ type: "confirm_password_visible", value })}
        onChange={(event) => dispatch({ type: "confirm_password", value: event.target.value })}
      />
      <Checkbox
        ref={refs.agreeToTerms}
        name="agree_to_terms"
        checked={state.agreeToTerms}
        disabled={pending}
        error={state.fieldErrors.agreeToTerms}
        onChange={(event) => dispatch({ type: "agree_to_terms", value: event.target.checked })}
        label={<>I agree to the DocuSense terms of service and data handling policy.</>}
      />
      {state.formError ? (
        <div ref={refs.error} tabIndex={-1} className="ds-signup-error-summary">
          <Alert tone="error" title={state.formError.title} message={state.formError.message} />
          {state.formError.requestId ? (
            <p className="ds-signup-request-id">Request ID: {state.formError.requestId}</p>
          ) : null}
        </div>
      ) : null}
      <Button type="submit" variant="primary" isPending={pending} pendingLabel="Creating workspace…">
        Create workspace
      </Button>
    </form>
  );
}
