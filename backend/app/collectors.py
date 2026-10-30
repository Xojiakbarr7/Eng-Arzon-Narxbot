"""Bounded collection of public structured offers, without private API calls."""
import asyncio
from collections import deque
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import ssl
from urllib.parse import urljoin, urlparse, parse_qsl, urlencode, urlunparse

import httpx

from .collection_types import CollectedItem

USER_AGENT = "EngArzonBot/1.0 (+public-price-monitor)"
HOSTS = {"asaxiy": "asaxiy.uz", "uzum": "uzum.uz", "olx": "www.olx.uz"}
OLX_GOODS = {"elektronika", "detskiy-mir", "dom-i-sad", "moda-i-stil", "hobbi-otdyh-i-sport"}
USED_WORDS = re.compile(r"ishlatilgan|ishlatil[gd]an|\bb/u\b|б[ /]?у\b|подержан|пользован|запчаст|ehtiyot\s*qism|nosoz|неисправ|remont\s*talab", re.I)


def public_url(source, value):
    parsed = urlparse(str(value))
    if source not in HOSTS or parsed.scheme != "https" or parsed.hostname != HOSTS[source] or parsed.username or parsed.password:
        raise ValueError("Manbaning o‘z HTTPS domeni kerak")
    try:
        if parsed.port not in (None, 443): raise ValueError("HTTPS porti kerak")
    except ValueError:
        raise ValueError("URL porti noto‘g‘ri") from None
    path = parsed.path
    if source == "asaxiy": allowed = path in ("/product", "/uz/product") or path.startswith(("/product/", "/uz/product/"))
    elif source == "uzum": allowed = path.startswith(("/uz/category/", "/ru/category/", "/uz/product/", "/ru/product/"))
    else: allowed = path.startswith("/d/obyavlenie/") or path.strip("/").split("/")[0] in OLX_GOODS
    query = parse_qsl(parsed.query, keep_blank_values=True)
    if not allowed or any(key not in {"page", "currentPage", "skuId"} for key, _ in query):
        raise ValueError("Faqat ochiq katalog/mahsulot yo‘li kerak")
    return urlunparse(("https", HOSTS[source], path, "", urlencode(query), ""))


class StructuredPage(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.documents, self.next_urls, self._parts = [], [], None
        self.breadcrumbs, self._in_breadcrumb = [], False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "nav" and attrs.get("aria-label", "").lower() == "breadcrumb": self._in_breadcrumb = True
        if self._in_breadcrumb and tag == "a" and attrs.get("href"): self.breadcrumbs.append(attrs["href"])
        if tag == "script" and attrs.get("type", "").lower() == "application/ld+json": self._parts = []
        if tag in ("a", "link") and "next" in attrs.get("rel", "").split() and attrs.get("href"):
            self.next_urls.append(attrs["href"])

    def handle_data(self, data):
        if self._parts is not None: self._parts.append(data)

    def handle_endtag(self, tag):
        if tag == "nav": self._in_breadcrumb = False
        if tag == "script" and self._parts is not None:
            try: self.documents.append(json.loads("".join(self._parts)))
            except (ValueError, TypeError): pass
            self._parts = None


def nodes(value):
    if isinstance(value, list):
        for item in value: yield from nodes(item)
    elif isinstance(value, dict):
        yield value
        # Only explicit JSON-LD graph/list entries, never reviews or recommendations.
        for key in ("@graph", "itemListElement", "item"):
            if key in value: yield from nodes(value[key])


def kind(node, expected):
    value = node.get("@type")
    return value == expected or isinstance(value, list) and expected in value


def scalar_name(value):
    return str(value.get("name", "")) if isinstance(value, dict) else str(value or "")


def asaxiy_category(breadcrumbs, page_url, fallback):
    roots = {"telefony-i-gadzhety": "elektronika", "kompyutery-i-orgtehnika": "elektronika",
             "televizory-video-i-audio": "elektronika", "bytovaya-tehnika": "maishiy-texnika",
             "klimaticheskaya-tehnika": "maishiy-texnika", "mebel": "uy-mebel", "dlya-doma": "uy-mebel",
             "posuda": "uy-mebel", "odejda-obuv-i-aksessuari": "kiyim", "futbolki": "kiyim",
             "jenskie-futbolki": "kiyim", "krasota-i-zdorove": "gozallik", "detskiye-tovari": "bolalar",
             "sport-i-otdyh": "sport", "knigi": "kitob", "kancelyarskie-tovary": "kitob",
             "kofe-i-chay": "kundalik", "suvi": "kundalik"}
    result = fallback
    for value in breadcrumbs:
        parsed = urlparse(urljoin(page_url, value))
        if parsed.hostname != HOSTS["asaxiy"]: continue
        parts = parsed.path.strip("/").split("/")
        if parts and parts[0] == "uz": parts = parts[1:]
        if len(parts) < 2 or parts[0] != "product": continue
        if parts[1] in roots: result = roots[parts[1]]
        elif parts[1] == "instrumenty-i-avtotovary":
            detail = "/".join(parts[2:])
            result = "avto" if any(word in detail for word in ("avto", "shiny", "akkumul", "kolesnye")) else "qurilish"
    return result


def observation(source, product, offer, category, now):
    if not kind(offer, "Offer") or str(offer.get("itemCondition", "")).rsplit("/", 1)[-1] != "NewCondition": return None
    name = str(product.get("name") or offer.get("name") or "").strip()
    if not 2 <= len(name) <= 200 or USED_WORDS.search(name): return None
    if offer.get("priceCurrency") != "UZS": return None
    try:
        price = Decimal(str(offer["price"]))
        if not price.is_finite() or price != price.to_integral_value() or not 0 < price <= 10**12: return None
        url = public_url(source, offer.get("url") or product.get("url"))
    except (KeyError, ValueError, InvalidOperation): return None
    if source == "olx" and not urlparse(url).path.startswith("/d/obyavlenie/"): return None
    if source == "uzum" and "/product/" not in urlparse(url).path: return None
    expiry = offer.get("priceValidUntil")
    if expiry:
        try:
            until = datetime.fromisoformat(str(expiry).replace("Z", "+00:00"))
            if (until.replace(tzinfo=timezone.utc) if until.tzinfo is None else until) < now: return None
        except ValueError: return None
    image = product.get("image") or offer.get("image")
    if isinstance(image, list): image = image[0] if image else None
    if isinstance(image, dict): image = image.get("url")
    barcode = next((str(product[k]) for k in ("gtin14", "gtin13", "gtin12", "gtin8", "gtin") if product.get(k)), None)
    available = str(offer.get("availability", "")).rsplit("/", 1)[-1]
    if available not in ("InStock", "OutOfStock", "SoldOut", "Discontinued"): return None
    attrs = {"Holat": "Yangi (manba ma’lumoti)"}
    area = offer.get("areaServed")
    if isinstance(area, dict) and area.get("name"): attrs["Hudud"] = str(area["name"])[:120]
    reference = url
    sku = str(product.get("sku") or "").strip()
    if source == "asaxiy" and sku and len(sku) <= 100:
        reference = "sku:" + sku
    elif source == "olx":
        listing_id = re.search(r"-ID([A-Za-z0-9]+)\.html$", urlparse(url).path)
        if listing_id: reference = "listing:" + listing_id.group(1)
    elif source == "uzum":
        sku_ids = [value for key, value in parse_qsl(urlparse(url).query) if key == "skuId"]
        if len(sku_ids) == 1 and sku_ids[0].isdigit(): reference = "sku:" + sku_ids[0]
    if isinstance(image, str) and image.strip():
        image = urljoin(url, image.strip())
    else:
        image = None
    return CollectedItem(source=source, reference=reference, name=name, price=int(price), url=url, category_slug=category,
                         observed_at=now, in_stock=available == "InStock", brand=scalar_name(product.get("brand"))[:80],
                         model=str(product.get("model") or product.get("mpn") or "")[:120], attributes=attrs,
                         barcode=barcode, image_url=image if image and urlparse(image).scheme == "https" else None)


def parse_page(source, html, page_url, category, now=None):
    now = now or datetime.now(timezone.utc)
    parser = StructuredPage(); parser.feed(html)
    if source == "asaxiy": category = asaxiy_category(parser.breadcrumbs, page_url, category)
    items, links = [], []
    for document in parser.documents:
        for node in nodes(document):
            if kind(node, "Product"):
                offers = node.get("offers", [])
                offers = offers if isinstance(offers, list) else [offers]
                if len(offers) > 1 and source != "olx": continue
                for offer in offers:
                    if not isinstance(offer, dict): continue
                    if source == "olx" and kind(offer, "AggregateOffer"):
                        for entry in offer.get("offers", []):
                            # Each listing is its own product; the category lowPrice is never imported.
                            if isinstance(entry, dict):
                                item = observation(source, entry, entry, category, now)
                                if item: items.append(item)
                    elif kind(offer, "Offer"):
                        item = observation(source, node, offer, category, now)
                        if item: items.append(item)
            if kind(node, "ItemList"):
                for entry in node.get("itemListElement", []):
                    if isinstance(entry, dict) and kind(entry, "ListItem") and entry.get("url"): links.append(entry["url"])
    links += [urljoin(page_url, value) for value in parser.next_urls]
    return items, links


def robots_allowed(text, url):
    """Longest-match Allow/Disallow, including the wildcard rules these stores use."""
    groups, agents, rules = [], [], []
    for raw in text.splitlines() + ["User-agent: __end__"]:
        line = raw.split("#", 1)[0].strip()
        if ":" not in line: continue
        key, value = (part.strip() for part in line.split(":", 1))
        if key.lower() == "user-agent":
            if rules:
                groups.append((agents, rules)); agents, rules = [], []
            agents.append(value.lower())
        elif key.lower() in ("allow", "disallow") and agents and value:
            rules.append((key.lower() == "allow", value))
    matches = [(len(agent) if agent != "*" else 0, group_rules) for group_agents, group_rules in groups
               for agent in group_agents if agent == "*" or agent in USER_AGENT.lower()]
    if not matches: return True
    specificity = max(score for score, _ in matches)
    parsed = urlparse(url); target = parsed.path + ("?" + parsed.query if parsed.query else "")
    candidates = []
    for score, group_rules in matches:
        if score != specificity: continue
        for allow, pattern in group_rules:
            end = pattern.endswith("$")
            pattern = pattern[:-1] if end else pattern
            regex = "^" + ".*".join(re.escape(part) for part in pattern.split("*")) + ("$" if end else "")
            if re.search(regex, target): candidates.append((len(pattern.replace("*", "")), allow))
    return max(candidates, default=(0, True))[1]


class SourceUnavailable(RuntimeError):
    pass


async def read_limited(client, url):
    async with client.stream("GET", url) as response:
        if response.status_code in (401, 403, 429, 503): raise SourceUnavailable("Manba kirishni chekladi")
        if response.status_code != 200: raise ValueError(f"HTTP {response.status_code}")
        body = bytearray()
        async for part in response.aiter_bytes():
            body.extend(part)
            if len(body) > 3_000_000: raise ValueError("Sahifa 3 MB limitidan katta")
        return body.decode("utf-8", errors="replace")


async def collect_sources(config_path):
    config = json.loads(Path(config_path).read_text(encoding="utf-8-sig"))
    limit = max(1, min(int(config.get("max_pages_per_source", 40)), 200))
    item_limit = max(1, min(int(config.get("max_items_per_source", 200)), 1000))
    delay = max(1.0, min(float(config.get("request_delay_seconds", 2)), 60))
    results, reports = [], []
    async with httpx.AsyncClient(verify=ssl.create_default_context(), timeout=25, follow_redirects=False,
                                 headers={"User-Agent": USER_AGENT}, limits=httpx.Limits(max_connections=2)) as client:
        for source_config in config.get("sources", []):
            source = source_config.get("source")
            if source not in HOSTS or not source_config.get("enabled", False): continue
            report = {"source": source, "pages": 0, "items": 0, "errors": [], "failed_paths": []}
            try:
                robots = await read_limited(client, f"https://{HOSTS[source]}/robots.txt")
                seeds = source_config.get("seeds", [])
                # Rotate the category order daily so bounded coverage is shared.
                if seeds:
                    offset = datetime.now(timezone.utc).date().toordinal() % len(seeds)
                    seeds = seeds[offset:] + seeds[:offset]
                queues, seen, accepted, priorities = [], set(), {}, {}
                for seed in seeds:
                    url = public_url(source, seed["url"])
                    queues.append(deque([(url, seed["category"], len(urlparse(url).path.strip("/").split("/")))]))
                while any(queues) and report["pages"] < limit and len(accepted) < item_limit:
                    for queue in queues:
                        if not queue or report["pages"] >= limit or len(accepted) >= item_limit: continue
                        url, category, priority = queue.popleft()
                        if url in seen: continue
                        seen.add(url)
                        if not robots_allowed(robots, url):
                            report["errors"].append("robots_denied"); continue
                        await asyncio.sleep(delay)
                        report["pages"] += 1
                        try:
                            html = await read_limited(client, url)
                            items, links = parse_page(source, html, url, category)
                            for item in items:
                                if (item.reference in accepted or len(accepted) < item_limit) and priority >= priorities.get(item.reference, -1):
                                    accepted[item.reference] = item
                                    priorities[item.reference] = priority
                            if source_config.get("discover", True):
                                for link in links[:100]:
                                    try: next_url = public_url(source, urljoin(url, link))
                                    except ValueError: continue
                                    if next_url not in seen and len(queue) < 200: queue.append((next_url, category, priority))
                        except (httpx.HTTPError, ValueError):
                            report["errors"].append("page_fetch_failed")
                            if len(report["failed_paths"]) < 20: report["failed_paths"].append(urlparse(url).path)
                results.extend(accepted.values()); report["items"] = len(accepted)
                if not accepted: report["errors"].append("no_structured_new_offers")
            except (httpx.HTTPError, ValueError, KeyError, TypeError, SourceUnavailable) as exc:
                # Report only the safe error class/code, not response contents or URLs.
                reason = "source_unavailable_or_invalid_config"
                if isinstance(exc, SourceUnavailable):
                    reason = "source_access_limited"
                elif isinstance(exc, ValueError) and str(exc).startswith("HTTP "):
                    code = str(exc).split(" ", 1)[1]
                    if code.isdecimal():
                        reason = "source_http_" + code
                elif isinstance(exc, httpx.ConnectError):
                    reason = "source_connection_failed"
                elif isinstance(exc, httpx.TimeoutException):
                    reason = "source_timed_out"
                elif isinstance(exc, httpx.HTTPError):
                    reason = "source_network_error"
                report["errors"].append(reason)
            reports.append(report)
    return results, reports
