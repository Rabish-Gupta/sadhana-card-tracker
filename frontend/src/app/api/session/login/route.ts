import { NextResponse } from "next/server";
import { AUTH_COOKIE } from "@/lib/auth/constants";
import { backendFailure, fetchBackend, passthrough, requestIdFrom } from "@/lib/api/bff";
import type { AccessTokenResponse, UserPublic } from "@/lib/api/types";

export async function POST(request: Request) {
  const requestId = requestIdFrom(request);
  try {
    const body = await request.text();
    const loginResponse = await fetchBackend("/api/v1/auth/login", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body,
    }, requestId);
    if (!loginResponse.ok) return passthrough(loginResponse, requestId);

    const token = (await loginResponse.json()) as AccessTokenResponse;
    const meResponse = await fetchBackend("/api/v1/auth/me", {
      headers: { authorization: `Bearer ${token.access_token}` },
    }, requestId);
    if (!meResponse.ok) return passthrough(meResponse, requestId);

    const user = (await meResponse.json()) as UserPublic;
    const response = NextResponse.json(user, { headers: { "cache-control": "no-store", "x-request-id": requestId } });
    response.cookies.set(AUTH_COOKIE, token.access_token, {
      httpOnly: true,
      sameSite: "lax",
      secure: process.env.NODE_ENV === "production",
      path: "/",
      maxAge: token.expires_in,
      priority: "high",
    });
    return response;
  } catch (error) {
    return backendFailure(error, requestId);
  }
}
