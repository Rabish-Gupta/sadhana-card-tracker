const args = process.argv.slice(2);
function value(name, fallback) {
  const index = args.indexOf(name);
  return index >= 0 ? args[index + 1] : fallback;
}
const baseUrl = (value("--url", "http://localhost:3000") ?? "").replace(/\/$/, "");
const email = value("--email");
const password = value("--password");
if (!email || !password) {
  console.error("Usage: node scripts/frontend_smoke_test.mjs --email <email> --password <password> [--url http://localhost:3000]");
  process.exit(2);
}
function pass(message) { console.log(`PASS: ${message}`); }
function assert(condition, message) { if (!condition) throw new Error(message); }

const health = await fetch(`${baseUrl}/api/backend-health`);
assert(health.status === 200, `backend-health expected 200, got ${health.status}`);
const healthJson = await health.json();
assert(healthJson.status === "ok", `unexpected backend health: ${JSON.stringify(healthJson)}`);
pass("Next.js BFF reaches FastAPI /health without browser CORS");

const login = await fetch(`${baseUrl}/api/session/login`, {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify({ email, password }),
  redirect: "manual",
});
const loginText = await login.text();
assert(login.status === 200, `session login expected 200, got ${login.status}: ${loginText}`);
const user = JSON.parse(loginText);
const setCookie = login.headers.get("set-cookie");
assert(setCookie?.includes("sadhana_access_token="), "login did not set HttpOnly session cookie");
assert(/httponly/i.test(setCookie), "auth cookie is not HttpOnly");
const cookie = setCookie.split(";", 1)[0];
pass("login stores FastAPI JWT in HttpOnly Next.js cookie");

const me = await fetch(`${baseUrl}/api/session/me`, { headers: { cookie } });
assert(me.status === 200, `session me expected 200, got ${me.status}`);
const meJson = await me.json();
assert(meJson.id === user.id && meJson.role === user.role, "session /me does not match login user");
pass("session /me is authenticated through the BFF");

const protectedPath = user.role === "ADMIN" ? "/api/backend/admin/registrations/pending" : "/api/backend/cards/today";
const protectedResponse = await fetch(`${baseUrl}${protectedPath}`, { headers: { cookie } });
assert(protectedResponse.status === 200, `protected proxy expected 200, got ${protectedResponse.status}: ${await protectedResponse.text()}`);
pass(`role-appropriate protected FastAPI route works through same-origin proxy (${user.role})`);

const logout = await fetch(`${baseUrl}/api/session/logout`, { method: "POST", headers: { cookie } });
assert(logout.status === 200, `logout expected 200, got ${logout.status}`);
const clearCookie = logout.headers.get("set-cookie") ?? "";
assert(clearCookie.includes("sadhana_access_token="), "logout did not clear auth cookie");
pass("logout clears frontend session cookie");

console.log("\nALL FRONTEND FOUNDATION SMOKE TESTS PASSED");
