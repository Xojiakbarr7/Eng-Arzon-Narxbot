"""Webhook authentication and graceful behavior without Telegram credentials."""
from fastapi.testclient import TestClient
from app.main import app
from app.telegram_webhook import webhook_secret


def test_webhook_secret_and_configuration():
    assert len(webhook_secret("s" * 32)) == 64
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/health").json()["telegram_webhook"] is False
        assert client.post("/telegram/webhook", json={"update_id": 100}).status_code == 503


def test_webhook_rejects_unsigned_requests():
    # Simulate configured runtime to ensure no third party can forge updates.
    with TestClient(app) as client:
        app.state.telegram_bot = object()
        app.state.telegram_dispatcher = object()
        app.state.telegram_secret = "expected-secret"
        try:
            assert client.post("/telegram/webhook", json={"update_id": 101}).status_code == 403
            assert client.post("/telegram/webhook", headers={"X-Telegram-Bot-Api-Secret-Token": "wrong-secret"}, json={"update_id": 101}).status_code == 403
        finally:
            del app.state.telegram_bot
            del app.state.telegram_dispatcher
            del app.state.telegram_secret
