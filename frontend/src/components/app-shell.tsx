import Link from "next/link";
import type { ReactNode } from "react";
import type { UserPublic } from "@/lib/api/types";
import { LogoutButton } from "@/components/logout-button";
import { RoleNav } from "@/components/role-nav";
import { publicAppVersion } from "@/lib/env";

export function AppShell({ user, children }: { user: UserPublic; children: ReactNode }) {
  const devoteeLinks: Array<[string, string]> = [
    ["Dashboard", "/devotee"],
    ["Today", "/devotee/card"],
    ["Previous Cards", "/devotee/history"],
    ["Weekly", "/devotee/weekly"],
    ["4-Week Report", "/devotee/monthly"],
    ["Lifecycle", "/devotee/lifecycle"],
  ];
  const adminLinks: Array<[string, string]> = [
    ["Dashboard", "/admin"],
    ["Registrations", "/admin/registrations"],
    ["Devotees", "/admin/devotees"],
    ["Lifecycle", "/admin/lifecycle"],
    ["Configuration", "/admin/config"],
    ["Corrections", "/admin/corrections"],
  ];
  const links = user.role === "ADMIN" ? adminLinks : devoteeLinks;

  return (
    <div className="min-h-screen">
      <a href="#main-content" className="skip-link">Skip to main content</a>
      <header className="sticky top-0 z-40 border-b border-slate-200 bg-white/95 backdrop-blur">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-5 py-4">
          <div>
            <Link href="/" className="text-lg font-bold text-slate-900">Sadhana Card Tracker</Link>
            <p className="text-xs text-slate-500">Sadhana and academic consistency, tracked separately</p>
          </div>
          <RoleNav links={links} />
          <div className="order-2 flex items-center gap-3 md:order-3">
            <div className="hidden text-right sm:block">
              <p className="text-sm font-semibold text-slate-900">{user.full_name}</p>
              <p className="text-xs text-slate-500">{user.role} · UI {publicAppVersion()}</p>
            </div>
            <LogoutButton />
          </div>
        </div>
      </header>
      <main id="main-content" className="mx-auto max-w-7xl px-5 py-8" tabIndex={-1}>{children}</main>
      <footer className="mx-auto max-w-7xl px-5 pb-8 text-center text-xs text-slate-400">
        Data, evaluation and analysis are kept separate. No combined spiritual/academic balance score is used.
      </footer>
    </div>
  );
}
