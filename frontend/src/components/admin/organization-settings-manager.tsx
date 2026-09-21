"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api/client";
import type { OrganizationSettingVersionPublic } from "@/lib/api/types";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { MutationFeedback } from "@/components/admin/mutation-feedback";

const weekDays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

export function OrganizationSettingsManager({ current, versions }: { current: OrganizationSettingVersionPublic; versions: OrganizationSettingVersionPublic[] }) {
  const router = useRouter();
  const pending = versions.find((v) => v.status === "PENDING") ?? null;
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(null); setSuccess(null);
    const fd = new FormData(event.currentTarget);
    const payload = {
      effective_from_week: String(fd.get("effective_from_week") || "") || null,
      timezone: String(fd.get("timezone") || "") || null,
      week_start_day: Number(fd.get("week_start_day")),
      daily_finalize_time: String(fd.get("daily_finalize_time") || "") || null,
      promotion_month: Number(fd.get("promotion_month")),
    };
    try {
      const endpoint = pending ? `/api/backend/admin/config/organization-setting-versions/${pending.id}` : "/api/backend/admin/config/organization-settings/versions";
      const method = pending ? "PATCH" : "POST";
      await apiFetch<OrganizationSettingVersionPublic>(endpoint, { method, body: JSON.stringify(payload) });
      setSuccess(pending ? "Pending organization settings updated." : "Pending organization settings created.");
      router.refresh();
    } catch (e) { setError(e instanceof Error ? e.message : "Organization settings update failed."); }
    finally { setBusy(false); }
  }

  const base = pending ?? current;
  return <div className="space-y-6"><MutationFeedback error={error} success={success} />
    <Card><CardHeader title="Current active settings" description="Runtime settings used to interpret new cards and lifecycle boundaries." /><dl className="grid gap-4 p-5 text-sm sm:grid-cols-2 lg:grid-cols-4"><div><dt className="text-slate-500">Timezone</dt><dd className="font-semibold">{current.timezone}</dd></div><div><dt className="text-slate-500">Week starts</dt><dd className="font-semibold">{weekDays[current.week_start_day] ?? current.week_start_day}</dd></div><div><dt className="text-slate-500">Daily deadline</dt><dd className="font-semibold">{current.daily_finalize_time}</dd></div><div><dt className="text-slate-500">Promotion month</dt><dd className="font-semibold">{months[current.promotion_month - 1] ?? current.promotion_month}</dd></div></dl></Card>
    <Card><CardHeader title={pending ? `Edit PENDING version v${pending.version_number}` : "Schedule settings change"} description="A single pending version is editable. ACTIVE/ARCHIVED settings remain immutable history." /><form onSubmit={submit} className="grid gap-4 p-5 md:grid-cols-2 lg:grid-cols-3"><label className="text-sm font-medium">Effective week<Input name="effective_from_week" type="date" defaultValue={pending?.effective_from_week ?? ""} className="mt-1" /></label><label className="text-sm font-medium">IANA timezone<Input name="timezone" defaultValue={base.timezone} required className="mt-1" /></label><label className="text-sm font-medium">Week start<Select name="week_start_day" defaultValue={String(base.week_start_day)} className="mt-1">{weekDays.map((d, i) => <option key={d} value={i}>{d}</option>)}</Select></label><label className="text-sm font-medium">Daily finalize time<Input name="daily_finalize_time" type="time" step="1" defaultValue={base.daily_finalize_time} required className="mt-1" /></label><label className="text-sm font-medium">Promotion month<Select name="promotion_month" defaultValue={String(base.promotion_month)} className="mt-1">{months.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}</Select></label><div className="self-end"><Button disabled={busy} type="submit">{busy ? "Saving…" : pending ? "Update pending version" : "Create pending version"}</Button></div></form></Card>
    <Card><CardHeader title="Version history" /><div className="overflow-x-auto"><table className="w-full min-w-[720px] text-left text-sm"><thead className="bg-slate-50 text-slate-500"><tr><th className="px-4 py-3">Version</th><th>Effective week</th><th>Status</th><th>Timezone</th><th>Week start</th><th>Deadline</th><th>Promotion</th></tr></thead><tbody>{versions.map((v) => <tr key={v.id} className="border-t"><td className="px-4 py-3 font-semibold">v{v.version_number}</td><td>{v.effective_from_week}</td><td>{v.status}</td><td>{v.timezone}</td><td>{weekDays[v.week_start_day] ?? v.week_start_day}</td><td>{v.daily_finalize_time}</td><td>{months[v.promotion_month - 1] ?? v.promotion_month}</td></tr>)}</tbody></table></div></Card>
  </div>;
}
