"""Import real observations without guessing that two titles are one variant.

The caller owns the transaction. Delivery remains unconfirmed until an admin
checks store terms; collecting a retail price does not establish shipping cost.
"""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from urllib.parse import urlparse

from sqlalchemy import select

from .models import Category, Offer, PriceHistory, Product, Store, utcnow
from .services import validate_gtin


SOURCES = {
    "asaxiy": ("Asaxiy", "asaxiy.uz"),
    "uzum": ("Uzum Market", "uzum.uz"),
    "olx": ("OLX", "www.olx.uz"),
    "olcha": ("Olcha", "olcha.uz"),
    "texnomart": ("Texnomart", "texnomart.uz"),
    "idea": ("IDEA", "idea.uz"),
}


def _aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _https_url(value, domain=None):
    if not isinstance(value, str) or len(value) > 1000:
        return False
    try:
        parsed = urlparse(value)
        return bool(parsed.scheme == "https" and parsed.hostname and not parsed.username
                    and not parsed.password and parsed.port in (None, 443)
                    and (domain is None or parsed.hostname.lower() == domain))
    except ValueError:
        return False


def _validate(item, now):
    if not isinstance(item.source, str) or item.source not in SOURCES:
        return "unknown_source"
    if not isinstance(item.reference, str) or not 1 <= len(item.reference.strip()) <= 1000:
        return "invalid_reference"
    if not isinstance(item.name, str) or not 2 <= len(item.name.strip()) <= 200:
        return "invalid_name"
    if not isinstance(item.category_slug, str) or not 1 <= len(item.category_slug) <= 100:
        return "invalid_category"
    if type(item.price) is not int or not 0 < item.price <= 10**12:
        return "invalid_price"
    if item.condition != "new" or type(item.in_stock) is not bool:
        return "not_confirmed_new"
    if not _https_url(item.url, SOURCES[item.source][1]):
        return "invalid_source_url"
    if not isinstance(item.observed_at, datetime) or item.observed_at.tzinfo is None or item.observed_at.utcoffset() is None:
        return "invalid_observed_at"
    if not now - timedelta(hours=48) <= item.observed_at <= now + timedelta(minutes=5):
        return "observation_outside_window"
    if not isinstance(item.brand, str) or len(item.brand) > 80 or not isinstance(item.model, str) or len(item.model) > 120:
        return "invalid_identity"
    if not isinstance(item.attributes, dict) or len(item.attributes) > 30 or any(
        not isinstance(key, str) or not 1 <= len(key) <= 100
        or not isinstance(value, str) or len(value) > 500
        for key, value in item.attributes.items()
    ):
        return "invalid_attributes"
    return None


def _available_barcode(db, raw, product_id):
    if not isinstance(raw, str):
        return None
    try:
        normalized = validate_gtin(raw).zfill(14)
    except ValueError:
        return None
    for other in db.scalars(select(Product).where(Product.barcode.is_not(None))):
        if other.id != product_id and other.barcode.zfill(14) == normalized:
            return None
    return normalized


def import_observations(db, items):
    """Upsert observed prices; never commit, invent freshness, or merge titles.

    A source/reference is one source-specific product. Cross-store matching
    requires a separate confirmed canonical mapping, not fuzzy name matching.
    """
    result = {"imported": 0, "skipped": 0, "product_ids": [], "errors": []}
    now = utcnow()
    for index, item in enumerate(items):
        error = _validate(item, now)
        category = None
        if error is None:
            category = db.scalar(select(Category).where(
                Category.slug == item.category_slug, Category.active.is_(True), Category.parent_id.is_(None)))
            if category is None:
                error = "unknown_category"
        slug = f"{item.source}-" + sha256(item.reference.strip().encode("utf-8")).hexdigest()[:24] if error is None else None
        product = db.scalar(select(Product).where(Product.slug == slug)) if error is None else None
        if product is not None and product.is_demo:
            error = "demo_identity_collision"
        source_name, domain = SOURCES.get(item.source, (None, None))
        store = db.scalar(select(Store).where(Store.slug == item.source)) if error is None else None
        if store is not None and store.domain.lower() != domain:
            error = "store_domain_mismatch"
        offer = None
        if error is None and product is not None and store is not None:
            offer = db.scalar(select(Offer).where(Offer.product_id == product.id, Offer.store_id == store.id))
            if offer is not None and (offer.is_demo or _aware(offer.updated_at) > _aware(item.observed_at)):
                error = "older_or_demo_offer"
        if error is not None:
            result["skipped"] += 1
            if len(result["errors"]) < 20:
                result["errors"].append({"index": index, "reason": error})
            continue

        if store is None:
            store = Store(name=source_name, slug=item.source, domain=domain,
                          delivery_fee=0, free_delivery_threshold=None,
                          adapter_status="public", is_demo=True)
            db.add(store)
            db.flush()
        else:
            store.adapter_status = "public"
        attributes = {**item.attributes, "Manba": source_name, "Holat": "Yangi (manba bo‘yicha)",
                      "_condition": "new", "_source": item.source, "_reference": item.reference.strip()}
        if product is None:
            product = Product(slug=slug, name=item.name.strip(), brand=item.brand.strip() or "Ko‘rsatilmagan",
                              model=item.model.strip() or item.name.strip()[:120], category_id=category.id,
                              attributes=attributes, is_demo=False)
            db.add(product)
            db.flush()
        else:
            product.name = item.name.strip()
            product.brand = item.brand.strip() or product.brand
            product.model = item.model.strip() or product.model
            product.category_id = category.id
            product.attributes = {**{key: value for key, value in product.attributes.items() if not key.startswith("_")},
                                  **attributes}
        product.description = "Manbadan kuzatilgan yangi mahsulot. Narx va mavjudlikni xarid sahifasida tekshiring."
        product.image_url = item.image_url if _https_url(item.image_url) else None
        barcode = _available_barcode(db, item.barcode, product.id)
        if barcode is not None:
            product.barcode = barcode
        observed_at = item.observed_at.astimezone(timezone.utc)
        if offer is None:
            offer = Offer(product_id=product.id, store_id=store.id, price=item.price,
                          currency="UZS", in_stock=item.in_stock, url=item.url,
                          is_demo=False, updated_at=observed_at)
            db.add(offer)
        else:
            offer.price, offer.in_stock = item.price, item.in_stock
            offer.url, offer.updated_at = item.url, observed_at
        latest = db.scalar(select(PriceHistory).where(
            PriceHistory.product_id == product.id, PriceHistory.store_id == store.id,
            PriceHistory.is_demo.is_(False)).order_by(PriceHistory.observed_at.desc(), PriceHistory.id.desc()).limit(1))
        if item.in_stock and (latest is None or latest.price != item.price
                              or _aware(latest.observed_at).date() != observed_at.date()):
            db.add(PriceHistory(product_id=product.id, store_id=store.id, price=item.price,
                                observed_at=observed_at, is_demo=False))
        result["imported"] += 1
        if product.id not in result["product_ids"]:
            result["product_ids"].append(product.id)
    db.flush()
    return result
