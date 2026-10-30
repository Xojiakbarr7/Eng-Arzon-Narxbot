"""Run the existing aiogram bot through a protected Telegram webhook on Render.

This allows a single ASGI web service to host both the catalog API and Telegram bot.
Polling and webhooks must NOT be used simultaneously for the same bot token.
"""
import asyncio
from contextlib import suppress
import hashlib
import hmac
import logging
import os
from pathlib import Path
import sys
from urllib.parse import urlparse

import httpx
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, MenuButtonWebApp, Update
from fastapi import FastAPI, HTTPException, Request

from .config import get_settings

logger = logging.getLogger("eng_arzon.webhook")
WEBHOOK_PATH = "/telegram/webhook"


def webhook_secret(internal_token: str) -> str:
    return hmac.new(internal_token.encode("utf-8"), b"eng-arzon-telegram-webhook-v1", hashlib.sha256).hexdigest()


async def enable_webhook(application: FastAPI) -> None:
    settings = get_settings()
    token = settings.bot_token.strip()
    internal_token = settings.bot_internal_token.strip()
    base_url = (os.getenv("TELEGRAM_WEBHOOK_BASE_URL") or os.getenv("RENDER_EXTERNAL_URL") or "").strip().rstrip("/")
    if not token:
        logger.warning("Telegram webhook disabled: BOT_TOKEN is not configured")
        return
    if len(internal_token) < 32:
        logger.warning("Telegram webhook disabled: BOT_INTERNAL_TOKEN must have at least 32 characters")
        return
    parsed = urlparse(base_url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.path not in ("", "/") or parsed.username or parsed.password:
        logger.warning("Telegram webhook disabled: configure TELEGRAM_WEBHOOK_BASE_URL as the public HTTPS service origin")
        return

    # rootDir=backend on Render, but bot/main.py remains a sibling at repo root.
    project_root = Path(__file__).resolve().parents[2]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    try:
        from bot.main import Api, miniapp, notification_loop, router
    except ImportError:
        logger.exception("Telegram bot module could not be imported")
        return

    bot = Bot(token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    local_client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application),
        base_url="http://eng-arzon-internal",
        timeout=20,
    )
    dp = Dispatcher()
    dp.include_router(router)
    api = Api(local_client, internal_token)
    dp["api"] = api
    try:
        await bot.set_my_commands([
            BotCommand(command="start", description="Asosiy menyu"),
            BotCommand(command="search", description="Mahsulot qidirish"),
            BotCommand(command="basket", description="Eng arzon savatcha"),
            BotCommand(command="alerts", description="Narx kuzatuvlari"),
            BotCommand(command="favorites", description="Sevimlilarim"),
            BotCommand(command="myid", description="Telegram ID raqamim"),
            BotCommand(command="admin", description="Admin boshqaruvi"),
            BotCommand(command="help", description="Yordam"),
        ])
        await bot.set_webhook(
            base_url + WEBHOOK_PATH,
            secret_token=webhook_secret(internal_token),
            allowed_updates=dp.resolve_used_update_types(),
            drop_pending_updates=False,
        )
        markup = miniapp()
        if markup:
            with suppress(Exception):
                await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(text="Katalog", web_app=markup.inline_keyboard[0][0].web_app))
    except Exception:
        logger.exception("Telegram webhook registration failed; API remains available")
        await local_client.aclose()
        await bot.session.close()
        return

    application.state.telegram_bot = bot
    application.state.telegram_dispatcher = dp
    application.state.telegram_secret = webhook_secret(internal_token)
    application.state.telegram_client = local_client
    application.state.telegram_worker = asyncio.create_task(notification_loop(bot, api))
    logger.info("Telegram webhook registered on the current Render web service")


async def disable_webhook(application: FastAPI) -> None:
    worker = getattr(application.state, "telegram_worker", None)
    if worker:
        worker.cancel()
        with suppress(asyncio.CancelledError):
            await worker
    client = getattr(application.state, "telegram_client", None)
    if client:
        await client.aclose()
    bot = getattr(application.state, "telegram_bot", None)
    if bot:
        # Do not delete the webhook on shutdown: Render's free service can spin down.
        await bot.session.close()


async def telegram_update(request: Request):
    application = request.app
    bot = getattr(application.state, "telegram_bot", None)
    dispatcher = getattr(application.state, "telegram_dispatcher", None)
    if bot is None or dispatcher is None:
        raise HTTPException(503, "Telegram webhook is not configured")
    supplied = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    expected = application.state.telegram_secret
    if not supplied or not hmac.compare_digest(supplied, expected):
        raise HTTPException(403, "Telegram webhook signature required")
    try:
        data = await request.json()
        update = Update.model_validate(data, context={"bot": bot})
    except (ValueError, TypeError) as exc:
        raise HTTPException(400, "Invalid Telegram update") from exc
    await dispatcher.feed_update(bot, update)
    return {"ok": True}
