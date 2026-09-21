import { serverApi } from "@/lib/auth/server";
import type { AdminCategoryPublic, UserPublic } from "@/lib/api/types";
import { DevoteeManager } from "@/components/admin/devotee-manager";

export default async function DevoteesPage() {
  const [users, categories] = await Promise.all([
    serverApi<UserPublic[]>("/admin/devotees"),
    serverApi<AdminCategoryPublic[]>("/admin/config/categories"),
  ]);
  return <div className="space-y-5"><div><p className="text-sm font-semibold text-amber-700">Admin · Accounts</p><h1 className="mt-1 text-3xl font-bold">Devotees</h1><p className="mt-2 text-slate-600">Create, review, activate or deactivate devotees without deleting historical records.</p></div><DevoteeManager users={users} categories={categories} /></div>;
}
