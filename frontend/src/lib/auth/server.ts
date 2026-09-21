import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { AUTH_COOKIE } from "@/lib/auth/constants";
import { fetchBackend } from "@/lib/api/bff";
import type { UserPublic, UserRole } from "@/lib/api/types";

async function tokenFromCookie(): Promise<string | null> {
  return (await cookies()).get(AUTH_COOKIE)?.value ?? null;
}

async function backendJson<T>(path: string, init: RequestInit = {}): Promise<{ response: Response; value: T | null; text: string }> {
  const token = await tokenFromCookie();
  const headers = new Headers(init.headers);
  if (token) headers.set("authorization", `Bearer ${token}`);
  if (init.body && !headers.has("content-type")) headers.set("content-type", "application/json");
  try {
    const response = await fetchBackend(`/api/v1${path.startsWith("/") ? path : `/${path}`}`, { ...init, headers });
    const text = await response.text();
    let value: T | null = null;
    if (text && (response.headers.get("content-type") ?? "").includes("application/json")) {
      value = JSON.parse(text) as T;
    }
    return { response, value, text };
  } catch (error) {
    if (error instanceof Error && (error.name === "TimeoutError" || error.name === "AbortError")) {
      throw new Error("FastAPI backend timed out. Retry shortly.");
    }
    throw new Error("FastAPI backend is unavailable. Start or restore the backend and retry.");
  }
}

export async function serverApi<T>(path: string, init: RequestInit = {}): Promise<T> {
  const { response, value, text } = await backendJson<T>(path, init);
  if (response.status === 401 || response.status === 403) redirect("/login?reason=session-expired");
  if (!response.ok) throw new Error(`Backend ${response.status}: ${text.slice(0, 400)}`);
  if (value === null) throw new Error("Backend returned an empty response where JSON was expected.");
  return value;
}

export async function safeServerApi<T>(path: string, allowedMissingStatuses = [404]): Promise<T | null> {
  const { response, value, text } = await backendJson<T>(path);
  if (allowedMissingStatuses.includes(response.status)) return null;
  if (response.status === 401 || response.status === 403) redirect("/login?reason=session-expired");
  if (!response.ok) throw new Error(`Backend ${response.status}: ${text.slice(0, 400)}`);
  return value;
}

export async function getCurrentUser(): Promise<UserPublic | null> {
  const token = await tokenFromCookie();
  if (!token) return null;
  try {
    const response = await fetchBackend("/api/v1/auth/me", { headers: { authorization: `Bearer ${token}` } });
    if (response.status === 401 || response.status === 403) return null;
    if (!response.ok) throw new Error(`Backend auth check failed (${response.status})`);
    return (await response.json()) as UserPublic;
  } catch (error) {
    if (error instanceof Error && error.message.startsWith("Backend auth check failed")) throw error;
    if (error instanceof Error && (error.name === "TimeoutError" || error.name === "AbortError")) {
      throw new Error("FastAPI backend timed out. Retry shortly.");
    }
    throw new Error("FastAPI backend is unavailable. Start the backend and retry.");
  }
}

export async function requireRole(role: UserRole): Promise<UserPublic> {
  const user = await getCurrentUser();
  if (!user) redirect("/login");
  if (user.role !== role) redirect(user.role === "ADMIN" ? "/admin" : "/devotee");
  return user;
}
