import {
  AlertCircle,
  Ban,
  CheckCircle2,
  CircleAlert,
  Clock3,
  FileQuestion,
  LoaderCircle,
  SearchX,
  ShieldAlert,
  TriangleAlert,
  type LucideIcon,
} from "lucide-react";
import type { Route } from "next";
import Link from "next/link";
import type { CSSProperties, ReactNode } from "react";

import { Button } from "./button";

export type Tone = "neutral" | "technical" | "success" | "warning" | "danger";

export function Badge({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return <span className="ds-badge" data-tone={tone}>{children}</span>;
}

export type DocumentStatus =
  | "queued"
  | "partitioning"
  | "chunking"
  | "vectorizing"
  | "extracting"
  | "processing"
  | "pending_review"
  | "approved"
  | "completed"
  | "rejected"
  | "failed";

const STATUS: Record<DocumentStatus, { label: string; tone: Tone; icon: LucideIcon }> = {
  queued: { label: "Queued", tone: "technical", icon: Clock3 },
  partitioning: { label: "Partitioning", tone: "technical", icon: LoaderCircle },
  chunking: { label: "Chunking", tone: "technical", icon: LoaderCircle },
  vectorizing: { label: "Vectorizing", tone: "technical", icon: LoaderCircle },
  extracting: { label: "Extracting", tone: "technical", icon: LoaderCircle },
  processing: { label: "Processing", tone: "technical", icon: LoaderCircle },
  pending_review: { label: "Pending review", tone: "warning", icon: TriangleAlert },
  approved: { label: "Approved", tone: "success", icon: CheckCircle2 },
  completed: { label: "Completed", tone: "success", icon: CheckCircle2 },
  rejected: { label: "Rejected", tone: "danger", icon: Ban },
  failed: { label: "Failed", tone: "danger", icon: AlertCircle },
};

export function StatusBadge({ status }: { status: DocumentStatus }) {
  const item = STATUS[status];
  const Icon = item.icon;
  return (
    <span className="ds-status-badge" data-tone={item.tone}>
      <Icon aria-hidden="true" size={14} />
      {item.label}
    </span>
  );
}

export function Alert({
  tone = "info",
  title,
  message,
  action,
}: {
  tone?: "info" | "warning" | "error" | "success";
  title: string;
  message?: string;
  action?: ReactNode;
}) {
  const Icon = tone === "error" ? CircleAlert : tone === "warning" ? TriangleAlert :
    tone === "success" ? CheckCircle2 : AlertCircle;
  return (
    <div className="ds-alert" data-tone={tone} role={tone === "error" ? "alert" : "status"}>
      <Icon aria-hidden="true" size={18} />
      <div>
        <p className="ds-alert-title">{title}</p>
        {message ? <p className="ds-alert-message">{message}</p> : null}
      </div>
      {action}
    </div>
  );
}

export function Skeleton({
  shape = "text",
  width,
  height,
}: {
  shape?: "text" | "control" | "row" | "panel";
  width?: CSSProperties["width"];
  height?: CSSProperties["height"];
}) {
  return <span className="ds-skeleton" data-shape={shape} style={{ width, height }} aria-hidden="true" />;
}

export function EmptyState({
  title,
  message,
  action,
}: {
  title: string;
  message: string;
  action?: ReactNode;
}) {
  return (
    <section className="ds-empty-state">
      <SearchX aria-hidden="true" size={26} />
      <h2>{title}</h2>
      <p>{message}</p>
      {action}
    </section>
  );
}

export type RouteStateKind = "error" | "forbidden" | "not-found" | "offline";

export function RouteState({
  kind,
  title,
  message,
  requestId,
  actionLabel,
  href,
  onAction,
}: {
  kind: RouteStateKind;
  title: string;
  message: string;
  requestId?: string;
  actionLabel?: string;
  href?: string;
  onAction?: () => void;
}) {
  const Icon = kind === "forbidden" ? ShieldAlert : kind === "not-found" ? FileQuestion :
    kind === "offline" ? AlertCircle : CircleAlert;
  return (
    <section className="ds-route-state" aria-labelledby="route-state-title">
      <Icon aria-hidden="true" size={30} />
      <h1 id="route-state-title">{title}</h1>
      <p>{message}</p>
      {requestId ? <span className="ds-request-id">Request ID: {requestId}</span> : null}
      {actionLabel && href ? <Link className="ds-button" data-variant="secondary" href={href as Route}>{actionLabel}</Link> : null}
      {actionLabel && onAction ? <Button onClick={onAction}>{actionLabel}</Button> : null}
    </section>
  );
}
