import { readFile } from "node:fs/promises";

const spec = JSON.parse(await readFile(new URL("../contracts/backend-openapi.json", import.meta.url), "utf8"));
const requiredPaths = [
  "/api/v1/auth/register", "/api/v1/auth/login", "/api/v1/auth/me", "/api/v1/auth/logout",
  "/api/v1/cards/today", "/api/v1/cards/{card_date}",
  "/api/v1/weekly/latest", "/api/v1/monthly/latest",
  "/api/v1/lifecycle/status", "/api/v1/lifecycle/bhima-status",
  "/api/v1/admin/registrations/pending", "/api/v1/admin/registrations/{user_id}/approve", "/api/v1/admin/registrations/{user_id}/reject",
  "/api/v1/admin/devotees", "/api/v1/admin/devotees/{user_id}/activate", "/api/v1/admin/devotees/{user_id}/deactivate",
  "/api/v1/admin/lifecycle/sahadeva-reviews", "/api/v1/admin/lifecycle/devotees/{user_id}/sahadeva-review", "/api/v1/admin/lifecycle/run-now",
  "/api/v1/admin/config/categories", "/api/v1/admin/config/activities", "/api/v1/admin/config/activities/{activity_id}/fields",
  "/api/v1/admin/config/scoring-rules", "/api/v1/admin/config/scoring-rules/{rule_id}/versions", "/api/v1/admin/config/scoring-rule-versions/{version_id}",
  "/api/v1/admin/config/standards", "/api/v1/admin/config/standards/{standard_id}/versions", "/api/v1/admin/config/standard-versions/{version_id}",
  "/api/v1/admin/config/category-activity-configs", "/api/v1/admin/config/category-activity-configs/{config_id}",
  "/api/v1/admin/config/organization-settings/current", "/api/v1/admin/config/organization-settings/versions", "/api/v1/admin/config/organization-setting-versions/{version_id}",
  "/api/v1/admin/config/activate-due",
  "/api/v1/admin/corrections/devotees/{user_id}/cards/{card_date}", "/api/v1/admin/corrections/devotees/{user_id}/category-history", "/api/v1/admin/corrections/devotees/{user_id}/category",
];
const missing = requiredPaths.filter((path) => !spec.paths?.[path]);
if (missing.length) throw new Error(`Backend contract missing required paths: ${missing.join(", ")}`);

function enumValues(name) { return spec.components?.schemas?.[name]?.enum ?? []; }
function assertEnum(name, expected) { const actual = enumValues(name); if (JSON.stringify(actual) !== JSON.stringify(expected)) throw new Error(`${name} changed: ${JSON.stringify(actual)}`); }
function schema(name) { const value = spec.components?.schemas?.[name]; if (!value) throw new Error(`Backend contract missing schema ${name}`); return value; }
function hasOperation(path, method) { if (!spec.paths[path]?.[method]) throw new Error(`${method.toUpperCase()} ${path} missing`); }

assertEnum("UserRole", ["DEVOTEE", "ADMIN"]);
assertEnum("AccountStatus", ["PENDING", "ACTIVE", "INACTIVE", "REJECTED"]);
assertEnum("ScoringType", ["DAILY", "WEEKLY_AGGREGATED", "NON_SCORED", "SYSTEM_DERIVED"]);
assertEnum("ActivityInputType", ["NUMBER", "COUNT", "DURATION", "TIME", "BOOLEAN", "TEXT", "SELECTION"]);
assertEnum("EmploymentStatus", ["WORKING", "NOT_WORKING"]);
assertEnum("VersionStatus", ["PENDING", "ACTIVE", "ARCHIVED"]);
assertEnum("RuleType", ["BOOLEAN", "THRESHOLD", "PERCENTAGE", "SYSTEM_DERIVED", "NO_SCORE"]);
assertEnum("StandardPeriod", ["DAILY", "WEEKLY"]);

const registrationRequired = schema("RegistrationRequest").required ?? [];
for (const field of ["full_name", "email", "password", "phone_number", "college", "branch", "current_academic_year", "college_joining_year"]) {
  if (!registrationRequired.includes(field)) throw new Error(`RegistrationRequest no longer requires ${field}`);
}
const valueUpdate = schema("DailyActivityValueUpdate");
for (const field of ["field_id", "is_filled", "numeric_value", "time_value", "boolean_value", "text_value"]) {
  if (!valueUpdate.properties?.[field]) throw new Error(`DailyActivityValueUpdate missing ${field}`);
}
for (const schemaName of [
  "AdminCreateDevoteeRequest", "SahadevaReviewRequest", "ActivityCreateRequest", "ActivityFieldCreateRequest",
  "ScoringRuleVersionCreateRequest", "StandardVersionCreateRequest", "CategoryActivityConfigCreateRequest",
  "OrganizationSettingVersionCreateRequest", "HistoricalCardCorrectionRequest", "HistoricalCategoryCorrectionRequest",
]) schema(schemaName);

hasOperation("/api/v1/cards/today", "get"); hasOperation("/api/v1/cards/today", "patch");
hasOperation("/api/v1/admin/config/activities", "post");
hasOperation("/api/v1/admin/config/category-activity-configs/{config_id}", "patch");
hasOperation("/api/v1/admin/corrections/devotees/{user_id}/cards/{card_date}", "patch");
hasOperation("/api/v1/admin/corrections/devotees/{user_id}/category", "patch");

console.log(`Backend contract verified: ${Object.keys(spec.paths).length} paths; Step 14-16 auth/devotee/admin contracts intact.`);
