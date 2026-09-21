export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly payload: unknown,
    public readonly requestId: string | null = null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function extractMessage(payload: unknown, fallback: string): string {
  if (!payload || typeof payload !== "object") return fallback;
  const detail = (payload as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (!item || typeof item !== "object") return "Invalid input";
        const typed = item as { loc?: unknown[]; msg?: string };
        const field = typed.loc?.at(-1);
        return `${typeof field === "string" ? `${field}: ` : ""}${typed.msg ?? "Invalid input"}`;
      })
      .join(" · ");
  }
  return fallback;
}

export async function apiFetch<T>(input: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("content-type")) headers.set("content-type", "application/json");

  let response: Response;
  try {
    response = await fetch(input, {
      ...init,
      headers,
      credentials: "same-origin",
      cache: "no-store",
    });
  } catch {
    throw new ApiError("The application server is unreachable. Check your connection and retry.", 0, null, null);
  }

  const contentType = response.headers.get("content-type") ?? "";
  const payload = contentType.includes("application/json") ? await response.json() : await response.text();
  const requestId = response.headers.get("x-request-id");

  if (!response.ok) {
    if (response.status === 401 && typeof window !== "undefined" && !input.includes("/api/session/login")) {
      window.location.assign("/login?reason=session-expired");
    }
    const fallback = response.status === 504
      ? "The backend took too long to respond. Retry shortly."
      : response.status === 502
        ? "The backend is temporarily unavailable. Retry shortly."
        : `Request failed with status ${response.status}`;
    throw new ApiError(extractMessage(payload, fallback), response.status, payload, requestId);
  }

  return payload as T;
}
