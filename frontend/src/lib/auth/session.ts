import "server-only";

import { createHmac, timingSafeEqual } from "node:crypto";
import { cookies } from "next/headers";

import type { SessionProfile, StoredSession, UserRole } from "./session-types";

const isProduction = process.env.NODE_ENV === "production";
const TOKEN_COOKIE = isProduction ? "__Host-docusense_session" : "docusense_dev_session";
const PROFILE_COOKIE = isProduction ? "__Host-docusense_profile" : "docusense_dev_profile";
const DEFAULT_MAX_AGE_SECONDS = 60 * 60;

function signingSecret(): string | null {
  const secret = process.env.FRONTEND_SESSION_SIGNING_SECRET;
  return secret && secret.length >= 32 ? secret : null;
}

function signature(payload: string, secret: string): string {
  return createHmac("sha256", secret).update(payload).digest("base64url");
}

function encodeProfile(profile: StoredSession, secret: string): string {
  const payload = Buffer.from(JSON.stringify(profile)).toString("base64url");
  return `${payload}.${signature(payload, secret)}`;
}

function isRole(value: unknown): value is UserRole {
  return value === "admin" || value === "operator" || value === "viewer";
}

function decodeProfile(value: string, secret: string): StoredSession | null {
  const [payload, receivedSignature, extra] = value.split(".");
  if (!payload || !receivedSignature || extra) return null;

  const expectedSignature = signature(payload, secret);
  const expected = Buffer.from(expectedSignature);
  const received = Buffer.from(receivedSignature);
  if (expected.length !== received.length || !timingSafeEqual(expected, received)) return null;

  try {
    const candidate = JSON.parse(Buffer.from(payload, "base64url").toString("utf8")) as Partial<StoredSession>;
    if (
      typeof candidate.userId !== "string" ||
      typeof candidate.email !== "string" ||
      typeof candidate.displayName !== "string" ||
      !isRole(candidate.role) ||
      typeof candidate.organizationId !== "string" ||
      typeof candidate.organizationName !== "string" ||
      typeof candidate.expiresAt !== "number" ||
      candidate.expiresAt <= Date.now()
    ) return null;
    return candidate as StoredSession;
  } catch {
    return null;
  }
}

const cookieOptions = {
  httpOnly: true,
  secure: isProduction,
  sameSite: "lax" as const,
  path: "/",
};

export function isSessionConfigurationReady(): boolean {
  return Boolean(signingSecret());
}

export async function writeSession(
  token: string,
  profile: SessionProfile,
  expiresInSeconds = DEFAULT_MAX_AGE_SECONDS,
): Promise<void> {
  const secret = signingSecret();
  if (!secret) throw new Error("Session signing is not configured.");

  const maxAge = Math.max(60, Math.min(Math.floor(expiresInSeconds), 24 * 60 * 60));
  const stored: StoredSession = { ...profile, expiresAt: Date.now() + maxAge * 1000 };
  const store = await cookies();
  store.set(TOKEN_COOKIE, token, { ...cookieOptions, maxAge });
  store.set(PROFILE_COOKIE, encodeProfile(stored, secret), { ...cookieOptions, maxAge });
}

export async function readSession(): Promise<SessionProfile | null> {
  const secret = signingSecret();
  if (!secret) return null;
  const store = await cookies();
  const token = store.get(TOKEN_COOKIE)?.value;
  const encodedProfile = store.get(PROFILE_COOKIE)?.value;
  if (!token || !encodedProfile) return null;
  const stored = decodeProfile(encodedProfile, secret);
  if (!stored) return null;
  return {
    userId: stored.userId,
    email: stored.email,
    displayName: stored.displayName,
    role: stored.role,
    organizationId: stored.organizationId,
    organizationName: stored.organizationName,
  };
}

export async function readAccessToken(): Promise<string | null> {
  const secret = signingSecret();
  if (!secret) return null;
  const store = await cookies();
  const token = store.get(TOKEN_COOKIE)?.value;
  const encodedProfile = store.get(PROFILE_COOKIE)?.value;
  if (!token || !encodedProfile || !decodeProfile(encodedProfile, secret)) return null;
  return token;
}

export async function clearSession(): Promise<void> {
  const store = await cookies();
  store.set(TOKEN_COOKIE, "", { ...cookieOptions, maxAge: 0 });
  store.set(PROFILE_COOKIE, "", { ...cookieOptions, maxAge: 0 });
}
