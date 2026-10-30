import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.daily_worker import DailySettings, DeliveryError, claim_day, day_key, is_due, render_digest, run_cycle, select_deals, telegram_units
from app.models import Category, DailyRun, Offer, Product, Store


NOW = datetime(2026, 10, 29, 4, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def worker_clock(monkeypatch):
    monkeypatch.setattr("app.daily_worker.utcnow", lambda: NOW)


@pytest.fixture
def sessions():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as db:
        db.add(Category(id=1, name="Elektronika", slug="elektronika"))
        db.add(Category(id=2, name="Kitob", slug="kitob"))
        db.add(Store(id=1, name="Asaxiy", slug="asaxiy", domain="asaxiy.uz", is_demo=True))
        db.commit()
    yield factory
    engine.dispose()


def add_offer(db, number, *, category=1, price=100, condition="new", demo=False, age=0, stock=True, url=None):
    product = Product(name=f"Product {number}", slug=f"product-{number}", brand="T", model=str(number), category_id=category,
                      attributes={"_condition": condition, "_source": "asaxiy"}, is_demo=demo)
    db.add(product)
    db.flush()
    db.add(Offer(product_id=product.id, store_id=1, price=price, url=url or f"https://asaxiy.uz/product/item-{number}",
                 in_stock=stock, is_demo=demo, updated_at=NOW - timedelta(hours=age)))
    db.flush()
    return product.id


def test_schedule_and_persistent_key_follow_tashkent_not_utc():
    settings = DailySettings()
    assert not is_due(NOW - timedelta(seconds=1), settings)
    assert is_due(NOW, settings)
    assert day_key(datetime(2026, 10, 29, 23, tzinfo=timezone.utc), settings)[1] == "2026-10-30"


def test_only_current_accepted_new_fresh_real_offers_are_selected(sessions):
    with sessions() as db:
        good = add_offer(db, 1, price=200)
        cheap = add_offer(db, 2, price=100)
        book = add_offer(db, 3, category=2, price=30)
        rejected = [add_offer(db, 4, condition="used"), add_offer(db, 5, demo=True), add_offer(db, 6, age=49),
                    add_offer(db, 7, stock=False), add_offer(db, 8, url="https://asaxiy.uz.attacker.com/product/x")]
        add_offer(db, 9, price=1)  # Not accepted in this run: never posted.
        db.commit()
        deals = select_deals(db, [good, cheap, book, *rejected], NOW, limit=3)
        assert {deal["product_id"] for deal in deals} == {good, cheap, book}
        assert {deal["product_id"] for deal in deals[:2]} == {cheap, book}


def test_digest_escapes_untrusted_titles_and_respects_telegram_limit():
    deal = {"name": '<b>Injected & title</b>', "category": "Phone & book", "store": 'A < B', "price": 150000,
            "url": "https://asaxiy.uz/product/" + "x" * 900, "source": "asaxiy"}
    message = render_digest([deal] * 10, NOW)
    assert "&lt;b&gt;Injected &amp; title&lt;/b&gt;" in message
    assert "<b>Injected" not in message
    assert telegram_units(message) <= 4000
    assert "Yetkazish haqi alohida" in message
    assert 1 <= message.count("Do‘konda ko‘rish") < 10


def test_dry_run_never_opens_database_or_sends_even_when_disabled():
    async def collector(_):
        return [object()], [{"source": "asaxiy", "count": 1}]

    def forbidden_session():
        raise AssertionError("dry-run touched database")

    async def forbidden_publisher(*args):
        raise AssertionError("dry-run sent Telegram message")

    result = asyncio.run(run_cycle(DailySettings(), sessions=forbidden_session, collector=collector, publisher=forbidden_publisher, dry_run=True))
    assert result["status"] == "dry-run"
    assert result["collected"] == 1


def test_success_is_not_recollected_or_reposted_after_restart(sessions):
    sent, collected = [], []

    async def collector(_):
        collected.append(True)
        return [object()], [{"source": "asaxiy", "count": 1}]

    def importer(db, _):
        product_id = add_offer(db, 1)
        return {"imported": 1, "skipped": 0, "product_ids": [product_id]}

    async def publisher(token, channel, message):
        with sessions() as db:
            assert db.scalar(select(DailyRun)).status == "sending"
        sent.append(message)
        return 456

    settings = DailySettings(enabled=True, post_enabled=True, channel="@mychannel", token="test-only")
    first = asyncio.run(run_cycle(settings, now=NOW, sessions=sessions, collector=collector, importer=importer, publisher=publisher))
    second = asyncio.run(run_cycle(settings, now=NOW + timedelta(minutes=1), sessions=sessions, collector=collector, importer=importer, publisher=publisher))
    assert first["status"] == "sent"
    assert second == {"status": "skipped", "previous": "sent"}
    assert len(sent) == len(collected) == 1
    with sessions() as db:
        row = db.scalar(select(DailyRun))
        assert row.telegram_message_id == 456


def test_timeout_is_uncertain_and_is_never_automatically_retried(sessions):
    async def collector(_):
        return [object()], []

    def importer(db, _):
        return {"imported": 1, "product_ids": [add_offer(db, 1)]}

    async def publisher(*_):
        raise DeliveryError("ReadTimeout", ambiguous=True)

    settings = DailySettings(enabled=True, post_enabled=True, channel="@mychannel", token="test-only")
    first = asyncio.run(run_cycle(settings, now=NOW, sessions=sessions, collector=collector, importer=importer, publisher=publisher))
    second = asyncio.run(run_cycle(settings, now=NOW + timedelta(minutes=2), sessions=sessions, collector=collector, importer=importer, publisher=publisher))
    assert first["status"] == "uncertain"
    assert second == {"status": "skipped", "previous": "uncertain"}


def test_interrupted_sending_claim_is_recorded_without_resending(sessions):
    settings = DailySettings(enabled=True, post_enabled=True, channel="@mychannel")
    key, day, target = day_key(NOW, settings)
    with sessions() as db:
        db.add(DailyRun(run_key=key, day=day, destination=target, status="sending", updated_at=NOW - timedelta(minutes=10)))
        db.commit()
    assert claim_day(sessions, NOW, settings) == (None, "uncertain")


def test_collection_failure_does_not_send_old_catalog(sessions):
    async def collector(_):
        return [], [{"source": "asaxiy", "error": "HTTPError"}]

    with sessions() as db:
        add_offer(db, 1)
        db.commit()

    def importer(db, _):
        return {"imported": 0, "product_ids": []}

    async def publisher(*_):
        raise AssertionError("old catalog was published")

    settings = DailySettings(enabled=True, post_enabled=True, channel="@mychannel", token="test-only")
    result = asyncio.run(run_cycle(settings, now=NOW, sessions=sessions, collector=collector, importer=importer, publisher=publisher))
    assert result["status"] == "empty"


def test_env_requires_channel_for_posts_and_bounds_batch(monkeypatch):
    monkeypatch.setenv("DAILY_POST_ENABLED", "true")
    monkeypatch.setenv("DAILY_CHANNEL_ID", "")
    with pytest.raises(ValueError, match="DAILY_CHANNEL_ID"):
        DailySettings.from_env()
    monkeypatch.setenv("DAILY_CHANNEL_ID", "@mychannel")
    monkeypatch.setenv("BOT_TOKEN", "test-only")
    monkeypatch.setenv("DAILY_MAX_ITEMS", "500")
    monkeypatch.setenv("COLLECTION_POLL_SECONDS", "1")
    settings = DailySettings.from_env()
    assert settings.max_items == 10
    assert settings.interval_seconds == 30


def test_slow_collection_uses_completion_clock_for_freshness(sessions):
    completed = NOW + timedelta(minutes=10)
    async def collector(_):
        return [object()], []
    def importer(db, _):
        pid = add_offer(db, 1)
        db.scalar(select(Offer).where(Offer.product_id == pid)).updated_at = completed
        return {"imported": 1, "product_ids": [pid]}
    settings = DailySettings(enabled=True)
    result = asyncio.run(run_cycle(settings, now=NOW, sessions=sessions, collector=collector,
                                   importer=importer, clock=lambda: completed))
    assert result["status"] == "ready" and result["selected"] == 1
