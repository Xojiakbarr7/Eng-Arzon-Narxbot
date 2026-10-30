from dataclasses import replace
from datetime import timedelta
from hashlib import sha256

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from app.collection_ingest import import_observations
from app.collection_types import CollectedItem
from app.db import Base
from app.models import Offer, PriceHistory, Product, Store, utcnow
from app.schemas import BasketItem
from app.seed import seed_catalog
from app.services import aware, optimize_basket, product_detail


@pytest.fixture
def db():
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_catalog(session, False)
        yield session
    engine.dispose()


def observed(**changes):
    item = CollectedItem(source="asaxiy", reference="test-128-gray", name="Phone X 128 GB Gray",
                         price=2_000_000, url="https://asaxiy.uz/product/test-phone-128-gray",
                         category_slug="elektronika", observed_at=utcnow(),
                         brand="Test", model="Phone X", attributes={"Xotira": "128 GB", "Rang": "Gray"})
    return replace(item, **changes)


def count(db, model):
    return db.scalar(select(func.count()).select_from(model))


def test_reimport_updates_price_without_duplicate_products_or_same_day_history(db):
    item = observed()
    first = import_observations(db, [item])
    db.commit()
    assert first["imported"] == 1
    assert import_observations(db, [item])["product_ids"] == first["product_ids"]
    db.commit()
    assert count(db, Product) == count(db, Offer) == count(db, PriceHistory) == 1
    assert db.get(Product, first["product_ids"][0]).attributes["_condition"] == "new"
    changed = replace(item, price=1_900_000, observed_at=item.observed_at + timedelta(seconds=1))
    import_observations(db, [changed])
    db.commit()
    assert count(db, Product) == count(db, Offer) == 1
    assert count(db, PriceHistory) == 2
    assert db.scalar(select(Offer)).price == 1_900_000


def test_similar_titles_and_other_store_never_merge_variant_identity(db):
    a = observed()
    b = replace(a, reference="test-256-gray", name="Phone X 256 GB Gray", attributes={"Xotira": "256 GB"})
    c = replace(a, source="uzum", url="https://uzum.uz/uz/product/test-phone", reference="uzum-123")
    result = import_observations(db, [a, b, c])
    db.commit()
    assert result["imported"] == 3
    assert len(set(result["product_ids"])) == count(db, Product) == 3
    assert count(db, Offer) == 3
    assert len({p.slug for p in db.scalars(select(Product))}) == 3


def test_rejected_or_older_observations_do_not_refresh_existing_offer(db):
    item = observed()
    import_observations(db, [item])
    db.commit()
    bad = [replace(item, condition="used"), replace(item, condition="unknown"),
           replace(item, price=True), replace(item, price=0), replace(item, price=10**12 + 1),
           replace(item, reference=None), replace(item, category_slug="does-not-exist"),
           replace(item, observed_at=utcnow() - timedelta(hours=49)),
           replace(item, observed_at=utcnow() + timedelta(minutes=6)),
           replace(item, observed_at=utcnow().replace(tzinfo=None)),
           replace(item, observed_at=item.observed_at - timedelta(seconds=1)),
           replace(item, url="https://asaxiy.uz.evil.example/product/phone"),
           replace(item, url="https://asaxiy.uz@evil.example/product/phone"),
           replace(item, url="https://asaxiy.uz:444/product/phone"),
           replace(item, url="https://user:pass@asaxiy.uz/product/phone")]
    result = import_observations(db, bad)
    db.commit()
    assert result["skipped"] == len(bad) and result["imported"] == 0
    assert count(db, Product) == count(db, Offer) == count(db, PriceHistory) == 1
    offer = db.scalar(select(Offer))
    assert aware(offer.updated_at) == item.observed_at
    assert offer.price == item.price


def test_real_prices_are_visible_but_basket_waits_for_confirmed_shipping(db):
    item = observed(source="olx", url="https://www.olx.uz/d/obyavlenie/test-ID123.html")
    pid = import_observations(db, [item])["product_ids"][0]
    db.commit()
    product = db.get(Product, pid)
    detail = product_detail(db, product)
    assert detail["min_price"] == item.price and not detail["is_demo"]
    assert detail["offers"][0]["delivery_fee"] is None
    assert detail["offers"][0]["shipping_notice"]
    with pytest.raises(HTTPException, match="yetkazish haqi tasdiqlanmagan"):
        optimize_basket(db, [BasketItem(product_id=pid)], "tashkent")
    store = db.scalar(select(Store).where(Store.slug == "olx"))
    store.is_demo, store.delivery_fee = False, 12_000
    db.commit()
    assert optimize_basket(db, [BasketItem(product_id=pid)], "tashkent")["total"] == item.price + 12_000


def test_caller_can_rollback_and_demo_records_cannot_be_replaced(db):
    item = observed()
    import_observations(db, [item])
    db.rollback()
    assert count(db, Product) == count(db, Offer) == count(db, PriceHistory) == 0
    slug = "asaxiy-" + sha256(item.reference.encode()).hexdigest()[:24]
    demo = Product(name="Demo item", slug=slug, brand="Demo", model="Demo", category_id=1, is_demo=True)
    db.add(demo)
    db.commit()
    result = import_observations(db, [item])
    db.commit()
    assert result["skipped"] == 1 and count(db, Offer) == 0
    assert db.get(Product, demo.id).name == "Demo item" and demo.is_demo


@pytest.mark.parametrize("incoming_barcode", [None, "123", "2000000000022"])
def test_refresh_preserves_manual_gtin_and_absent_variant_attributes(db, incoming_barcode):
    item = observed(attributes={"Rang": "Gray"})
    pid = import_observations(db, [item])["product_ids"][0]
    product = db.get(Product, pid)
    product.barcode = "6291041500213"
    product.attributes = {**product.attributes, "Xotira": "128 GB", "Rang": "Old Gray",
                          "_condition": "edited", "_reference": "edited"}
    other = Product(name="Other variant", slug="other-variant", brand="Test", model="Other",
                    category_id=product.category_id, barcode="2000000000022", is_demo=False)
    db.add(other)
    db.commit()
    refreshed = replace(item, barcode=incoming_barcode, observed_at=utcnow(),
                        attributes={"Rang": "Gray", "Quvvat": "18 W"})
    assert import_observations(db, [refreshed])["imported"] == 1
    db.commit()
    assert product.barcode == "6291041500213"
    assert product.attributes["Xotira"] == "128 GB"
    assert product.attributes["Rang"] == "Gray"
    assert product.attributes["Quvvat"] == "18 W"
    assert product.attributes["_condition"] == "new"
    assert product.attributes["_reference"] == item.reference
