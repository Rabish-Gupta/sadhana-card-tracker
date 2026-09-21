"use client";

import { FormEvent, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api/client";
import type { AdminCategoryPublic, AccountStatus, UserPublic } from "@/lib/api/types";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { MutationFeedback } from "@/components/admin/mutation-feedback";
import Link from "next/link";

const statuses: Array<"ALL" | AccountStatus> = ["ALL", "ACTIVE", "INACTIVE", "PENDING", "REJECTED"];

export function DevoteeManager({ users, categories }: { users: UserPublic[]; categories: AdminCategoryPublic[] }) {
  const router = useRouter();
  const [filter, setFilter] = useState<(typeof statuses)[number]>("ALL");
  const [busy, setBusy] = useState<string | null>(null);
  const [reason, setReason] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const filtered = useMemo(() => filter === "ALL" ? users : users.filter((u) => u.account_status === filter), [filter, users]);

  async function changeStatus(user: UserPublic, action: "activate" | "deactivate") {
    const why = reason[user.id]?.trim();
    if (!why || why.length < 3) { setError("A reason of at least 3 characters is required for account status changes."); return; }
    setBusy(user.id); setError(null); setSuccess(null);
    try {
      await apiFetch<UserPublic>(`/api/backend/admin/devotees/${user.id}/${action}`, { method: "POST", body: JSON.stringify({ reason: why }) });
      setSuccess(`${user.full_name} ${action === "activate" ? "activated" : "deactivated"}.`);
      router.refresh();
    } catch (e) { setError(e instanceof Error ? e.message : "Account status change failed."); }
    finally { setBusy(null); }
  }

  async function createDevotee(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setCreating(true); setError(null); setSuccess(null);
    const form = new FormData(event.currentTarget);
    const categoryCode = String(form.get("category_code") ?? "");
    const category = categories.find((c) => c.code === categoryCode);
    const academicYearRaw = String(form.get("current_academic_year") ?? "");
    const payload = {
      full_name: String(form.get("full_name") ?? "").trim(),
      email: String(form.get("email") ?? "").trim(),
      password: String(form.get("password") ?? ""),
      phone_number: String(form.get("phone_number") ?? "").trim(),
      college: String(form.get("college") ?? "").trim(),
      branch: String(form.get("branch") ?? "").trim(),
      college_joining_year: Number(form.get("college_joining_year")),
      category_code: categoryCode,
      current_academic_year: category?.academic_year ?? (academicYearRaw ? Number(academicYearRaw) : null),
    };
    try {
      await apiFetch<UserPublic>("/api/backend/admin/devotees", { method: "POST", body: JSON.stringify(payload) });
      setSuccess(`${payload.full_name} created as an ACTIVE devotee.`);
      event.currentTarget.reset(); router.refresh();
    } catch (e) { setError(e instanceof Error ? e.message : "Devotee creation failed."); }
    finally { setCreating(false); }
  }

  return (
    <div className="space-y-6">
      <MutationFeedback error={error} success={success} />
      <Card>
        <CardHeader title="Create devotee directly" description="Admin-created accounts are ACTIVE immediately. Category/year consistency is still enforced by FastAPI." />
        <form onSubmit={createDevotee} className="grid gap-4 p-5 md:grid-cols-2 lg:grid-cols-3">
          <label className="text-sm font-medium">Full name<Input name="full_name" minLength={2} required className="mt-1" /></label>
          <label className="text-sm font-medium">Email<Input name="email" type="email" required className="mt-1" /></label>
          <label className="text-sm font-medium">Temporary password<Input name="password" type="password" minLength={8} required className="mt-1" /></label>
          <label className="text-sm font-medium">Phone<Input name="phone_number" minLength={7} required className="mt-1" /></label>
          <label className="text-sm font-medium">College<Input name="college" minLength={2} required className="mt-1" /></label>
          <label className="text-sm font-medium">Branch<Input name="branch" minLength={2} required className="mt-1" /></label>
          <label className="text-sm font-medium">College joining year<Input name="college_joining_year" type="number" min={2000} max={2100} required className="mt-1" /></label>
          <label className="text-sm font-medium">Category<Select name="category_code" required className="mt-1" defaultValue=""><option value="" disabled>Select category</option>{categories.filter((c) => c.is_active && !c.is_archived).map((c) => <option key={c.id} value={c.code}>{c.display_name}</option>)}</Select></label>
          <label className="text-sm font-medium">Academic year (only if needed)<Select name="current_academic_year" className="mt-1" defaultValue=""><option value="">Use category mapping / not applicable</option>{[1,2,3,4].map((y) => <option key={y} value={y}>{y}</option>)}</Select></label>
          <div className="md:col-span-2 lg:col-span-3"><Button disabled={creating} type="submit">{creating ? "Creating…" : "Create active devotee"}</Button></div>
        </form>
      </Card>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div><h2 className="text-xl font-bold">Devotee accounts</h2><p className="text-sm text-slate-500">Deactivate instead of deleting historical accounts.</p></div>
        <Select className="w-44" value={filter} onChange={(e) => setFilter(e.target.value as (typeof statuses)[number])}>{statuses.map((s) => <option key={s}>{s}</option>)}</Select>
      </div>

      <div className="space-y-4">
        {filtered.map((user) => (
          <Card key={user.id} className="p-5">
            <div className="grid gap-5 lg:grid-cols-[1fr_380px]">
              <div>
                <div className="flex flex-wrap items-start justify-between gap-3"><div><p className="font-semibold">{user.full_name}</p><p className="text-sm text-slate-500">{user.email} · {user.phone_number}</p></div><span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold">{user.account_status}</span></div>
                {user.devotee_profile ? <p className="mt-3 text-sm text-slate-600">{user.devotee_profile.current_category.display_name} · {user.devotee_profile.college} · {user.devotee_profile.branch}</p> : null}
                <div className="mt-4 flex flex-wrap gap-2"><Link className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold hover:bg-slate-50" href={`/admin/corrections?userId=${user.id}`}>Historical corrections</Link></div>
              </div>
              <div className="space-y-2">
                {(user.account_status === "ACTIVE" || user.account_status === "INACTIVE") ? <>
                  <Textarea value={reason[user.id] ?? ""} onChange={(e) => setReason((old) => ({ ...old, [user.id]: e.target.value }))} placeholder="Mandatory reason for activation/deactivation" />
                  {user.account_status === "ACTIVE" ? <Button variant="danger" disabled={busy === user.id} onClick={() => void changeStatus(user, "deactivate")}>Deactivate</Button> : <Button disabled={busy === user.id} onClick={() => void changeStatus(user, "activate")}>Reactivate</Button>}
                </> : <p className="text-sm text-slate-500">Status changes for this account are handled by the registration workflow.</p>}
              </div>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
