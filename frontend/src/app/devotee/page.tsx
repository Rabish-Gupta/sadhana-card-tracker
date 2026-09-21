import Link from "next/link";
import { requireRole, safeServerApi, serverApi } from "@/lib/auth/server";
import type { DailyCardPublic, FourWeekReportPublic, LifecycleStatusPublic, WeeklyEvaluationPublic } from "@/lib/api/types";
import { Badge } from "@/components/ui/badge";
import { Card, CardHeader } from "@/components/ui/card";
import { Notice } from "@/components/ui/notice";
import { Progress } from "@/components/ui/progress";
import { formatDate, formatDecimal } from "@/lib/utils";

export default async function DevoteeDashboard() {
  const user = await requireRole("DEVOTEE");
  const [card, lifecycle, weekly, monthly] = await Promise.all([
    serverApi<DailyCardPublic>("/cards/today"),
    serverApi<LifecycleStatusPublic>("/lifecycle/status"),
    safeServerApi<WeeklyEvaluationPublic>("/weekly/latest", [404, 409]),
    safeServerApi<FourWeekReportPublic>("/monthly/latest", [404, 409]),
  ]);
  const countable = card.activities.filter((activity) => activity.counts_toward_card_fill);
  const filled = countable.filter((activity) => activity.is_filled).length;
  const completeness = countable.length ? (filled / countable.length) * 100 : 0;

  return (
    <div className="space-y-6">
      <div>
        <p className="text-sm font-semibold text-amber-700">Hare Krishna, {user.full_name}</p>
        <h1 className="mt-1 text-3xl font-bold text-slate-900">Your dashboard</h1>
        <p className="mt-2 text-slate-600">Recorded data, scoring evaluation, and analysis are shown separately. No combined balance score is used.</p>
      </div>

      {(lifecycle.bhima_choice_required || lifecycle.pending_category_transition || lifecycle.pending_deactivation_week) ? (
        <Notice tone="warning">
          {lifecycle.bhima_choice_required ? "Your initial Bhima employment choice is required. " : ""}
          {lifecycle.pending_category_transition ? `Pending transition: ${lifecycle.pending_category_transition.target_category_name} from ${formatDate(lifecycle.pending_category_transition.effective_from_week)}. ` : ""}
          {lifecycle.pending_deactivation_week ? `Deactivation scheduled from ${formatDate(lifecycle.pending_deactivation_week)}.` : ""}
          <Link href="/devotee/lifecycle" className="ml-1 font-semibold underline">Open lifecycle</Link>
        </Notice>
      ) : null}

      <div className="grid gap-4 md:grid-cols-3">
        <Card className="p-5"><p className="text-xs uppercase tracking-wide text-slate-500">Category</p><p className="mt-2 text-xl font-bold">{lifecycle.current_category_name}</p><div className="mt-3"><Badge>{lifecycle.current_category_code}</Badge></div></Card>
        <Card className="p-5"><p className="text-xs uppercase tracking-wide text-slate-500">Today&apos;s countable activities</p><p className="mt-2 text-xl font-bold">{filled}/{countable.length} complete</p><Progress value={completeness} className="mt-3" /><p className="mt-2 text-xs text-slate-500">Card-fill score is determined only at finalization.</p></Card>
        <Card className="p-5"><p className="text-xs uppercase tracking-wide text-slate-500">Card status</p><p className="mt-2 text-xl font-bold">{card.status.replaceAll("_", " ")}</p><p className="mt-2 text-sm text-slate-500">{formatDate(card.card_date)} · revision {card.revision_number}</p></Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="p-5">
          <div className="flex items-center justify-between gap-3"><h2 className="font-bold">Latest official week</h2><Link href="/devotee/weekly" className="text-sm font-semibold text-amber-700">Details →</Link></div>
          {weekly ? <div className="mt-4 grid grid-cols-2 gap-4 text-sm"><div><p className="text-slate-500">Sadhana</p><p className="mt-1 text-2xl font-bold">{formatDecimal(weekly.sadhana_percentage)}</p><p className="text-xs text-slate-500">{weekly.sadhana_score}/{weekly.sadhana_max_score}</p></div><div><p className="text-slate-500">Academic</p><p className="mt-1 text-2xl font-bold">{formatDecimal(weekly.academic_percentage)}</p><p className="text-xs text-slate-500">{weekly.academic_score}/{weekly.academic_max_score}</p></div></div> : <p className="mt-4 text-sm text-slate-500">No complete official week is available yet.</p>}
        </Card>
        <Card className="p-5">
          <div className="flex items-center justify-between gap-3"><h2 className="font-bold">Latest four-week report</h2><Link href="/devotee/monthly" className="text-sm font-semibold text-amber-700">Details →</Link></div>
          {monthly ? <div className="mt-4 grid grid-cols-2 gap-4 text-sm"><div><p className="text-slate-500">Sadhana</p><p className="mt-1 text-2xl font-bold">{formatDecimal(monthly.sadhana.percentage)}</p><p className="text-xs text-slate-500">{monthly.sadhana.score}/{monthly.sadhana.maximum_score}</p></div><div><p className="text-slate-500">Academic</p><p className="mt-1 text-2xl font-bold">{formatDecimal(monthly.academic.percentage)}</p><p className="text-xs text-slate-500">{monthly.academic.score}/{monthly.academic.maximum_score}</p></div></div> : <p className="mt-4 text-sm text-slate-500">Four adjacent complete weeks are not available yet.</p>}
        </Card>
      </div>

      <Card>
        <CardHeader title="Continue" description="Use Update throughout the day; previous cards remain read-only." />
        <div className="grid gap-3 p-5 sm:grid-cols-2 lg:grid-cols-5">
          {[["Today's card","/devotee/card"],["Previous cards","/devotee/history"],["Latest weekly","/devotee/weekly"],["4-week report","/devotee/monthly"],["Lifecycle","/devotee/lifecycle"]].map(([label,href]) => <Link key={href} href={href} className="rounded-xl border border-slate-200 p-4 font-semibold hover:border-amber-300 hover:bg-amber-50">{label}</Link>)}
        </div>
      </Card>

      <Card className="p-5"><h2 className="font-bold">Profile</h2><dl className="mt-4 grid gap-4 text-sm sm:grid-cols-2 lg:grid-cols-4"><div><dt className="text-slate-500">College</dt><dd className="font-semibold">{user.devotee_profile?.college ?? "—"}</dd></div><div><dt className="text-slate-500">Branch</dt><dd className="font-semibold">{user.devotee_profile?.branch ?? "—"}</dd></div><div><dt className="text-slate-500">Academic year</dt><dd className="font-semibold">{user.devotee_profile?.current_academic_year ?? "Passed out"}</dd></div><div><dt className="text-slate-500">Account</dt><dd className="font-semibold">{user.account_status}</dd></div></dl></Card>
    </div>
  );
}
