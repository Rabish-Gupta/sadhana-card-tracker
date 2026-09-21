import { AdminSectionNav } from "@/components/admin/admin-section-nav";
import { ScoringRuleManager } from "@/components/admin/scoring-rule-manager";
import { serverApi } from "@/lib/auth/server";
import type { ActivityPublic, ScoringRulePublic, ScoringRuleVersionPublic } from "@/lib/api/types";

export default async function RulesPage() {
  const [activities, rules] = await Promise.all([serverApi<ActivityPublic[]>("/admin/config/activities?include_archived=true"), serverApi<ScoringRulePublic[]>("/admin/config/scoring-rules")]);
  const pairs = await Promise.all(rules.map(async (rule) => [rule.id, await serverApi<ScoringRuleVersionPublic[]>(`/admin/config/scoring-rules/${rule.id}/versions`)] as const));
  return <div className="space-y-5"><div><p className="text-sm font-semibold text-amber-700">Admin · Configuration</p><h1 className="mt-1 text-3xl font-bold">Scoring rules</h1><p className="mt-2 text-slate-600">Manage rule identities and future-week versions without changing historical evaluations.</p></div><AdminSectionNav /><ScoringRuleManager activities={activities} rules={rules} versionsByRule={Object.fromEntries(pairs)} /></div>;
}
