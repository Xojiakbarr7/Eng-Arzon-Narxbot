import asyncio
from datetime import datetime, timezone

import httpx

from app.olcha_source import parse_products, safe_price, collect_olcha


NOW = datetime(2026, 10, 30, tzinfo=timezone.utc)


def payload():
    return {
        "data": {"products": [
            {
                "id": 501,
                "alias": "smartfon-x-8-256gb",
                "name_uz": "Smartfon X 8/256GB",
                "discount_price": 1_500_000,
                "total_price": "1 600 000",
                "quantity": 5,
                "out_of_stock": False,
                "main_image": "https://olcha.uz/image/original/products/test.jpg",
            },
            {
                "id": 502, "alias": "bad-broken", "name_ru": "No price",
                "discount_price": "not-a-price", "total_price": None,
            },
        ], "paginator": {"last_page": 1}}
    }


def test_source_preserves_real_price_photo_and_direct_link():
    items = parse_products(payload(), "telefony", NOW)
    assert len(items) == 1
    product = items[0]
    assert product.source == "olcha"
    assert product.price == 1_500_000
    assert product.url == "https://olcha.uz/ru/product/view/smartfon-x-8-256gb"
    assert product.image_url == "https://olcha.uz/image/original/products/test.jpg"
    assert product.in_stock and product.condition == "new"
    assert safe_price(True) is None
    assert safe_price(-1) is None
    assert safe_price("1 500 000") == 1_500_000


def test_robots_denial_must_not_fetch_catalog(monkeypatch):
    calls = []
    def respond(req):
        calls.append(str(req.url))
        return httpx.Response(200, text="User-agent: *\nDisallow: /api/\n")
    async_client = httpx.AsyncClient
    monkeypatch.setattr("app.olcha_source.httpx.AsyncClient", lambda **kwargs: async_client(transport=httpx.MockTransport(respond), **kwargs))
    products, report = asyncio.run(collect_olcha({"categories": ["telefony"]}, delay=1))
    assert products == []
    assert report["errors"] == ["robots_denied"]
    assert len(calls) == 1


def test_public_catalog_cannot_be_faked_if_limited(monkeypatch):
    calls = []
    def respond(req):
        calls.append(str(req.url))
        if req.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(403, text="Access denied")
    async_client = httpx.AsyncClient
    monkeypatch.setattr("app.olcha_source.httpx.AsyncClient", lambda **kwargs: async_client(transport=httpx.MockTransport(respond), **kwargs))
    async def no_delay(_): return None
    monkeypatch.setattr("app.olcha_source.asyncio.sleep", no_delay)
    items, report = asyncio.run(collect_olcha({"categories": ["telefony"]}, delay=1))
    assert not items
    assert "source_access_limited" in report["errors"]
    assert len(calls) == 2


def test_olcha_public_json_is_importable_without_demo(monkeypatch):
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session
    from app.db import Base
    from app.seed import seed_catalog
    from app.collection_ingest import import_observations
    from app.models import Product, Offer
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        seed_catalog(db, False)
        r = import_observations(db, parse_products(payload(), "telefony", datetime.now(timezone.utc)))
        db.commit()
        assert r["imported"] == 1 and not r["errors"]
        product = db.get(Product, r["product_ids"][0])
        assert product.is_demo is False
        assert product.image_url and product.image_url.startswith("https://olcha.uz/")
        offer = db.scalar(select(Offer).where(Offer.product_id == product.id))
        assert offer.url.startswith("https://olcha.uz/ru/product/view/") and offer.price == 1_500_000
    engine.dispose()


def test_category_map_has_non_electronics_catalog_options():
    from app.olcha_source import CATEGORY_MAP
    assert CATEGORY_MAP["knigi"] == "kitob"
    assert CATEGORY_MAP["sporttovary"] == "sport"
    assert CATEGORY_MAP["mebel-1"] == "uy-mebel"
    assert CATEGORY_MAP["krasota-i-zdorove"] == "gozallik"
    assert CATEGORY_MAP["avtomobilnye-aksessuary"] == "avto"
    assert CATEGORY_MAP["vse-dlya-remonta-i-stroitelstva"] == "qurilish"


def test_bounded_collector_keeps_cheaper_goods_across_categories(monkeypatch):
    from app.olcha_source import CATEGORY_MAP
    categories = ["telefony", "knigi", "sporttovary"]
    requests = []

    def reply(request):
        requests.append(str(request.url))
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /api/v2/products\n")
        category = request.url.params["category"]
        page = int(request.url.params["page"])
        offset = categories.index(category) * 100 + page * 10
        items = [
            {
                "id": offset + i,
                "alias": f"product-{offset + i}",
                "name_uz": f"{category} mahsuloti {i}",
                "discount_price": (i + 1) * 100000,
                "quantity": 5,
                "main_image": "https://olcha.uz/image/original/products/test.jpg",
            }
            for i in range(4)
        ]
        return httpx.Response(200, json={"data": {"products": items}})

    real_client = httpx.AsyncClient
    monkeypatch.setattr("app.olcha_source.httpx.AsyncClient", lambda **kwargs: real_client(transport=httpx.MockTransport(reply), **kwargs))
    async def no_delay(_): pass
    monkeypatch.setattr("app.olcha_source.asyncio.sleep", no_delay)

    items, report = asyncio.run(collect_olcha(
        {"categories": categories, "pages_per_category": 2},
        delay=1, max_items=6,
    ))
    assert report["pages"] == 6 and report["items"] == 6
    assert len(items) == 6
    assert {item.category_slug for item in items} == {
        "elektronika", "kitob", "sport"
    }
    assert {item.price for item in items} == {100000, 200000}
    assert len(requests) == 7  # robots + two pages for each category
