"""Conservative, rate-limited reader for public Olcha catalog listings.

Only fetch public unauthenticated JSON if the API host's robots.txt permits
it (or robots.txt returns 404/410 per RFC 9309). Never log in, rotate IPs,
retry blocks, solve challenges, or claim any unobserved product/price.
"""
import asyncio
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import re
from urllib.parse import urlparse

import httpx

from .collection_types import CollectedItem
from .collectors import USER_AGENT, robots_allowed, SourceUnavailable

API_HOST = "mobile.olcha.uz"
API_PATH = "/api/v2/products"
API_URL = f"https://{API_HOST}{API_PATH}"
CATEGORY_MAP = {
    "telefony": "elektronika",
    "televizory": "elektronika",
    "noutbuki": "elektronika",
    "konditsionery": "maishiy-texnika",
    "stiralnye-mashiny": "maishiy-texnika",
    "tekhnika-dlya-kukhni": "maishiy-texnika",
    "sporttovary": "sport",
    "krasota-i-zdorove": "gozallik",
    "avtomobilnye-aksessuary": "avto",
    "mebel": "uy-mebel",
    "mebel-1": "uy-mebel",
    "knigi": "kitob",
    "vse-dlya-remonta-i-stroitelstva": "qurilish",
    "podarki-i-suveniry": "uy-mebel",
}
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{2,180}$")
PER_PAGE = 20


def safe_price(raw):
    if isinstance(raw, bool) or raw is None:
        return None
    try:
        value = Decimal(str(raw).replace(" ", "").replace("\u00a0", ""))
        if value.is_finite() and value == value.to_integral_value() and 0 < value <= 10**12:
            return int(value)
    except (InvalidOperation, ValueError):
        pass
    return None


def parse_products(data, category, now):
    if category not in CATEGORY_MAP or not isinstance(data, dict):
        return []
    payload = data.get("data")
    if not isinstance(payload, dict) or not isinstance(payload.get("products"), list):
        return []
    output = []
    for item in payload["products"]:
        if not isinstance(item, dict):
            continue
        alias = item.get("alias")
        name = item.get("name_uz") or item.get("name_ru") or item.get("name")
        product_id = item.get("id")
        if not isinstance(alias, str) or not SLUG.fullmatch(alias):
            continue
        if not isinstance(name, str) or not 2 <= len(name.strip()) <= 200:
            continue
        if isinstance(product_id, bool) or not isinstance(product_id, int) or product_id <= 0:
            continue
        price = safe_price(item.get("discount_price")) or safe_price(item.get("total_price"))
        if price is None:
            continue
        image = item.get("main_image")
        image_parsed = urlparse(image) if isinstance(image, str) else None
        image_url = image if image_parsed and image_parsed.scheme == "https" and image_parsed.hostname in {"olcha.uz", "cdn.olcha.uz"} else None
        try:
            quantity = int(item.get("quantity") or 0)
        except (ValueError, TypeError):
            quantity = 0
        if quantity < 0:
            quantity = 0
        # A declared out-of-stock flag overrides a conflicting quantity.
        in_stock = quantity > 0 and item.get("out_of_stock") is not True
        output.append(CollectedItem(
            source="olcha", reference=str(product_id), name=name.strip(), price=price,
            url=f"https://olcha.uz/ru/product/view/{alias}",
            category_slug=CATEGORY_MAP[category], observed_at=now,
            in_stock=in_stock, brand="", model=name.strip()[:120],
            attributes={"Holat": "Yangi (do‘kon katalogi)", "Manba": "Olcha"},
            image_url=image_url,
        ))
    return output


async def collect_olcha(source_config, *, delay=2.0, max_items=100):
    report = {"source": "olcha", "pages": 0, "items": 0, "errors": [], "failed_paths": []}
    results = {}
    requested = source_config.get("categories", ["telefony"])
    if not isinstance(requested, list):
        requested = []
    categories = list(dict.fromkeys(slug for slug in requested if isinstance(slug, str) and slug in CATEGORY_MAP))[:20]
    pages_per_category = max(1, min(int(source_config.get("pages_per_category", 2)), 5))
    # A few expensive electronics must not crowd out books, sport or household goods.
    per_category_limit = max(1, max_items // max(1, len(categories)))
    delay = max(1.0, min(float(delay), 60.0))
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json", "Accept-Language": "uz", "clientmodel": "web"}
    async with httpx.AsyncClient(timeout=25, follow_redirects=False, headers=headers,
                                 limits=httpx.Limits(max_connections=1)) as client:
        try:
            robots = await client.get(f"https://{API_HOST}/robots.txt")
            if robots.status_code == 200:
                robots_text = robots.text[:250_000]
            elif robots.status_code in (404, 410):
                robots_text = ""
            else:
                report["errors"].append("source_access_limited" if robots.status_code in (401, 403, 429, 503) else f"robots_http_{robots.status_code}")
                return [], report
        except httpx.HTTPError:
            report["errors"].append("robots_unavailable")
            return [], report
        for category in categories:
            category_items = {}
            for page in range(1, pages_per_category + 1):
                if len(results) >= max_items:
                    break
                params = {"page": page, "per_page": PER_PAGE, "category": category}
                request_url = str(httpx.URL(API_URL, params=params))
                if not robots_allowed(robots_text, request_url):
                    report["errors"].append("robots_denied")
                    break
                await asyncio.sleep(delay)
                try:
                    async with client.stream("GET", API_URL, params=params) as response:
                        if response.status_code in (401, 403, 429, 503):
                            report["errors"].append("source_access_limited")
                            return list(results.values()), report
                        if response.status_code != 200:
                            report["errors"].append(f"products_http_{response.status_code}")
                            break
                        content = await response.aread()
                        if len(content) > 2_000_000:
                            report["errors"].append("products_too_large")
                            break
                        data = __import__("json").loads(content)
                    report["pages"] += 1
                    batch = parse_products(data, category, datetime.now(timezone.utc))
                    for item in batch:
                        category_items[item.reference] = item
                    if not batch:
                        break
                except (ValueError, TypeError, httpx.HTTPError):
                    report["errors"].append("products_unavailable_or_invalid")
                    break
            # Pick affordable observed listings first; keep every category represented.
            for item in sorted(category_items.values(), key=lambda x: (not x.in_stock, x.price, x.reference))[:per_category_limit]:
                if len(results) < max_items or item.reference in results:
                    results[item.reference] = item
    report["items"] = len(results)
    if not results and not report["errors"]:
        report["errors"].append("no_eligible_product_offers")
    return list(results.values()), report
