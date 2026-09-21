import { serverApi } from "@/lib/auth/server";
import type { UserPublic } from "@/lib/api/types";
import { RegistrationManager } from "@/components/admin/registration-manager";

export default async function PendingRegistrationsPage() {
  const pending = await serverApi<UserPublic[]>("/admin/registrations/pending");
  return (
    <div className="space-y-5">
      <div><p className="text-sm font-semibold text-amber-700">Admin · Accounts</p><h1 className="mt-1 text-3xl font-bold">Pending registrations</h1><p className="mt-2 text-slate-600">Approve or reject self-registrations without rewriting the devotee's submitted profile.</p></div>
      <RegistrationManager users={pending} />
    </div>
  );
}
