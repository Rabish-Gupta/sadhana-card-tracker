import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function Notice({
  children,
  tone = "info",
  className,
}: {
  children: ReactNode;
  tone?: "info" | "success" | "warning" | "danger";
  className?: string;
}) {
  return (
    <div
      className={cn(
        "rounded-xl border px-4 py-3 text-sm",
        tone === "info" && "border-sky-200 bg-sky-50 text-sky-900",
        tone === "success" && "border-emerald-200 bg-emerald-50 text-emerald-900",
        tone === "warning" && "border-amber-200 bg-amber-50 text-amber-950",
        tone === "danger" && "border-red-200 bg-red-50 text-red-900",
        className,
      )}
    >
      {children}
    </div>
  );
}
