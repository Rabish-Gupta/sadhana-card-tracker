import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { AUTH_COOKIE } from "@/lib/auth/constants";
import { backendFailure, fetchBackend, passthrough, requestIdFrom } from "@/lib/api/bff";
import { bffMaxBodyBytes } from "@/lib/env";

type RouteContext = { params: Promise<{ path: string[] }> };

async function proxy(request: Request, context: RouteContext) {
  const requestId = requestIdFrom(request);
  const { path } = await context.params;
  const joined = path.join("/");

  if (joined === "auth/login" || joined === "auth/logout") {
    return NextResponse.json({ detail: "Use /api/session/login or /api/session/logout", request_id: requestId }, { status: 400, headers: { "x-request-id": requestId } });
  }

  const token = (await cookies()).get(AUTH_COOKIE)?.value;
  const incomingUrl = new URL(request.url);
  const targetPath = `/api/v1/${joined}${incomingUrl.search}`;

  const headers = new Headers();
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);
  if (token) headers.set("authorization", `Bearer ${token}`);

  const method = request.method.toUpperCase();
  let body: string | undefined;
  if (method !== "GET" && method !== "HEAD") {
    body = await request.text();
    if (new TextEncoder().encode(body).byteLength > bffMaxBodyBytes()) {
      return NextResponse.json({ detail: "Request body is too large", request_id: requestId }, { status: 413, headers: { "x-request-id": requestId } });
    }
  }

  try {
    const backendResponse = await fetchBackend(targetPath, { method, headers, body }, requestId);
    return passthrough(backendResponse, requestId);
  } catch (error) {
    return backendFailure(error, requestId);
  }
}

export const GET = proxy;
export const POST = proxy;
export const PATCH = proxy;
export const PUT = proxy;
export const DELETE = proxy;
