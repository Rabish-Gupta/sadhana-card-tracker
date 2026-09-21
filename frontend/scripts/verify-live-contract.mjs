import { readFile } from "node:fs/promises";

const args = process.argv.slice(2);
function value(name, fallback) { const i = args.indexOf(name); return i >= 0 ? args[i + 1] : fallback; }
const backend = (value("--backend-url", process.env.BACKEND_BASE_URL ?? "http://127.0.0.1:8000") ?? "").replace(/\/$/, "");
const expected = JSON.parse(await readFile(new URL("../contracts/backend-openapi.json", import.meta.url), "utf8"));
const response = await fetch(`${backend}/openapi.json`, { signal: AbortSignal.timeout(15000) });
if (!response.ok) throw new Error(`Live backend OpenAPI returned ${response.status}`);
const live = await response.json();
const expectedPaths = Object.keys(expected.paths ?? {}).sort();
const livePaths = Object.keys(live.paths ?? {}).sort();
if (JSON.stringify(expectedPaths) !== JSON.stringify(livePaths)) {
  const missing = expectedPaths.filter((p) => !livePaths.includes(p));
  const extra = livePaths.filter((p) => !expectedPaths.includes(p));
  throw new Error(`Live backend path drift. Missing=${missing.join(",") || "none"}; Extra=${extra.join(",") || "none"}`);
}
const enums = ["UserRole", "AccountStatus", "ScoringType", "ActivityInputType", "EmploymentStatus", "VersionStatus", "RuleType", "StandardPeriod"];
for (const name of enums) {
  const a = expected.components?.schemas?.[name]?.enum ?? [];
  const b = live.components?.schemas?.[name]?.enum ?? [];
  if (JSON.stringify(a) !== JSON.stringify(b)) throw new Error(`Live backend enum drift for ${name}`);
}
for (const path of expectedPaths) {
  const expectedMethods = Object.keys(expected.paths[path] ?? {}).filter((m) => ["get", "post", "patch", "put", "delete"].includes(m)).sort();
  const liveMethods = Object.keys(live.paths[path] ?? {}).filter((m) => ["get", "post", "patch", "put", "delete"].includes(m)).sort();
  if (JSON.stringify(expectedMethods) !== JSON.stringify(liveMethods)) throw new Error(`Live backend method drift for ${path}`);
}
console.log(`Live backend contract matches frozen frontend snapshot: ${livePaths.length} paths.`);
