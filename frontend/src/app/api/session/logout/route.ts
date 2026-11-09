import { NextResponse } from "next/server";

import { isSameOriginRequest } from "@/lib/auth/request-security";
import { clearSession } from "@/lib/auth/session";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  if (!isSameOriginRequest(request)) {
    return NextResponse.json({
      success: false,
      error: { code: "INVALID_ORIGIN", message: "The request origin could not be verified." },
    }, { status: 403 });
  }

  await clearSession();
  return NextResponse.json({ success: true, data: { signed_out: true } });
}
