"""Secure Telegram webhook served by the existing FastAPI Web Service.

This is opt-in. It does not activate until TELEGRAM_WEBHOOK_ENABLED=true,
BOT_TOKEN and BOT_INTERNAL_TOKEN are configured, and an HTTPS URL is set.
"""
import asyncio
import hashlib
import hmac
import json
import logging
import os
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, Update
from fastapi import HTTPException, Request

from .telegram_bot import Api, router, notification_loop, miniapp

log = logging.getLogger("eng_arzon.webhook")


def webhook_secret(token: str) -> str:
    # Telegram accepts alphanumeric URL-safe characters, 1..256 in length.
    return hashlib.sha256(("eng-arzon-webhook-v1:" + token).encode()).hexdigest()


def enabled() -> bool:
    return os.getenv("TELEGRAM_WEBHOOK_ENABLED", "false").strip().lower() == "true"


@dataclass
class TelegramRuntime:
    bot: Bot
    dp: Dispatcher
    client: httpx.AsyncClient
    secret: str
    notification_task: asyncio.Task


runtime: TelegramRuntime | None = None


async def start_webhook() -> None:
    global runtime
    if not enabled():
        log.info("Telegram webhook disabled. Set TELEGRAM_WEBHOOK_ENABLED=true to enable.")
        return
    token = os.getenv("BOT_TOKEN", "").strip()
    internal_token = os.getenv("BOT_INTERNAL_TOKEN", "").strip()
    base_url = os.getenv("TELEGRAM_WEBHOOK_BASE_URL", "").strip().rstrip("/")
    if not token or len(internal_token) < 32:
        log.warning("Telegram webhook not started: BOT_TOKEN or BOT_INTERNAL_TOKEN missing.")
        return
    parsed = urlparse(base_url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        log.warning("Telegram webhook not started: a valid HTTPS TELEGRAM_WEBHOOK_BASE_URL is required.")
        return

    bot = Bot(token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    client = httpx.AsyncClient(base_url=f"http://127.0.0.1:{os.getenv('PORT', '10000')}", timeout=20)
    dp = Dispatcher()
    dp.include_router(router)
    api = Api(client, internal_token)
    dp["api"] = api
    secret = webhook_secret(token)
    try:
        await bot.set_my_commands([
            BotCommand(command="start", description="Asosiy menyu"),
            BotCommand(command="search", description="Mahsulot qidirish"),
            BotCommand(command="basket", description="Eng arzon savatcha"),
            BotCommand(command="alerts", description="Narx kuzatuvlari"),
            BotCommand(command="favorites", description="Sevimlilar"),
            BotCommand(command="myid", description="Telegram ID raqamim"),
            BotCommand(command="admin", description="Admin boshqaruvi"),
            BotCommand(command="help", description="Yordam"),
        ])
        await bot.set_webhook(
            url=base_url + "/api/telegram/webhook",
            secret_token=secret,
            allowed_updates=dp.resolve_used_update_types(),
            drop_pending_updates=False,
            max_connections=5,
        )
    except Exception as exc:
        log.error("Telegram webhook registration failed: %s", type(exc).__name__)
        await bot.session.close()
        await client.aclose()
        return

    worker = asyncio.create_task(notification_loop(bot, api))
    runtime = TelegramRuntime(bot=bot, dp=dp, client=client, secret=secret, notification_task=worker)
    log.info("Telegram webhook registered successfully.")


async def stop_webhook() -> None:
    global runtime
    active, runtime = runtime, None
    if active is None:
        return
    active.notification_task.cancel()
    try:
        await active.notification_task
    except asyncio.CancelledError:
        pass
    # Do not delete webhook on shutdown: a replacement instance may already
    # have registered its own webhook during a rolling deploy.
    await active.bot.session.close()
    await active.client.aclose()


async def accept_update(request: Request) -> dict:
    active = runtime
    if not active:
        raise HTTPException(503, "Telegram webhook hali sozlanmagan")
    received = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not hmac.compare_digest(received.encode(), active.secret.encode()):
        raise HTTPException(403, "Telegram webhook imzosi noto‘g‘ri")
    if int(request.headers.get("content-length", "0") or 0) > 1024 * 1024:
        raise HTTPException(413, "Telegram update juda katta")
    raw = await request.body()
    if len(raw) > 1024 * 1024:
        raise HTTPException(413, "Telegram update juda katta")
    try:
        data = json.loads(raw)
        update = Update.model_validate(data, context={"bot": active.bot})
    except (ValueError, TypeError):
        raise HTTPException(400, "Telegram update formati noto‘g‘ri")
    await active.dp.feed_update(active.bot, update)
    return {"ok": True}
