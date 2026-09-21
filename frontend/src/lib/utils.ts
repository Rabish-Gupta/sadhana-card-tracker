export function cn(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

export function decimalToNumber(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined || value === "") return null;
  const numeric = typeof value === "number" ? value : Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

export function formatDecimal(value: string | number | null | undefined, suffix = "%"): string {
  const numberValue = decimalToNumber(value);
  if (numberValue === null) return value === null || value === undefined || value === "" ? "—" : String(value);
  return `${numberValue.toFixed(2)}${suffix}`;
}

export function formatCompactNumber(value: string | number | null | undefined): string {
  const numeric = decimalToNumber(value);
  if (numeric === null) return "—";
  return Number.isInteger(numeric) ? String(numeric) : numeric.toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
}

export function formatDate(value: string): string {
  const [year, month, day] = value.split("-").map(Number);
  if (!year || !month || !day) return value;
  return new Intl.DateTimeFormat("en-IN", { day: "2-digit", month: "short", year: "numeric" }).format(
    new Date(Date.UTC(year, month - 1, day)),
  );
}

export function formatDateTime(value: string | null | undefined, timeZone?: string): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  try {
    return new Intl.DateTimeFormat("en-IN", {
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      hour12: true,
      ...(timeZone ? { timeZone } : {}),
    }).format(date);
  } catch {
    return date.toLocaleString("en-IN");
  }
}

export function formatTime(value: string | null | undefined): string {
  if (!value) return "—";
  const [hoursRaw, minutesRaw] = value.split(":");
  const hours = Number(hoursRaw);
  const minutes = Number(minutesRaw);
  if (!Number.isFinite(hours) || !Number.isFinite(minutes)) return value;
  const suffix = hours >= 12 ? "PM" : "AM";
  const displayHour = hours % 12 || 12;
  return `${displayHour}:${String(minutes).padStart(2, "0")} ${suffix}`;
}

export function unitLabel(unit: string | null | undefined): string {
  if (!unit) return "";
  const normalized: Record<string, string> = {
    MINUTE: "min",
    MINUTES: "min",
    ROUND: "rounds",
    ROUNDS: "rounds",
    HOUR: "hr",
    HOURS: "hr",
  };
  return normalized[unit] ?? unit.toLowerCase().replaceAll("_", " ");
}

export function signedDecimal(value: string | number | null | undefined, suffix = " pp"): string {
  const numeric = decimalToNumber(value);
  if (numeric === null) return "—";
  const sign = numeric > 0 ? "+" : "";
  return `${sign}${numeric.toFixed(2)}${suffix}`;
}

export function trendTone(value: string | number | null | undefined): "positive" | "negative" | "neutral" {
  const numeric = decimalToNumber(value);
  if (numeric === null || numeric === 0) return "neutral";
  return numeric > 0 ? "positive" : "negative";
}
