"""Daily catalog refresh and one durable Telegram channel digest.

Enable explicitly through COLLECTION_ENABLED and DAILY_POST_ENABLED. Delivery
with an unknown outcome is never retried automatically: inspect the channel
before resetting an uncertain/sending daily_runs row. Collection failures and
empty results likewise remain recorded until the next day or manual review.
"""
import argparse
import asyncio
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from html import escape
import json
import logging
import os
from pathlib import Path
import re
import ssl
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from .db import SessionLocal
from .models import Category, DailyRun, Offer, Product, Store, utcnow
from .services import aware, product_summary
from .channel_photos import safe_image_url, send_product_photo, PhotoDeliveryError

log = logging.getLogger("eng_arzon.daily")
TASHKENT = ZoneInfo("Asia/Tashkent")
SOURCE_HOSTS = {"asaxiy": "asaxiy.uz", "uzum": "uzum.uz", "olx": "www.olx.uz"}


def flag(value):
    return str(value).lower() in {"true", "1", "yes"}


@dataclass(frozen=True)
class DailySettings:
    enabled: bool = False
    post_enabled: bool = False
    channel: str = ""
    hour: int = 9
    minute: int = 0
    max_items: int = 10
    interval_seconds: int = 60
    collection_interval_hours: int = 2
    config_path: str = str(Path(__file__).resolve().parents[1] / "collection-sources.json")
    token: str = ""

    @classmethod
    def from_env(cls):
        schedule = os.getenv("DAILY_POST_TIME", "09:00")
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", schedule):
            raise ValueError("DAILY_POST_TIME HH:MM formatida bo‘lsin")
        hour, minute = map(int, schedule.split(":"))
        channel = os.getenv("DAILY_CHANNEL_ID", "").strip()
        enabled = flag(os.getenv("COLLECTION_ENABLED", "false"))
        posts = flag(os.getenv("DAILY_POST_ENABLED", "false"))
        token = os.getenv("BOT_TOKEN", "").strip()
        if posts and (not re.fullmatch(r"(?:@[A-Za-z][A-Za-z0-9_]{4,31}|-100\d{5,})", channel) or not token):
            raise ValueError("Kanalga yuborish uchun DAILY_CHANNEL_ID va BOT_TOKEN kerak")
        collection_interval = int(os.getenv("COLLECTION_INTERVAL_HOURS", "2"))
        if collection_interval not in (1, 2, 3, 4, 6, 8, 12, 24):
            raise ValueError("COLLECTION_INTERVAL_HOURS 1,2,3,4,6,8,12 yoki 24 bo‘lsin")
        return cls(
            enabled=enabled, post_enabled=posts, channel=channel,
            collection_interval_hours=collection_interval,
            hour=hour, minute=minute,
            max_items=max(1, min(10, int(os.getenv("DAILY_MAX_ITEMS", "10")))),
            interval_seconds=max(30, int(os.getenv("COLLECTION_POLL_SECONDS", "60"))),
            config_path=os.getenv("COLLECTION_CONFIG", cls.config_path), token=token,
        )


def is_due(now, settings):
    local = aware(now).astimezone(TASHKENT)
    return (local.hour, local.minute) >= (settings.hour, settings.minute)


def day_key(now, settings):
    local = aware(now).astimezone(TASHKENT)
    day = local.date().isoformat()
    destination = settings.channel if settings.post_enabled else "catalog"
    if settings.post_enabled:
        # Channel posts stay once a day, not 12 times daily.
        return f"{day}:{destination}", day, destination
    # A unique DB claim per two-hour wall-clock slot, in Tashkent time.
    slot = local.hour // settings.collection_interval_hours
    return f"{day}:slot-{slot:02d}:{destination}", day, destination


def claim_day(sessions, now, settings):
    """Commit the unique claim before external requests, without a long DB lock."""
    key, day, destination = day_key(now, settings)
    with sessions() as db:
        if db.bind.dialect.name == "postgresql":
            if not db.scalar(text("SELECT pg_try_advisory_xact_lock(74199202)")):
                return None, "busy"
        existing = db.scalar(select(DailyRun).where(DailyRun.run_key == key))
        if existing:
            if existing.status == "sending" and aware(existing.updated_at) < now - timedelta(minutes=5):
                existing.status, existing.error, existing.updated_at = "uncertain", "interrupted_delivery", now
                db.commit()
                return None, "uncertain"
            return None, existing.status
        row = DailyRun(run_key=key, day=day, destination=destination, status="collecting", created_at=now, updated_at=now)
        db.add(row)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return None, "claimed"
        return row.id, "collecting"


def set_state(sessions, run_id, status, now, **values):
    with sessions() as db:
        row = db.get(DailyRun, run_id)
        row.status, row.updated_at = status, now
        for key, value in values.items():
            setattr(row, key, value)
        db.commit()


def safe_offer_url(value, source):
    try:
        parsed = urlparse(value)
        return bool(
            parsed.scheme == "https" and parsed.hostname == SOURCE_HOSTS.get(source)
            and not parsed.username and not parsed.password and parsed.port in (None, 443)
            and len(value) <= 1000 and not any(ord(char) < 32 for char in value)
        )
    except (TypeError, ValueError):
        return False


def select_deals(db, product_ids, now, limit=10):
    """Choose fresh, new, accepted observations; unknown shipping stays unknown."""
    if not product_ids:
        return []
    rows = db.execute(
        select(Product, Offer, Store, Category)
        .join(Offer, Offer.product_id == Product.id)
        .join(Store, Store.id == Offer.store_id)
        .join(Category, Category.id == Product.category_id)
        .where(Product.id.in_(product_ids), Product.is_demo.is_(False), Offer.is_demo.is_(False), Offer.in_stock.is_(True), Category.active.is_(True))
    )
    by_product = {}
    for product, offer, store, category in rows:
        source = product.attributes.get("_source", "")
        if product.attributes.get("_condition") != "new" or not safe_offer_url(offer.url, source):
            continue
        if not now - timedelta(hours=48) <= aware(offer.updated_at) <= now + timedelta(minutes=5) or offer.price <= 0:
            continue
        price_data = product_summary(db, product)
        deal = {"product_id": product.id, "name": product.name, "price": offer.price,
                "store": store.name, "url": offer.url, "category": category.name,
                "category_id": category.id, "source": source,
                "image_url": product.image_url if safe_image_url(product.image_url) else None,
                "discount_percent": price_data["discount_percent"], "old_price": price_data["old_price"]}
        if product.id not in by_product or offer.price < by_product[product.id]["price"]:
            by_product[product.id] = deal
    categories = defaultdict(list)
    for deal in sorted(by_product.values(), key=lambda item: (-item["discount_percent"], item["price"], item["product_id"])):
        categories[deal["category_id"]].append(deal)
    keys = sorted(categories)
    if keys:
        offset = aware(now).astimezone(TASHKENT).date().toordinal() % len(keys)
        keys = keys[offset:] + keys[:offset]
    result = []
    # One per category first; remaining slots use the next cheapest in turn.
    while keys and len(result) < max(1, min(10, limit)):
        next_keys = []
        for key in keys:
            if len(result) >= max(1, min(10, limit)):
                break
            result.append(categories[key].pop(0))
            if categories[key]:
                next_keys.append(key)
        keys = next_keys
    return result


def telegram_units(value):
    return len(value.encode("utf-16-le")) // 2


def render_digest(deals, now):
    day = aware(now).astimezone(TASHKENT).strftime("%d.%m.%Y")
    title = f"🛍 <b>Kuzatilgan takliflar ichida arzonlari</b>\n{day} · yangi mahsulotlar\n"
    footer = "\nFaqat kuzatilgan takliflar. Yetkazish haqi alohida. Narx va holat — manba ma’lumoti. OLX’da o‘lchov birligi va minimal buyurtmani aniqlang."
    blocks = []
    for deal in deals[:10]:
        if not safe_offer_url(deal.get("url"), deal.get("source")):
            continue
        price = f"{int(deal['price']):,}".replace(",", " ")
        block = (
            f"\n<b>{escape(str(deal['name'])[:120])}</b>\n"
            f"{escape(str(deal['category'])[:50])} · {price} so‘m\n"
            f"{escape(str(deal['store'])[:40])} — "
            f'<a href="{escape(deal["url"], quote=True)}">Do‘konda ko‘rish</a>\n'
        )
        if telegram_units(title + "".join(blocks) + block + footer) <= 4000:
            blocks.append(block)
    return title + "".join(blocks) + footer if blocks else ""


class DeliveryError(Exception):
    def __init__(self, kind, ambiguous=True):
        super().__init__(kind)
        self.kind, self.ambiguous = kind, ambiguous


async def send_digest(token, channel, message):
    # HTTPX INFO logging includes URLs, and Telegram places the token in the URL.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    try:
        async with httpx.AsyncClient(verify=ssl.create_default_context(), timeout=25) as client:
            response = await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": channel, "text": message, "parse_mode": "HTML", "link_preview_options": {"is_disabled": True}},
            )
    except httpx.HTTPError as exc:
        raise DeliveryError(type(exc).__name__, ambiguous=True) from None
    if response.status_code >= 500:
        raise DeliveryError("telegram_server_error", ambiguous=True)
    if response.is_error:
        raise DeliveryError(f"telegram_http_{response.status_code}", ambiguous=False)
    try:
        body = response.json()
        if not body.get("ok"):
            raise DeliveryError("telegram_rejected", ambiguous=False)
        message_id = body["result"]["message_id"]
        if not isinstance(message_id, int) or message_id <= 0:
            raise ValueError()
        return message_id
    except (ValueError, KeyError, TypeError):
        raise DeliveryError("telegram_invalid_response", ambiguous=True) from None


async def run_cycle(settings, *, now=None, sessions=SessionLocal, collector=None, importer=None, publisher=None, dry_run=False, clock=None):
    now = aware(now or utcnow())
    if not settings.enabled and not dry_run:
        return {"status": "disabled"}
    if collector is None:
        from .collectors import collect_sources
        collector = collect_sources
    if dry_run:
        items, reports = await collector(settings.config_path)
        return {"status": "dry-run", "collected": len(items), "sources": reports}
    run_id, state = claim_day(sessions, now, settings)
    if run_id is None:
        return {"status": "skipped", "previous": state}
    try:
        log.warning("Catalog collecting source pages for %s", day_key(now, settings)[0])
        items, reports = await collector(settings.config_path)
        log.warning("Catalog collection completed: items=%d sources=%s", len(items), json.dumps(reports, ensure_ascii=True)[:1400])
        if importer is None:
            from .collection_ingest import import_observations
            importer = import_observations
        with sessions() as db:
            stats = importer(db, items)
            db.commit()
            completed_at = aware((clock or utcnow)())
            deals = select_deals(db, stats.get("product_ids", []), completed_at, settings.max_items)
        postable = [deal for deal in deals if safe_image_url(deal.get("image_url"))]
        message = render_digest(deals, completed_at)
        log.warning("Catalog import: imported=%d, selected=%d", stats.get("imported", 0), len(deals))
        state = "ready" if (message if publisher is not None or not settings.post_enabled else postable) else "empty"
        set_state(sessions, run_id, state, completed_at, item_count=len(postable) if settings.post_enabled and publisher is None else len(deals), message=message, source_report=reports)
    except Exception as exc:
        set_state(sessions, run_id, "failed", now, error=type(exc).__name__[:80])
        log.error("Daily collection failed: %s", type(exc).__name__)
        return {"status": "failed", "error": type(exc).__name__}
    result = {"status": state, "collected": len(items), "imported": stats.get("imported", 0), "selected": len(deals), "sources": reports}
    if not settings.post_enabled or state == "empty":
        return result
    if publisher is None:
        posted = []
        for deal in postable:
            set_state(sessions, run_id, "sending", aware((clock or utcnow)()), source_report=reports + [{"posted": posted}])
            try:
                message_id = await send_product_photo(settings.token, settings.channel, deal)
            except Exception as exc:
                ambiguous = not isinstance(exc, PhotoDeliveryError) or exc.ambiguous
                status = "uncertain" if ambiguous else "failed"
                error = exc.kind if isinstance(exc, PhotoDeliveryError) else type(exc).__name__
                set_state(sessions, run_id, status, utcnow(), error=error[:80], source_report=reports + [{"posted": posted}])
                log.error("Daily photo posts stopped after %d: %s", len(posted), error[:80])
                return {**result, "status": status, "posted": len(posted)}
            posted.append({"product_id": deal["product_id"], "message_id": message_id})
            set_state(sessions, run_id, "sending", utcnow(), telegram_message_id=message_id, source_report=reports + [{"posted": posted}])
        set_state(sessions, run_id, "sent", utcnow(), item_count=len(posted))
        return {**result, "status": "sent", "posted": len(posted)}
    set_state(sessions, run_id, "sending", aware((clock or utcnow)()))
    try:
        message_id = await publisher(settings.token, settings.channel, message)
    except Exception as exc:
        ambiguous = not isinstance(exc, DeliveryError) or exc.ambiguous
        state = "uncertain" if ambiguous else "failed"
        error = exc.kind if isinstance(exc, DeliveryError) else type(exc).__name__
        set_state(sessions, run_id, state, utcnow(), error=error[:80])
        log.error("Channel delivery requires review: %s", error[:80])
        return {**result, "status": state}
    set_state(sessions, run_id, "sent", utcnow(), telegram_message_id=message_id)
    return {**result, "status": "sent"}


async def serve(settings):
    previous = {}
    # The Mini App collector always runs in 2-hour slots. Channel posting,
    # when enabled separately, remains a once-daily job.
    catalog_settings = replace(settings, post_enabled=False)
    while True:
        for task, active_settings in (("catalog", catalog_settings), ("channel", settings)):
            if task == "channel" and (not settings.post_enabled or not is_due(utcnow(), settings)):
                continue
            slot_key = day_key(utcnow(), active_settings)[0]
            if previous.get(task, (None, None))[0] == slot_key:
                continue
            try:
                result = await run_cycle(active_settings)
                # Avoid excess log entries on each minute poll.
                log.warning("Catalog scheduler %s %s: %s", task, slot_key, json.dumps(result, ensure_ascii=True)[:1800])
                previous[task] = (slot_key, result.get("status"))
            except Exception:
                # Do not prevent a future slot from running on a transient failure.
                log.exception("Catalog scheduler failed for %s", slot_key)
                previous[task] = (slot_key, "failed")
        await asyncio.sleep(settings.interval_seconds)


def main():
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    parser = argparse.ArgumentParser(description="Kunlik katalog yig‘ish va kanalga bitta xulosa")
    parser.add_argument("--once", action="store_true", help="Jadval vaqtini kutmay, bir kunlik ishni bajaring")
    parser.add_argument("--dry-run", action="store_true", help="Manbalarni tekshirish: baza va Telegramga yozilmaydi")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    settings = DailySettings.from_env()
    if args.once or args.dry_run:
        result = asyncio.run(run_cycle(settings, dry_run=args.dry_run))
        print(json.dumps(result, ensure_ascii=True))
    elif not settings.enabled:
        log.info("COLLECTION_ENABLED=false; daily worker disabled")
    else:
        log.info("Daily worker ready")
        asyncio.run(serve(settings))


if __name__ == "__main__":
    main()
