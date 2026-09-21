import Link from "next/link";

export default function NotFound() {
  return (
    <main className="mx-auto flex min-h-screen max-w-xl flex-col items-center justify-center px-6 text-center">
      <p className="text-sm font-semibold uppercase tracking-[0.2em] text-amber-700">404</p>
      <h1 className="mt-3 text-3xl font-bold text-slate-900">Page not found</h1>
      <p className="mt-3 text-slate-600">The requested page does not exist in this frontend checkpoint.</p>
      <Link className="mt-6 rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white" href="/">
        Go home
      </Link>
    </main>
  );
}
