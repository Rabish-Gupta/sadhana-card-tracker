const args = process.argv.slice(2);
function value(name, fallback) { const index = args.indexOf(name); return index >= 0 ? args[index + 1] : fallback; }
const baseUrl = (value("--url", "http://localhost:3000") ?? "").replace(/\/$/, "");
const adminEmail = value("--admin-email");
const adminPassword = value("--admin-password");
if (!adminEmail || !adminPassword) {
  console.error("Usage: node scripts/admin_frontend_smoke_test.mjs --admin-email <email> --admin-password <password> [--url http://localhost:3000]");
  process.exit(2);
}
function pass(message) { console.log(`PASS: ${message}`); }
function assert(condition, message) { if (!condition) throw new Error(message); }
async function jsonOrText(response) { const text = await response.text(); try { return text ? JSON.parse(text) : null; } catch { return text; } }
function cookieFrom(response) { const setCookie = response.headers.get("set-cookie"); assert(setCookie?.includes("sadhana_access_token="), "session login did not set auth cookie"); return setCookie.split(";", 1)[0]; }
async function sessionLogin(email, password) {
  const response = await fetch(`${baseUrl}/api/session/login`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ email, password }) });
  const payload = await jsonOrText(response); assert(response.status === 200, `login expected 200, got ${response.status}: ${JSON.stringify(payload)}`); return { cookie: cookieFrom(response), user: payload };
}
async function backend(path, { cookie, method = "GET", body } = {}) {
  const headers = {}; if (cookie) headers.cookie = cookie; if (body !== undefined) headers["content-type"] = "application/json";
  const response = await fetch(`${baseUrl}/api/backend${path}`, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  return { response, payload: await jsonOrText(response) };
}

const stamp = Date.now();
const email = `frontend-admin-step16-${stamp}@sadhanatracker.com`;
const password = "FrontendAdminTest123!";
let userId = null;
let adminCookie = null;
try {
  const admin = await sessionLogin(adminEmail, adminPassword);
  adminCookie = admin.cookie;
  assert(admin.user.role === "ADMIN", "supplied account is not an Admin");
  pass("Admin session works through HttpOnly BFF cookie");

  for (const page of [
    "/admin", "/admin/registrations", "/admin/devotees", "/admin/lifecycle", "/admin/config",
    "/admin/config/activities", "/admin/config/rules", "/admin/config/standards",
    "/admin/config/category-activities", "/admin/config/organization", "/admin/corrections",
  ]) {
    const response = await fetch(`${baseUrl}${page}`, { headers: { cookie: adminCookie } });
    assert(response.status === 200, `${page} expected 200, got ${response.status}`);
  }
  pass("All Step 16 Admin pages render behind role protection");

  const adminReads = [
    "/admin/registrations/pending", "/admin/devotees", "/admin/lifecycle/sahadeva-reviews?include_not_due=true",
    "/admin/config/categories", "/admin/config/activities?include_archived=true", "/admin/config/scoring-rules",
    "/admin/config/standards", "/admin/config/category-activity-configs", "/admin/config/organization-settings/current",
    "/admin/config/organization-settings/versions",
  ];
  for (const path of adminReads) {
    const result = await backend(path, { cookie: adminCookie });
    assert(result.response.status === 200, `${path} expected 200, got ${result.response.status}: ${JSON.stringify(result.payload)}`);
  }
  pass("Admin read/configuration contracts integrate through frontend proxy");

  const registration = await backend("/auth/register", { method: "POST", body: {
    full_name: "Frontend Admin UI Smoke", email, password, phone_number: "+919811112222",
    college: "Admin UI Smoke College", branch: "CSE", current_academic_year: 2, college_joining_year: 2025,
  }});
  assert(registration.response.status === 201, `registration expected 201, got ${registration.response.status}: ${JSON.stringify(registration.payload)}`);
  userId = registration.payload.user_id;
  const approval = await backend(`/admin/registrations/${userId}/approve`, { cookie: adminCookie, method: "POST" });
  assert(approval.response.status === 200 && approval.payload.account_status === "ACTIVE", `approval failed: ${JSON.stringify(approval.payload)}`);
  pass("Admin registration approval mutation integrates through BFF");

  const history = await backend(`/admin/corrections/devotees/${userId}/category-history`, { cookie: adminCookie });
  assert(history.response.status === 200 && Array.isArray(history.payload.history), `category history expected 200, got ${history.response.status}`);
  pass("Historical correction workbench contract is reachable through BFF");
} finally {
  if (userId && adminCookie) {
    const cleanup = await backend(`/admin/devotees/${userId}/deactivate`, { cookie: adminCookie, method: "POST", body: { reason: "Frontend Step 16 smoke-test cleanup" } });
    if (cleanup.response.status === 200) pass("Disposable Admin-UI devotee logically deactivated");
    else console.warn(`WARN: cleanup returned ${cleanup.response.status}: ${JSON.stringify(cleanup.payload)}`);
  }
}
console.log("\nALL ADMIN FRONTEND SMOKE TESTS PASSED");
