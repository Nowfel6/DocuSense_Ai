import { FileScan } from "lucide-react";
import type { Route } from "next";
import Link from "next/link";

export function Wordmark({ href = "/" }: { href?: string }) {
  return (
    <Link className="ds-wordmark" href={href as Route} aria-label="DocuSense home">
      <span className="ds-wordmark-mark" aria-hidden="true"><FileScan size={21} strokeWidth={1.75} /></span>
      <span className="ds-wordmark-text">DocuSense</span>
    </Link>
  );
}
