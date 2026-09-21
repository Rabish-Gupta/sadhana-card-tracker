from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)

frontend_pkg = json.loads((ROOT / "frontend/package.json").read_text())
require(frontend_pkg["version"] == "0.4.0", "Unexpected frontend version")
backend_pyproject = (ROOT / "backend/pyproject.toml").read_text()
require('version = "0.11.2"' in backend_pyproject, "Unexpected backend version")

spec = json.loads((ROOT / "frontend/contracts/backend-openapi.json").read_text())
require(len(spec.get("paths", {})) == 48, "Frozen backend contract must contain 48 paths")

migration_hashes = {
    "0001_initial_schema.py": "dd53278f59b5f20e584480e0c230379bab8e61f035faf6e377c89f3e07a56eca",
    "0002_org_setting_versions.py": "5352986d101291fc6916755cd0cf6c4f0f04b30c19c58170a244ad06fda00580",
    "0003_lifecycle_fields.py": "1fdfb82fb5f82ad4f22e599cf1f91ad11ad486a8e383e673d8dfa4807f261abe",
}
for name, expected in migration_hashes.items():
    actual = sha(ROOT / "backend/migrations/versions" / name)
    require(actual == expected, f"Migration drift detected for {name}: {actual}")

for secret_name in [".env", ".env.local", ".env.production"]:
    require(not (ROOT / secret_name).exists(), f"Release must not contain {secret_name}")
    require(not (ROOT / "frontend" / secret_name).exists(), f"Frontend release must not contain {secret_name}")
    require(not (ROOT / "backend" / secret_name).exists(), f"Backend release must not contain {secret_name}")

compose = (ROOT / "deploy/docker-compose.yml").read_text()
for service in ["db:", "migrate:", "backend:", "frontend:"]:
    require(service in compose, f"Compose missing service {service}")
require("service_completed_successfully" in compose, "Backend must wait for migrations")
require("/api/readiness" in compose, "Frontend healthcheck must use readiness endpoint")

print("Release structure/hashes validated")
print("frontend=0.4.0 backend=0.11.2 paths=48 migrations=3")
