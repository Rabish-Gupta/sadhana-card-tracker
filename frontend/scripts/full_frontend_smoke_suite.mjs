import { spawnSync } from "node:child_process";

const args = process.argv.slice(2);
function value(name, fallback) { const index = args.indexOf(name); return index >= 0 ? args[index + 1] : fallback; }
const adminEmail = value("--admin-email");
const adminPassword = value("--admin-password");
const url = value("--url", "http://localhost:3000");
if (!adminEmail || !adminPassword) {
  console.error("Usage: node scripts/full_frontend_smoke_suite.mjs --admin-email <email> --admin-password <password> [--url http://localhost:3000]");
  process.exit(2);
}
const runs = [
  ["production_integration_smoke_test.mjs", ["--url", url]],
  ["frontend_smoke_test.mjs", ["--email", adminEmail, "--password", adminPassword, "--url", url]],
  ["devotee_frontend_smoke_test.mjs", ["--admin-email", adminEmail, "--admin-password", adminPassword, "--url", url]],
  ["admin_frontend_smoke_test.mjs", ["--admin-email", adminEmail, "--admin-password", adminPassword, "--url", url]],
];
for (const [script, scriptArgs] of runs) {
  console.log(`\n=== RUNNING ${script} ===`);
  const result = spawnSync(process.execPath, [`scripts/${script}`, ...scriptArgs], { stdio: "inherit" });
  if (result.status !== 0) process.exit(result.status ?? 1);
}
console.log("\nALL FRONTEND STEP 14 + STEP 15 + STEP 16 + STEP 17 SMOKE TESTS PASSED");
