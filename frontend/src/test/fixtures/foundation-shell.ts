import type { SessionProfile } from "@/lib/auth/session-types";

export const fixtureMetadata = {
  feature: "frontend-foundation-completion",
  apiMode: "DESIGN_FIXTURE",
  provenance: "Synthetic test and Stage 3 preview data only",
  containsProductionData: false,
} as const;

export const operatorProfile: SessionProfile = {
  userId: "fixture-user-operator",
  email: "amina.rahman@example.invalid",
  displayName: "Amina Rahman",
  role: "operator",
  organizationId: "fixture-org-northstar",
  organizationName: "Northstar Freight Demo",
};

export const longLabelProfile: SessionProfile = {
  ...operatorProfile,
  displayName: "Amina Rahman — Regional Document Operations Coordinator",
  organizationName: "Northstar Freight Demonstration and Document Operations Workspace",
};

export const notificationCounts = [0, 3, null] as const;

export const allFoundationStatuses = [
  "queued",
  "partitioning",
  "chunking",
  "vectorizing",
  "extracting",
  "processing",
  "pending_review",
  "approved",
  "completed",
  "rejected",
  "failed",
] as const;
