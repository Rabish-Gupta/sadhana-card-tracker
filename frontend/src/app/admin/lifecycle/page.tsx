import { serverApi } from "@/lib/auth/server";
import type { SahadevaReviewItem } from "@/lib/api/types";
import { LifecycleManager } from "@/components/admin/lifecycle-manager";

export default async function AdminLifecyclePage() {
  const reviews = await serverApi<SahadevaReviewItem[]>("/admin/lifecycle/sahadeva-reviews?include_not_due=true");
  return <div className="space-y-5"><div><p className="text-sm font-semibold text-amber-700">Admin · Lifecycle</p><h1 className="mt-1 text-3xl font-bold">Lifecycle & Sahadeva review</h1><p className="mt-2 text-slate-600">Review first-year devotees and inspect/retry the organization lifecycle processor. All changes remain week-boundary based.</p></div><LifecycleManager reviews={reviews} /></div>;
}
