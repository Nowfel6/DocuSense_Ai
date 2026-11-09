"use client";

import { ExternalLink, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { formatDateTime } from "@/lib/formatting/format";

import { millisecondsUntilSourceRefresh, sourceHref } from "./source-view";
import type { SourceView } from "./types";
import styles from "./document-detail-chunk-inspector.module.css";

export function SourceViewAction({
  source,
  page,
  blocked = false,
  refreshing = false,
  onRefresh,
  compact = false,
}: {
  source: SourceView;
  page?: number;
  blocked?: boolean;
  refreshing?: boolean;
  onRefresh: () => void;
  compact?: boolean;
}) {
  const [, setClockRevision] = useState(0);

  useEffect(() => {
    const delay = millisecondsUntilSourceRefresh(source);
    if (delay <= 0) return;
    const timer = globalThis.setTimeout(() => setClockRevision((value) => value + 1), Math.min(delay + 20, 2_147_483_647));
    return () => globalThis.clearTimeout(timer);
  }, [source]);

  const href = blocked ? null : sourceHref(source, page);

  return (
    <div className={styles.sourceAction} data-compact={compact || undefined}>
      {href ? (
        <a className="ds-button" data-variant="secondary" href={href} target="_blank" rel="noopener noreferrer">
          <ExternalLink aria-hidden="true" size={16} />
          {page && source.mime_type === "application/pdf" ? `Open source page ${page}` : "Open source"}
        </a>
      ) : (
        <Button onClick={onRefresh} isPending={refreshing} pendingLabel="Refreshing source…">
          <RefreshCw aria-hidden="true" size={16} />
          Refresh source link
        </Button>
      )}
      {!compact ? (
        <p>
          Short-lived external view. Link expires {formatDateTime(source.expires_at)}.
          {href ? " If it does not open, return here and refresh the link." : " Refresh it before opening."}
        </p>
      ) : null}
    </div>
  );
}

