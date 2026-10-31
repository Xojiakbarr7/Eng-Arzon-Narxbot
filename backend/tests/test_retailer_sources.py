import asyncio
from datetime import datetime, timezone

import httpx

from app.retailer_sources import collect_retailer, parse_idea, parse_texnomart

NOW = datetime(2026, 10, 31, tzinfo=timezone.utc)


def texnomart_response():
    return {"data": {"products": [
        {"id": 359853, "name": "Smartfon Vivo V70 FE 8/256GB Blue", "sale_price": 6111000,
         "old_price": 8900000,
         "store_count": 2, "availability": "available",
         "image": "https://mini-io-api.texnomart.uz/catalog/product/359853.webp"},
        {"id": 11, "name": "Installment only", "sale_price": 0, "axiom_monthly_price": "150 000 so'mdan"},
    ]}}


def idea_response():
    return {"products": [
        {"id": 1042, "name": "VCC 5252 Black", "title_name": "Samsung VCC 5252 Black changyutgichi",
         "category_id": 26, "current_price": 999000, "in_stock": 11,
         "url": "https://idea.uz/product/1042-samsung-vcc-5252-black-changyutgichi",
         "img": "https://api.idea.uz/storage/products/vacuum.jpg"},
        {"id": 9000, "title_name": "Other", "category_id": 999, "current_price": 1,
         "in_stock": 1, "url": "https://idea.uz/product/9000"},
    ]}


def test_texnomart_cash_not_installment_or_old_price():
    items = parse_texnomart(texnomart_response(), "elektronika", NOW)
    assert len(items) == 1
    assert items[0].price == 6111000 and items[0].in_stock
    assert items[0].source == "texnomart"
    assert items[0].url == "https://texnomart.uz/product/detail/359853/"
    assert items[0].image_url.startswith("https://mini-io-api.texnomart.uz/")

    no_stock = texnomart_response()
    no_stock["data"]["products"][0]["store_count"] = None
    no_stock["data"]["products"][0]["availability"] = "withManager"
    assert parse_texnomart(no_stock, "elektronika", NOW)[0].in_stock is False


def test_idea_product_uses_exact_link_current_price_and_category():
    items = parse_idea(idea_response(), NOW)
    assert len(items) == 1
    assert items[0].source == "idea"
    assert items[0].name == "Samsung VCC 5252 Black changyutgichi"
    assert items[0].price == 999000 and items[0].in_stock
    assert items[0].category_slug == "maishiy-texnika"
    assert items[0].url.startswith("https://idea.uz/product/")

    hostile = idea_response()
    hostile["products"][0]["url"] = "https://idea.uz.evil.example/product/1042"
    assert not parse_idea(hostile, NOW)


def test_public_rest_collects_only_after_robots_permission(monkeypatch):
    requests = []

    def serve(req):
        requests.append(str(req.url))
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /api/common/v1/search/result\n")
        return httpx.Response(200, json=texnomart_response())

    original = httpx.AsyncClient
    monkeypatch.setattr("app.retailer_sources.httpx.AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(serve), **kwargs))
    async def no_delay(_): pass
    monkeypatch.setattr("app.retailer_sources.asyncio.sleep", no_delay)
    items, report = asyncio.run(collect_retailer("texnomart", {"queries": ["smartfon"], "pages_per_query": 1}, delay=1))
    assert len(items) == 1 and report["items"] == 1 and report["pages"] == 1
    assert len(requests) == 2


def test_robots_disallow_prevents_any_api_request(monkeypatch):
    requests = []

    def serve(req):
        requests.append(str(req.url))
        return httpx.Response(200, text="User-agent: *\nDisallow: /api/\n")

    original = httpx.AsyncClient
    monkeypatch.setattr("app.retailer_sources.httpx.AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(serve), **kwargs))
    items, report = asyncio.run(collect_retailer("idea", {"queries": ["samsung"]}, delay=1))
    assert items == [] and report["errors"] == ["robots_denied"]
    assert len(requests) == 1


def test_api_throttle_does_not_attempt_other_queries(monkeypatch):
    requests = []

    def serve(req):
        requests.append(str(req.url))
        return httpx.Response(404) if req.url.path == "/robots.txt" else httpx.Response(429)

    original = httpx.AsyncClient
    monkeypatch.setattr("app.retailer_sources.httpx.AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(serve), **kwargs))
    async def no_delay(_): pass
    monkeypatch.setattr("app.retailer_sources.asyncio.sleep", no_delay)
    items, report = asyncio.run(collect_retailer("idea", {"queries": ["samsung", "artel"]}, delay=1))
    assert not items and report["errors"] == ["source_access_limited"]
    assert len(requests) == 2


def test_idea_imports_observed_offer_without_demo():
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session
    from app.db import Base
    from app.seed import seed_catalog
    from app.collection_ingest import import_observations
    from app.models import Product, Offer, Store

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        seed_catalog(db, False)
        result = import_observations(db, parse_idea(idea_response(), datetime.now(timezone.utc)))
        db.commit()
        assert result["imported"] == 1 and not result["errors"]
        product = db.get(Product, result["product_ids"][0])
        assert not product.is_demo and product.category_id
        offer = db.scalar(select(Offer).where(Offer.product_id == product.id))
        store = db.get(Store, offer.store_id)
        assert offer.price == 999000 and offer.in_stock
        assert store.slug == "idea" and offer.url.startswith("https://idea.uz/")
    engine.dispose()
