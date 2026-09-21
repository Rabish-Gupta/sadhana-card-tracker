import { Badge } from "@/components/ui/badge";
import { Card, CardHeader } from "@/components/ui/card";
import { Notice } from "@/components/ui/notice";
import { Progress } from "@/components/ui/progress";
import { safeServerApi } from "@/lib/auth/server";
import type { ActivityCategory, FourWeekActivityPublic, FourWeekReportPublic, FourWeekScoreSummaryPublic } from "@/lib/api/types";
import { decimalToNumber, formatCompactNumber, formatDate, formatDecimal, signedDecimal } from "@/lib/utils";

function SummaryCard({ label, summary, previousChange }: { label: string; summary: FourWeekScoreSummaryPublic; previousChange?: string | null }) {
  const percentage = decimalToNumber(summary.percentage) ?? 0;
  return (
    <Card className="p-6">
      <p className="text-sm font-semibold text-slate-500">{label}</p>
      <p className="mt-2 text-3xl font-bold text-slate-900">{summary.score} / {summary.maximum_score}</p>
      <p className="mt-1 text-sm text-slate-600">{formatDecimal(summary.percentage)}</p>
      <Progress value={percentage} className="mt-4" />
      <dl className="mt-5 grid grid-cols-2 gap-3 text-xs">
        <div><dt className="text-slate-500">4-week average</dt><dd className="mt-1 font-semibold">{formatDecimal(summary.trend.average_percentage)}</dd></div>
        <div><dt className="text-slate-500">Week 1 → Week 4</dt><dd className="mt-1 font-semibold">{signedDecimal(summary.trend.change_percentage_points)}</dd></div>
        <div><dt className="text-slate-500">Range</dt><dd className="mt-1 font-semibold">{formatDecimal(summary.trend.range_percentage_points, " pp")}</dd></div>
        <div><dt className="text-slate-500">vs previous 4 weeks</dt><dd className="mt-1 font-semibold">{previousChange == null ? "—" : signedDecimal(previousChange)}</dd></div>
      </dl>
    </Card>
  );
}

function standardSummary(activity: FourWeekActivityPublic): string {
  if (activity.daily_standard_evaluated_days) return `${activity.daily_standard_achieved_days ?? 0}/${activity.daily_standard_evaluated_days} days`;
  if (activity.weekly_standard_evaluated_weeks) return `${activity.weekly_standard_met_weeks ?? 0}/${activity.weekly_standard_evaluated_weeks} weeks`;
  if (activity.standard_achievement_average != null) return formatDecimal(activity.standard_achievement_average);
  return "—";
}

function ActivitySection({ activities, category }: { activities: FourWeekActivityPublic[]; category: ActivityCategory }) {
  const rows = activities.filter((activity) => activity.category === category);
  return (
    <Card>
      <CardHeader
        title={category === "SADHANA" ? "Sadhana activity analysis" : "Academic / lifestyle activity analysis"}
        description="Four adjacent complete weeks. Raw totals, evaluation scores, and standards stay distinct."
      />
      <div className="overflow-x-auto">
        <table className="w-full min-w-[800px] text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500"><tr><th className="px-5 py-3">Activity</th><th className="px-4 py-3">4-week score</th><th className="px-4 py-3">Raw total</th><th className="px-4 py-3">Standard</th><th className="px-4 py-3">Weekly pattern</th></tr></thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map((activity) => (
              <tr key={activity.activity_id} className="align-top">
                <td className="px-5 py-4"><p className="font-semibold text-slate-900">{activity.name}</p><p className="mt-1 text-xs text-slate-500">{activity.scoring_types_seen?.join(" / ").replaceAll("_", " ").toLowerCase() ?? "tracked"}</p></td>
                <td className="px-4 py-4 font-semibold">{activity.final_score_total == null ? "—" : `${activity.final_score_total}${activity.maximum_score_total != null ? ` / ${activity.maximum_score_total}` : ""}`}<p className="mt-1 text-xs font-normal text-slate-500">{formatDecimal(activity.score_percentage)}</p></td>
                <td className="px-4 py-4 font-medium">{formatCompactNumber(activity.raw_total_sum)}</td>
                <td className="px-4 py-4 text-slate-600">{standardSummary(activity)}</td>
                <td className="px-4 py-4"><div className="flex gap-1.5">{((activity.weekly_final_scores?.some((value) => value !== null) ? activity.weekly_final_scores : activity.weekly_raw_totals) ?? []).map((value, index) => <span key={index} className="min-w-9 rounded-md bg-slate-100 px-2 py-1 text-center text-xs font-semibold text-slate-700">{value == null ? "—" : Number(value).toString()}</span>)}</div></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

export default async function MonthlyPage() {
  const report = await safeServerApi<FourWeekReportPublic>("/monthly/latest", [404, 409]);
  if (!report) return <Card className="p-6"><h1 className="text-2xl font-bold">4-week report</h1><p className="mt-2 text-slate-600">Four adjacent complete official weeks are not available yet.</p></Card>;
  const activities = report.activities ?? [];
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4"><div><h1 className="text-3xl font-bold">Four-week report</h1><p className="mt-2 text-slate-600">{formatDate(report.period_start_date)} – {formatDate(report.period_end_date)} · exactly {report.weeks_count} adjacent complete weeks</p></div><Badge>Project monthly report</Badge></div>
      <Notice tone="info">This project&apos;s monthly report is four adjacent complete organization weeks, not a calendar month. A week that crosses a calendar-month boundary remains whole.</Notice>
      <div className="grid gap-4 md:grid-cols-2">
        <SummaryCard label="Sadhana" summary={report.sadhana} previousChange={report.previous_period?.sadhana_change_percentage_points} />
        <SummaryCard label="Academic" summary={report.academic} previousChange={report.previous_period?.academic_change_percentage_points} />
      </div>
      {report.weeks?.length ? (
        <Card>
          <CardHeader title="Four weekly results" description="Sadhana and Academic remain separate in every week." />
          <div className="grid gap-3 p-5 md:grid-cols-2 xl:grid-cols-4">
            {report.weeks.map((week, index) => (
              <div key={week.week_start_date} className="rounded-xl border border-slate-200 p-4">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Week {index + 1}</p>
                <p className="mt-1 text-sm font-semibold">{formatDate(week.week_start_date)} – {formatDate(week.week_end_date)}</p>
                <div className="mt-4 space-y-2 text-sm"><div className="flex justify-between"><span className="text-slate-500">Sadhana</span><strong>{week.sadhana_score}/{week.sadhana_max_score}</strong></div><div className="flex justify-between"><span className="text-slate-500">Academic</span><strong>{week.academic_score}/{week.academic_max_score}</strong></div></div>
              </div>
            ))}
          </div>
        </Card>
      ) : null}
      {activities.length ? <><ActivitySection activities={activities} category="SADHANA" /><ActivitySection activities={activities} category="ACADEMIC" /></> : null}
      {report.previous_period ? <Card className="p-5"><h2 className="font-semibold">Previous four-week period</h2><p className="mt-2 text-sm text-slate-600">{formatDate(report.previous_period.period_start_date)} – {formatDate(report.previous_period.period_end_date)} · Sadhana {formatDecimal(report.previous_period.sadhana_percentage)} · Academic {formatDecimal(report.previous_period.academic_percentage)}</p></Card> : null}
      {report.observations?.length ? <Card className="p-6"><h2 className="font-semibold">Factual observations</h2><p className="mt-1 text-xs text-slate-500">Observations summarize recorded patterns and standards; they are not judgments of spiritual advancement.</p><ul className="mt-4 space-y-2 text-sm text-slate-700">{report.observations.map((item) => <li key={item} className="rounded-lg bg-slate-50 px-3 py-2">• {item}</li>)}</ul></Card> : null}
    </div>
  );
}
