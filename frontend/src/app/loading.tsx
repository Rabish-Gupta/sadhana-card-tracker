export default function Loading() {
  return (
    <main className="mx-auto max-w-7xl px-5 py-10" aria-busy="true" aria-live="polite">
      <div className="animate-pulse space-y-5">
        <div className="h-7 w-56 rounded bg-slate-200" />
        <div className="h-4 w-80 max-w-full rounded bg-slate-200" />
        <div className="grid gap-4 md:grid-cols-3">
          {[0, 1, 2].map((item) => <div key={item} className="h-28 rounded-2xl border border-slate-200 bg-white" />)}
        </div>
        <div className="h-64 rounded-2xl border border-slate-200 bg-white" />
      </div>
      <span className="sr-only">Loading</span>
    </main>
  );
}
