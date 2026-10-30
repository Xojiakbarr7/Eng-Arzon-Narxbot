"""The Telegram Mini App is hosted separately and must use a restricted CORS policy."""
from fastapi.testclient import TestClient
from app.main import app


def test_miniapp_cors_preflight_allows_only_configured_origins():
    with TestClient(app) as client:
        valid = client.options(
            "/api/products",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "X-Telegram-Init-Data",
            },
        )
        assert valid.status_code == 200
        assert valid.headers["access-control-allow-origin"] == "http://localhost:5173"

        invalid = client.options(
            "/api/products",
            headers={"Origin": "https://untrusted.example", "Access-Control-Request-Method": "GET"},
        )
        assert "access-control-allow-origin" not in invalid.headers
