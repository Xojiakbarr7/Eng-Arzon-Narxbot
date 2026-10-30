"""Telegram uchun himoyalangan HTTPS kirishi; lokal demo sessiyasi tashqariga chiqmaydi."""
from pathlib import Path
from starlette.responses import JSONResponse
from starlette.staticfiles import StaticFiles
from starlette.datastructures import Headers
from starlette.exceptions import HTTPException
from .security import validate_init_data


class TelegramMiniAppGateway:
    def __init__(self, core, directory, token, ttl=3600):
        if not token:
            raise ValueError("Telegram Mini App uchun BOT_TOKEN kerak")
        self.core = core
        self.static = StaticFiles(directory=str(directory), html=True, check_dir=False)
        self.token = token
        self.ttl = ttl

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.core(scope, receive, send)
        path = scope.get("path", "/")
        if path.startswith("/api/internal") or path in ("/docs", "/redoc", "/openapi.json"):
            return await JSONResponse({"detail": "Topilmadi"}, status_code=404)(scope, receive, send)
        if path.startswith("/api/"):
            if path != "/api/health" and not (path.startswith("/api/admin") and Headers(scope=scope).get("authorization", "").startswith("Bearer ")):
                try:
                    validate_init_data(Headers(scope=scope).get("x-telegram-init-data", ""), self.token, self.ttl)
                except (ValueError, KeyError, TypeError):
                    return await JSONResponse({"detail": "Ilovani Telegram botidagi Katalog tugmasi orqali oching."}, status_code=401)(scope, receive, send)
            return await self.core(scope, receive, send)
        try:
            return await self.static(scope, receive, send)
        except HTTPException as exc:
            return await JSONResponse({"detail": "Topilmadi"}, status_code=exc.status_code)(scope, receive, send)


from .main import app as core_app
from .config import get_settings

settings = get_settings()
app = TelegramMiniAppGateway(core_app, Path(__file__).resolve().parents[2] / "frontend" / "dist", settings.bot_token, settings.init_data_ttl_seconds)
