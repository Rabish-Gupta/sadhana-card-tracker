"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Notice } from "@/components/ui/notice";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch } from "@/lib/api/client";
import type { EmploymentStatus, LifecycleStatusPublic } from "@/lib/api/types";
import { formatDate } from "@/lib/utils";

export function BhimaStatusForm({ initialStatus }: { initialStatus: LifecycleStatusPublic }) {
  const [status, setStatus] = useState(initialStatus);
  const currentEmployment: EmploymentStatus | null = status.current_category_code === "BHIMA_WORKING"
    ? "WORKING"
    : status.current_category_code === "BHIMA_NOT_WORKING"
      ? "NOT_WORKING"
      : null;
  const pendingEmployment: EmploymentStatus | null = status.pending_category_transition?.target_category_code === "BHIMA_WORKING"
    ? "WORKING"
    : status.pending_category_transition?.target_category_code === "BHIMA_NOT_WORKING"
      ? "NOT_WORKING"
      : null;

  const [choice, setChoice] = useState<EmploymentStatus | null>(pendingEmployment ?? currentEmployment ?? null);
  const [reason, setReason] = useState("Devotee updated Bhima employment status");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const canChoose = status.current_category_code === "YUDHISHTHIRA" || currentEmployment !== null;
  if (!canChoose) return null;

  async function save() {
    if (choice === null) {
      setError("Choose Working or Not Working before saving.");
      return;
    }
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const updated = await apiFetch<LifecycleStatusPublic>("/api/backend/lifecycle/bhima-status", {
        method: "POST",
        body: JSON.stringify({ employment_status: choice, reason: reason.trim() || "Devotee updated Bhima employment status" }),
      });
      setStatus(updated);
      const activeCode = choice === "WORKING" ? "BHIMA_WORKING" : "BHIMA_NOT_WORKING";
      if (updated.current_category_code === activeCode && updated.pending_category_transition === null) {
        setMessage("Current Bhima status retained; any pending opposite-status change has been cancelled.");
      } else {
        setMessage("Bhima status choice saved. It will take effect at the applicable organization week boundary.");
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to save Bhima status.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-4 rounded-2xl border border-amber-200 bg-amber-50/60 p-5">
      <div>
        <h3 className="text-lg font-bold text-slate-900">Bhima employment status</h3>
        <p className="mt-1 text-sm text-slate-600">
          {status.bhima_choice_required
            ? "Choose your initial Bhima status. The system does not assume Working or Not Working for you."
            : "You may change Working ↔ Not Working yourself. Changes take effect from the next week boundary."}
        </p>
      </div>
      {status.pending_category_transition ? (
        <Notice tone="warning">
          Pending: <strong>{status.pending_category_transition.target_category_name}</strong> from {formatDate(status.pending_category_transition.effective_from_week)}. You may revise this pending choice before activation.
        </Notice>
      ) : null}
      <div className="grid gap-3 sm:grid-cols-2">
        {(["WORKING", "NOT_WORKING"] as const).map((item) => (
          <button
            type="button"
            key={item}
            onClick={() => setChoice(item)}
            className={`rounded-xl border p-4 text-left transition ${choice === item ? "border-amber-500 bg-white shadow-sm" : "border-slate-200 bg-white/70 hover:border-slate-300"}`}
          >
            <p className="font-bold text-slate-900">{item === "WORKING" ? "Bhima — Working" : "Bhima — Not Working"}</p>
            <p className="mt-1 text-xs text-slate-500">{item === "WORKING" ? "Currently working after graduation." : "Currently not working after graduation."}</p>
          </button>
        ))}
      </div>
      <label className="block text-sm font-semibold text-slate-700">
        Reason / note
        <Textarea value={reason} onChange={(event) => setReason(event.target.value)} className="mt-2" maxLength={1000} />
      </label>
      {error ? <Notice tone="danger">{error}</Notice> : null}
      {message ? <Notice tone="success">{message}</Notice> : null}
      <Button onClick={save} disabled={saving || choice === null || reason.trim().length < 3}>{saving ? "Saving…" : "Save choice"}</Button>
    </div>
  );
}
