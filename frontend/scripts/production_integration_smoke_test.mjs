const args = process.argv.slice(2);
function value(name, fallback) { const index = args.indexOf(name); return index >= 0 ? args[index + 1] : fallback; }
const baseUrl = (value("--url", "http://localhost:3000") ?? "").replace(/\/$/, "");
function assert(condition, message) { if (!condition) throw new Error(message); }
function pass(message) { console.log(`PASS: ${message}`); }

const readiness = await fetch(`${baseUrl}/api/readiness`, { cache: "no-store" });
const readinessText = await readiness.text();
assert(readiness.status === 200, `readiness expected 200, got ${readiness.status}: ${readinessText}`);
const readinessJson = JSON.parse(readinessText);
assert(readinessJson.status === "ready" && readinessJson.backend_status === "ok", `unexpected readiness: ${readinessText}`);
assert(readiness.headers.get("x-request-id"), "readiness missing request correlation id");
pass("frontend readiness confirms FastAPI availability with request correlation");

const version = await fetch(`${baseUrl}/api/version`, { cache: "no-store" });
assert(version.status === 200, `version expected 200, got ${version.status}`);
const versionJson = await version.json();
assert(versionJson.version === "0.4.0", `unexpected frontend version ${versionJson.version}`);
assert(versionJson.backend_contract === "v0.11.2", `unexpected backend contract ${versionJson.backend_contract}`);
pass("frontend release identifies v0.4.0 against backend contract v0.11.2");

const page = await fetch(`${baseUrl}/login`, { redirect: "manual" });
assert(page.status === 200, `login page expected 200, got ${page.status}`);
assert((page.headers.get("x-content-type-options") ?? "").toLowerCase() === "nosniff", "missing nosniff header");
assert((page.headers.get("x-frame-options") ?? "").toUpperCase() === "DENY", "missing DENY frame protection");
assert((page.headers.get("referrer-policy") ?? "").toLowerCase() === "same-origin", "missing same-origin referrer policy");
assert((page.headers.get("content-security-policy") ?? "").includes("frame-ancestors 'none'"), "missing frame-ancestors CSP");
pass("security headers are present on rendered frontend pages");

const blocked = await fetch(`${baseUrl}/api/backend/auth/login`, {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify({}),
});
assert(blocked.status === 400, `generic proxy must block direct auth/login, got ${blocked.status}`);
pass("generic BFF proxy cannot bypass dedicated login/logout session endpoints");

const health = await fetch(`${baseUrl}/api/backend-health`, { cache: "no-store" });
assert(health.status === 200, `backend-health expected 200, got ${health.status}`);
assert(health.headers.get("x-request-id"), "backend-health missing request id");
pass("BFF health proxy emits correlation id and reaches stable backend");

console.log("\nALL PRODUCTION INTEGRATION SMOKE TESTS PASSED");
