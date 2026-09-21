const args = process.argv.slice(2);
function value(name, fallback) {
  const index = args.indexOf(name);
  return index >= 0 ? args[index + 1] : fallback;
}
const baseUrl = (value("--url", "http://localhost:3000") ?? "").replace(/\/$/, "");
const adminEmail = value("--admin-email");
const adminPassword = value("--admin-password");
if (!adminEmail || !adminPassword) {
  console.error("Usage: node scripts/devotee_frontend_smoke_test.mjs --admin-email <email> --admin-password <password> [--url http://localhost:3000]");
  process.exit(2);
}
function pass(message) { console.log(`PASS: ${message}`); }
function assert(condition, message) { if (!condition) throw new Error(message); }
async function jsonOrText(response) {
  const text = await response.text();
  try { return text ? JSON.parse(text) : null; } catch { return text; }
}
function cookieFrom(response) {
  const setCookie = response.headers.get("set-cookie");
  assert(setCookie?.includes("sadhana_access_token="), "session login did not set auth cookie");
  return setCookie.split(";", 1)[0];
}
async function sessionLogin(email, password) {
  const response = await fetch(`${baseUrl}/api/session/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  const payload = await jsonOrText(response);
  assert(response.status === 200, `login expected 200, got ${response.status}: ${JSON.stringify(payload)}`);
  return { cookie: cookieFrom(response), user: payload };
}
async function backend(path, { cookie, method = "GET", body } = {}) {
  const headers = {};
  if (cookie) headers.cookie = cookie;
  if (body !== undefined) headers["content-type"] = "application/json";
  const response = await fetch(`${baseUrl}/api/backend${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  return { response, payload: await jsonOrText(response) };
}

const stamp = Date.now();
const devoteeEmail = `frontend-devotee-${stamp}@sadhanatracker.com`;
const devoteePassword = "FrontendTest123!";
let devoteeUserId = null;
let adminCookie = null;

try {
  const health = await fetch(`${baseUrl}/api/backend-health`);
  assert(health.status === 200, `health expected 200, got ${health.status}`);
  pass("Next.js frontend reaches stable FastAPI backend");

  const admin = await sessionLogin(adminEmail, adminPassword);
  adminCookie = admin.cookie;
  assert(admin.user.role === "ADMIN", "supplied account is not an Admin");
  pass("Admin session works through HttpOnly BFF cookie");

  const registration = await backend("/auth/register", {
    method: "POST",
    body: {
      full_name: "Frontend Devotee Smoke",
      email: devoteeEmail,
      password: devoteePassword,
      phone_number: "+919876543210",
      college: "Frontend Smoke College",
      branch: "CSE",
      current_academic_year: 3,
      college_joining_year: 2024,
    },
  });
  assert(registration.response.status === 201, `registration expected 201, got ${registration.response.status}: ${JSON.stringify(registration.payload)}`);
  devoteeUserId = registration.payload.user_id;
  pass("Devotee self-registration contract works through frontend proxy");

  const approval = await backend(`/admin/registrations/${devoteeUserId}/approve`, { cookie: adminCookie, method: "POST" });
  assert(approval.response.status === 200, `approval expected 200, got ${approval.response.status}: ${JSON.stringify(approval.payload)}`);
  pass("Admin approval works through frontend proxy");

  const devotee = await sessionLogin(devoteeEmail, devoteePassword);
  assert(devotee.user.role === "DEVOTEE", "approved test user did not login as DEVOTEE");
  const devoteeCookie = devotee.cookie;
  pass("Devotee login/session works through frontend BFF");

  for (const page of ["/devotee", "/devotee/card", "/devotee/history", "/devotee/weekly", "/devotee/monthly", "/devotee/lifecycle"]) {
    const response = await fetch(`${baseUrl}${page}`, { headers: { cookie: devoteeCookie } });
    assert(response.status === 200, `${page} expected 200, got ${response.status}`);
  }
  pass("All Step 15 devotee pages render behind role protection");

  const today = await backend("/cards/today", { cookie: devoteeCookie });
  assert(today.response.status === 200, `today card expected 200, got ${today.response.status}: ${JSON.stringify(today.payload)}`);
  assert(Array.isArray(today.payload.activities) && today.payload.activities.length > 0, "daily card has no dynamic activities");
  pass("Today card loads dynamic backend activity/field contract");

  if (today.payload.editable) {
    const updatesByActivity = new Map();
    let booleanField = null;
    let numericField = null;
    for (const activity of today.payload.activities) {
      if (activity.is_system_derived) continue;
      for (const field of activity.values) {
        if (!booleanField && field.input_type === "BOOLEAN") booleanField = { activity, field };
        if (!numericField && ["NUMBER", "COUNT", "DURATION"].includes(field.input_type)) numericField = { activity, field };
      }
    }
    assert(booleanField && numericField, "could not find generic boolean and numeric fields for update test");
    for (const item of [
      { source: booleanField, update: { field_id: booleanField.field.field_id, is_filled: true, boolean_value: false } },
      { source: numericField, update: { field_id: numericField.field.field_id, is_filled: true, numeric_value: 0 } },
    ]) {
      const key = item.source.activity.activity_id;
      const current = updatesByActivity.get(key) ?? [];
      current.push(item.update);
      updatesByActivity.set(key, current);
    }
    const patch = await backend("/cards/today", {
      cookie: devoteeCookie,
      method: "PATCH",
      body: { activities: [...updatesByActivity].map(([activity_id, values]) => ({ activity_id, values })) },
    });
    assert(patch.response.status === 200, `card update expected 200, got ${patch.response.status}: ${JSON.stringify(patch.payload)}`);
    const allValues = patch.payload.activities.flatMap((activity) => activity.values);
    const savedBoolean = allValues.find((field) => field.field_id === booleanField.field.field_id);
    const savedNumeric = allValues.find((field) => field.field_id === numericField.field.field_id);
    assert(savedBoolean?.is_filled === true && savedBoolean.boolean_value === false, "intentional No was not preserved");
    assert(savedNumeric?.is_filled === true && Number(savedNumeric.numeric_value) === 0, "intentional numeric zero was not preserved");
    pass("Dynamic Update preserves intentional No/0 separately from N/A");
  } else {
    pass("Today card is already finalized; editable PATCH test safely skipped");
  }

  const lifecycle = await backend("/lifecycle/status", { cookie: devoteeCookie });
  assert(lifecycle.response.status === 200, `lifecycle expected 200, got ${lifecycle.response.status}`);
  assert(typeof lifecycle.payload.current_category_code === "string", "lifecycle payload missing current category");
  pass("Lifecycle status integrates through frontend proxy");

  for (const path of ["/weekly/latest", "/monthly/latest"]) {
    const result = await backend(path, { cookie: devoteeCookie });
    assert([200, 404, 409].includes(result.response.status), `${path} returned unexpected ${result.response.status}: ${JSON.stringify(result.payload)}`);
  }
  pass("Weekly and four-week report endpoints integrate with expected not-ready states");
} finally {
  if (devoteeUserId && adminCookie) {
    const cleanup = await backend(`/admin/devotees/${devoteeUserId}/deactivate`, {
      cookie: adminCookie,
      method: "POST",
      body: { reason: "Frontend Step 15 smoke-test cleanup" },
    });
    if (cleanup.response.status === 200) pass("Disposable devotee logically deactivated");
    else console.warn(`WARN: cleanup returned ${cleanup.response.status}: ${JSON.stringify(cleanup.payload)}`);
  }
}

console.log("\nALL DEVOTEE FRONTEND SMOKE TESTS PASSED");
