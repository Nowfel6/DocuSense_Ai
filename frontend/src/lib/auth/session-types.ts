export type UserRole = "admin" | "operator" | "viewer";

export interface SessionProfile {
  userId: string;
  email: string;
  displayName: string;
  role: UserRole;
  organizationId: string;
  organizationName: string;
}

export interface StoredSession extends SessionProfile {
  expiresAt: number;
}
