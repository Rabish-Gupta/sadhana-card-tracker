"use client";

import { FormEvent, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { apiFetch, ApiError } from "@/lib/api/client";
import type { UserPublic } from "@/lib/api/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export function LoginForm() {
  const router = useRouter();
  const search = useSearchParams();
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setPending(true);
    const form = new FormData(event.currentTarget);
    try {
      const user = await apiFetch<UserPublic>("/api/session/login", {
        method: "POST",
        body: JSON.stringify({ email: form.get("email"), password: form.get("password") }),
      });
      router.replace(user.role === "ADMIN" ? "/admin" : "/devotee");
      router.refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to sign in");
    } finally {
      setPending(false);
    }
  }

  return (
    <form className="space-y-4" onSubmit={submit}>
      {search.get("reason") === "session-expired" ? (
        <div className="rounded-lg bg-amber-50 p-3 text-sm text-amber-800">Your session expired. Please sign in again.</div>
      ) : null}
      {error ? <div className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</div> : null}
      <label className="block text-sm font-medium text-slate-700">Email<Input className="mt-1" name="email" type="email" autoComplete="email" required /></label>
      <label className="block text-sm font-medium text-slate-700">Password<Input className="mt-1" name="password" type="password" autoComplete="current-password" required /></label>
      <Button className="w-full" disabled={pending}>{pending ? "Signing in…" : "Sign in"}</Button>
    </form>
  );
}
