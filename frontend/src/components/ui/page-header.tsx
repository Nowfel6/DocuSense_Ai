import type { ReactNode } from "react";

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="ds-page-header">
      <div>
        <h1 className="ds-page-title">{title}</h1>
        {description ? <p className="ds-page-description">{description}</p> : null}
      </div>
      {actions ? <div className="ds-row">{actions}</div> : null}
    </header>
  );
}
