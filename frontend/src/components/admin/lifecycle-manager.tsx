"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api/client";
import type { SahadevaReviewDecision, SahadevaReviewItem, SahadevaReviewResult } from "@/lib/api/types";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { MutationFeedback } from "@/components/admin/mutation-feedback";

export function LifecycleManager({ reviews }: { reviews: SahadevaReviewItem[] }) {
  const router = useRouter();
  const [decision, setDecision] = useState<Record<string, SahadevaReviewDecision>>({});
  const [reason, setReason] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  async function submitReview(item: SahadevaReviewItem) {
    const selected = decision[item.user_id];
    const why = reason[item.user_id]?.trim();
    if (!selected) { setError("Choose a Sahadeva review decision."); return; }
    if (!why || why.length < 3) { setError("A reason of at least 3 characters is required."); return; }
    setBusy(item.user_id); setError(null); setSuccess(null);
    try {
      const result = await apiFetch<SahadevaReviewResult>(`/api/backend/admin/lifecycle/devotees/${item.user_id}/sahadeva-review`, {
        method: "POST", body: JSON.stringify({ decision: selected, reason: why }),
      });
      setSuccess(`Decision scheduled for ${result.effective_from_week}.`); router.refresh();
    } catch (e) { setError(e instanceof Error ? e.message : "Review failed."); }
    finally { setBusy(null); }
  }

  async function runNow() {
    setBusy("run-now"); setError(null); setSuccess(null);
    try {
      const result = await apiFetch<Record<string, unknown>>("/api/backend/admin/lifecycle/run-now", { method: "POST" });
      setSuccess(`Lifecycle run completed. Lock acquired: ${String(result.lock_acquired ?? "unknown")}.`); router.refresh();
    } catch (e) { setError(e instanceof Error ? e.message : "Lifecycle run failed."); }
    finally { setBusy(null); }
  }

  return (
    <div className="space-y-6">
      <MutationFeedback error={error} success={success} />
      <Card><CardHeader title="Lifecycle processor" description="Normally runs automatically. Use this only as an Admin diagnostic/retry action." /><div className="p-5"><Button variant="secondary" disabled={busy === "run-now"} onClick={() => void runNow()}>{busy === "run-now" ? "Running…" : "Run lifecycle now"}</Button></div></Card>
      <div className="space-y-4">
        {reviews.length === 0 ? <Card className="p-6 text-slate-600">No Sahadeva reviews found.</Card> : reviews.map((item) => (
          <Card key={item.user_id} className="p-5">
            <div className="grid gap-5 lg:grid-cols-[1fr_420px]">
              <div><div className="flex flex-wrap items-center gap-2"><p className="font-semibold">{item.full_name}</p>{item.review_due ? <span className="rounded-full bg-red-100 px-2 py-1 text-xs font-semibold text-red-700">REVIEW DUE</span> : <span className="rounded-full bg-slate-100 px-2 py-1 text-xs font-semibold">Upcoming</span>}</div><p className="text-sm text-slate-500">{item.email}</p><p className="mt-3 text-sm text-slate-600">Review week: <strong>{item.due_week}</strong></p>{item.pending_decision ? <p className="mt-1 text-sm text-amber-700">Pending: {item.pending_decision} · {item.pending_effective_week}</p> : null}</div>
              <div className="space-y-3"><Select value={decision[item.user_id] ?? ""} onChange={(e) => setDecision((old) => ({ ...old, [item.user_id]: e.target.value as SahadevaReviewDecision }))}><option value="" disabled>Select decision</option><option value="CONTINUE_TO_NAKULA">Continue to Nakula</option><option value="DEACTIVATE">Deactivate after first year</option></Select><Textarea value={reason[item.user_id] ?? ""} onChange={(e) => setReason((old) => ({ ...old, [item.user_id]: e.target.value }))} placeholder="Mandatory reason" /><Button disabled={busy === item.user_id} onClick={() => void submitReview(item)}>Schedule decision</Button></div>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
