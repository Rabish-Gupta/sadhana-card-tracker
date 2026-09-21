"use client";

import { FormEvent, useState } from "react";
import { apiFetch, ApiError } from "@/lib/api/client";
import type { RegistrationResponse } from "@/lib/api/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export function RegisterForm() {
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSuccess(null);
    setPending(true);
    const form = new FormData(event.currentTarget);
    try {
      const result = await apiFetch<RegistrationResponse>("/api/backend/auth/register", {
        method: "POST",
        body: JSON.stringify({
          full_name: form.get("full_name"),
          email: form.get("email"),
          password: form.get("password"),
          phone_number: form.get("phone_number"),
          college: form.get("college"),
          branch: form.get("branch"),
          current_academic_year: Number(form.get("current_academic_year")),
          college_joining_year: Number(form.get("college_joining_year")),
        }),
      });
      setSuccess(result.message);
      event.currentTarget.reset();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to register");
    } finally {
      setPending(false);
    }
  }

  return (
    <form className="grid gap-4 sm:grid-cols-2" onSubmit={submit}>
      {success ? <div className="sm:col-span-2 rounded-lg bg-emerald-50 p-3 text-sm text-emerald-800">{success}</div> : null}
      {error ? <div className="sm:col-span-2 rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</div> : null}
      <label className="text-sm font-medium text-slate-700">Full name<Input className="mt-1" name="full_name" minLength={2} required /></label>
      <label className="text-sm font-medium text-slate-700">Email<Input className="mt-1" name="email" type="email" required /></label>
      <label className="text-sm font-medium text-slate-700">Password<Input className="mt-1" name="password" type="password" minLength={8} required /></label>
      <label className="text-sm font-medium text-slate-700">Phone<Input className="mt-1" name="phone_number" minLength={7} required /></label>
      <label className="text-sm font-medium text-slate-700">College<Input className="mt-1" name="college" minLength={2} required /></label>
      <label className="text-sm font-medium text-slate-700">Branch<Input className="mt-1" name="branch" minLength={2} required /></label>
      <label className="text-sm font-medium text-slate-700">Current academic year<Input className="mt-1" name="current_academic_year" type="number" min={1} max={4} required /></label>
      <label className="text-sm font-medium text-slate-700">College joining year<Input className="mt-1" name="college_joining_year" type="number" min={2000} max={2100} required /></label>
      <Button className="sm:col-span-2" disabled={pending}>{pending ? "Submitting…" : "Register for approval"}</Button>
    </form>
  );
}
