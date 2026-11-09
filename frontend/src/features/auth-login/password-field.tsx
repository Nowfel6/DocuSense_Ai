"use client";

import { Eye, EyeOff } from "lucide-react";
import { forwardRef } from "react";

import { IconButton } from "@/components/ui/button";
import { TextField, type TextFieldProps } from "@/components/ui/fields";

export interface PasswordFieldProps extends Omit<TextFieldProps, "label" | "type"> {
  visible: boolean;
  onVisibleChange: (visible: boolean) => void;
}

export const PasswordField = forwardRef<HTMLInputElement, PasswordFieldProps>(
  function PasswordField({ visible, onVisibleChange, ...props }, ref) {
    const label = visible ? "Hide password" : "Show password";
    return (
      <div className="ds-password-field">
        <TextField ref={ref} label="Password" type={visible ? "text" : "password"} {...props} />
        <IconButton
          className="ds-password-toggle"
          variant="subtle"
          label={label}
          icon={visible ? <EyeOff aria-hidden="true" size={18} /> : <Eye aria-hidden="true" size={18} />}
          aria-pressed={visible}
          onMouseDown={(event) => event.preventDefault()}
          onClick={() => onVisibleChange(!visible)}
        />
      </div>
    );
  },
);
