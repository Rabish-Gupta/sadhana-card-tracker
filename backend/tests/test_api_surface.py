from app.main import app


def test_expected_auth_and_admin_routes_exist() -> None:
    # Test the public FastAPI/OpenAPI contract rather than private route internals.
    # Newer FastAPI versions may represent included routers with internal
    # _IncludedRouter objects in app.routes even though the endpoints are
    # correctly registered and exposed.
    paths = set(app.openapi()["paths"])
    expected = {
        "/health",
        "/api/v1/auth/register",
        "/api/v1/auth/login",
        "/api/v1/auth/me",
        "/api/v1/auth/logout",
        "/api/v1/admin/registrations/pending",
        "/api/v1/admin/registrations/{user_id}/approve",
        "/api/v1/admin/registrations/{user_id}/reject",
        "/api/v1/admin/devotees",
        "/api/v1/admin/devotees/{user_id}/deactivate",
        "/api/v1/admin/devotees/{user_id}/activate",
        "/api/v1/weekly/latest",
        "/api/v1/weekly/{week_start_date}",
    }
    assert expected.issubset(paths)
