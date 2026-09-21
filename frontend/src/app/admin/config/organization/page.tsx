import { AdminSectionNav } from "@/components/admin/admin-section-nav";
import { OrganizationSettingsManager } from "@/components/admin/organization-settings-manager";
import { serverApi } from "@/lib/auth/server";
import type { OrganizationSettingVersionPublic } from "@/lib/api/types";

export default async function OrganizationSettingsPage() {
  const [current, versions] = await Promise.all([
    serverApi<OrganizationSettingVersionPublic>("/admin/config/organization-settings/current"),
    serverApi<OrganizationSettingVersionPublic[]>("/admin/config/organization-settings/versions"),
  ]);
  return <div className="space-y-5"><div><p className="text-sm font-semibold text-amber-700">Admin · Configuration</p><h1 className="mt-1 text-3xl font-bold">Organization settings</h1><p className="mt-2 text-slate-600">Versioned timezone, week boundary, card deadline and promotion settings.</p></div><AdminSectionNav /><OrganizationSettingsManager current={current} versions={versions} /></div>;
}
