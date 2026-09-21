"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api/client";
import type { UserPublic } from "@/lib/api/types";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { MutationFeedback } from "@/components/admin/mutation-feedback";

export function RegistrationManager({ users }: { users: UserPublic[] }) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [reason, setReason] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  async function act(user: UserPublic, action: "approve" | "reject") {
    setBusy(user.id); setError(null); setSuccess(null);
    try {
      const body = action === "reject" ? JSON.stringify({ reason: reason[user.id]?.trim() || null }) : undefined;
      await apiFetch<UserPublic>(`/api/backend/admin/registrations/${user.id}/${action}`, { method: "POST", body });
      setSuccess(`${user.full_name} ${action === "approve" ? "approved" : "rejected"}.`);
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Registration action failed.");
    } finally { setBusy(null); }
  }

  if (users.length === 0) return <Card className="p-6 text-slate-600">No pending registrations.</Card>;
  return (
    <div className="space-y-4">
      <MutationFeedback error={error} success={success} />
      {users.map((user) => (
        <Card className="p-5" key={user.id}>
          <div className="grid gap-5 lg:grid-cols-[1fr_360px]">
            <div>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div><p className="text-lg font-semibold">{user.full_name}</p><p className="text-sm text-slate-500">{user.email} · {user.phone_number}</p></div>
                <span className="rounded-full bg-amber-100 px-3 py-1 text-xs font-semibold text-amber-800">PENDING</span>
              </div>
              {user.devotee_profile ? (
                <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
                  <div><dt className="text-slate-500">College / branch</dt><dd className="font-medium">{user.devotee_profile.college} · {user.devotee_profile.branch}</dd></div>
                  <div><dt className="text-slate-500">Current category</dt><dd className="font-medium">{user.devotee_profile.current_category.display_name}</dd></div>
                  <div><dt className="text-slate-500">Joining year</dt><dd className="font-medium">{user.devotee_profile.college_joining_year}</dd></div>
                  <div><dt className="text-slate-500">Academic year</dt><dd className="font-medium">{user.devotee_profile.current_academic_year ?? "—"}</dd></div>
                </dl>
              ) : null}
            </div>
            <div className="space-y-3">
              <Textarea value={reason[user.id] ?? ""} onChange={(e) => setReason((old) => ({ ...old, [user.id]: e.target.value }))} placeholder="Reason for rejection (optional)" />
              <div className="flex gap-2">
                <Button disabled={busy === user.id} onClick={() => void act(user, "approve")}>Approve</Button>
                <Button variant="danger" disabled={busy === user.id} onClick={() => void act(user, "reject")}>Reject</Button>
              </div>
              <p className="text-xs text-slate-500">Self-registration data is reviewed as submitted; approval does not edit the registration.</p>
            </div>
          </div>
        </Card>
      ))}
    </div>
  );
}
