"""HTTPS manzilini tekshiradi va botning Katalog menyusiga ulaydi. Token chiqarilmaydi."""
import asyncio
import json
import ssl
import sys
from pathlib import Path
from urllib.parse import urlparse
import httpx
from dotenv import dotenv_values, set_key
from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.types import MenuButtonWebApp, WebAppInfo


async def main(url):
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None, 443) or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ValueError("To‘liq HTTPS asosiy manzil talab qilinadi")
    root = Path(__file__).resolve().parents[1]
    env_path = root / ".env"
    config = dotenv_values(env_path)
    token = config.get("BOT_TOKEN", "")
    if not token:
        raise ValueError("BOT_TOKEN sozlanmagan")
    url = url.rstrip("/")
    async with httpx.AsyncClient(verify=ssl.create_default_context(), timeout=20) as client:
        health = await client.get(url + "/api/health")
        health.raise_for_status()
        if health.json().get("version") != "1.0.0":
            raise ValueError("Manzilda ushbu loyiha topilmadi")
        unsigned = await client.get(url + "/api/products")
        if unsigned.status_code != 401:
            raise ValueError("Telegram himoyasi yoqilmagan; bu manzil ulanmaydi")
    async with Bot(token, session=AiohttpSession(timeout=20)) as bot:
        await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(text="Katalog", web_app=WebAppInfo(url=url + "/?view=catalog")))
        # Telegram menyusi bir nechta serverda qisqa muddatda yangilanishi mumkin.
        for attempt in range(5):
            menu = await bot.get_chat_menu_button()
            if menu.type == "web_app" and menu.web_app.url == url + "/?view=catalog":
                break
            await asyncio.sleep(1)
        else:
            raise RuntimeError("Telegram menyusi tasdiqlanmadi")
        account = await bot.get_me()
    set_key(str(env_path), "MINI_APP_URL", url, quote_mode="never")
    print(json.dumps({"ok": True, "username": account.username, "url": url, "telegram_menu_verified": True}))


if __name__ == "__main__":
    try:
        if len(sys.argv) != 2:
            raise ValueError("HTTPS manzil argumentini bering")
        asyncio.run(main(sys.argv[1]))
    except Exception as exc:
        print(json.dumps({"ok": False, "error_type": type(exc).__name__}))
        raise SystemExit(1)
