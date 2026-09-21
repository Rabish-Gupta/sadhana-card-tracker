import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { AUTH_COOKIE } from "@/lib/auth/constants";
import { backendFailure, fetchBackend, passthrough, requestIdFrom } from "@/lib/api/bff";

export async function GET(request: Request) {
  const requestId = requestIdFrom(request);
  const token = (await cookies()).get(AUTH_COOKIE)?.value;
  if (!token) return NextResponse.json({ detail: "Not authenticated" }, { status: 401, headers: { "cache-control": "no-store", "x-request-id": requestId } });
  try {
    const response = await fetchBackend("/api/v1/auth/me", {
      headers: { authorization: `Bearer ${token}` },
    }, requestId);
    return passthrough(response, requestId);
  } catch (error) {
    return backendFailure(error, requestId);
  }
}
