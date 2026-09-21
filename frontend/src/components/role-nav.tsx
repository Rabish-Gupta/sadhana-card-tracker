"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export function RoleNav({ links }: { links: Array<[string, string]> }) {
  const pathname = usePathname();
  return (
    <nav aria-label="Primary navigation" className="order-3 flex w-full gap-1 overflow-x-auto md:order-2 md:w-auto">
      {links.map(([label, href]) => {
        const active = pathname === href || (href !== "/admin" && href !== "/devotee" && pathname.startsWith(`${href}/`));
        return (
          <Link
            key={href}
            href={href}
            aria-current={active ? "page" : undefined}
            className={`whitespace-nowrap rounded-lg px-3 py-2 text-sm font-medium transition ${active ? "bg-amber-100 text-amber-950" : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"}`}
          >
            {label}
          </Link>
        );
      })}
    </nav>
  );
}
