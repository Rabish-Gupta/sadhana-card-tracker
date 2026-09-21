"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api/client";
import type { ActivityCategory, ActivityFieldPublic, ActivityInputType, ActivityPublic } from "@/lib/api/types";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { MutationFeedback } from "@/components/admin/mutation-feedback";

const inputTypes: ActivityInputType[] = ["NUMBER", "COUNT", "DURATION", "TIME", "BOOLEAN", "TEXT", "SELECTION"];

export function ActivityManager({ activities }: { activities: ActivityPublic[] }) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [archiveReason, setArchiveReason] = useState<Record<string, string>>({});

  async function mutate<T>(key: string, url: string, method: string, body?: unknown, message?: string) {
    setBusy(key); setError(null); setSuccess(null);
    try {
      await apiFetch<T>(url, { method, body: body === undefined ? undefined : JSON.stringify(body) });
      setSuccess(message ?? "Saved."); router.refresh();
    } catch (e) { setError(e instanceof Error ? e.message : "Configuration change failed."); }
    finally { setBusy(null); }
  }

  async function createActivity(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const fd = new FormData(event.currentTarget);
    const payload = { code: String(fd.get("code") ?? "").trim().toUpperCase(), name: String(fd.get("name") ?? "").trim(), category: String(fd.get("category")) as ActivityCategory, description: String(fd.get("description") ?? "").trim() || null, is_system_derived: fd.get("is_system_derived") === "on" };
    await mutate<ActivityPublic>("new-activity", "/api/backend/admin/config/activities", "POST", payload, `Activity ${payload.name} created.`);
    if (!error) event.currentTarget.reset();
  }

  async function createField(event: FormEvent<HTMLFormElement>, activity: ActivityPublic) {
    event.preventDefault(); const fd = new FormData(event.currentTarget);
    const payload = { field_key: String(fd.get("field_key") ?? "").trim(), label: String(fd.get("label") ?? "").trim(), input_type: String(fd.get("input_type")) as ActivityInputType, unit_code: String(fd.get("unit_code") ?? "").trim() || null, display_order: Number(fd.get("display_order") ?? 0), required_for_completion: fd.get("required_for_completion") === "on" };
    await mutate<ActivityFieldPublic>(`new-field-${activity.id}`, `/api/backend/admin/config/activities/${activity.id}/fields`, "POST", payload, `Field ${payload.label} created.`);
  }

  return <div className="space-y-6"><MutationFeedback error={error} success={success} />
    <Card><CardHeader title="Create activity" description="Activity code/category/system-derived semantics are fixed after creation. Archive + replace if meaning changes." /><form onSubmit={createActivity} className="grid gap-4 p-5 md:grid-cols-2 lg:grid-cols-3"><label className="text-sm font-medium">Code<Input name="code" minLength={2} maxLength={50} required className="mt-1" placeholder="EXTRA_READING" /></label><label className="text-sm font-medium">Name<Input name="name" minLength={2} maxLength={150} required className="mt-1" /></label><label className="text-sm font-medium">Category<Select name="category" className="mt-1"><option value="SADHANA">Sadhana</option><option value="ACADEMIC">Academic</option></Select></label><label className="text-sm font-medium md:col-span-2">Description<Input name="description" className="mt-1" /></label><label className="flex items-center gap-2 self-end text-sm font-medium"><input name="is_system_derived" type="checkbox" /> System-derived</label><div className="md:col-span-2 lg:col-span-3"><Button disabled={busy === "new-activity"}>Create activity</Button></div></form></Card>
    <div className="space-y-5">{activities.map((activity) => <Card key={activity.id}><CardHeader title={activity.name} description={`${activity.code} · ${activity.category}${activity.is_system_derived ? " · SYSTEM DERIVED" : ""}${activity.is_archived ? " · ARCHIVED" : ""}`} /><div className="space-y-5 p-5">
      <form className="grid gap-3 md:grid-cols-[1fr_2fr_auto]" onSubmit={(e) => { e.preventDefault(); const fd = new FormData(e.currentTarget); void mutate<ActivityPublic>(`edit-${activity.id}`, `/api/backend/admin/config/activities/${activity.id}`, "PATCH", { name: String(fd.get("name")), description: String(fd.get("description") ?? "") || null }, "Activity metadata updated."); }}><Input name="name" defaultValue={activity.name} required /><Input name="description" defaultValue={activity.description ?? ""} placeholder="Description" /><Button variant="secondary" disabled={busy === `edit-${activity.id}`}>Save metadata</Button></form>
      <div><h3 className="font-semibold">Fields</h3><p className="mt-1 text-xs text-slate-500">field_key, input_type and unit semantics are intentionally immutable after creation.</p><div className="mt-3 space-y-2">{activity.fields.length === 0 ? <p className="text-sm text-slate-500">No user-input fields.</p> : activity.fields.map((field) => <form key={field.id} className="grid gap-2 rounded-xl border border-slate-200 p-3 md:grid-cols-[1fr_100px_130px_auto]" onSubmit={(e) => { e.preventDefault(); const fd = new FormData(e.currentTarget); void mutate<ActivityFieldPublic>(`field-${field.id}`, `/api/backend/admin/config/activity-fields/${field.id}`, "PATCH", { label: String(fd.get("label")), display_order: Number(fd.get("display_order")) }, "Field display metadata updated."); }}><div><Input name="label" defaultValue={field.label} disabled={field.is_archived} /><p className="mt-1 text-xs text-slate-500">{field.field_key} · {field.input_type}{field.unit_code ? ` · ${field.unit_code}` : ""}</p></div><Input name="display_order" type="number" min={0} defaultValue={field.display_order} disabled={field.is_archived} /><Button variant="secondary" disabled={field.is_archived || busy === `field-${field.id}`}>Save</Button>{field.is_archived ? <span className="self-center text-xs font-semibold text-slate-500">Archived</span> : <Button type="button" variant="danger" onClick={() => { const why = window.prompt("Reason for archiving this field?")?.trim(); if (why) void mutate<ActivityFieldPublic>(`archive-field-${field.id}`, `/api/backend/admin/config/activity-fields/${field.id}/archive`, "POST", { reason: why }, "Field archived."); }}>Archive</Button>}</form>)}</div></div>
      {!activity.is_system_derived && !activity.is_archived ? <form onSubmit={(e) => void createField(e, activity)} className="grid gap-3 rounded-xl bg-slate-50 p-4 md:grid-cols-2 lg:grid-cols-4"><label className="text-sm font-medium">Field key<Input name="field_key" required className="mt-1" /></label><label className="text-sm font-medium">Label<Input name="label" required className="mt-1" /></label><label className="text-sm font-medium">Input type<Select name="input_type" className="mt-1">{inputTypes.map((t) => <option key={t}>{t}</option>)}</Select></label><label className="text-sm font-medium">Unit code<Input name="unit_code" className="mt-1" placeholder="MINUTES" /></label><label className="text-sm font-medium">Display order<Input name="display_order" type="number" min={0} defaultValue={activity.fields.length} className="mt-1" /></label><label className="flex items-center gap-2 self-end pb-3 text-sm font-medium"><input name="required_for_completion" type="checkbox" defaultChecked /> Required for completion</label><div className="self-end pb-1"><Button disabled={busy === `new-field-${activity.id}`}>Add field</Button></div></form> : null}
      {!activity.is_archived ? <div className="border-t pt-4"><Textarea value={archiveReason[activity.id] ?? ""} onChange={(e) => setArchiveReason((old) => ({ ...old, [activity.id]: e.target.value }))} placeholder="Reason required to archive the activity" /><Button className="mt-2" variant="danger" disabled={!archiveReason[activity.id]?.trim() || busy === `archive-${activity.id}`} onClick={() => void mutate<ActivityPublic>(`archive-${activity.id}`, `/api/backend/admin/config/activities/${activity.id}/archive`, "POST", { reason: archiveReason[activity.id].trim() }, "Activity archived.")}>Archive activity</Button></div> : null}
    </div></Card>)}</div>
  </div>;
}
