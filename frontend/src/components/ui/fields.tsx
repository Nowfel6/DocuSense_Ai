"use client";

import {
  forwardRef,
  useEffect,
  useId,
  useImperativeHandle,
  useRef,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
} from "react";

export type MessageTone = "help" | "error" | "success";

export function FormMessage({
  id,
  tone = "help",
  children,
}: {
  id?: string;
  tone?: MessageTone;
  children: ReactNode;
}) {
  return <p id={id} className="ds-field-message" data-tone={tone}>{children}</p>;
}

export interface TextFieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  helpText?: string;
  error?: string;
}

export const TextField = forwardRef<HTMLInputElement, TextFieldProps>(
  function TextField({ id, label, helpText, error, className = "", ...props }, ref) {
    const generatedId = useId();
    const inputId = id ?? generatedId;
    const helpId = helpText ? `${inputId}-help` : undefined;
    const errorId = error ? `${inputId}-error` : undefined;
    const describedBy = [helpId, errorId].filter(Boolean).join(" ") || undefined;

    return (
      <div className="ds-field">
        <label className="ds-label" htmlFor={inputId}>{label}</label>
        <input
          ref={ref}
          id={inputId}
          className={`ds-input ${className}`.trim()}
          aria-invalid={Boolean(error) || undefined}
          aria-describedby={describedBy}
          {...props}
        />
        {helpText ? <FormMessage id={helpId}>{helpText}</FormMessage> : null}
        {error ? <FormMessage id={errorId} tone="error">{error}</FormMessage> : null}
      </div>
    );
  },
);

export interface SelectFieldProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label: string;
  helpText?: string;
  error?: string;
  children: ReactNode;
}

export const SelectField = forwardRef<HTMLSelectElement, SelectFieldProps>(
  function SelectField({ id, label, helpText, error, className = "", children, ...props }, ref) {
    const generatedId = useId();
    const selectId = id ?? generatedId;
    const helpId = helpText ? `${selectId}-help` : undefined;
    const errorId = error ? `${selectId}-error` : undefined;
    const describedBy = [helpId, errorId].filter(Boolean).join(" ") || undefined;

    return (
      <div className="ds-field">
        <label className="ds-label" htmlFor={selectId}>{label}</label>
        <select
          ref={ref}
          id={selectId}
          className={`ds-select ${className}`.trim()}
          aria-invalid={Boolean(error) || undefined}
          aria-describedby={describedBy}
          {...props}
        >
          {children}
        </select>
        {helpText ? <FormMessage id={helpId}>{helpText}</FormMessage> : null}
        {error ? <FormMessage id={errorId} tone="error">{error}</FormMessage> : null}
      </div>
    );
  },
);

export interface CheckboxProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "type"> {
  label: ReactNode;
  indeterminate?: boolean;
  error?: string;
}

export const Checkbox = forwardRef<HTMLInputElement, CheckboxProps>(
  function Checkbox({ id, label, indeterminate = false, error, ...props }, forwardedRef) {
    const generatedId = useId();
    const inputId = id ?? generatedId;
    const innerRef = useRef<HTMLInputElement>(null);
    const errorId = error ? `${inputId}-error` : undefined;

    useImperativeHandle(forwardedRef, () => innerRef.current as HTMLInputElement);
    useEffect(() => {
      if (innerRef.current) innerRef.current.indeterminate = indeterminate;
    }, [indeterminate]);

    return (
      <div className="ds-field">
        <label className="ds-checkbox-row" htmlFor={inputId}>
          <input
            ref={innerRef}
            id={inputId}
            type="checkbox"
            className="ds-checkbox"
            aria-invalid={Boolean(error) || undefined}
            aria-describedby={errorId}
            {...props}
          />
          <span>{label}</span>
        </label>
        {error ? <FormMessage id={errorId} tone="error">{error}</FormMessage> : null}
      </div>
    );
  },
);
