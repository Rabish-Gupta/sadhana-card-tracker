"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Notice } from "@/components/ui/notice";
import { ApiError, apiFetch } from "@/lib/api/client";
import type { DailyActivityValuePublic, DailyCardPublic } from "@/lib/api/types";
import { formatDate, formatDateTime, formatTime, unitLabel } from "@/lib/utils";

function displayValue(value: DailyActivityValuePublic): string {
  if (!value.is_filled) return "N/A";
  if (value.input_type === "BOOLEAN") return value.boolean_value ? "Yes" : "No";
  if (value.input_type === "TIME") return formatTime(value.time_value);
  if (["NUMBER", "COUNT", "DURATION"].includes(value.input_type)) {
    return `${Number(value.numeric_value).toString()}${value.unit_code ? ` ${unitLabel(value.unit_code)}` : ""}`;
  }
  return value.text_value ?? "N/A";
}

export function HistoryBrowser() {
  const [date, setDate] = useState("");
  const [card, setCard] = useState<DailyCardPublic | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function load() {
    if (!date) return;
    setLoading(true);
    setError(null);
    setCard(null);
    try {
      setCard(await apiFetch<DailyCardPublic>(`/api/backend/cards/${date}`));
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 404) setError("No historical card exists for that date.");
      else if (caught instanceof Error) setError(caught.message);
      else setError("Unable to load that card.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Previous cards</h1>
        <p className="mt-2 text-slate-600">Historical cards are read-only for devotees. Missing values are shown as N/A.</p>
      </div>
      <Card className="p-5">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <label className="flex-1 text-sm font-semibold text-slate-700">
            Card date
            <Input type="date" value={date} onChange={(event) => setDate(event.target.value)} className="mt-2" />
          </label>
          <Button onClick={load} disabled={!date || loading}>{loading ? "Loading…" : "Open card"}</Button>
        </div>
      </Card>
      {error ? <Notice tone="warning">{error}</Notice> : null}
      {card ? (
        <>
          <Card className="p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-xl font-bold">{formatDate(card.card_date)}</h2>
                <p className="mt-1 text-sm text-slate-500">{card.category_name} · finalized {formatDateTime(card.finalized_at, card.timezone_snapshot)}</p>
              </div>
              <Badge>{card.status}</Badge>
            </div>
          </Card>
          <div className="grid gap-4 lg:grid-cols-2">
            {card.activities.map((activity) => (
              <Card key={activity.activity_id}>
                <CardHeader title={activity.name} action={<Badge>{activity.category}</Badge>} />
                <div className="space-y-2 p-5">
                  {activity.values.length ? activity.values.map((value) => (
                    <div key={value.field_id} className="flex justify-between gap-4 rounded-lg bg-slate-50 px-3 py-2 text-sm">
                      <span className="text-slate-500">{value.label}</span><span className="font-semibold">{displayValue(value)}</span>
                    </div>
                  )) : <p className="text-sm text-slate-500">System-derived activity</p>}
                  <div className="flex justify-between border-t border-slate-100 pt-3 text-sm"><span className="text-slate-500">Score</span><span className="font-semibold">{activity.daily_score ?? "—"}{activity.max_score_snapshot !== null ? ` / ${activity.max_score_snapshot}` : ""}</span></div>
                </div>
              </Card>
            ))}
          </div>
        </>
      ) : null}
    </div>
  );
}
