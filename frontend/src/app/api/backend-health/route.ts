import { backendFailure, fetchBackend, passthrough, requestIdFrom } from "@/lib/api/bff";

export async function GET(request: Request) {
  const requestId = requestIdFrom(request);
  try {
    const response = await fetchBackend("/health", {}, requestId);
    return passthrough(response, requestId);
  } catch (error) {
    return backendFailure(error, requestId);
  }
}
