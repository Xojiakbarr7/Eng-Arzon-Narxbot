from datetime import timedelta
from sqlalchemy import select
from .models import Category, Product, Store, Offer, PriceHistory, utcnow


CATEGORY_TREE = [
    ("Elektronika", "elektronika", "📱", "Smartfonlar|Planshetlar|Noutbuklar|Kompyuterlar|Monitorlar|Televizorlar|Smart soatlar|Quloqchinlar|Powerbanklar|Zaryadlovchilar|Telefon aksessuarlari|O‘yin konsollari|Printerlar"),
    ("Maishiy texnika", "maishiy-texnika", "🏠", "Muzlatkichlar|Kir yuvish mashinalari|Konditsionerlar|Changyutgichlar|Mikroto‘lqinli pechlar|Plitalar|Blenderlar|Go‘sht maydalagichlar|Elektr choynaklar|Dazmollar|Isitgichlar|Havo namlagichlar"),
    ("Uy va mebel", "uy-mebel", "🛋️", "Divanlar|Yotoq jihozlari|Shkaflar|Stollar|Stullar|Matraslar|Shishiriladigan matraslar|Gilamlar|Yoritish jihozlari|Oshxona buyumlari|Uy bezaklari"),
    ("Kiyim-kechak", "kiyim", "👕", "Erkaklar kiyimi|Ayollar kiyimi|Bolalar kiyimi|Oyoq kiyimlar|Sumkalar|Aksessuarlar|Sport kiyimlari"),
    ("Go‘zallik va parvarish", "gozallik", "💄", "Parfyumeriya|Kosmetika|Terini parvarishlash|Soch parvarishi|Fenlar|Trimmerlar|Elektr ustaralar|Gigiyena mahsulotlari"),
    ("Bolalar uchun", "bolalar", "🧸", "O‘yinchoqlar|Bolalar aravachalari|Bolalar mebellari|Maktab anjomlari|Bolalar parvarishi|Rivojlantiruvchi o‘yinlar"),
    ("Avtotovarlar", "avto", "🚗", "Avtomobil aksessuarlari|Avtoelektronika|Videoregistratorlar|Avtomobil gilamchalari|Telefon ushlagichlar|Avtomobil parvarishi"),
    ("Sport va sayohat", "sport", "🏋️", "Fitnes jihozlari|Velosipedlar|Turistik jihozlar|Ryukzaklar|To‘plar|Sport aksessuarlari"),
    ("Qurilish va ta’mirlash", "qurilish", "🛠️", "Elektr asboblari|Qo‘l asboblari|Drel va perforatorlar|Santexnika|Elektr jihozlari|Bog‘ anjomlari"),
    ("Kitob va kanselyariya", "kitob", "📚", "Badiiy kitoblar|O‘quv qo‘llanmalar|Darsliklar|Daftarlar|Ruchkalar|Ofis anjomlari"),
    ("Oziq-ovqat va kundalik", "kundalik", "🛒", "Ichimliklar|Shirinliklar|Qadoqlangan mahsulotlar|Tozalash vositalari|Uy-ro‘zg‘or buyumlari"),
]


def demo_barcode(index: int):
    payload = f"200{index:09d}"
    check = (10 - sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(payload)) % 10) % 10
    return payload + str(check)


def seed_catalog(db, demo: bool):
    if not db.scalar(select(Category.id).limit(1)):
        roots = []
        for index, (name, slug, emoji, children) in enumerate(CATEGORY_TREE, 1):
            root = Category(name=name, slug=slug, emoji=emoji, sort_order=index)
            db.add(root)
            roots.append(root)
        db.flush()
        for root, (_, slug, emoji, children) in zip(roots, CATEGORY_TREE):
            for child_index, child in enumerate(children.split("|"), 1):
                db.add(Category(name=child, slug=f"{slug}-{child_index}", emoji=emoji, parent_id=root.id, sort_order=child_index))
        db.commit()
    if not db.scalar(select(Store.id).limit(1)):
        stores = [("Uzum Market", "uzum", "uzum.uz", 15000, 500000), ("Asaxiy", "asaxiy", "asaxiy.uz", 25000, 1000000), ("Olcha", "olcha", "olcha.uz", 20000, 700000), ("Texnomart", "texnomart", "texnomart.uz", 30000, 1500000), ("MediaPark", "mediapark", "mediapark.uz", 25000, 1000000)]
        for name, slug, domain, delivery, free in stores:
            db.add(Store(name=name, slug=slug, domain=domain, delivery_fee=delivery, free_delivery_threshold=free))
        db.commit()
    if not demo or db.scalar(select(Product.id).limit(1)):
        return
    # Use allocated IDs: PostgreSQL sequences need not start at 1.
    root_ids = dict(db.execute(select(Category.slug, Category.id).where(Category.parent_id.is_(None))).all())
    store_ids = list(db.scalars(select(Store.id).order_by(Store.id)))
    products = [
        ("Apple iPhone 16 Pro 256 GB", "Apple", "iPhone 16 Pro", 1, "📱", 14990000, {"Xotira": "256 GB", "Rang": "Natural titanium"}),
        ("Samsung Galaxy A55 128 GB", "Samsung", "Galaxy A55", 1, "📱", 3590000, {"Xotira": "128 GB", "Rang": "Navy"}),
        ("Redmi Note 14 Pro 256 GB", "Xiaomi", "Redmi Note 14 Pro", 1, "📱", 3290000, {"Xotira": "256 GB", "RAM": "8 GB"}),
        ("Apple AirPods Pro 2 USB-C", "Apple", "AirPods Pro 2", 1, "🎧", 2490000, {"Ulanish": "Bluetooth", "Port": "USB-C"}),
        ("Lenovo IdeaPad Slim 3 8/512 GB", "Lenovo", "IdeaPad Slim 3", 1, "💻", 5190000, {"RAM": "8 GB", "SSD": "512 GB"}),
        ("Samsung Galaxy A55 256 GB", "Samsung", "Galaxy A55", 1, "📱", 3890000, {"Xotira": "256 GB", "Rang": "Navy"}),
        ("Xiaomi Smart Air Fryer 6L", "Xiaomi", "Smart Air Fryer 6L", 2, "🍳", 1190000, {"Hajm": "6 L", "Quvvat": "1500 W"}),
        ("Artel elektr choynak 1.7L", "Artel", "KE-1700", 2, "🫖", 219000, {"Hajm": "1.7 L"}),
        ("Bosch changyutgich BGC05", "Bosch", "BGC05", 2, "🧹", 1490000, {"Quvvat": "700 W"}),
        ("IKEA ish stoli 120×60", "IKEA", "LAGKAPTEN 120", 3, "🪑", 890000, {"O‘lcham": "120×60 sm"}),
        ("Basic paxtali futbolka M", "Basic", "Cotton M", 4, "👕", 99000, {"O‘lcham": "M", "Rang": "Oq"}),
        ("Philips soch quritgich BHD360", "Philips", "BHD360", 5, "💨", 429000, {"Quvvat": "2100 W"}),
        ("LEGO Classic 10696", "LEGO", "10696", 6, "🧩", 399000, {"Yosh": "4+", "Detallar": "484"}),
        ("70mai Dash Cam M310", "70mai", "M310", 7, "📹", 549000, {"Video": "1296p"}),
        ("Decathlon sayohat ryukzagi 20L", "Quechua", "NH100 20L", 8, "🎒", 249000, {"Hajm": "20 L"}),
        ("Bosch akkumulyatorli drel 12V", "Bosch", "GSR 120-LI", 9, "🛠️", 1190000, {"Kuchlanish": "12 V"}),
        ("Atom odatlar — James Clear", "Asaxiy Books", "Atom odatlar UZ", 10, "📘", 69000, {"Til": "O‘zbekcha", "Muqova": "Qattiq"}),
        ("Suv 1.5L, 6 dona", "Hydrolife", "Still 1.5L×6", 11, "💧", 24000, {"Hajm": "9 L"}),
        ("Ariel kir yuvish kukuni 3 kg", "Ariel", "Color 3 kg", 11, "🧺", 89000, {"Og‘irlik": "3 kg"}),
        ("Xiaomi Power Bank 10000 mAh", "Xiaomi", "PB100DZM", 1, "🔋", 179000, {"Sig‘im": "10000 mAh", "Port": "USB-C"}),
    ]
    now = utcnow()
    for index, (name, brand, model, category, emoji, price, attributes) in enumerate(products, 1):
        product = Product(name=name, slug=f"demo-product-{index}", brand=brand, model=model, category_id=root_ids[CATEGORY_TREE[category - 1][1]], emoji=emoji, attributes=attributes, barcode=demo_barcode(index), is_demo=True, description="Sinov katalogi. Narxlar, mavjudlik va tarix sun’iy namuna; haqiqiy do‘kon taklifi emas.")
        db.add(product)
        db.flush()
        for sid, store_id in enumerate(store_ids, 1):
            amount = price + ((sid * 3 + index) % 7) * max(1000, price // 100)
            db.add(Offer(product_id=product.id, store_id=store_id, price=amount, in_stock=not (index % 4 == 0 and sid == 2), is_demo=True, updated_at=now))
        for days_ago in range(35, -1, -1):
            factor = (1.13 + (days_ago % 6) * .007) if index % 3 == 0 else (1.03 + (days_ago % 7) * .004)
            historical = round(price * factor / 1000) * 1000 if days_ago else price + ((3 + index) % 7) * max(1000, price // 100)
            db.add(PriceHistory(product_id=product.id, store_id=store_ids[0], price=historical, observed_at=now - timedelta(days=days_ago), is_demo=True))
    db.commit()
