"""Kalitsiz MVP uchun ajratilgan SQLite integration testlari."""
import csv
import io
from datetime import timedelta
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app import main
from app.config import get_settings
from app.db import Base, get_db
from app.models import Product, Offer, PriceHistory, PriceAlert, NotificationHistory, User, utcnow
from app.seed import demo_barcode
from app.services import history_for


@pytest.fixture
def ctx(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    @event.listens_for(engine, "connect")
    def fk(connection, _): connection.execute("PRAGMA foreign_keys=ON")
    sessions = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main, "SessionLocal", sessions)
    settings = get_settings()
    monkeypatch.setattr(settings, "demo_mode", True)
    monkeypatch.setattr(settings, "admin_token", "test-admin-token-very-long-secret")
    monkeypatch.setattr(settings, "bot_internal_token", "test-internal-token")
    monkeypatch.setattr(settings, "bot_token", "test-bot-token")
    monkeypatch.setattr(settings, "rate_limit_per_minute", 10000)
    main.rate_windows.clear()
    def override():
        with sessions() as db: yield db
    main.app.dependency_overrides[get_db] = override
    with TestClient(main.app) as client:
        yield client, sessions
    main.app.dependency_overrides.clear()
    engine.dispose()


ADMIN = {"Authorization": "Bearer test-admin-token-very-long-secret"}
BOT = {"X-Bot-Token": "test-internal-token", "X-Telegram-User-Id": "1001"}


def create_real(client):
    body = {"name": "Real canonical test 128GB", "slug": "real-canonical-128", "brand": "Test", "model": "X128", "category_id": 1, "attributes": {"Xotira": "128GB"}}
    response = client.post("/api/admin/products", json=body, headers=ADMIN)
    assert response.status_code == 201
    return response.json()["id"]


def test_catalog_demo_labels_variant_identity_and_filters(ctx):
    client, _ = ctx
    assert client.get("/api/health").json()["demo_mode"]
    result = client.get("/api/products", params={"q": "samsung a55"}).json()
    assert len(result["items"]) == 2
    assert {p["attributes"]["Xotira"] for p in result["items"]} == {"128 GB", "256 GB"}
    assert all(p["is_demo"] for p in result["items"])
    assert client.get("/api/products", params={"q": "самсунг"}).json()["total"] == 2
    result = client.get("/api/products", params={"category": "kitob", "max_price": 100000}).json()
    assert result["total"] == 1
    assert client.get("/api/products", params={"min_price": 100, "max_price": 1}).status_code == 422
    detail = client.get("/api/products/1").json()
    assert all(o["is_demo"] and o["url"] is None for o in detail["offers"])
    assert all(h["is_demo"] for h in detail["history"])


def test_barcode_checksum_and_gtin_padding(ctx):
    client, _ = ctx
    code = demo_barcode(3)
    assert client.get("/api/barcode/" + code).json()["id"] == 3
    assert client.get("/api/barcode/" + code.zfill(14)).json()["id"] == 3
    assert client.get("/api/barcode/12345").status_code == 422
    bad = code[:-1] + str((int(code[-1]) + 1) % 10)
    assert client.get("/api/barcode/" + bad).status_code == 422
    assert client.get("/api/barcode/6291041500213").status_code == 404


def test_favorites_and_alerts_are_owned_and_persistent(ctx):
    client, _ = ctx
    assert client.post("/api/favorites/1").status_code == 200
    assert client.post("/api/favorites/1").status_code == 200
    assert len(client.get("/api/favorites").json()) == 1
    response = client.post("/api/alerts", json={"product_id": 1, "target_price": 12000000})
    alert_id = response.json()["id"]
    assert client.get("/api/favorites", headers=BOT).json() == []
    assert client.get("/api/alerts", headers=BOT).json() == []
    assert client.patch(f"/api/alerts/{alert_id}", json={"enabled": False}, headers=BOT).status_code == 404
    assert client.patch(f"/api/alerts/{alert_id}", json={"enabled": False}).json()["enabled"] is False
    assert client.delete("/api/favorites/1").status_code == 200
    assert client.get("/api/favorites").json() == []


def test_profile_deletion_cascades_personal_data(ctx):
    client, sessions = ctx
    client.get("/api/products?q=samsung")
    client.post("/api/favorites/1")
    client.post("/api/alerts", json={"product_id": 1, "target_price": 1000})
    assert client.delete("/api/profile").status_code == 200
    assert client.get("/api/favorites").json() == []
    assert client.get("/api/alerts").json() == []
    assert client.get("/api/profile/search-history").json() == []


def test_profile_settings_validate_and_persist(ctx):
    client, _ = ctx
    values = {"language": "ru", "region": "navoiy", "notifications_enabled": False}
    assert client.patch("/api/profile", json=values).status_code == 200
    profile = client.get("/api/profile").json()
    assert all(profile[key] == value for key, value in values.items())
    assert client.patch("/api/profile", json={"region": "unknown"}).status_code == 422
    assert client.patch("/api/profile", json={"language": "unknown"}).status_code == 422


def test_production_rejects_short_internal_secret():
    from app.config import Settings
    with pytest.raises(ValueError, match="BOT_INTERNAL_TOKEN"):
        Settings(app_env="production", demo_mode=False, bot_token="test-token", admin_token="a" * 32, bot_internal_token="short")


def test_basket_excludes_out_of_stock_and_stale(ctx):
    client, sessions = ctx
    with sessions() as db:
        for offer in db.scalars(select(Offer).where(Offer.product_id == 1)):
            offer.in_stock = False
        db.commit()
    response = client.post("/api/basket/optimize", json={"items": [{"product_id": 1, "quantity": 1}]})
    assert response.status_code == 409
    assert response.json()["detail"]["unavailable"]
    assert client.post("/api/basket/optimize", json={"items": []}).status_code == 422
    assert client.post("/api/basket/optimize", json={"items": [{"product_id": 2, "quantity": 1}], "region": "unknown"}).status_code == 422


def test_statistics_do_not_invent_unobserved_days(ctx):
    client, sessions = ctx
    pid = create_real(client)
    with sessions() as db:
        for minute in range(40):
            db.add(PriceHistory(product_id=pid, store_id=1, price=100000 + minute, observed_at=utcnow() - timedelta(minutes=minute), is_demo=False))
        db.commit()
        history = history_for(db, pid)
        assert len(history) <= 2
    detail = client.get(f"/api/products/{pid}").json()
    assert detail["insight"]["verdict"] == "insufficient"


def test_admin_auth_csv_atomic_validation_and_real_provenance(ctx):
    client, sessions = ctx
    assert client.get("/api/admin/stats").status_code == 401
    pid = create_real(client)
    assert client.put("/api/admin/stores/1", json={"delivery_fee": 15000, "free_delivery_threshold": 500000, "adapter_status": "csv"}, headers=ADMIN).status_code == 200
    good = f"product_id,store_id,price,currency,in_stock,url\n{pid},1,199000,UZS,true,https://uzum.uz/uz/product/test\n"
    preview = client.post("/api/admin/import", json={"csv_text": good}, headers=ADMIN).json()
    assert preview["ok"] and not preview["committed"]
    assert client.get(f"/api/products/{pid}").json()["offers"] == []
    invalid = good + f"{pid},1,200000,UZS,true,https://evil.test/\n"
    response = client.post("/api/admin/import", json={"csv_text": invalid, "commit": True}, headers=ADMIN).json()
    assert not response["ok"] and not response["committed"]
    assert client.get(f"/api/products/{pid}").json()["offers"] == []
    response = client.post("/api/admin/import", json={"csv_text": good, "commit": True}, headers=ADMIN).json()
    assert response["committed"]
    detail = client.get(f"/api/products/{pid}").json()
    assert detail["is_demo"] is False
    assert detail["offers"][0]["is_demo"] is False
    assert detail["insight"]["verdict"] == "insufficient"
    assert detail["offers"][0]["total_price"] == 214000
    assert client.patch("/api/profile", json={"region": "andijan"}).status_code == 200
    regional_detail = client.get(f"/api/products/{pid}").json()
    assert regional_detail["offers"][0]["delivery_fee"] is None
    assert regional_detail["offers"][0]["total_price"] is None
    assert regional_detail["offers"][0]["shipping_notice"]
    assert client.get("/api/products?sort=total_price").status_code == 200
    assert client.post("/api/basket/optimize", json={"items": [{"product_id": pid, "quantity": 1}], "region": "andijan"}).status_code == 409


def test_demo_import_cannot_turn_fake_data_into_live_data(ctx):
    client, _ = ctx
    csv_text = "product_id,store_id,price,currency,in_stock,url\n1,1,100000,UZS,true,https://uzum.uz/product/test\n"
    response = client.post("/api/admin/import", json={"csv_text": csv_text, "commit": True}, headers=ADMIN).json()
    assert not response["committed"]
    assert "Demo" in response["errors"][0]["message"]


def test_truncated_csv_is_validation_error_not_server_error(ctx):
    client, _ = ctx
    pid = create_real(client)
    client.put("/api/admin/stores/1", json={"delivery_fee": 15000}, headers=ADMIN)
    text = f"product_id,store_id,price,currency,in_stock,url\n{pid},1,100000,UZS\n"
    response = client.post("/api/admin/import", json={"csv_text": text, "commit": True}, headers=ADMIN)
    assert response.status_code == 200
    assert response.json()["ok"] is False and response.json()["committed"] is False


def test_internal_bot_auth_cannot_be_spoofed(ctx):
    client, _ = ctx
    assert client.get("/api/profile", headers={"X-Telegram-User-Id": "1001"}).status_code == 401
    assert client.get("/api/profile", headers={"X-Bot-Token": "wrong", "X-Telegram-User-Id": "1001"}).status_code == 401
    assert client.get("/api/profile", headers=BOT).json()["telegram_id"] == "1001"
    assert client.post("/api/internal/notifications/claim").status_code == 401


def test_malformed_signed_telegram_user_returns_401(ctx):
    client, _ = ctx
    for user in ([], True, {"id": True}, {"id": -1}):
        pairs = {"auth_date": str(int(time.time())), "user": json.dumps(user)}
        secret = hmac.new(b"WebAppData", b"test-bot-token", hashlib.sha256).digest()
        check = "\n".join(f"{key}={value}" for key, value in sorted(pairs.items()))
        pairs["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
        assert client.get("/api/profile", headers={"X-Telegram-Init-Data": urlencode(pairs)}).status_code == 401


def test_assistant_decimal_budget_stays_within_budget(ctx):
    client, _ = ctx
    response = client.post("/api/assistant", json={"message": "3.5 milliongacha telefon"}).json()
    assert response["mode"] == "statistical"
    assert all(p["min_price"] <= 3500000 for p in response["products"])
    assert "generativ AI ulanmagan" in response["notice"]


def test_notifications_skip_demo_and_deduplicate_real_alert(ctx):
    client, sessions = ctx
    client.post("/api/alerts", json={"product_id": 1, "target_price": 999999999}, headers=BOT)
    internal = {"X-Bot-Token": "test-internal-token"}
    assert client.post("/api/internal/notifications/claim", headers=internal).json()["items"] == []
    pid = create_real(client)
    with sessions() as db:
        db.add(Offer(product_id=pid, store_id=1, price=100000, is_demo=False, updated_at=utcnow()))
        db.commit()
    client.post("/api/alerts", json={"product_id": pid, "target_price": 200000}, headers=BOT)
    items = client.post("/api/internal/notifications/claim", headers=internal).json()["items"]
    assert len(items) == 1 and items[0]["user_id"] == 1001
    assert client.post("/api/internal/notifications/claim", headers=internal).json()["items"] == []
    assert client.post(f"/api/internal/notifications/{items[0]['id']}/ack", headers=internal, json={"delivered": True}).status_code == 200
    assert client.post("/api/internal/notifications/claim", headers=internal).json()["items"] == []
