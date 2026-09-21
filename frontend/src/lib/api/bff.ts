import { NextResponse } from "next/server";
import { backendRequestTimeoutMs, backendUrl } from "@/lib/env";

export function requestIdFrom(request?: Request): string {
  return request?.headers.get("x-request-id")?.trim() || crypto.randomUUID();
}

export async function fetchBackend(path: string, init: RequestInit = {}, requestId?: string): Promise<Response> {
  const headers = new Headers(init.headers);
  headers.set("accept", headers.get("accept") ?? "application/json");
  if (requestId) headers.set("x-request-id", requestId);
  return fetch(backendUrl(path), {
    ...init,
    headers,
    cache: "no-store",
    signal: AbortSignal.timeout(backendRequestTimeoutMs()),
  });
}

export async function passthrough(response: Response, requestId: string): Promise<NextResponse> {
  const body = await response.text();
  return new NextResponse(body || null, {
    status: response.status,
    headers: {
      "content-type": response.headers.get("content-type") ?? "application/json",
      "cache-control": "no-store",
      "x-request-id": requestId,
    },
  });
}

export function backendFailure(error: unknown, requestId: string): NextResponse {
  const timedOut = error instanceof Error && (error.name === "TimeoutError" || error.name === "AbortError");
  return NextResponse.json(
    { detail: timedOut ? "FastAPI backend request timed out" : "FastAPI backend is unavailable", request_id: requestId },
    { status: timedOut ? 504 : 502, headers: { "cache-control": "no-store", "x-request-id": requestId } },
  );
}
