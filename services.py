from collections import defaultdict
from datetime import timezone, timedelta
from statistics import median
from sqlalchemy import select
from fastapi import HTTPException
from .models import Product, Offer, Store, PriceHistory, Favorite, Category, utcnow
from .config import get_settings


REGIONS = {"tashkent": "Toshkent shahri", "tashkent-region": "Toshkent viloyati", "andijan": "Andijon", "bukhara": "Buxoro", "fergana": "Farg‘ona", "jizzakh": "Jizzax", "namangan": "Namangan", "navoiy": "Navoiy", "kashkadarya": "Qashqadaryo", "samarkand": "Samarqand", "sirdarya": "Sirdaryo", "surkhandarya": "Surxondaryo", "khorezm": "Xorazm", "karakalpakstan": "Qoraqalpog‘iston"}


def aware(dt):
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def is_stale(offer):
    return (utcnow() - aware(offer.updated_at)).total_seconds() > get_settings().offer_max_age_hours * 3600


def usable_offers(db, product_id):
    return [o for o in db.scalars(select(Offer).where(Offer.product_id == product_id, Offer.in_stock.is_(True))) if not is_stale(o) and (get_settings().demo_mode or not o.is_demo)]


def product_or_404(db, product_id):
    product = db.get(Product, product_id)
    if not product or (product.is_demo and not get_settings().demo_mode):
        raise HTTPException(404, "Mahsulot topilmadi")
    return product


def history_for(db, product_id, days=180):
    rows = db.scalars(select(PriceHistory).where(PriceHistory.product_id == product_id, PriceHistory.observed_at >= utcnow() - timedelta(days=days)).order_by(PriceHistory.observed_at)).all()
    grouped = {}
    for row in rows:
        if row.is_demo and not get_settings().demo_mode:
            continue
        date = row.observed_at.date().isoformat()
        if date not in grouped or row.price < grouped[date][0]:
            grouped[date] = (row.price, row.is_demo)
    return [{"date": date, "price": price, "is_demo": demo} for date, (price, demo) in sorted(grouped.items())]


def price_insight(history, current_price, is_demo=False):
    # Current day excluded from the baseline; one minimum per actual observation day.
    baseline = [p for p in history if p["date"] < utcnow().date().isoformat()]
    span = (utcnow().date() - __import__("datetime").date.fromisoformat(baseline[0]["date"])).days if baseline else 0
    values = [p["price"] for p in baseline]
    common = {"current_price": current_price, "sample_count": len(values), "span_days": span, "is_demo": is_demo or any(p["is_demo"] for p in history), "average_price": round(sum(values) / len(values)) if values else None, "lowest_price": min(values) if values else None, "percent_vs_average": None}
    if current_price is None or len(values) < 14 or span < 14:
        return {**common, "verdict": "insufficient", "title": "Tarix hali yetarli emas", "explanation": "Kamida 14 ta alohida kun narxi va 14 kunlik kuzatuv kerak. Kelajakdagi narx taxmin qilinmadi."}
    pct = (current_price / common["average_price"] - 1) * 100
    common["percent_vs_average"] = round(pct, 1)
    if pct <= -7:
        verdict, title = "buy", "Hozirgi narx qulay"
        text = f"Narx kuzatilgan davr o‘rtachasidan {abs(pct):.1f}% past. Xarid qilish uchun nisbatan qulay davr."
    elif pct >= 7:
        verdict, title = "wait", "Kutib kuzatish mumkin"
        text = f"Narx kuzatilgan davr o‘rtachasidan {pct:.1f}% yuqori. Shoshilmasangiz, maqsadli narx kuzatuvini yoqing."
    else:
        verdict, title = "neutral", "Narx odatiy oraliqda"
        text = "Narx kuzatilgan davr o‘rtachasiga yaqin. Yetkazib berish va kafolatni ham hisobga oling."
    prefix = "Demo tarix tahlili. " if common["is_demo"] else ""
    return {**common, "verdict": verdict, "title": title, "explanation": prefix + text + " Bu statistik tahlil; narxning tushishi kafolatlanmaydi."}


def product_summary(db, product, user_id=None):
    offers = usable_offers(db, product.id)
    minimum = min((o.price for o in offers), default=None)
    history = history_for(db, product.id, 30)
    previous = [p["price"] for p in history if p["date"] < utcnow().date().isoformat()]
    reference = median(previous) if len(previous) >= 7 else None
    discount = max(0, round((1 - minimum / reference) * 100)) if reference and minimum else 0
    category = db.get(Category, product.category_id)
    favorite = bool(user_id and db.scalar(select(Favorite.id).where(Favorite.user_id == user_id, Favorite.product_id == product.id)))
    return {"id": product.id, "name": product.name, "slug": product.slug, "brand": product.brand, "model": product.model, "category_id": product.category_id, "category_name": category.name if category else "", "description": product.description, "image_url": product.image_url, "emoji": product.emoji, "attributes": {k: v for k, v in product.attributes.items() if not k.startswith("_")}, "barcode": product.barcode, "min_price": minimum, "old_price": round(reference) if discount else None, "store_count": len(offers), "is_demo": product.is_demo, "discount_percent": discount, "favorite": favorite}


def delivery(store, subtotal, region="tashkent"):
    if store.free_delivery_threshold and subtotal >= store.free_delivery_threshold:
        return 0
    # Demo fees outside the capital are a documented scenario, never a live quote.
    return store.delivery_fee + (15000 if region != "tashkent" and store.is_demo else 0)


def product_detail(db, product, user_id=None, days=180, region="tashkent"):
    summary = product_summary(db, product, user_id)
    offers = []
    for offer in db.scalars(select(Offer).where(Offer.product_id == product.id)):
        if offer.is_demo and not get_settings().demo_mode:
            continue
        store = db.get(Store, offer.store_id)
        shipping_known = offer.is_demo or (not store.is_demo and region == "tashkent")
        fee = delivery(store, offer.price, region) if shipping_known else None
        notice = None if shipping_known else "Bu hudud uchun yetkazish haqi tasdiqlanmagan. Yakuniy narxni do‘konda aniqlang."
        offers.append({"id": offer.id, "store_id": offer.store_id, "store_name": store.name, "price": offer.price, "delivery_fee": fee, "total_price": offer.price + fee if fee is not None else None, "shipping_notice": notice, "currency": offer.currency, "in_stock": offer.in_stock, "url": offer.url, "updated_at": aware(offer.updated_at).isoformat(), "is_demo": offer.is_demo, "stale": is_stale(offer)})
    history = history_for(db, product.id, days)
    return {**summary, "region": region, "offers": sorted(offers, key=lambda o: (not o["in_stock"], o["stale"], o["total_price"] is None, o["total_price"] if o["total_price"] is not None else float("inf"))), "history": history, "insight": price_insight(history, summary["min_price"], product.is_demo)}


def validate_gtin(code):
    if not code.isascii() or not code.isdigit() or len(code) not in (8, 12, 13, 14):
        raise ValueError("GTIN 8, 12, 13 yoki 14 ta raqamdan iborat bo‘lishi kerak")
    total = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(code[:-1])))
    if (10 - total % 10) % 10 != int(code[-1]):
        raise ValueError("Shtrix-kod tekshiruv raqami xato")
    return code


def optimize_basket(db, items, region):
    if region not in REGIONS:
        raise HTTPException(422, "Hudud noto‘g‘ri")
    quantities = defaultdict(int)
    for item in items:
        quantities[item.product_id] += item.quantity
    if len(quantities) > 8 or any(q > 20 for q in quantities.values()):
        raise HTTPException(422, "Savatda 8 tagacha tur va har biridan 20 tagacha mahsulot mumkin")
    products = {pid: product_or_404(db, pid) for pid in quantities}
    stores = {s.id: s for s in db.scalars(select(Store))}
    candidates = {pid: usable_offers(db, pid) for pid in quantities}
    missing = [products[pid].name for pid, offers in candidates.items() if not offers]
    if missing:
        raise HTTPException(409, {"message": "Ba’zi mahsulotlar uchun yangilangan mavjud taklif yo‘q", "unavailable": missing})
    candidates = {pid: [offer for offer in offers if offer.is_demo or not stores[offer.store_id].is_demo]
                  for pid, offers in candidates.items()}
    unconfirmed = [products[pid].name for pid, offers in candidates.items() if not offers]
    if unconfirmed:
        raise HTTPException(409, {"message": "Bu mahsulotlar uchun yetkazish haqi tasdiqlanmagan. Do‘kon narxini katalogda ko‘ring; savatcha uchun admin yetkazish shartlarini tasdiqlashi kerak.", "unavailable": unconfirmed})
    if region != "tashkent" and any(not o.is_demo for offers in candidates.values() for o in offers):
        raise HTTPException(409, "Haqiqiy takliflar uchun bu hududdagi yetkazish narxi tasdiqlanmagan. Hozircha Toshkent shahrini tanlang.")
    # Exact subset DP: for each store and every subset of up to 8 products,
    # calculate that store's shipping once, then partition items among stores.
    ids = list(quantities)
    full = (1 << len(ids)) - 1
    costs = {}
    offer_map = {}
    for sid, store in stores.items():
        offer_map[sid] = {pid: next((o for o in candidates[pid] if o.store_id == sid), None) for pid in ids}
        subcost = {0: (0, 0)}
        for mask in range(1, full + 1):
            selected = [pid for i, pid in enumerate(ids) if mask & (1 << i)]
            if all(offer_map[sid][pid] for pid in selected):
                subtotal = sum(offer_map[sid][pid].price * quantities[pid] for pid in selected)
                subcost[mask] = (subtotal, delivery(store, subtotal, region))
        costs[sid] = subcost
    dp = {0: (0, [])}
    for sid in stores:
        next_dp = dict(dp)
        for covered, (total, assignments) in dp.items():
            remaining = full ^ covered
            subset = remaining
            while subset:
                if subset in costs[sid]:
                    subtotal, fee = costs[sid][subset]
                    new_total = total + subtotal + fee
                    combined = covered | subset
                    if combined not in next_dp or new_total < next_dp[combined][0]:
                        next_dp[combined] = (new_total, assignments + [(sid, subset)])
                subset = (subset - 1) & remaining
        dp = next_dp
    total, assignments = dp[full]
    out_items, out_stores = [], []
    for sid, mask in assignments:
        subtotal, fee = costs[sid][mask]
        store = stores[sid]
        out_stores.append({"store_id": sid, "store_name": store.name, "subtotal": subtotal, "delivery_fee": fee, "total": subtotal + fee})
        for i, pid in enumerate(ids):
            if mask & (1 << i):
                offer = offer_map[sid][pid]
                out_items.append({"product_id": pid, "name": products[pid].name, "quantity": quantities[pid], "store_id": sid, "store_name": store.name, "unit_price": offer.price, "subtotal": offer.price * quantities[pid]})
    single = min((sum(costs[sid][full]) for sid in stores if full in costs[sid]), default=None)
    demo = any(products[pid].is_demo for pid in ids)
    return {"items": out_items, "stores": out_stores, "subtotal": sum(s["subtotal"] for s in out_stores), "delivery_total": sum(s["delivery_fee"] for s in out_stores), "total": total, "single_store_total": single, "savings": max(0, single - total) if single is not None else 0, "is_demo": demo, "warnings": ["Demo narx va yetkazish shartlari. Haqiqiy buyurtma berilmadi."] if demo else [], "region": region, "algorithm": "exact-subset-dp"}
