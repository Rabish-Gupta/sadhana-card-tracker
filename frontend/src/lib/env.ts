function normalizeBackendOrigin(value: string): string {
  const raw = value.trim().replace(/\/+$/, "");
  const withoutApi = raw.endsWith("/api/v1") ? raw.slice(0, -7) : raw;
  let url: URL;
  try {
    url = new URL(withoutApi);
  } catch {
    throw new Error("BACKEND_BASE_URL must be an absolute http(s) URL");
  }
  if (!['http:', 'https:'].includes(url.protocol)) {
    throw new Error("BACKEND_BASE_URL must use http or https");
  }
  if (url.pathname !== '/' || url.search || url.hash) {
    throw new Error("BACKEND_BASE_URL must contain only an origin, without path/query/fragment");
  }
  return url.origin;
}

function positiveInteger(name: string, fallback: number): number {
  const raw = process.env[name];
  if (!raw) return fallback;
  const parsed = Number.parseInt(raw, 10);
  if (!Number.isFinite(parsed) || parsed <= 0) throw new Error(`${name} must be a positive integer`);
  return parsed;
}

export function getBackendOrigin(): string {
  return normalizeBackendOrigin(process.env.BACKEND_BASE_URL ?? "http://127.0.0.1:8000");
}

export function backendUrl(path: string): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${getBackendOrigin()}${normalizedPath}`;
}

export function backendRequestTimeoutMs(): number {
  return positiveInteger("BACKEND_REQUEST_TIMEOUT_MS", 15_000);
}

export function bffMaxBodyBytes(): number {
  return positiveInteger("BFF_MAX_BODY_BYTES", 1_048_576);
}

export function publicAppVersion(): string {
  return process.env.NEXT_PUBLIC_APP_VERSION ?? "0.4.0";
}
