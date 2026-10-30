"""Eng Arzon Narx FastAPI entry point.

Restored after a GitHub web upload flattened the original directory structure.
Business logic lives in services.py, seed.py, imports.py and security.py.
"""
from contextlib import asynccontextmanager
import asyncio
import logging
from datetime import timedelta
import re

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import get_settings
from .db import Base, SessionLocal, engine, get_db
from .imports import import_csv
from .models import (
    AuditLog, Category, DailyRun, Favorite, ImportJob, NotificationHistory, Offer,
    PriceAlert, PriceHistory, Product, SearchHistory, Store, User, utcnow,
)
from .schemas import (
    AlertRequest, AlertUpdate, AssistantRequest, BasketRequest,
    CategoryRequest, CsvImportRequest, NotificationAck, ProductRequest,
    ProfileUpdate, StoreUpdate,
)
from .security import current_user, require_admin, require_internal
from .telegram_webhook import enable_webhook, disable_webhook, telegram_update
from .daily_worker import DailySettings, serve, flag
from .seed import seed_catalog
from .services import (
    REGIONS, aware, history_for, is_stale, optimize_basket,
    product_detail, product_or_404, product_summary, usable_offers,
    validate_gtin,
)

rate_windows = {}


@asynccontextmanager
async def lifespan(application: FastAPI):
    # Initial bootstrap for SQLite and a new PostgreSQL database. A deployment
    # with existing schema should additionally run Alembic migrations.
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_catalog(db, get_settings().demo_mode)
    await enable_webhook(application)
    daily_task = None
    if flag(__import__("os").getenv("COLLECTION_ENABLED", "false")):
        try:
            daily_settings = DailySettings.from_env()
            daily_task = asyncio.create_task(serve(daily_settings))
            logging.getLogger("eng_arzon.daily").info("Daily collection scheduled for %02d:%02d Tashkent", daily_settings.hour, daily_settings.minute)
        except (ValueError, TypeError) as exc:
            logging.getLogger("eng_arzon.daily").error("Daily collection configuration invalid: %s", type(exc).__name__)
    try:
        yield
    finally:
        if daily_task is not None:
            daily_task.cancel()
            try:
                await daily_task
            except asyncio.CancelledError:
                pass
        await disable_webhook(application)


app = FastAPI(
    title="Eng Arzon Narx API",
    version="1.0.0",
    lifespan=lifespan,
)

# Only explicitly trusted Mini App origins may call the JSON API in browsers.
# Telegram initData is still verified independently for each user request.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip().rstrip("/") for origin in get_settings().cors_origins.split(",") if origin.strip()],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Telegram-Init-Data"],
)



def ensure_region(region: str) -> str:
    if region not in REGIONS:
        raise HTTPException(status_code=422, detail="Hudud noto‘g‘ri")
    return region


def as_profile(user: User):
    return {
        "id": user.id,
        "telegram_id": user.telegram_id,
        "first_name": user.first_name,
        "language": user.language,
        "region": user.region,
        "notifications_enabled": user.notifications_enabled,
        "regions": [{"id": key, "name": value} for key, value in REGIONS.items()],
    }


def alert_row(db: Session, row: PriceAlert):
    product = db.get(Product, row.product_id)
    return {
        "id": row.id,
        "product_id": row.product_id,
        "product_name": product.name if product else "Mahsulot",
        "target_price": row.target_price,
        "enabled": row.enabled,
        "created_at": aware(row.created_at).isoformat(),
    }


@app.get("/api/health")
def health():
    return {"status": "ok", "ok": True, "demo_mode": get_settings().demo_mode, "telegram_webhook": bool(getattr(app.state, "telegram_bot", None))}


@app.get("/api/catalog/status")
def catalog_status(db: Session = Depends(get_db)):
    # Public, aggregate-only telemetry. Never return source URLs or credentials.
    product_count = db.scalar(select(func.count()).select_from(Product).where(Product.is_demo.is_(False))) or 0
    available_count = db.scalar(
        select(func.count(func.distinct(Product.id)))
        .select_from(Product).join(Offer, Offer.product_id == Product.id)
        .where(Product.is_demo.is_(False), Offer.is_demo.is_(False), Offer.in_stock.is_(True))
    ) or 0
    latest = db.scalar(select(DailyRun).where(DailyRun.destination == "catalog").order_by(DailyRun.created_at.desc(), DailyRun.id.desc()).limit(1))
    return {
        "real_products": product_count,
        "products_with_offers": available_count,
        "refresh_interval_hours": 2,
        "last_refresh_status": latest.status if latest else "not_started",
        "last_refresh_at": aware(latest.updated_at).isoformat() if latest else None,
    }


@app.post("/telegram/webhook", include_in_schema=False)
async def telegram_webhook_route(request: Request):
    return await telegram_update(request)


@app.get("/api/categories")
def categories(db: Session = Depends(get_db)):
    items = db.scalars(select(Category).where(Category.active.is_(True)).order_by(Category.sort_order, Category.id)).all()
    return [{"id": c.id, "name": c.name, "slug": c.slug, "emoji": c.emoji, "parent_id": c.parent_id} for c in items]


@app.get("/api/stores")
def stores(db: Session = Depends(get_db)):
    items = db.scalars(select(Store).order_by(Store.id)).all()
    return [
        {"id": x.id, "name": x.name, "slug": x.slug, "adapter_status": x.adapter_status,
         "delivery_fee": x.delivery_fee, "free_delivery_threshold": x.free_delivery_threshold,
         "is_demo": x.is_demo}
        for x in items
    ]


def search_catalog(db: Session, user: User, q: str, category: str, store: str,
                   min_price: int | None, max_price: int | None,
                   sort: str, page: int, page_size: int):
    if min_price is not None and max_price is not None and min_price > max_price:
        raise HTTPException(422, "Minimal narx maksimal narxdan yuqori")
    rows = db.scalars(select(Product).order_by(Product.id)).all()
    q = q.strip().casefold()
    q = q.replace("самсунг", "samsung").replace("айфон", "iphone").replace("сяоми", "xiaomi")
    if q:
        db.add(SearchHistory(user_id=user.id, query=q[:200]))
        db.commit()
    category_ids = None
    if category:
        match = db.scalar(select(Category).where(Category.slug == category))
        if match is None:
            return [], 0
        all_categories = db.scalars(select(Category)).all()
        category_ids = {match.id}
        while True:
            more = {c.id for c in all_categories if c.parent_id in category_ids}
            if more.issubset(category_ids):
                break
            category_ids.update(more)
    store_ids = None
    if store:
        store_row = db.scalar(select(Store).where(Store.slug == store))
        store_ids = {store_row.id} if store_row else set()
    output = []
    for product in rows:
        if product.is_demo and not get_settings().demo_mode:
            continue
        if category_ids is not None and product.category_id not in category_ids:
            continue
        fields = " ".join([product.name, product.brand, product.model, product.slug, " ".join(str(v) for v in product.attributes.values())]).casefold()
        if q and not all(part in fields for part in q.split()):
            continue
        offers = usable_offers(db, product.id)
        if store_ids is not None and not any(o.store_id in store_ids for o in offers):
            continue
        item = product_summary(db, product, user.id)
        price = item["min_price"]
        if min_price is not None and (price is None or price < min_price):
            continue
        if max_price is not None and (price is None or price > max_price):
            continue
        output.append(item)
    if sort in ("price_asc", "total_price"):
        output.sort(key=lambda x: (x["min_price"] is None, x["min_price"] or 0, x["id"]))
    elif sort == "price_desc":
        output.sort(key=lambda x: (x["min_price"] is None, -(x["min_price"] or 0), x["id"]))
    elif sort == "discount":
        output.sort(key=lambda x: (-x["discount_percent"], x["id"]))
    elif sort == "newest":
        output.sort(key=lambda x: -x["id"])
    total = len(output)
    return output[(page - 1) * page_size:page * page_size], total


@app.get("/api/products")
def products(
    q: str = Query("", max_length=200),
    category: str = "",
    store: str = "",
    min_price: int | None = Query(None, ge=0),
    max_price: int | None = Query(None, ge=0),
    sort: str = "price_asc",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    items, total = search_catalog(db, user, q, category, store, min_price, max_price, sort, page, page_size)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@app.get("/api/products/{product_id}")
def product_by_id(product_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return product_detail(db, product_or_404(db, product_id), user.id, region=user.region)


@app.get("/api/barcode/{code}")
def barcode(code: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    try:
        validate_gtin(code)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    product = db.scalar(select(Product).where(Product.barcode == code))
    if product is None and len(code) == 14:
        # GTIN-14 zero-padding for an EAN-13/UPC code in the catalog.
        for length in (13, 12, 8):
            if code.startswith("0" * (14 - length)):
                product = db.scalar(select(Product).where(Product.barcode == code[-length:]))
                if product:
                    break
    if product is None:
        raise HTTPException(404, "Bunday shtrix-kodli mahsulot topilmadi")
    return product_detail(db, product_or_404(db, product.id), user.id, region=user.region)


@app.get("/api/profile")
def profile(user: User = Depends(current_user)):
    return as_profile(user)


@app.patch("/api/profile")
def update_profile(data: ProfileUpdate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    update = data.model_dump(exclude_none=True)
    if "region" in update:
        ensure_region(update["region"])
    for key, value in update.items():
        setattr(user, key, value)
    db.commit()
    db.refresh(user)
    return as_profile(user)


@app.get("/api/profile/search-history")
def get_search_history(db: Session = Depends(get_db), user: User = Depends(current_user)):
    rows = db.scalars(select(SearchHistory).where(SearchHistory.user_id == user.id).order_by(SearchHistory.id.desc()).limit(50)).all()
    return [{"id": x.id, "query": x.query, "created_at": aware(x.created_at).isoformat()} for x in rows]


@app.delete("/api/profile")
def remove_profile(db: Session = Depends(get_db), user: User = Depends(current_user)):
    alert_ids = select(PriceAlert.id).where(PriceAlert.user_id == user.id)
    db.execute(delete(NotificationHistory).where(NotificationHistory.alert_id.in_(alert_ids)))
    for model in (SearchHistory, Favorite, PriceAlert):
        db.execute(delete(model).where(model.user_id == user.id))
    db.delete(user)
    db.commit()
    return {"ok": True}


@app.get("/api/favorites")
def favorites(db: Session = Depends(get_db), user: User = Depends(current_user)):
    ids = db.scalars(select(Favorite.product_id).where(Favorite.user_id == user.id)).all()
    return [product_summary(db, p, user.id) for product_id in ids if (p := db.get(Product, product_id)) and (get_settings().demo_mode or not p.is_demo)]


@app.post("/api/favorites/{product_id}")
def add_favorite(product_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    product_or_404(db, product_id)
    exists = db.scalar(select(Favorite).where(Favorite.user_id == user.id, Favorite.product_id == product_id))
    if exists is None:
        db.add(Favorite(user_id=user.id, product_id=product_id))
        db.commit()
    return {"ok": True, "product_id": product_id}


@app.delete("/api/favorites/{product_id}")
def delete_favorite(product_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    db.execute(delete(Favorite).where(Favorite.user_id == user.id, Favorite.product_id == product_id))
    db.commit()
    return {"ok": True}


@app.get("/api/alerts")
def alerts(db: Session = Depends(get_db), user: User = Depends(current_user)):
    rows = db.scalars(select(PriceAlert).where(PriceAlert.user_id == user.id).order_by(PriceAlert.id.desc())).all()
    return [alert_row(db, row) for row in rows]


@app.post("/api/alerts")
def create_alert(data: AlertRequest, db: Session = Depends(get_db), user: User = Depends(current_user)):
    product_or_404(db, data.product_id)
    row = db.scalar(select(PriceAlert).where(PriceAlert.user_id == user.id, PriceAlert.product_id == data.product_id))
    if row is None:
        row = PriceAlert(user_id=user.id, **data.model_dump())
        db.add(row)
    else:
        row.target_price = data.target_price
        row.enabled = data.enabled
    db.commit()
    db.refresh(row)
    return alert_row(db, row)


@app.patch("/api/alerts/{alert_id}")
def change_alert(alert_id: int, data: AlertUpdate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    row = db.scalar(select(PriceAlert).where(PriceAlert.id == alert_id, PriceAlert.user_id == user.id))
    if row is None:
        raise HTTPException(404, "Kuzatuv topilmadi")
    for key, value in data.model_dump(exclude_none=True).items():
        setattr(row, key, value)
    db.commit()
    return alert_row(db, row)


@app.delete("/api/alerts/{alert_id}")
def remove_alert(alert_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    row = db.scalar(select(PriceAlert).where(PriceAlert.id == alert_id, PriceAlert.user_id == user.id))
    if row is None:
        raise HTTPException(404, "Kuzatuv topilmadi")
    db.delete(row)
    db.commit()
    return {"ok": True}


@app.post("/api/basket/optimize")
def basket(data: BasketRequest, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return optimize_basket(db, data.items, ensure_region(data.region))


@app.post("/api/assistant")
def assistant(data: AssistantRequest, db: Session = Depends(get_db), user: User = Depends(current_user)):
    message = data.message.casefold()
    # This is a rule-based catalog assistant, not a generative AI service.
    budget = None
    match = re.search(r"(\d+(?:[.,]\d+)?)\s*(million|mln|milliongacha|mlngacha|млн)", message)
    if match:
        budget = int(float(match.group(1).replace(",", ".")) * 1_000_000)
    else:
        match = re.search(r"(\d[\d\s]{4,})\s*(so['‘’]?m|sum|сум)", message)
        if match:
            budget = int(match.group(1).replace(" ", ""))
    terms = {
        "telefon": "telefon", "smartfon": "telefon", "iphone": "iphone",
        "samsung": "samsung", "noutbuk": "noutbuk", "kitob": "kitob",
        "simsiz": "quloqchin", "quloqchin": "quloqchin",
    }
    q = next((value for key, value in terms.items() if key in message), "")
    if q == "telefon":
        q = ""
    items, _ = search_catalog(db, user, q, "", "", None, budget, "price_asc", 1, 8)
    answer = (
        ("Byudjetingizga mos kuzatilgan katalog takliflari." if budget else "Katalogdagi eng arzon mavjud variantlar.")
        if items else "Hozircha mos mahsulot topilmadi."
    )
    return {"mode": "statistical", "answer": answer, "products": items,
            "notice": "Bu katalogga asoslangan qoidaviy yordamchi, generativ AI ulanmagan."}


@app.get("/api/admin/stats", dependencies=[Depends(require_admin)])
def admin_stats(db: Session = Depends(get_db)):
    models = {"products": Product, "categories": Category, "stores": Store,
              "offers": Offer, "users": User, "alerts": PriceAlert, "imports": ImportJob}
    return {name: db.scalar(select(func.count()).select_from(model)) for name, model in models.items()}


@app.post("/api/admin/categories", status_code=201, dependencies=[Depends(require_admin)])
def admin_create_category(data: CategoryRequest, db: Session = Depends(get_db)):
    if data.parent_id and not db.get(Category, data.parent_id):
        raise HTTPException(404, "Ota kategoriya topilmadi")
    row = Category(**data.model_dump())
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Bu slug mavjud") from exc
    db.refresh(row)
    return {"id": row.id, "name": row.name, "slug": row.slug}


@app.post("/api/admin/products", status_code=201, dependencies=[Depends(require_admin)])
def admin_create_product(data: ProductRequest, db: Session = Depends(get_db)):
    if not db.get(Category, data.category_id):
        raise HTTPException(404, "Kategoriya topilmadi")
    if data.barcode:
        try:
            validate_gtin(data.barcode)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
    row = Product(**data.model_dump(), is_demo=False)
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Slug yoki shtrix-kod takrorlandi") from exc
    db.refresh(row)
    return {"id": row.id, "name": row.name, "slug": row.slug}


@app.put("/api/admin/stores/{store_id}", dependencies=[Depends(require_admin)])
def admin_update_store(store_id: int, data: StoreUpdate, db: Session = Depends(get_db)):
    row = db.get(Store, store_id)
    if row is None:
        raise HTTPException(404, "Do‘kon topilmadi")
    for key, value in data.model_dump().items():
        setattr(row, key, value)
    row.is_demo = False
    db.add(AuditLog(action="store_update", details={"store_id": store_id}))
    db.commit()
    return {"id": row.id, "name": row.name, "delivery_fee": row.delivery_fee,
            "free_delivery_threshold": row.free_delivery_threshold, "adapter_status": row.adapter_status}


@app.post("/api/admin/import", dependencies=[Depends(require_admin)])
def admin_import(data: CsvImportRequest, db: Session = Depends(get_db)):
    return import_csv(db, data.csv_text, data.commit)


@app.post("/api/internal/notifications/claim", dependencies=[Depends(require_internal)])
def claim_notifications(db: Session = Depends(get_db)):
    now = utcnow()
    due = []
    alerts = db.scalars(select(PriceAlert).where(PriceAlert.enabled.is_(True))).all()
    for alert in alerts:
        user = db.get(User, alert.user_id)
        product = db.get(Product, alert.product_id)
        if user is None or product is None or not user.notifications_enabled:
            continue
        # Never send alerts based on unverified demo prices or stale offers.
        offer = next((o for o in sorted(usable_offers(db, product.id), key=lambda x: x.price)
                      if not o.is_demo and o.price <= alert.target_price), None)
        if offer is None:
            continue
        key = f"alert:{alert.id}:{now.date().isoformat()}"
        record = db.scalar(select(NotificationHistory).where(NotificationHistory.dedupe_key == key))
        if record is None:
            record = NotificationHistory(alert_id=alert.id, price=offer.price,
                                         dedupe_key=key, status="pending")
            db.add(record)
            db.flush()
        if record.status == "delivered" or record.attempts >= 5:
            continue
        if record.status == "claimed" and record.claimed_at and aware(record.claimed_at) > now - timedelta(minutes=5):
            continue
        record.status = "claimed"
        record.claimed_at = now
        record.attempts += 1
        due.append({"id": record.id, "user_id": int(user.telegram_id),
                    "text": f"🔔 {product.name}: {offer.price:,} so‘m. Maqsadli narxga tushdi!".replace(",", " ")})
        if len(due) >= 25:
            break
    db.commit()
    return {"items": due}


@app.post("/api/internal/notifications/{notification_id}/ack", dependencies=[Depends(require_internal)])
def ack_notification(notification_id: int, data: NotificationAck, db: Session = Depends(get_db)):
    row = db.get(NotificationHistory, notification_id)
    if row is None:
        raise HTTPException(404, "Xabar topilmadi")
    if row.status == "claimed":
        row.status = "delivered" if data.delivered else "pending"
        db.commit()
    return {"ok": True, "delivered": row.status == "delivered"}
