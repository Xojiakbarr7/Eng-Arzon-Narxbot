import asyncio
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode
from pathlib import Path
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient


def test_public_gateway_requires_signed_telegram_and_hides_admin(tmp_path, monkeypatch):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "bot_token", "test-token")
    from app.public_app import TelegramMiniAppGateway
    (tmp_path / "index.html").write_text("Mini App", encoding="utf-8")
    async def endpoint(request):
        return JSONResponse({"ok": True})
    core = Starlette(routes=[Route("/api/products", endpoint), Route("/api/health", endpoint)])
    gateway = TelegramMiniAppGateway(core, tmp_path, "test-token")
    with TestClient(gateway) as client:
        assert client.get("/").status_code == 200
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/products").status_code == 401
        assert client.get("/api/products", headers={"X-Bot-Token": "anything", "X-Telegram-User-Id": "123"}).status_code == 401
        assert client.get("/api/admin/stats").status_code == 401
        assert client.get("/api/internal/notifications/claim").status_code == 404
        assert client.get("/.env").status_code == 404
        fields = {"auth_date": str(int(time.time())), "user": json.dumps({"id": 123})}
        secret = hmac.new(b"WebAppData", b"test-token", hashlib.sha256).digest()
        check = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
        fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
        assert client.get("/api/products", headers={"X-Telegram-Init-Data": urlencode(fields)}).status_code == 200
