"use client";

export default function GlobalError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <main className="mx-auto flex min-h-screen max-w-xl flex-col items-center justify-center px-6 text-center">
      <p className="text-sm font-semibold uppercase tracking-[0.2em] text-red-700">Something went wrong</p>
      <h1 className="mt-3 text-3xl font-bold text-slate-900">Unable to load this screen</h1>
      <p className="mt-3 text-slate-600">Please retry. If the backend is stopped, start FastAPI and try again.</p>
      <button className="mt-6 rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white" onClick={reset}>
        Retry
      </button>
    </main>
  );
}
