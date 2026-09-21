import { cn } from "@/lib/utils";

export function Progress({ value, className }: { value: number; className?: string }) {
  const bounded = Math.max(0, Math.min(100, Number.isFinite(value) ? value : 0));
  return (
    <div className={cn("h-2 overflow-hidden rounded-full bg-slate-100", className)} aria-label={`${bounded.toFixed(0)} percent`}>
      <div className="h-full rounded-full bg-amber-500 transition-all" style={{ width: `${bounded}%` }} />
    </div>
  );
}
