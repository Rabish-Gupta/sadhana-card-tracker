import { AdminSectionNav } from "@/components/admin/admin-section-nav";
import { ActivityManager } from "@/components/admin/activity-manager";
import { serverApi } from "@/lib/auth/server";
import type { ActivityPublic } from "@/lib/api/types";

export default async function ActivitiesPage() {
  const activities = await serverApi<ActivityPublic[]>("/admin/config/activities?include_archived=true");
  return <div className="space-y-5"><div><p className="text-sm font-semibold text-amber-700">Admin · Configuration</p><h1 className="mt-1 text-3xl font-bold">Activities & fields</h1><p className="mt-2 text-slate-600">Manage dynamic activities while preserving semantic history.</p></div><AdminSectionNav /><ActivityManager activities={activities} /></div>;
}
