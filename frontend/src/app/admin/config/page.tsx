import Link from "next/link";
import { AdminSectionNav } from "@/components/admin/admin-section-nav";
import { ConfigActivation } from "@/components/admin/config-activation";
import { Card, CardHeader } from "@/components/ui/card";

const areas = [
  ["Activities & fields", "Dynamic Sadhana/Academic activities and their input fields.", "/admin/config/activities"],
  ["Scoring rules", "Rule definitions plus future-week versioned executable configuration.", "/admin/config/rules"],
  ["Standards", "Daily/weekly target definitions kept separate from marks.", "/admin/config/standards"],
  ["Category configs", "Per-category activity applicability, scoring type, aggregation and card-fill participation.", "/admin/config/category-activities"],
  ["Organization settings", "Timezone, week start, daily deadline and promotion month with version history.", "/admin/config/organization"],
];

export default function AdminConfigPage() {
  return <div className="space-y-6"><div><p className="text-sm font-semibold text-amber-700">Admin · Configuration</p><h1 className="mt-1 text-3xl font-bold">Versioned configuration</h1><p className="mt-2 text-slate-600">Changes that affect scoring or time interpretation are scheduled safely for organization week boundaries.</p></div><AdminSectionNav /><div className="grid gap-4 md:grid-cols-2">{areas.map(([title, desc, href]) => <Link key={href} href={href}><Card className="h-full p-5 transition hover:border-amber-300"><h2 className="font-semibold">{title}</h2><p className="mt-2 text-sm text-slate-600">{desc}</p></Card></Link>)}</div><Card><CardHeader title="Activation diagnostic" description="Automatic lifecycle processing normally activates due PENDING versions. This manual action is safe and idempotent." /><div className="p-5"><ConfigActivation /></div></Card></div>;
}
