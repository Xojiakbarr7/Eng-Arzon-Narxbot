"""Exercise first startup and subsequent inserts on both supported databases."""
import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.orm import Session

from app.db import Base
from app.models import Category, Offer, PriceHistory, Product, Store
from app.seed import CATEGORY_TREE, seed_catalog


@pytest.fixture(params=["sqlite", "postgresql"])
def seed_engine(request):
    if request.param == "sqlite":
        engine = create_engine("sqlite://")

        @event.listens_for(engine, "connect")
        def enable_foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(engine)
        yield engine
        engine.dispose()
        return

    url = os.environ.get("TEST_POSTGRES_URL")
    if not url:
        pytest.skip("TEST_POSTGRES_URL points to a dedicated PostgreSQL test database")
    schema = "seed_test_" + uuid4().hex
    admin = create_engine(url)
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    try:
        Base.metadata.create_all(engine)
        # Restores and sequences with gaps must preserve the same relationships.
        with engine.begin() as connection:
            for table, start in [("categories", 101), ("stores", 201), ("products", 301)]:
                connection.execute(text(f'ALTER SEQUENCE "{table}_id_seq" RESTART WITH {start}'))
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


@pytest.mark.parametrize("demo", [False, True])
def test_fresh_seed_relationships_idempotence_and_later_inserts(seed_engine, demo):
    with Session(seed_engine) as db:
        seed_catalog(db, demo)
        seed_catalog(db, demo)
        categories = list(db.scalars(select(Category)))
        roots = {c.slug: c for c in categories if c.parent_id is None}
        expected_count = len(CATEGORY_TREE) + sum(len(row[3].split("|")) for row in CATEGORY_TREE)
        assert len(categories) == expected_count
        for _, slug, _, children in CATEGORY_TREE:
            for index, _ in enumerate(children.split("|"), 1):
                child = next(c for c in categories if c.slug == f"{slug}-{index}")
                assert child.parent_id == roots[slug].id
        assert db.scalar(select(func.count()).select_from(Store)) == 5
        assert db.scalar(select(func.count()).select_from(Product)) == (20 if demo else 0)
        assert db.scalar(select(func.count()).select_from(Offer)) == (100 if demo else 0)
        assert db.scalar(select(func.count()).select_from(PriceHistory)) == (720 if demo else 0)
        if demo:
            iphone = db.scalar(select(Product).where(Product.slug == "demo-product-1"))
            assert iphone.category_id == roots["elektronika"].id
            assert db.scalar(select(func.count()).select_from(Offer).where(Offer.product_id == iphone.id)) == 5

        # Admin-created records must still receive unique database-generated IDs.
        db.add(Category(name="New category", slug="new-category"))
        db.add(Store(name="New store", slug="new-store", domain="example.com"))
        db.add(Product(name="New product", slug="new-product", brand="Test", model="Test", category_id=roots["elektronika"].id))
        db.commit()
        assert db.scalar(select(func.count()).select_from(Category)) == expected_count + 1
        assert db.scalar(select(func.count()).select_from(Store)) == 6
        assert db.scalar(select(func.count()).select_from(Product)) == (21 if demo else 1)
