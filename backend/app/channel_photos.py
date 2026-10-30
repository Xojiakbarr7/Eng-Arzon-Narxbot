"""Individual photo publications. Real source images only; never generate a fake product photo."""
import ipaddress
import logging
import ssl
from html import escape
from urllib.parse import urlparse

import httpx


def safe_image_url(value):
    if not isinstance(value, str) or len(value) > 1000 or any(ord(ch) < 32 for ch in value):
        return False
    try:
        parsed = urlparse(value)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None, 443):
            return False
        host = parsed.hostname.lower()
        if host in {"localhost", "metadata.google.internal"} or host.endswith((".local", ".internal", ".localhost")):
            return False
        try:
            return ipaddress.ip_address(host).is_global
        except ValueError:
            return "." in host and not host.startswith(".") and not host.endswith(".")
    except (TypeError, ValueError):
        return False


def photo_caption(deal):
    from .daily_worker import safe_offer_url
    if not safe_offer_url(deal.get("url"), deal.get("source")) or not safe_image_url(deal.get("image_url")):
        raise ValueError("A real HTTPS photo and validated shop link are required")
    name = escape(str(deal["name"])[:120])
    store = escape(str(deal["store"])[:60])
    category = escape(str(deal["category"])[:60])
    price = f"{int(deal['price']):,}".replace(",", " ")
    discount = int(deal.get("discount_percent") or 0)
    old = int(deal.get("old_price") or 0)
    discount_line = ""
    if discount > 0 and old > int(deal["price"]):
        discount_line = f"\n📉 <b>{discount}% arzonlashgan</b> · oldin {old:,} so‘m".replace(",", " ")
    url = escape(deal["url"], quote=True)
    return (
        f"🛍 <b>{name}</b>\n"
        f"💰 <b>{price} so‘m</b>{discount_line}\n"
        f"🏪 {store} · {category}\n"
        f'🔗 <a href="{url}">Mahsulotni do‘kondan olish</a>\n'
        "Narx kuzatilgan vaqtda amal qilgan. Yetkazish va holatni do‘konda tekshiring."
    )


class PhotoDeliveryError(Exception):
    def __init__(self, kind, ambiguous=True):
        super().__init__(kind)
        self.kind, self.ambiguous = kind, ambiguous


async def send_product_photo(token, channel, deal):
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    caption = photo_caption(deal)
    try:
        async with httpx.AsyncClient(verify=ssl.create_default_context(), timeout=35) as client:
            response = await client.post(
                f"https://api.telegram.org/bot{token}/sendPhoto",
                json={
                    "chat_id": channel,
                    "photo": deal["image_url"],
                    "caption": caption,
                    "parse_mode": "HTML",
                    "reply_markup": {"inline_keyboard": [[{
                        "text": f"🛒 {str(deal['store'])[:35]}dan olish",
                        "url": deal["url"],
                    }]]},
                },
            )
    except httpx.HTTPError as exc:
        raise PhotoDeliveryError(type(exc).__name__, ambiguous=True) from None
    if response.status_code >= 500:
        raise PhotoDeliveryError("telegram_server_error", ambiguous=True)
    if response.is_error:
        raise PhotoDeliveryError(f"telegram_http_{response.status_code}", ambiguous=False)
    try:
        body = response.json()
        if not body.get("ok"):
            raise PhotoDeliveryError("telegram_rejected", ambiguous=False)
        message_id = body["result"]["message_id"]
        if type(message_id) is not int or message_id < 1:
            raise ValueError("message_id")
        return message_id
    except (ValueError, KeyError, TypeError):
        raise PhotoDeliveryError("telegram_invalid_response", ambiguous=True) from None
