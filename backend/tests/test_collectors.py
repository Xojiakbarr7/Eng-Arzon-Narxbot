import asyncio
from datetime import datetime, timezone
import json

import httpx
import pytest

from app.collectors import parse_page, public_url, robots_allowed, collect_sources

NOW = datetime(2026, 10, 29, 6, tzinfo=timezone.utc)


def html(value):
    return '<script type="application/ld+json">' + json.dumps(value) + '</script>'


def offer(**changes):
    return {"@type": "Offer", "name": "Test 128 GB Gray", "price": "2000000", "priceCurrency": "UZS",
            "itemCondition": "https://schema.org/NewCondition", "availability": "https://schema.org/InStock",
            "url": "https://asaxiy.uz/product/test-128-gray", **changes}


def test_main_cash_offer_is_not_installment_related_price_or_aggregate_minimum():
    product = {"@type": "Product", "name": "Test 128 GB Gray", "sku": "test-128", "offers": offer()}
    page = '<span>Oylik 200000</span><aside>Qo‘shimcha 10000</aside>' + html(product)
    items, _ = parse_page("asaxiy", page, offer()["url"], "elektronika", NOW)
    assert len(items) == 1 and items[0].price == 2_000_000
    assert items[0].name == "Test 128 GB Gray"
    product["offers"] = {"@type": "AggregateOffer", "lowPrice": 10000, "priceCurrency": "UZS"}
    assert parse_page("asaxiy", html(product), offer()["url"], "elektronika", NOW)[0] == []
    product["offers"] = [offer(), offer(price=3000000)]
    assert parse_page("asaxiy", html(product), offer()["url"], "elektronika", NOW)[0] == []


def test_olx_new_listings_only_not_category_lowprice_or_contradictory_used_title():
    entries = [offer(url="https://www.olx.uz/d/obyavlenie/new-ID1.html"),
               offer(url="https://www.olx.uz/d/obyavlenie/used-ID2.html", itemCondition="https://schema.org/UsedCondition"),
               offer(url="https://www.olx.uz/d/obyavlenie/lie-ID3.html", name="Kam ishlatilgan telefon"),
               offer(url="https://www.olx.uz/d/obyavlenie/unknown-ID4.html", itemCondition=""),
               offer(url="https://www.olx.uz/d/obyavlenie/usd-ID5.html", priceCurrency="USD")]
    product = {"@type": "Product", "name": "Elektronika", "offers": {"@type": "AggregateOffer", "lowPrice": 1, "offers": entries}}
    items, _ = parse_page("olx", html(product), "https://www.olx.uz/elektronika/", "elektronika", NOW)
    assert len(items) == 1 and items[0].name != "Elektronika"
    assert items[0].price == 2_000_000


@pytest.mark.parametrize("changes", [{"price": 0}, {"price": "NaN"}, {"price": "1.5"}, {"availability": ""},
    {"priceCurrency": "USD"}, {"url": "https://asaxiy.uz.evil.example/product/x"},
    {"priceValidUntil": "2020-01-01"}, {"name": "Nosoz telefon"}])
def test_invalid_or_expired_offers_are_not_imported(changes):
    value = offer(**changes)
    product = {"@type": "Product", "name": value["name"], "offers": value}
    assert parse_page("asaxiy", html(product), offer()["url"], "elektronika", NOW)[0] == []


def test_robots_wildcards_longest_allow_and_private_paths():
    rules = "User-agent: *\nAllow: /product/super-price$\nDisallow: /*price\nDisallow: /ajax/\n"
    assert robots_allowed(rules, "https://asaxiy.uz/product/super-price")
    assert not robots_allowed(rules, "https://asaxiy.uz/product/phone?price=1")
    assert not robots_allowed(rules, "https://asaxiy.uz/ajax/list")
    for url in ("https://asaxiy.uz/ajax/test", "http://asaxiy.uz/product/x", "https://asaxiy.uz/product?key=test"):
        with pytest.raises(ValueError): public_url("asaxiy", url)


def test_item_list_discovery_uses_product_links_not_arbitrary_anchor():
    page = html({"@type": "ItemList", "itemListElement": [{"@type": "ListItem", "url": offer()["url"]}]})
    breadcrumb = html({"@type": "BreadcrumbList", "itemListElement": [{"@type": "ListItem", "url": "https://asaxiy.uz/product/knigi"}]})
    items, links = parse_page("asaxiy", page + breadcrumb + '<a href="https://evil.example/">Other</a>', "https://asaxiy.uz/product", "elektronika", NOW)
    assert items == [] and links == [offer()["url"]]


def test_same_sku_keeps_identity_when_title_url_or_locale_changes():
    product = {"@type": "Product", "sku": "test-128", "name": "Phone 128 GB", "offers": offer()}
    first = parse_page("asaxiy", html(product), offer()["url"], "elektronika", NOW)[0][0]
    product["offers"]["url"] = "https://asaxiy.uz/uz/product/new-title-128"
    second = parse_page("asaxiy", html(product), product["offers"]["url"], "elektronika", NOW)[0][0]
    assert first.reference == second.reference == "sku:test-128"


def test_product_breadcrumb_overrides_broad_listing_category():
    product = {"@type": "Product", "name": "Test product", "offers": offer()}
    crumbs = '<nav aria-label="breadcrumb"><a href="/product/posuda/termokrujki">Idishlar</a></nav>'
    items, _ = parse_page("asaxiy", crumbs + html(product), offer()["url"], "kundalik", NOW)
    assert items[0].category_slug == "uy-mebel"
    crumbs = '<nav aria-label="breadcrumb"><a href="/product/instrumenty-i-avtotovary/payalnye-instrumenty">Asboblar</a></nav>'
    items, _ = parse_page("asaxiy", crumbs + html(product), offer()["url"], "avto", NOW)
    assert items[0].category_slug == "qurilish"


def test_collector_stops_source_on_throttle_without_bypassing(monkeypatch, tmp_path):
    path = tmp_path / "sources.json"
    path.write_text(json.dumps({"sources": [{"source": "asaxiy", "enabled": True, "seeds": [
        {"url": "https://asaxiy.uz/product", "category": "elektronika"},
        {"url": "https://asaxiy.uz/product/other", "category": "elektronika"}]}]}), encoding="utf-8")
    calls = []
    def respond(request):
        calls.append(str(request.url))
        return httpx.Response(200, text="User-agent: *\nAllow: /\n") if request.url.path == "/robots.txt" else httpx.Response(429)
    real_client = httpx.AsyncClient
    monkeypatch.setattr("app.collectors.httpx.AsyncClient", lambda **kwargs: real_client(transport=httpx.MockTransport(respond), **kwargs))
    async def no_sleep(_): pass
    monkeypatch.setattr("app.collectors.asyncio.sleep", no_sleep)
    items, reports = asyncio.run(collect_sources(str(path)))
    assert items == [] and len(calls) == 2
    assert reports[0]["errors"] == ["source_access_limited"]


def test_more_specific_category_wins_for_same_listing(monkeypatch, tmp_path):
    path = tmp_path / "categories.json"
    path.write_text(json.dumps({"sources": [{"source": "olx", "enabled": True, "discover": False, "seeds": [
        {"url": "https://www.olx.uz/dom-i-sad/", "category": "uy-mebel"},
        {"url": "https://www.olx.uz/dom-i-sad/tovari-dlya-stroitelstva-remonta/", "category": "qurilish"}]}]}), encoding="utf-8")
    entry = offer(url="https://www.olx.uz/d/obyavlenie/material-IDabc123.html")
    page = html({"@type": "Product", "name": "Category", "offers": {"@type": "AggregateOffer", "offers": [entry]}})
    def respond(request):
        return httpx.Response(200, text="User-agent: *\nAllow: /\n" if request.url.path == "/robots.txt" else page)
    real_client = httpx.AsyncClient
    monkeypatch.setattr("app.collectors.httpx.AsyncClient", lambda **kwargs: real_client(transport=httpx.MockTransport(respond), **kwargs))
    async def no_sleep(_): pass
    monkeypatch.setattr("app.collectors.asyncio.sleep", no_sleep)
    items, _ = asyncio.run(collect_sources(str(path)))
    assert len(items) == 1 and items[0].category_slug == "qurilish"
