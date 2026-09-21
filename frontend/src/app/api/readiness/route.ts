import { NextResponse } from "next/server";
import { backendFailure, fetchBackend, requestIdFrom } from "@/lib/api/bff";
import { publicAppVersion } from "@/lib/env";

export async function GET(request: Request) {
  const requestId = requestIdFrom(request);
  try {
    const response = await fetchBackend("/health", {}, requestId);
    if (!response.ok) {
      return NextResponse.json({ status: "not_ready", frontend_version: publicAppVersion(), backend_status: response.status, request_id: requestId }, { status: 503, headers: { "cache-control": "no-store", "x-request-id": requestId } });
    }
    return NextResponse.json({ status: "ready", frontend_version: publicAppVersion(), backend_status: "ok", request_id: requestId }, { headers: { "cache-control": "no-store", "x-request-id": requestId } });
  } catch (error) {
    const failed = backendFailure(error, requestId);
    return NextResponse.json({ status: "not_ready", frontend_version: publicAppVersion(), backend_status: failed.status, request_id: requestId }, { status: 503, headers: { "cache-control": "no-store", "x-request-id": requestId } });
  }
}
