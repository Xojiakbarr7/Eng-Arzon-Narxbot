import csv
import io
from urllib.parse import urlparse
from datetime import datetime, timezone
from sqlalchemy import select
from .models import Product, Store, Offer, PriceHistory, ImportJob, AuditLog, utcnow
from .config import get_settings


def import_csv(db, text, commit=False):
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    required = {"product_id", "store_id", "price", "currency", "in_stock", "url"}
    if not reader.fieldnames or not required.issubset(reader.fieldnames):
        return {"ok": False, "committed": False, "row_count": 0, "errors": [{"row": 1, "message": "Ustunlar: product_id,store_id,price,currency,in_stock,url"}], "preview": []}
    rows, errors, seen = [], [], set()
    for line, row in enumerate(reader, 2):
        if line > 1001:
            errors.append({"row": line, "message": "Bir importda ko‘pi bilan 1000 qator"})
            break
        try:
            if any(row.get(key) is None or not str(row[key]).strip() for key in required):
                raise ValueError("Majburiy ustun qiymatlari bo‘sh yoki yetishmayapti")
            pid, sid, price = int(row["product_id"]), int(row["store_id"]), int(row["price"])
            product, store = db.get(Product, pid), db.get(Store, sid)
            if product is None or store is None:
                raise ValueError("Mahsulot yoki do‘kon ID topilmadi")
            if product.is_demo:
                raise ValueError("Demo mahsulotga haqiqiy narx yozilmaydi. Avval alohida haqiqiy mahsulot yarating")
            if store.is_demo:
                raise ValueError("Avval do‘konning yetkazish shartlarini admin panelda tasdiqlang")
            if not 0 < price <= 10**12 or row["currency"] != "UZS":
                raise ValueError("Musbat butun UZS narxi talab qilinadi")
            if row["in_stock"].lower() not in ("true", "false", "1", "0"):
                raise ValueError("in_stock true/false bo‘lishi kerak")
            url = row["url"].strip()
            parsed = urlparse(url)
            allowed = {d.strip().lower() for d in get_settings().allowed_store_domains.split(",")}
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.hostname.lower() != store.domain.lower() or parsed.hostname.lower() not in allowed or parsed.port not in (None, 443):
                raise ValueError("URL do‘konning ruxsatli HTTPS domenida bo‘lishi kerak")
            if (pid, sid) in seen:
                raise ValueError("Bir importda mahsulot-do‘kon juftligi takrorlandi")
            seen.add((pid, sid))
            rows.append({"product_id": pid, "store_id": sid, "price": price, "currency": "UZS", "in_stock": row["in_stock"].lower() in ("true", "1"), "url": url})
        except (ValueError, TypeError, KeyError) as exc:
            errors.append({"row": line, "message": str(exc)})
    if not rows and not errors:
        errors.append({"row": 2, "message": "CSV bo‘sh"})
    if commit and not errors:
        now = utcnow()
        for values in rows:
            offer = db.scalar(select(Offer).where(Offer.product_id == values["product_id"], Offer.store_id == values["store_id"]))
            if offer is None:
                offer = Offer(**values, is_demo=False, updated_at=now)
                db.add(offer)
            else:
                for key, value in values.items(): setattr(offer, key, value)
                offer.is_demo, offer.updated_at = False, now
            if values["in_stock"]:
                db.add(PriceHistory(product_id=values["product_id"], store_id=values["store_id"], price=values["price"], observed_at=now, is_demo=False))
        db.add(ImportJob(status="completed", row_count=len(rows), error_count=0))
        db.add(AuditLog(action="csv_import", details={"rows": len(rows)}))
        db.commit()
    return {"ok": not errors, "committed": bool(commit and not errors), "row_count": len(rows), "errors": errors, "preview": rows[:20]}
