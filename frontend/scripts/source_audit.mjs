import { readFile, readdir } from "node:fs/promises";
import path from "node:path";

const root = new URL("../", import.meta.url);
async function walk(relative) {
  const absolute = new URL(relative, root);
  const entries = await readdir(absolute, { withFileTypes: true });
  const out = [];
  for (const entry of entries) {
    const child = path.posix.join(relative, entry.name);
    if (entry.isDirectory()) out.push(...await walk(`${child}/`));
    else out.push(child);
  }
  return out;
}
function assert(condition, message) { if (!condition) throw new Error(message); }
const files = (await walk("src/")).filter((name) => /\.(ts|tsx)$/.test(name));
const contents = new Map();
for (const file of files) contents.set(file, await readFile(new URL(file, root), "utf8"));
const joined = [...contents.values()].join("\n");
const clientJoined = [...contents.values()].filter((text) => text.trimStart().startsWith("\"use client\";")).join("\n");

assert(!joined.includes("localStorage"), "JWT/session data must not be stored in localStorage");
assert(!joined.includes("sessionStorage"), "JWT/session data must not be stored in sessionStorage");
assert(!clientJoined.includes("http://127.0.0.1:8000") && !clientJoined.includes("http://localhost:8000"), "browser source must not call FastAPI directly");

const dailyEditor = contents.get("src/components/devotee/daily-card-editor.tsx") ?? "";
for (const forbidden of ["MORNING_PROGRAM", "CHANTING", "BOOK_READING", "PERSONAL_HEARING", "MORNING_CLASS", "SHLOKA_VAISHNAVA_SONG", "STUDY_PREPARATION", "TO_BED", "WAKE_UP", "DAY_REST", "SEVA"]) {
  assert(!dailyEditor.includes(forbidden), `Daily Card editor hard-codes activity code ${forbidden}`);
}
assert(dailyEditor.includes("activity.values.map"), "Daily Card editor must render backend-provided fields dynamically");
assert(dailyEditor.includes("is_filled: false"), "Daily Card editor must preserve explicit N/A updates");
assert(dailyEditor.includes("boolean_value"), "Daily Card editor must support intentional boolean false");
assert(dailyEditor.includes("numeric_value"), "Daily Card editor must support intentional numeric zero");

const monthly = contents.get("src/app/devotee/monthly/page.tsx") ?? "";
assert(monthly.includes("four adjacent complete"), "4-week report definition must remain explicit in UI");
assert(!monthly.toLowerCase().includes("calendar month report"), "Do not redefine monthly report as a calendar month");

const lifecycle = contents.get("src/components/devotee/bhima-status-form.tsx") ?? "";
assert(lifecycle.includes('useState<EmploymentStatus | null>'), "Initial Bhima choice must not silently default to Working/Not Working");
assert(lifecycle.includes('status.current_category_code === "YUDHISHTHIRA"'), "Yudhishthira must be allowed to make/revise explicit Bhima choice");

const cookieRoute = contents.get("src/app/api/session/login/route.ts") ?? "";
assert(cookieRoute.includes("httpOnly: true"), "Auth cookie must remain HttpOnly");
assert(cookieRoute.includes('sameSite: "lax"'), "Auth cookie SameSite protection missing");

for (const required of [
  "src/app/devotee/card/page.tsx",
  "src/app/devotee/history/page.tsx",
  "src/app/devotee/weekly/page.tsx",
  "src/app/devotee/monthly/page.tsx",
  "src/app/devotee/lifecycle/page.tsx",
]) {
  assert(contents.has(required), `Missing Step 15 page: ${required}`);
}

console.log(`Frontend source audit passed across ${files.length} TypeScript/TSX files.`);

for (const required of [
  "src/app/admin/devotees/page.tsx",
  "src/app/admin/lifecycle/page.tsx",
  "src/app/admin/config/page.tsx",
  "src/app/admin/config/activities/page.tsx",
  "src/app/admin/config/rules/page.tsx",
  "src/app/admin/config/standards/page.tsx",
  "src/app/admin/config/category-activities/page.tsx",
  "src/app/admin/config/organization/page.tsx",
  "src/app/admin/corrections/page.tsx",
]) {
  assert(contents.has(required), `Missing Step 16 Admin page: ${required}`);
}
const correctionWorkbench = contents.get("src/components/admin/correction-workbench.tsx") ?? "";
assert(correctionWorkbench.includes("Policy B"), "Historical category correction UI must state Policy B semantics");
assert(correctionWorkbench.includes("is_filled: false"), "Historical-card correction must preserve N/A semantics");
assert(correctionWorkbench.includes("boolean_value"), "Historical-card correction must preserve intentional false");
const activitiesAdmin = contents.get("src/components/admin/activity-manager.tsx") ?? "";
assert(!activitiesAdmin.includes('name="input_type" defaultValue={field.input_type}'), "Existing ActivityField input_type must not be editable");
assert(!activitiesAdmin.includes('name="field_key" defaultValue={field.field_key}'), "Existing ActivityField field_key must not be editable");
const orgAdmin = contents.get("src/components/admin/organization-settings-manager.tsx") ?? "";
assert(orgAdmin.includes('v.status === "PENDING"'), "Organization settings editor must target PENDING version rather than mutate ACTIVE history");
const ruleAdmin = contents.get("src/components/admin/scoring-rule-manager.tsx") ?? "";
assert(ruleAdmin.includes('v.status === "PENDING"'), "Scoring rule editor must target PENDING version");
const standardAdmin = contents.get("src/components/admin/standard-manager.tsx") ?? "";
assert(standardAdmin.includes('v.status === "PENDING"'), "Standard editor must target PENDING version");
console.log("Step 16 Admin integration/source invariants passed.");


const nextConfig = await readFile(new URL("../next.config.ts", import.meta.url), "utf8");
assert(nextConfig.includes('output: "standalone"'), "Production standalone Next.js output must remain enabled");
for (const header of ["X-Content-Type-Options", "X-Frame-Options", "Referrer-Policy", "Permissions-Policy", "Content-Security-Policy"]) {
  assert(nextConfig.includes(header), `Missing production security header ${header}`);
}
const bffHelper = contents.get("src/lib/api/bff.ts") ?? "";
assert(bffHelper.includes("AbortSignal.timeout"), "BFF -> backend requests must have a timeout");
assert(bffHelper.includes("x-request-id"), "BFF request correlation must remain enabled");
const proxy = contents.get("src/app/api/backend/[...path]/route.ts") ?? "";
assert(proxy.includes("bffMaxBodyBytes"), "Generic BFF proxy must cap mutation body size");
assert(proxy.includes('joined === "auth/login"'), "Generic BFF proxy must not bypass dedicated auth session endpoint");
assert(contents.has("src/app/api/readiness/route.ts"), "Deployment readiness route is required");
assert(contents.has("src/app/api/version/route.ts"), "Runtime version route is required");
const shell = contents.get("src/components/app-shell.tsx") ?? "";
assert(shell.includes("Skip to main content") && shell.includes('id="main-content"'), "Keyboard skip link/accessibility target required");
console.log("Step 17 production-hardening/source invariants passed.");
