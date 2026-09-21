import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Notice } from "@/components/ui/notice";
import { BhimaStatusForm } from "@/components/devotee/bhima-status-form";
import { serverApi } from "@/lib/auth/server";
import type { LifecycleStatusPublic } from "@/lib/api/types";
import { formatDate } from "@/lib/utils";

export default async function LifecyclePage() {
  const status = await serverApi<LifecycleStatusPublic>("/lifecycle/status");
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Lifecycle status</h1>
        <p className="mt-2 text-slate-600">Category changes are week-boundary based so a single week is not interpreted using multiple category configurations.</p>
      </div>
      <Card className="p-6">
        <div className="flex flex-wrap items-center gap-3"><h2 className="text-xl font-bold">{status.current_category_name}</h2><Badge>{status.current_category_code}</Badge></div>
        <dl className="mt-5 grid gap-4 text-sm sm:grid-cols-2 lg:grid-cols-4">
          <div><dt className="text-slate-500">Academic year</dt><dd className="font-semibold">{status.current_academic_year ?? "Passed out"}</dd></div>
          <div><dt className="text-slate-500">Next promotion week</dt><dd className="font-semibold">{status.next_promotion_week ? formatDate(status.next_promotion_week) : "—"}</dd></div>
          <div><dt className="text-slate-500">Sahadeva review due</dt><dd className="font-semibold">{status.sahadeva_review_due ? "Yes" : "No"}</dd></div>
          <div><dt className="text-slate-500">Bhima choice required</dt><dd className="font-semibold">{status.bhima_choice_required ? "Yes" : "No"}</dd></div>
        </dl>
        {status.pending_category_transition ? <Notice tone="warning" className="mt-5">Pending transition to <strong>{status.pending_category_transition.target_category_name}</strong> from {formatDate(status.pending_category_transition.effective_from_week)}.</Notice> : null}
        {status.pending_deactivation_week ? <Notice tone="danger" className="mt-4">Account deactivation is scheduled for {formatDate(status.pending_deactivation_week)}{status.pending_deactivation_reason ? `: ${status.pending_deactivation_reason}` : "."}</Notice> : null}
        {status.sahadeva_review_due ? <Notice tone="info" className="mt-4">Your first-year Sahadeva review is due. An Admin will decide continuation to Nakula or deactivation; your historical data is preserved.</Notice> : null}
      </Card>
      <BhimaStatusForm initialStatus={status} />
    </div>
  );
}
