import type { SessionProfile } from "@/lib/auth/session-types";

export const authProfile: SessionProfile = {
  userId: "8fe77ea8-eebb-4e31-bcb2-e69467064708",
  email: "operator@example.test",
  displayName: "Example Operator",
  role: "operator",
  organizationId: "3cf4b83f-ebd9-449f-8756-d8cc190dfde2",
  organizationName: "Example Workspace",
};

export const loginSuccess = {
  success: true,
  data: { user: authProfile, expires_in: 3600 },
};

export function jsonResponse(payload: unknown, status = 200, headers?: HeadersInit): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json", ...headers },
  });
}
