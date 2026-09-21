import type { ReactNode } from "react";
import { AppShell } from "@/components/app-shell";
import { requireRole } from "@/lib/auth/server";

export default async function DevoteeLayout({ children }: { children: ReactNode }) {
  const user = await requireRole("DEVOTEE");
  return <AppShell user={user}>{children}</AppShell>;
}
