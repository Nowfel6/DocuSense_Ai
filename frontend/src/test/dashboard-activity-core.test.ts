import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { activityApiPath, dashboardApiPath, parseDashboardUrl, serializeReport, validateActivityEnvelope, validateDashboardEnvelope } from "@/features/dashboard-activity/api";
import { formatRate } from "@/features/dashboard-activity/format";
import { safeActivityLink } from "@/features/dashboard-activity/safe-activity-link";

import { activityEnvelope, dashboardEnvelope, documentId } from "./fixtures/dashboard-activity";

describe("dashboard/activity core contract", () => {
  it("keeps the reviewed OpenAPI dashboard surface current", () => {
    const schema = JSON.parse(readFileSync(resolve(__dirname, "../../../docs/api/openapi.yaml"), "utf8"));
    expect(Object.keys(schema.paths)).toHaveLength(18);
    expect(Object.keys(schema.components.schemas)).toHaveLength(95);
    expect(schema.paths["/api/v1/analytics/dashboard"].get.responses["200"]).toBeTruthy();
    expect(schema.paths["/api/v1/activity-events"].get.responses["429"].headers["Retry-After"]).toBeTruthy();
  });

  it("serializes UTC report ranges and keeps default requests minimal", () => {
    expect(dashboardApiPath({ bucket: "day" })).toBe("/api/v1/analytics/dashboard");
    const result = serializeReport({ mode: "custom", from: "2026-08-01T00:00", to: "2026-08-02T00:00", bucket: "week" }, Date.parse("2026-09-01T00:00:00Z"));
    expect(result.query).toEqual({ from: "2026-08-01T00:00:00Z", to: "2026-08-02T00:00:00Z", bucket: "week" });
    expect(parseDashboardUrl(new URLSearchParams("from=bad&to=bad"))).toMatchObject({ query: { bucket: "day" }, error: expect.any(String) });
  });

  it("preserves the activity page-one/page-two snapshot rule", () => {
    const query = { from: "2026-08-01T00:00:00Z", to: "2026-08-02T00:00:00Z", bucket: "day" as const };
    expect(activityApiPath(query, 1)).not.toContain("snapshot_at");
    expect(activityApiPath(query, 2, ["document_approved"], "2026-08-02T00:00:00Z")).toContain("snapshot_at=2026-08-02T00%3A00%3A00Z");
  });

  it("accepts a coherent dashboard and rejects cross-field corruption", () => {
    expect(validateDashboardEnvelope(dashboardEnvelope()).data.current.total_documents).toBe(10);
    const corrupted = structuredClone(dashboardEnvelope()) as unknown as Record<string, unknown>;
    const data = (corrupted.data as Record<string, unknown>);
    (data.current as Record<string, unknown>).total_documents = 11;
    expect(() => validateDashboardEnvelope(corrupted)).toThrow(/unexpected response/i);
  });

  it("decodes role-safe activity and rejects viewer identity leakage", () => {
    expect(validateActivityEnvelope(activityEnvelope("viewer"), "viewer").data.items[0].document_id).toBe(documentId);
    const leaked = structuredClone(activityEnvelope("viewer"));
    leaked.data.items[0].actor_display_name = "Hidden actor";
    expect(() => validateActivityEnvelope(leaked, "viewer")).toThrow(/unexpected response/i);
  });

  it("formats server percentage units and allows only exact document links", () => {
    const item = activityEnvelope("viewer").data.items[0];
    expect(formatRate("12.50")).toBe("12.50%");
    expect(formatRate(null)).toBe("No data");
    expect(safeActivityLink(item, "viewer")).toBe(`/documents/${documentId}`);
    expect(safeActivityLink({ ...item, link: `//evil.invalid/documents/${documentId}` }, "viewer")).toBeNull();
  });
});

