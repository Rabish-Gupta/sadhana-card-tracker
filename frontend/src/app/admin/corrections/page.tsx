import { serverApi } from "@/lib/auth/server";
import type { AdminCategoryPublic, UserPublic } from "@/lib/api/types";
import { CorrectionWorkbench } from "@/components/admin/correction-workbench";

export default async function CorrectionsPage({ searchParams }: { searchParams: Promise<{ userId?: string }> }) {
  const [{ userId }, devotees, categories] = await Promise.all([
    searchParams,
    serverApi<UserPublic[]>("/admin/devotees"),
    serverApi<AdminCategoryPublic[]>("/admin/config/categories"),
  ]);
  return <div className="space-y-5"><div><p className="text-sm font-semibold text-amber-700">Admin · Historical integrity</p><h1 className="mt-1 text-3xl font-bold">Historical corrections</h1><p className="mt-2 text-slate-600">Reason-required, audited corrections that recalculate using the historical configuration that belonged to the corrected period.</p></div><CorrectionWorkbench devotees={devotees} categories={categories} initialUserId={userId ?? ""} /></div>;
}
