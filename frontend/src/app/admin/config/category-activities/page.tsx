import { AdminSectionNav } from "@/components/admin/admin-section-nav";
import { CategoryConfigManager } from "@/components/admin/category-config-manager";
import { serverApi } from "@/lib/auth/server";
import type { ActivityPublic, AdminCategoryPublic, CategoryActivityConfigPublic, ScoringRulePublic, StandardPublic } from "@/lib/api/types";

export default async function CategoryActivitiesPage() {
  const [configs, categories, activities, rules, standards] = await Promise.all([
    serverApi<CategoryActivityConfigPublic[]>("/admin/config/category-activity-configs"),
    serverApi<AdminCategoryPublic[]>("/admin/config/categories"),
    serverApi<ActivityPublic[]>("/admin/config/activities?include_archived=true"),
    serverApi<ScoringRulePublic[]>("/admin/config/scoring-rules"),
    serverApi<StandardPublic[]>("/admin/config/standards"),
  ]);
  return <div className="space-y-5"><div><p className="text-sm font-semibold text-amber-700">Admin · Configuration</p><h1 className="mt-1 text-3xl font-bold">Category activity configuration</h1><p className="mt-2 text-slate-600">Control applicability, scoring mode, aggregation, standards and card-fill participation by devotee category.</p></div><AdminSectionNav /><CategoryConfigManager configs={configs} categories={categories} activities={activities} rules={rules} standards={standards} /></div>;
}
