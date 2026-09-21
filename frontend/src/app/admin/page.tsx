import Link from "next/link";
import { serverApi } from "@/lib/auth/server";
import type { ActivityPublic, OrganizationSettingVersionPublic, SahadevaReviewItem, UserPublic } from "@/lib/api/types";
import { Card, CardHeader } from "@/components/ui/card";

const workflows = [
  ["Registrations", "Approve/reject self-registrations without editing submitted profiles.", "/admin/registrations"],
  ["Devotee accounts", "Create active accounts, deactivate/reactivate and open correction workflows.", "/admin/devotees"],
  ["Lifecycle", "Sahadeva review and safe manual lifecycle retry.", "/admin/lifecycle"],
  ["Configuration", "Activities, scoring rules, standards, category configs and organization settings.", "/admin/config"],
  ["Historical corrections", "Audited Policy-B category and finalized-card corrections.", "/admin/corrections"],
];

export default async function AdminDashboard() {
  const [pending, devotees, reviews, activities, settings] = await Promise.all([
    serverApi<UserPublic[]>("/admin/registrations/pending"),
    serverApi<UserPublic[]>("/admin/devotees"),
    serverApi<SahadevaReviewItem[]>("/admin/lifecycle/sahadeva-reviews?include_not_due=true"),
    serverApi<ActivityPublic[]>("/admin/config/activities"),
    serverApi<OrganizationSettingVersionPublic>("/admin/config/organization-settings/current"),
  ]);
  const active = devotees.filter((user) => user.account_status === "ACTIVE").length;
  const due = reviews.filter((item) => item.review_due).length;
  return (
    <div className="space-y-6">
      <div><p className="text-sm font-semibold text-amber-700">Admin</p><h1 className="mt-1 text-3xl font-bold">Administration</h1><p className="mt-2 text-slate-600">Operate the stable FastAPI backend without duplicating scoring or lifecycle rules in the browser.</p></div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5"><Card className="p-5"><p className="text-sm text-slate-500">Pending registrations</p><p className="mt-2 text-3xl font-bold">{pending.length}</p></Card><Card className="p-5"><p className="text-sm text-slate-500">Active devotees</p><p className="mt-2 text-3xl font-bold">{active}</p></Card><Card className="p-5"><p className="text-sm text-slate-500">Sahadeva reviews due</p><p className="mt-2 text-3xl font-bold">{due}</p></Card><Card className="p-5"><p className="text-sm text-slate-500">Active activities</p><p className="mt-2 text-3xl font-bold">{activities.length}</p></Card><Card className="p-5"><p className="text-sm text-slate-500">Organization timezone</p><p className="mt-2 text-lg font-bold">{settings.timezone}</p></Card></div>
      <Card><CardHeader title="Admin workflows" description="All mutation screens call the existing versioned/audited FastAPI contracts through the same-origin BFF." /><div className="grid gap-3 p-5 md:grid-cols-2">{workflows.map(([title, desc, href]) => <Link key={href} href={href} className="rounded-xl border border-slate-200 p-4 transition hover:border-amber-300 hover:bg-amber-50/30"><p className="font-semibold">{title}</p><p className="mt-1 text-sm text-slate-600">{desc}</p></Link>)}</div></Card>
      <Card className="p-5 text-sm text-slate-600"><strong>Project principle:</strong> Admin screens expose factual data, configured standards and separate Sadhana/Academic evaluation. They do not create a combined balance score or claim to measure spiritual advancement.</Card>
    </div>
  );
}
