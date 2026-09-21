import { Badge } from "@/components/ui/badge";
import { Card, CardHeader } from "@/components/ui/card";
import { Notice } from "@/components/ui/notice";
import { Progress } from "@/components/ui/progress";
import { safeServerApi } from "@/lib/auth/server";
import type { ActivityCategory, WeeklyActivityResultPublic, WeeklyEvaluationPublic } from "@/lib/api/types";
import { decimalToNumber, formatCompactNumber, formatDate, formatDecimal, signedDecimal } from "@/lib/utils";

function StandardLine({ activity }: { activity: WeeklyActivityResultPublic }) {
  if (activity.standard_achievement == null) return <span className="text-slate-400">No configured standard</span>;
  const details = activity.calculation_details?.standard;
  if (details && typeof details === "object") {
    const data = details as Record<string, unknown>;
    if (data.period === "DAILY") return <span>{String(data.achieved_days ?? "—")}/{String(data.evaluated_days ?? "—")} days achieved · {formatDecimal(activity.standard_achievement)}</span>;
    if (data.period === "WEEKLY") return <span>{data.met ? "Target met" : "Target not met"} · {formatDecimal(activity.standard_achievement)}</span>;
  }
  return <span>{formatDecimal(activity.standard_achievement)}</span>;
}

function ActivityTable({ activities, category }: { activities: WeeklyActivityResultPublic[]; category: ActivityCategory }) {
  const filtered = activities.filter((item) => item.category === category);
  return (
    <Card>
      <CardHeader title={category === "SADHANA" ? "Sadhana activities" : "Academic / lifestyle activities"} description="Scores, raw weekly totals, and standards remain separate." />
      <div className="overflow-x-auto">
        <table className="w-full min-w-[760px] text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500"><tr><th className="px-5 py-3">Activity</th><th className="px-4 py-3">Raw</th><th className="px-4 py-3">Score</th><th className="px-4 py-3">Standard</th><th className="px-4 py-3">Previous</th></tr></thead>
          <tbody className="divide-y divide-slate-100">
            {filtered.map((activity) => (
              <tr key={activity.activity_id} className="align-top">
                <td className="px-5 py-4"><p className="font-semibold text-slate-900">{activity.name}</p><p className="mt-1 text-xs text-slate-500">{activity.scoring_type.replaceAll("_", " ").toLowerCase()}</p></td>
                <td className="px-4 py-4 font-medium">{activity.raw_total == null ? "—" : formatCompactNumber(activity.raw_total)}</td>
                <td className="px-4 py-4 font-semibold">{activity.final_activity_score == null ? "—" : `${activity.final_activity_score}${activity.maximum_score != null ? ` / ${activity.maximum_score}` : ""}`}</td>
                <td className="px-4 py-4 text-slate-600"><StandardLine activity={activity} /></td>
                <td className="px-4 py-4 text-slate-600">{activity.previous_week ? `${activity.previous_week.final_activity_score ?? "—"}${activity.previous_week.maximum_score != null ? ` / ${activity.previous_week.maximum_score}` : ""}` : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

export default async function WeeklyPage() {
  const report = await safeServerApi<WeeklyEvaluationPublic>("/weekly/latest", [404, 409]);
  if (!report) return <Card className="p-6"><h1 className="text-2xl font-bold">Weekly report</h1><p className="mt-2 text-slate-600">No complete official week is available yet. Partial lifecycle weeks are intentionally not prorated.</p></Card>;
  const activities = report.activities ?? [];
  const sadhanaPct = decimalToNumber(report.sadhana_percentage) ?? 0;
  const academicPct = decimalToNumber(report.academic_percentage) ?? 0;
  const prev = report.previous_week;
  const sadhanaChange = prev && report.sadhana_percentage != null && prev.sadhana_percentage != null ? sadhanaPct - (decimalToNumber(prev.sadhana_percentage) ?? 0) : null;
  const academicChange = prev && report.academic_percentage != null && prev.academic_percentage != null ? academicPct - (decimalToNumber(prev.academic_percentage) ?? 0) : null;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4"><div><h1 className="text-3xl font-bold">Latest weekly report</h1><p className="mt-2 text-slate-600">{formatDate(report.week_start_date)} – {formatDate(report.week_end_date)} · {report.category_name}</p></div><Badge>Official complete week</Badge></div>
      <Notice tone="info">Weekly evaluation uses the historical rule, standard, and category configuration attached to this week. Standards are analysis and do not add extra marks.</Notice>
      <div className="grid gap-4 md:grid-cols-2">
        <Card className="p-6"><p className="text-sm font-semibold text-slate-500">Sadhana</p><p className="mt-2 text-3xl font-bold">{report.sadhana_score} / {report.sadhana_max_score}</p><p className="mt-1 text-sm text-slate-600">{formatDecimal(report.sadhana_percentage)}</p><Progress value={sadhanaPct} className="mt-4" />{sadhanaChange !== null ? <p className="mt-3 text-xs text-slate-500">vs previous week: {signedDecimal(sadhanaChange)}</p> : null}</Card>
        <Card className="p-6"><p className="text-sm font-semibold text-slate-500">Academic</p><p className="mt-2 text-3xl font-bold">{report.academic_score} / {report.academic_max_score}</p><p className="mt-1 text-sm text-slate-600">{formatDecimal(report.academic_percentage)}</p><Progress value={academicPct} className="mt-4" />{academicChange !== null ? <p className="mt-3 text-xs text-slate-500">vs previous week: {signedDecimal(academicChange)}</p> : null}</Card>
      </div>
      {activities.length ? <><ActivityTable activities={activities} category="SADHANA" /><ActivityTable activities={activities} category="ACADEMIC" /></> : null}
    </div>
  );
}
