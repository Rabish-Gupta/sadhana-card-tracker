import Link from "next/link";

const sections = [
  ["Overview", "/admin/config"],
  ["Activities & fields", "/admin/config/activities"],
  ["Scoring rules", "/admin/config/rules"],
  ["Standards", "/admin/config/standards"],
  ["Category configs", "/admin/config/category-activities"],
  ["Organization", "/admin/config/organization"],
];

export function AdminSectionNav() {
  return (
    <nav className="flex gap-2 overflow-x-auto rounded-xl border border-slate-200 bg-white p-2">
      {sections.map(([label, href]) => (
        <Link key={href} href={href} className="whitespace-nowrap rounded-lg px-3 py-2 text-sm font-semibold text-slate-600 hover:bg-slate-100 hover:text-slate-900">
          {label}
        </Link>
      ))}
    </nav>
  );
}
