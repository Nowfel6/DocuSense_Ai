import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";

export type ButtonVariant = "primary" | "secondary" | "subtle" | "destructive";
export type ButtonSize = "default" | "compact";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  isPending?: boolean;
  pendingLabel?: string;
  children: ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    variant = "secondary",
    size = "default",
    isPending = false,
    pendingLabel = "Working…",
    disabled,
    type = "button",
    className = "",
    children,
    ...props
  },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      className={`ds-button ${className}`.trim()}
      data-variant={variant}
      data-size={size}
      disabled={disabled || isPending}
      aria-busy={isPending || undefined}
      {...props}
    >
      {isPending ? <span aria-hidden="true" className="ds-spinner" /> : null}
      {isPending ? pendingLabel : children}
    </button>
  );
});

export interface IconButtonProps extends Omit<ButtonProps, "children"> {
  label: string;
  icon: ReactNode;
}

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(
  function IconButton({ label, icon, className = "", ...props }, ref) {
    return (
      <Button
        ref={ref}
        className={`ds-icon-button ${className}`.trim()}
        aria-label={label}
        title={label}
        {...props}
      >
        {icon}
      </Button>
    );
  },
);
