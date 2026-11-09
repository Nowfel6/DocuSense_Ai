import type { ReactNode } from "react";

export interface ToastItem {
  id: string;
  title: string;
  message?: string;
  action?: ReactNode;
}

export function ToastRegion({ items }: { items: ToastItem[] }) {
  return (
    <div className="ds-toast-region" aria-live="polite" aria-label="Notifications">
      {items.map((item) => (
        <div className="ds-toast" key={item.id} role="status">
          <p className="ds-alert-title">{item.title}</p>
          {item.message ? <p className="ds-alert-message">{item.message}</p> : null}
          {item.action}
        </div>
      ))}
    </div>
  );
}
