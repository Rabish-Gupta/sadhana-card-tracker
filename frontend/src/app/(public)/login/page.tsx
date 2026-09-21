import Link from "next/link";
import { redirect } from "next/navigation";
import { getCurrentUser } from "@/lib/auth/server";
import { LoginForm } from "@/components/auth/login-form";
import { Card } from "@/components/ui/card";

export default async function LoginPage() {
  const user = await getCurrentUser();
  if (user) redirect(user.role === "ADMIN" ? "/admin" : "/devotee");
  return (
    <main className="mx-auto flex min-h-screen max-w-md items-center px-5 py-10">
      <Card className="w-full p-6">
        <p className="text-sm font-semibold uppercase tracking-[0.18em] text-amber-700">VOICE</p>
        <h1 className="mt-2 text-2xl font-bold text-slate-900">Welcome back</h1>
        <p className="mt-2 text-sm text-slate-600">Track sadhana and academic consistency without combining them into one score.</p>
        <div className="mt-6"><LoginForm /></div>
        <p className="mt-6 text-center text-sm text-slate-600">New devotee? <Link className="font-semibold text-amber-700" href="/register">Register</Link></p>
      </Card>
    </main>
  );
}
