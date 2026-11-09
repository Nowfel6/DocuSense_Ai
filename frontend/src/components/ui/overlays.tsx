"use client";

import { X } from "lucide-react";
import {
  useEffect,
  useId,
  useRef,
  type ReactNode,
  type RefObject,
} from "react";

import { Button, IconButton } from "./button";

export interface DialogProps {
  open: boolean;
  title: string;
  description?: string;
  children?: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  pending?: boolean;
  error?: string;
  onConfirm?: () => void;
  onClose: () => void;
  returnFocusRef?: RefObject<HTMLElement | null>;
  initialFocus?: "cancel" | "confirm";
  className?: string;
  placement?: "left" | "right";
}

export function Dialog({
  open,
  title,
  description,
  children,
  confirmLabel,
  cancelLabel = "Cancel",
  pending = false,
  error,
  onConfirm,
  onClose,
  returnFocusRef,
  initialFocus,
  className = "",
  placement,
}: DialogProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const descriptionId = useId();
  const previousFocus = useRef<HTMLElement | null>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const confirmRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    if (open && !node.open) {
      previousFocus.current = document.activeElement as HTMLElement | null;
      node.showModal();
      if (initialFocus === "cancel") cancelRef.current?.focus();
      if (initialFocus === "confirm") confirmRef.current?.focus();
    } else if (!open && node.open) {
      node.close();
    }
  }, [initialFocus, open]);

  function handleClosed() {
    onClose();
    (returnFocusRef?.current ?? previousFocus.current)?.focus();
  }

  return (
    <dialog
      ref={ref}
      className={`ds-dialog ${className}`.trim()}
      data-placement={placement}
      aria-labelledby={titleId}
      aria-describedby={description ? descriptionId : undefined}
      onClose={handleClosed}
      onCancel={(event) => {
        if (pending) event.preventDefault();
      }}
    >
      <div className="ds-dialog-content">
        <div className="ds-dialog-head">
          <div>
            <h2 className="ds-dialog-title" id={titleId}>{title}</h2>
            {description ? <p className="ds-dialog-description" id={descriptionId}>{description}</p> : null}
          </div>
          <IconButton
            label="Close dialog"
            variant="subtle"
            icon={<X aria-hidden="true" size={18} />}
            onClick={onClose}
            disabled={pending}
          />
        </div>
        {children}
        {error ? <p className="ds-field-message" data-tone="error" role="alert">{error}</p> : null}
        {(confirmLabel || cancelLabel) ? (
          <div className="ds-dialog-actions">
            <Button ref={cancelRef} variant="subtle" onClick={onClose} disabled={pending}>{cancelLabel}</Button>
            {confirmLabel && onConfirm ? (
              <Button ref={confirmRef} variant="primary" onClick={onConfirm} isPending={pending}>{confirmLabel}</Button>
            ) : null}
          </div>
        ) : null}
      </div>
    </dialog>
  );
}

export function Drawer(props: DialogProps) {
  return <Dialog {...props} className={`ds-drawer ${props.className ?? ""}`.trim()} />;
}

export function Tooltip({ content, children }: { content: string; children: ReactNode }) {
  const id = useId();
  return (
    <span className="ds-tooltip-wrap">
      <span aria-describedby={id}>{children}</span>
      <span id={id} className="ds-tooltip" role="tooltip">{content}</span>
    </span>
  );
}
