import type { ActivityItem, DashboardRole } from "./types";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function safeActivityLink(item: ActivityItem, role: DashboardRole): string | null {
  if (!item.link || item.subject_type !== "document" || !item.document_id || !UUID.test(item.document_id)) return null;
  if (role === "viewer" && item.event_type !== "document_approved") return null;
  if (/[\x00-\x1f\x7f\\#?]/.test(item.link) || /%2f|%5c/i.test(item.link)) return null;
  const expected = `/documents/${item.document_id}`;
  return item.link === expected ? expected : null;
}

