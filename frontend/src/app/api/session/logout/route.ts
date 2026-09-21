import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { AUTH_COOKIE } from "@/lib/auth/constants";
import { fetchBackend, requestIdFrom } from "@/lib/api/bff";

export async function POST(request: Request) {
  const requestId = requestIdFrom(request);
  const token = (await cookies()).get(AUTH_COOKIE)?.value;
  if (token) {
    try {
      await fetchBackend("/api/v1/auth/logout", {
        method: "POST",
        headers: { authorization: `Bearer ${token}` },
      }, requestId);
    } catch {
      // Current backend logout is stateless; clearing the HttpOnly BFF cookie is authoritative.
    }
  }
  const response = NextResponse.json({ ok: true }, { headers: { "cache-control": "no-store", "x-request-id": requestId } });
  response.cookies.set(AUTH_COOKIE, "", {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 0,
    priority: "high",
  });
  return response;
}
