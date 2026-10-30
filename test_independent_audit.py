"""Mustaqil tekshiruv: optimizatorni to‘liq sanash usuli bilan solishtiradi."""
from datetime import timedelta
from itertools import product as combinations
import hashlib
import hmac
import json
import random
import time
from urllib.parse import urlencode

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.config import get_settings
from app.models import Category, Product, Store, Offer, utcnow
from app.schemas import BasketItem
from app.security import validate_init_data
from app.services import optimize_basket, price_insight, validate_gtin


def test_exact_optimizer_matches_independent_exhaustive_oracle(monkeypatch):
    """Random narx, bepul yetkazish chegarasi, son va qoldiqlarni tekshiradi."""
    monkeypatch.setattr(get_settings(), "demo_mode", True)
    rng = random.Random(27102026)
    for scenario in range(32):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            db.add(Category(id=1, name="Test", slug="test"))
            db.flush()
            count = rng.randint(2, 4)
            quantities = [rng.randint(1, 3) for _ in range(count)]
            stores = []
            for sid in range(1, 4):
                store = Store(id=sid, name=f"S{sid}", slug=f"s{sid}", domain="asaxiy.uz", delivery_fee=rng.randint(0, 80), free_delivery_threshold=rng.choice([None, 100, 250]), is_demo=True)
                db.add(store)
                stores.append(store)
            db.flush()
            prices = {}
            for pid in range(1, count + 1):
                db.add(Product(id=pid, name=f"P{pid}", slug=f"p{pid}", brand="T", model=str(pid), category_id=1, is_demo=True))
            db.flush()
            for pid in range(1, count + 1):
                for sid in range(1, 4):
                    available = sid == 1 or rng.random() > 0.3
                    price = rng.randint(10, 160)
                    db.add(Offer(product_id=pid, store_id=sid, price=price, in_stock=available, is_demo=True, updated_at=utcnow()))
                    if available:
                        prices[pid, sid] = price
            db.commit()
            best = float("inf")
            for assignment in combinations(range(1, 4), repeat=count):
                if any((i + 1, sid) not in prices for i, sid in enumerate(assignment)):
                    continue
                subtotals = {}
                for i, sid in enumerate(assignment):
                    subtotals[sid] = subtotals.get(sid, 0) + prices[i + 1, sid] * quantities[i]
                cost = sum(subtotals.values())
                for sid, subtotal in subtotals.items():
                    store = stores[sid - 1]
                    cost += 0 if store.free_delivery_threshold and subtotal >= store.free_delivery_threshold else store.delivery_fee
                best = min(best, cost)
            result = optimize_basket(db, [BasketItem(product_id=i + 1, quantity=q) for i, q in enumerate(quantities)], "tashkent")
            assert result["total"] == best, f"scenario {scenario}"
            assert result["total"] == result["subtotal"] + result["delivery_total"]
            assert len({s["store_id"] for s in result["stores"]}) == len(result["stores"])
            assert sum(i["quantity"] for i in result["items"]) == sum(quantities)
        engine.dispose()


def signed_data(data, token="test-token"):
    encoded = {k: json.dumps(v, separators=(",", ":")) if isinstance(v, (dict, list)) else str(v) for k, v in data.items()}
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    check = "\n".join(f"{key}={value}" for key, value in sorted(encoded.items()))
    encoded["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(encoded)


def test_telegram_signature_tampering_expiry_and_duplicate_fields():
    valid = signed_data({"auth_date": int(time.time()), "user": {"id": 123, "first_name": "Test"}, "signature": "telegram-signature"})
    assert validate_init_data(valid, "test-token")["id"] == 123
    with pytest.raises(ValueError):
        validate_init_data(valid.replace("auth_date=", "auth_date=1"), "test-token")
    with pytest.raises(ValueError):
        validate_init_data(valid + "&auth_date=1", "test-token")
    for stamp in [int(time.time()) - 7200, int(time.time()) + 120]:
        with pytest.raises(ValueError):
            validate_init_data(signed_data({"auth_date": stamp, "user": {"id": 123}}), "test-token")


@pytest.mark.parametrize("code", ["96385074", "036000291452", "6291041500213", "06291041500213"])
def test_gs1_check_digit_known_vectors(code):
    assert validate_gtin(code) == code
    with pytest.raises(ValueError):
        validate_gtin(code[:-1] + str((int(code[-1]) + 1) % 10))


def test_repeated_same_day_samples_cannot_create_enough_history():
    today = utcnow().date()
    # The history service is responsible for daily aggregation; sparse observations
    # must remain insufficient and must never invent unobserved days.
    history = [{"date": (today - timedelta(days=i)).isoformat(), "price": 100, "is_demo": False} for i in [1, 2, 3]]
    assert price_insight(history, 50)["verdict"] == "insufficient"
    assert price_insight([], None)["sample_count"] == 0


def test_advice_compares_observed_prices_without_forecasting():
    today = utcnow().date()
    history = [{"date": (today - timedelta(days=i)).isoformat(), "price": 100, "is_demo": False} for i in range(30, 0, -1)]
    assert price_insight(history, 80)["verdict"] == "buy"
    assert price_insight(history, 120)["verdict"] == "wait"
    assert price_insight(history, 100)["verdict"] == "neutral"
    assert price_insight(history, 80, True)["is_demo"] is True
