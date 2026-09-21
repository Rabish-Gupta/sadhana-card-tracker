import { AdminSectionNav } from "@/components/admin/admin-section-nav";
import { StandardManager } from "@/components/admin/standard-manager";
import { serverApi } from "@/lib/auth/server";
import type { ActivityPublic, StandardPublic, StandardVersionPublic } from "@/lib/api/types";

export default async function StandardsPage() {
  const [activities, standards] = await Promise.all([serverApi<ActivityPublic[]>("/admin/config/activities?include_archived=true"), serverApi<StandardPublic[]>("/admin/config/standards")]);
  const pairs = await Promise.all(standards.map(async (standard) => [standard.id, await serverApi<StandardVersionPublic[]>(`/admin/config/standards/${standard.id}/versions`)] as const));
  return <div className="space-y-5"><div><p className="text-sm font-semibold text-amber-700">Admin · Configuration</p><h1 className="mt-1 text-3xl font-bold">Standards</h1><p className="mt-2 text-slate-600">Versioned daily/weekly targets remain separate from scoring rules.</p></div><AdminSectionNav /><StandardManager activities={activities} standards={standards} versionsByStandard={Object.fromEntries(pairs)} /></div>;
}
