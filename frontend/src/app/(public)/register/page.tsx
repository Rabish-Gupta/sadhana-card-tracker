import Link from "next/link";
import { redirect } from "next/navigation";
import { getCurrentUser } from "@/lib/auth/server";
import { RegisterForm } from "@/components/auth/register-form";
import { Card } from "@/components/ui/card";

export default async function RegisterPage() {
  const user = await getCurrentUser();
  if (user) redirect(user.role === "ADMIN" ? "/admin" : "/devotee");
  return (
    <main className="mx-auto flex min-h-screen max-w-3xl items-center px-5 py-10">
      <Card className="w-full p-6">
        <p className="text-sm font-semibold uppercase tracking-[0.18em] text-amber-700">Devotee registration</p>
        <h1 className="mt-2 text-2xl font-bold text-slate-900">Create your account</h1>
        <p className="mt-2 text-sm text-slate-600">Self-registration remains pending until an Admin approves it.</p>
        <div className="mt-6"><RegisterForm /></div>
        <p className="mt-6 text-center text-sm text-slate-600">Already registered? <Link className="font-semibold text-amber-700" href="/login">Sign in</Link></p>
      </Card>
    </main>
  );
}
