"""Small, permission-aware readers for public Texnomart and IDEA search catalogues.

Only anonymous GET requests to fixed HTTPS hosts/paths; robots rules are checked
for the API host before requesting product data. Never bypass rate limits,
redirects, access denials, CAPTCHAs, or use installment prices as cash prices.
"""
import asyncio
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx

from .collection_types import CollectedItem
from .collectors import USER_AGENT, robots_allowed
from .olcha_source import safe_price

SOURCES = {
    "texnomart": {
        "host": "gw.texnomart.uz", "path": "/api/common/v1/search/result",
        "categories": {
            "smartfon": "elektronika", "noutbuk": "elektronika",
            "televizor": "elektronika", "konditsioner": "maishiy-texnika",
            "muzlatgich": "maishiy-texnika", "kir yuvish": "maishiy-texnika",
            "changyutgich": "maishiy-texnika", "blender": "maishiy-texnika",
        },
    },
    "idea": {
        "host": "api.idea.uz", "path": "/api/v2/search",
        "categories": {
            "samsung": None, "artel": None, "televizor": None,
            "muzlatgich": None, "konditsioner": None, "changyutgich": None,
            "kir yuvish": None, "duxovka": None,
        },
    },
}
# Observational IDEA category IDs. Unknown categories are excluded rather
# than labeled as a wrong product type.
IDEA_CATEGORIES = {
    55: "elektronika", 9: "elektronika", 73: "elektronika",
    15: "maishiy-texnika", 24: "maishiy-texnika",
    26: "maishiy-texnika", 131: "maishiy-texnika",
    132: "maishiy-texnika", 23: "maishiy-texnika",
    179: "maishiy-texnika", 107: "maishiy-texnika",
    17: "maishiy-texnika",
}
IMAGE_HOSTS = {
    "texnomart": frozenset({"mini-io-api.texnomart.uz", "texnomart.uz", "www.texnomart.uz"}),
    "idea": frozenset({"api.idea.uz", "idea.uz", "www.idea.uz"}),
}


def image_url(value, source):
    if not isinstance(value, str) or len(value) > 1000:
        return None
    try:
        p = urlparse(value)
        if p.scheme == "https" and p.hostname in IMAGE_HOSTS[source] and not p.username and not p.password and p.port in (None, 443):
            return value
    except ValueError:
        pass
    return None


def parse_texnomart(payload, category, now):
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
        return []
    products = payload["data"].get("products")
    if not isinstance(products, list):
        return []
    results = []
    for entry in products:
        if not isinstance(entry, dict):
            continue
        ident = entry.get("id")
        name = entry.get("name")
        price = safe_price(entry.get("sale_price"))
        if type(ident) is not int or ident < 1 or not isinstance(name, str) or not 2 <= len(name.strip()) <= 200 or price is None:
            continue
        # withManager means call the operator; it is NOT confirmed in stock.
        availability = entry.get("availability")
        stock = entry.get("store_count")
        confirmed = (
            isinstance(stock, int) and not isinstance(stock, bool) and stock > 0
        ) or availability in ("inStock", "in_stock", "available")
        results.append(CollectedItem(
            source="texnomart", reference=str(ident), name=name.strip(),
            price=price, url=f"https://texnomart.uz/product/detail/{ident}/",
            category_slug=category, observed_at=now, in_stock=bool(confirmed),
            model=name.strip()[:120],
            attributes={"Mavjudlik": "Tasdiqlangan" if confirmed else "Do‘konda tekshiring"},
            image_url=image_url(entry.get("image"), "texnomart"),
        ))
    return results


def parse_idea(payload, now):
    if not isinstance(payload, dict) or not isinstance(payload.get("products"), list):
        return []
    results = []
    for entry in payload["products"]:
        if not isinstance(entry, dict):
            continue
        ident, url = entry.get("id"), entry.get("url")
        name = entry.get("title_name") or entry.get("name")
        price = safe_price(entry.get("current_price"))
        try:
            parsed = urlparse(url) if isinstance(url, str) else None
            valid_url = bool(parsed and parsed.scheme == "https" and parsed.hostname in ("idea.uz", "www.idea.uz")
                and parsed.path.startswith("/product/") and not parsed.username and not parsed.password and parsed.port in (None, 443))
        except ValueError:
            valid_url = False
        category = IDEA_CATEGORIES.get(entry.get("category_id"))
        if type(ident) is not int or ident < 1 or not valid_url or not isinstance(name, str) or not 2 <= len(name.strip()) <= 200 or price is None or not category:
            continue
        stock = entry.get("in_stock")
        confirmed = (type(stock) is int and stock > 0) or (stock is True)
        results.append(CollectedItem(
            source="idea", reference=str(ident), name=name.strip(),
            price=price, url=url, category_slug=category, observed_at=now,
            in_stock=confirmed, model=name.strip()[:120],
            attributes={"Mavjudlik": "Tasdiqlangan" if confirmed else "Do‘konda tekshiring"},
            image_url=image_url(entry.get("img"), "idea"),
        ))
    return results


async def collect_retailer(source, source_config, *, delay=2, max_items=420):
    spec = SOURCES[source]
    host, path = spec["host"], spec["path"]
    report = {"source": source, "pages": 0, "items": 0, "errors": [], "failed_paths": []}
    items = {}
    requested = source_config.get("queries")
    if not isinstance(requested, list):
        requested = list(spec["categories"])
    queries = list(dict.fromkeys(q for q in requested
                 if isinstance(q, str) and q in spec["categories"]))[:10]
    pages = max(1, min(int(source_config.get("pages_per_query", 1)), 3))
    delay = max(1.0, min(float(delay), 60.0))
    url = f"https://{host}{path}"
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json", "Accept-Language": "uz"}
    if source == "texnomart":
        headers.update({"accept-device": "web", "accept-region": "2"})
    async with httpx.AsyncClient(timeout=25, follow_redirects=False, headers=headers,
                                 limits=httpx.Limits(max_connections=1)) as client:
        try:
            robots = await client.get(f"https://{host}/robots.txt")
            if robots.status_code == 200:
                if len(robots.content) > 250_000:
                    report["errors"].append("robots_too_large")
                    return [], report
                rules = robots.text
            elif robots.status_code in (404, 410):
                rules = ""
            else:
                report["errors"].append("source_access_limited" if robots.status_code in (401, 403, 429, 503) else "robots_unavailable")
                return [], report
        except httpx.HTTPError:
            report["errors"].append("robots_unavailable")
            return [], report
        if not robots_allowed(rules, url):
            report["errors"].append("robots_denied")
            return [], report
        for query in queries:
            for page in range(1, pages + 1 if source == "texnomart" else 2):
                if len(items) >= max_items:
                    break
                params = (
                    {"q": query, "page": page, "limit": 20}
                    if source == "texnomart" else
                    {"search": query, "quantity": 50, "type[]": ["shops", "products"]}
                )
                request_url = str(httpx.URL(url, params=params))
                if not robots_allowed(rules, request_url):
                    report["errors"].append("robots_denied")
                    break
                await asyncio.sleep(delay)
                try:
                    async with client.stream("GET", url, params=params) as response:
                        if response.status_code in (401, 403, 429, 503):
                            report["errors"].append("source_access_limited")
                            report["items"] = len(items)
                            return list(items.values()), report
                        if source == "idea" and response.status_code == 404:
                            continue
                        if response.status_code != 200:
                            report["errors"].append(f"source_http_{response.status_code}")
                            break
                        body = await response.aread()
                        if len(body) > 2_000_000:
                            report["errors"].append("response_too_large")
                            break
                        payload = __import__("json").loads(body)
                    if not isinstance(payload, dict):
                        raise ValueError("invalid_payload")
                    report["pages"] += 1
                    batch = (parse_texnomart(payload, spec["categories"][query], datetime.now(timezone.utc))
                             if source == "texnomart" else parse_idea(payload, datetime.now(timezone.utc)))
                    if not batch and source == "texnomart":
                        break
                    for item in batch:
                        if len(items) < max_items or item.reference in items:
                            items[item.reference] = item
                except (ValueError, TypeError, httpx.HTTPError):
                    report["errors"].append("products_unavailable_or_invalid")
                    break
    report["items"] = len(items)
    if not items and not report["errors"]:
        report["errors"].append("no_eligible_product_offers")
    return list(items.values()), report
