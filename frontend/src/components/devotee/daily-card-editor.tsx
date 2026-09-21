"use client";

import { useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Notice } from "@/components/ui/notice";
import { Progress } from "@/components/ui/progress";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, apiFetch } from "@/lib/api/client";
import type {
  ActivityCategory,
  DailyActivityPublic,
  DailyActivityValuePublic,
  DailyActivityValueUpdate,
  DailyCardPublic,
  DailyCardUpdateRequest,
} from "@/lib/api/types";
import { cn, formatDate, formatDateTime, formatTime, unitLabel } from "@/lib/utils";

type DraftValue = {
  isFilled: boolean;
  numeric: string;
  time: string;
  boolean: boolean | null;
  text: string;
};

type DraftMap = Record<string, DraftValue>;

function draftFromCard(card: DailyCardPublic): DraftMap {
  const draft: DraftMap = {};
  for (const activity of card.activities) {
    for (const value of activity.values) {
      draft[value.field_id] = {
        isFilled: value.is_filled,
        numeric: value.is_filled ? value.numeric_value : "",
        time: value.is_filled ? (value.time_value ?? "") : "",
        boolean: value.is_filled ? value.boolean_value : null,
        text: value.is_filled ? (value.text_value ?? "") : "",
      };
    }
  }
  return draft;
}

function scoreLabel(activity: DailyActivityPublic): string {
  if (activity.scoring_type === "WEEKLY_AGGREGATED") return "Scored at week end";
  if (activity.scoring_type === "NON_SCORED") return "Tracked, not scored";
  if (activity.scoring_type === "SYSTEM_DERIVED" && activity.daily_score === null) return "Calculated at finalization";
  if (activity.daily_score === null) return "Pending";
  return `${activity.daily_score}${activity.max_score_snapshot !== null ? ` / ${activity.max_score_snapshot}` : ""}`;
}

function valuePayload(value: DailyActivityValuePublic, draft: DraftValue): DailyActivityValueUpdate {
  if (!draft.isFilled) return { field_id: value.field_id, is_filled: false };

  if (["NUMBER", "COUNT", "DURATION"].includes(value.input_type)) {
    if (draft.numeric.trim() === "") throw new Error(`${value.label}: enter a number or mark it Not entered.`);
    const parsed = Number(draft.numeric);
    if (!Number.isFinite(parsed)) throw new Error(`${value.label}: enter a valid number.`);
    if ((value.input_type === "COUNT" || value.input_type === "DURATION") && parsed < 0) {
      throw new Error(`${value.label}: value cannot be negative.`);
    }
    if (value.input_type === "COUNT" && !Number.isInteger(parsed)) {
      throw new Error(`${value.label}: enter a whole-number count.`);
    }
    return { field_id: value.field_id, is_filled: true, numeric_value: draft.numeric };
  }
  if (value.input_type === "TIME") {
    if (!draft.time) throw new Error(`${value.label}: select a time or mark it Not entered.`);
    return { field_id: value.field_id, is_filled: true, time_value: draft.time };
  }
  if (value.input_type === "BOOLEAN") {
    if (draft.boolean === null) throw new Error(`${value.label}: choose Yes, No, or Not entered.`);
    return { field_id: value.field_id, is_filled: true, boolean_value: draft.boolean };
  }
  const text = draft.text.trim();
  if (!text) throw new Error(`${value.label}: enter a value or mark it Not entered.`);
  return { field_id: value.field_id, is_filled: true, text_value: text };
}

function ReadOnlyValue({ value }: { value: DailyActivityValuePublic }) {
  let display = "N/A";
  if (value.is_filled) {
    if (value.input_type === "BOOLEAN") display = value.boolean_value ? "Yes" : "No";
    else if (value.input_type === "TIME") display = formatTime(value.time_value);
    else if (["NUMBER", "COUNT", "DURATION"].includes(value.input_type)) {
      display = `${Number(value.numeric_value).toString()}${value.unit_code ? ` ${unitLabel(value.unit_code)}` : ""}`;
    } else display = value.text_value ?? "N/A";
  }
  return <span className={cn("font-semibold", !value.is_filled && "text-slate-400")}>{display}</span>;
}

function EditableField({
  value,
  draft,
  disabled,
  onChange,
}: {
  value: DailyActivityValuePublic;
  draft: DraftValue;
  disabled: boolean;
  onChange: (next: DraftValue) => void;
}) {
  const clear = () => onChange({ isFilled: false, numeric: "", time: "", boolean: null, text: "" });
  const label = (
    <div className="mb-2 flex items-center justify-between gap-3">
      <div>
        <p className="text-sm font-semibold text-slate-800">{value.label}</p>
        <p className="text-xs text-slate-500">
          {value.required_for_completion ? "Required for completion" : "Tracked field"}
          {value.unit_code ? ` · ${unitLabel(value.unit_code)}` : ""}
        </p>
      </div>
      {draft.isFilled ? (
        <button type="button" disabled={disabled} onClick={clear} className="text-xs font-semibold text-slate-500 hover:text-slate-900 disabled:opacity-50">
          Clear to N/A
        </button>
      ) : (
        <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-500">N/A</span>
      )}
    </div>
  );

  if (value.input_type === "BOOLEAN") {
    const choice = (labelText: string, selected: boolean, booleanValue: boolean | null) => (
      <button
        type="button"
        disabled={disabled}
        onClick={() => onChange({ ...draft, isFilled: selected, boolean: booleanValue })}
        className={cn(
          "min-h-10 flex-1 rounded-lg border px-3 py-2 text-sm font-semibold transition",
          (selected ? draft.isFilled && draft.boolean === booleanValue : !draft.isFilled) ? "border-amber-500 bg-amber-50 text-amber-900" : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50",
          disabled && "cursor-not-allowed opacity-60",
        )}
      >
        {labelText}
      </button>
    );
    return (
      <div className="rounded-xl border border-slate-200 bg-slate-50/60 p-4">
        {label}
        <div className="flex gap-2">
          {choice("Not entered", false, null)}
          {choice("Yes", true, true)}
          {choice("No", true, false)}
        </div>
        <p className="mt-2 text-xs text-slate-500">“No” is intentionally recorded and is different from Not entered.</p>
      </div>
    );
  }

  if (["NUMBER", "COUNT", "DURATION"].includes(value.input_type)) {
    return (
      <div className="rounded-xl border border-slate-200 bg-slate-50/60 p-4">
        {label}
        <div className="relative">
          <Input
            type="number"
            step={value.input_type === "COUNT" ? "1" : "any"}
            min={value.input_type === "COUNT" || value.input_type === "DURATION" ? "0" : undefined}
            disabled={disabled}
            value={draft.isFilled ? draft.numeric : ""}
            placeholder="Not entered"
            onChange={(event) => onChange({ ...draft, isFilled: true, numeric: event.target.value })}
            className={value.unit_code ? "pr-20" : undefined}
          />
          {value.unit_code ? <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-xs font-semibold text-slate-500">{unitLabel(value.unit_code)}</span> : null}
        </div>
        <p className="mt-2 text-xs text-slate-500">Entering 0 records an intentional zero. Use “Clear to N/A” for missing/not entered.</p>
      </div>
    );
  }

  if (value.input_type === "TIME") {
    return (
      <div className="rounded-xl border border-slate-200 bg-slate-50/60 p-4">
        {label}
        <Input
          type="time"
          disabled={disabled}
          value={draft.isFilled ? draft.time : ""}
          onChange={(event) => onChange({ ...draft, isFilled: true, time: event.target.value })}
        />
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50/60 p-4">
      {label}
      {value.input_type === "TEXT" ? (
        <Textarea
          disabled={disabled}
          value={draft.isFilled ? draft.text : ""}
          placeholder="Not entered"
          onChange={(event) => onChange({ ...draft, isFilled: true, text: event.target.value })}
        />
      ) : (
        <Input
          disabled={disabled}
          value={draft.isFilled ? draft.text : ""}
          placeholder="Not entered"
          onChange={(event) => onChange({ ...draft, isFilled: true, text: event.target.value })}
        />
      )}
    </div>
  );
}

function ActivityCard({
  activity,
  editable,
  draft,
  onFieldChange,
}: {
  activity: DailyActivityPublic;
  editable: boolean;
  draft: DraftMap;
  onFieldChange: (fieldId: string, next: DraftValue) => void;
}) {
  return (
    <Card className={cn(activity.is_filled && "border-emerald-200")}>
      <CardHeader
        title={activity.name}
        description={activity.scoring_type.replaceAll("_", " ").toLowerCase()}
        action={<Badge>{activity.is_filled ? "Complete" : activity.is_system_derived ? "System" : "Incomplete"}</Badge>}
      />
      <div className="space-y-3 p-5">
        {activity.values.length === 0 ? (
          <Notice tone="info">This activity is system-derived. It is calculated from the card and cannot be edited directly.</Notice>
        ) : editable && !activity.is_system_derived ? (
          activity.values.map((value) => (
            <EditableField
              key={value.field_id}
              value={value}
              draft={draft[value.field_id]}
              disabled={!editable}
              onChange={(next) => onFieldChange(value.field_id, next)}
            />
          ))
        ) : (
          <div className="space-y-3">
            {activity.values.map((value) => (
              <div key={value.field_id} className="flex items-center justify-between gap-4 rounded-lg bg-slate-50 px-4 py-3 text-sm">
                <span className="text-slate-500">{value.label}</span>
                <ReadOnlyValue value={value} />
              </div>
            ))}
          </div>
        )}
        <div className="flex items-center justify-between border-t border-slate-100 pt-3 text-sm">
          <span className="text-slate-500">Evaluation</span>
          <span className="font-semibold text-slate-900">{scoreLabel(activity)}</span>
        </div>
      </div>
    </Card>
  );
}

export function DailyCardEditor({ initialCard }: { initialCard: DailyCardPublic }) {
  const [card, setCard] = useState(initialCard);
  const [draft, setDraft] = useState<DraftMap>(() => draftFromCard(initialCard));
  const [dirtyFields, setDirtyFields] = useState<Set<string>>(() => new Set());
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const countable = useMemo(() => card.activities.filter((activity) => activity.counts_toward_card_fill), [card.activities]);
  const completed = countable.filter((activity) => activity.is_filled).length;
  const completeness = countable.length ? (completed / countable.length) * 100 : 0;
  const dirty = dirtyFields.size > 0;

  const grouped = useMemo(() => {
    const categories: Record<ActivityCategory, DailyActivityPublic[]> = { SADHANA: [], ACADEMIC: [] };
    for (const activity of card.activities) categories[activity.category].push(activity);
    return categories;
  }, [card.activities]);

  function updateDraft(fieldId: string, next: DraftValue) {
    setDraft((current) => ({ ...current, [fieldId]: next }));
    setDirtyFields((current) => new Set(current).add(fieldId));
    setMessage(null);
    setError(null);
  }

  async function save() {
    if (!dirty || !card.editable) return;
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const activities: DailyCardUpdateRequest["activities"] = [];
      for (const activity of card.activities) {
        if (activity.is_system_derived) continue;
        const changed = activity.values.filter((value) => dirtyFields.has(value.field_id));
        if (!changed.length) continue;
        activities.push({
          activity_id: activity.activity_id,
          values: changed.map((value) => valuePayload(value, draft[value.field_id])),
        });
      }
      if (!activities.length) return;
      const updated = await apiFetch<DailyCardPublic>("/api/backend/cards/today", {
        method: "PATCH",
        body: JSON.stringify({ activities } satisfies DailyCardUpdateRequest),
      });
      setCard(updated);
      setDraft(draftFromCard(updated));
      setDirtyFields(new Set());
      setMessage(`Card updated. Revision ${updated.revision_number}.`);
    } catch (caught) {
      if (caught instanceof ApiError || caught instanceof Error) setError(caught.message);
      else setError("Unable to update the card.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-6 pb-28">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-3xl font-bold text-slate-900">Today&apos;s card</h1>
            <Badge>{card.status.replaceAll("_", " ")}</Badge>
          </div>
          <p className="mt-2 text-slate-600">
            {formatDate(card.card_date)} · {card.category_name} · deadline {formatTime(card.deadline_time_snapshot)} ({card.timezone_snapshot})
          </p>
        </div>
        <div className="min-w-64 rounded-2xl border border-slate-200 bg-white p-4 shadow-soft">
          <div className="flex items-center justify-between text-sm">
            <span className="font-semibold text-slate-700">Countable activities complete</span>
            <span className="font-bold text-slate-900">{completed}/{countable.length}</span>
          </div>
          <Progress value={completeness} className="mt-3" />
          <p className="mt-2 text-xs text-slate-500">Card-fill scoring is system-derived at finalization. This progress is informational.</p>
        </div>
      </div>

      {!card.editable ? (
        <Notice tone="warning">This card is read-only. Devotees can edit only today&apos;s card before its snapshotted deadline.</Notice>
      ) : (
        <Notice tone="info">There is no Submit action. Record or revise values during the day, then press <strong>Update card</strong>. Intentional 0/No is preserved separately from N/A.</Notice>
      )}
      {error ? <Notice tone="danger">{error}</Notice> : null}
      {message ? <Notice tone="success">{message}</Notice> : null}

      {(["SADHANA", "ACADEMIC"] as const).map((category) => (
        <section key={category} className="space-y-4">
          <div className="flex items-center gap-3">
            <h2 className="text-xl font-bold text-slate-900">{category === "SADHANA" ? "Sadhana" : "Academic / lifestyle"}</h2>
            <span className="text-sm text-slate-500">{grouped[category].length} activities</span>
          </div>
          <div className="grid gap-4 xl:grid-cols-2">
            {grouped[category].map((activity) => (
              <ActivityCard
                key={activity.activity_id}
                activity={activity}
                editable={card.editable}
                draft={draft}
                onFieldChange={updateDraft}
              />
            ))}
          </div>
        </section>
      ))}

      <div className="grid gap-3 rounded-2xl border border-slate-200 bg-white p-4 text-xs text-slate-500 sm:grid-cols-3">
        <div><span className="font-semibold text-slate-700">First update</span><br />{formatDateTime(card.first_update_at, card.timezone_snapshot)}</div>
        <div><span className="font-semibold text-slate-700">Last update</span><br />{formatDateTime(card.last_update_at, card.timezone_snapshot)}</div>
        <div><span className="font-semibold text-slate-700">Revision</span><br />{card.revision_number}</div>
      </div>

      {card.editable ? (
        <div className="fixed inset-x-0 bottom-0 z-30 border-t border-slate-200 bg-white/95 px-4 py-3 shadow-[0_-8px_30px_rgba(15,23,42,0.08)] backdrop-blur">
          <div className="mx-auto flex max-w-7xl items-center justify-between gap-4">
            <div className="text-sm">
              <p className="font-semibold text-slate-900">{dirty ? `${dirtyFields.size} field${dirtyFields.size === 1 ? "" : "s"} changed` : "All changes saved"}</p>
              <p className="text-xs text-slate-500">Updating does not finalize the card.</p>
            </div>
            <Button disabled={!dirty || saving} onClick={save}>{saving ? "Updating…" : "Update card"}</Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
