"""Long polling bot. Run from project root: python -m bot.main."""
import asyncio
import contextlib
import logging
import os
import re
from html import escape
from pathlib import Path
from urllib.parse import urlencode, urlparse

import httpx
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BotCommand, CallbackQuery, ErrorEvent, InlineKeyboardButton,
    InlineKeyboardMarkup, KeyboardButton, MenuButtonWebApp, Message,
    ReplyKeyboardMarkup, WebAppInfo,
)
from dotenv import dotenv_values, load_dotenv

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(ENV_FILE)
log = logging.getLogger("eng_arzon.bot")
router = Router()
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")

MENU = [
    ["🛍 Katalog", "🔎 Mahsulot qidirish"],
    ["💰 Eng arzon mahsulotlar", "🔥 Chegirmalar"],
    ["🧺 Eng arzon savatcha", "📷 Shtrix-kod"],
    ["🤖 AI xarid yordamchisi", "📸 Rasm bilan qidirish"],
    ["🔔 Narx kuzatuvlari", "❤️ Sevimlilarim"],
    ["⚖️ AI bilan solishtirish", "📊 Narxlar tarixi"],
    ["🎁 Bonuslar", "👤 Profilim"],
    ["⚙️ Sozlamalar", "☎️ Yordam"],
]
keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=t) for t in row] for row in MENU],
    resize_keyboard=True,
    input_field_placeholder="Mahsulot nomi yoki shtrix-kodni yozing",
)


class Flow(StatesGroup):
    search = State()
    barcode = State()
    assistant = State()
    basket = State()


class ApiError(Exception):
    pass


class Api:
    def __init__(self, client: httpx.AsyncClient, token: str):
        self.client = client
        self.token = token

    async def call(self, method, path, user_id=None, **kwargs):
        headers = {"X-Bot-Token": self.token}
        if user_id is not None:
            headers["X-Telegram-User-Id"] = str(user_id)
        try:
            response = await self.client.request(method, path, headers=headers, **kwargs)
        except httpx.HTTPError as exc:
            raise ApiError("Serverga ulanib bo‘lmadi. Birozdan keyin qayta urinib ko‘ring.") from exc
        if response.is_error:
            detail = response.json().get("detail", "So‘rov bajarilmadi") if response.headers.get("content-type", "").startswith("application/json") else "So‘rov bajarilmadi"
            if not isinstance(detail, str):
                detail = "Ma’lumot formati noto‘g‘ri. /help buyrug‘ini ko‘ring."
            raise ApiError(detail)
        return response.json() if response.content else None


def money(value):
    if value is None:
        return "Yangilangan taklif yo‘q"
    return f"{int(value):,}".replace(",", " ") + " so‘m"


def current_miniapp_url():
    if ENV_FILE.is_file():
        return str(dotenv_values(ENV_FILE).get("MINI_APP_URL") or "").strip()
    return os.getenv("MINI_APP_URL", "").strip()


def miniapp(view="catalog"):
    url = current_miniapp_url()
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        return None
    separator = "&" if "?" in url else "?"
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🛍 Mini App’ni ochish", web_app=WebAppInfo(url=url + separator + urlencode({"view": view})))
    ]])


async def open_app(message, view="catalog", text="Katalog va narxlarni Mini App’da ko‘ring."):
    markup = miniapp(view)
    await message.answer(text, reply_markup=markup)
    if markup is None:
        await message.answer("Mini App uchun administrator HTTPS manzilni MINI_APP_URL orqali sozlashi kerak. Hozir botda mahsulot nomini yozib qidirishingiz mumkin.")


async def show_products(message, products, title="Topilgan mahsulotlar"):
    if not products:
        await message.answer("Hozircha mahsulot topilmadi. Boshqa nom yoki modelni kiriting.")
        return
    await message.answer(f"<b>{escape(title)}</b>")
    for product in products[:6]:
        pid = product["id"]
        badge = "\n🧪 Demo narxlar" if product.get("is_demo") else ""
        await message.answer(
            f"<b>{escape(product['name'])}</b>\n"
            f"{money(product.get('min_price'))} · {product.get('store_count', 0)} do‘kon\n"
            f"Mahsulot ID: <code>{pid}</code>{badge}\n"
            f"Kuzatish: <code>/watch {pid} NARX</code>\n"
            f"Tarix: <code>/history {pid}</code>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❤️ Saqlash", callback_data=f"fav:{pid}")],
                *([[InlineKeyboardButton(text="🛍 Do‘konda ko‘rish", url=product["buy_url"])]]
                  if isinstance(product.get("buy_url"), str) and product["buy_url"].startswith("https://") else []),
            ]),
        )


def is_admin(user_id: int) -> bool:
    raw = os.getenv("ADMIN_TELEGRAM_IDS", "")
    return str(user_id) in {part.strip() for part in raw.split(",") if part.strip().isascii() and part.strip().isdigit()}


@router.message(Command("myid"))
async def show_my_id(message: Message):
    await message.answer(f"Sizning Telegram ID: <code>{message.from_user.id}</code>")


@router.message(Command("admin"))
async def admin_panel(message: Message, api: Api):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Sizga admin ruxsati berilmagan. ID: /myid")
        return
    data = await api.call("GET", "/api/admin/stats", message.from_user.id)
    labels = {"products": "Mahsulotlar", "categories": "Kategoriyalar", "stores": "Do‘konlar", "offers": "Takliflar", "users": "Foydalanuvchilar", "alerts": "Kuzatuvlar", "imports": "Importlar"}
    lines = ["🛡 <b>ADMIN PANEL</b>", ""]
    lines.extend(f"• {labels.get(k,k)}: <b>{v}</b>" for k,v in data.items() if isinstance(v,int))
    markup = miniapp("admin")
    await message.answer("\n".join(lines), reply_markup=markup)


@router.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "🛍 <b>ENG ARZON NARX BOT PRO</b>\n\n"
        "Mahsulotni toping, narxlarni solishtiring va savatchangizni tejab yig‘ing.\n"
        "Katalogdagi demo ma’lumotlar alohida belgilangan.\n\n"
        "Mahsulot nomi, model yoki shtrix-kodni yozing. /help — buyruqlar.",
        reply_markup=keyboard,
    )
    if miniapp():
        await open_app(message)


@router.message(Command("help"))
@router.message(F.text == "☎️ Yordam")
async def help_command(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "<b>Buyruqlar</b>\n"
        "/search iphone — qidirish\n"
        "/ai 3 mln so‘mgacha telefon — AI xarid yordamchisi\n"
        "/best — arzon mahsulotlar\n"
        "/deals — narx tarixidan chegirmalar\n"
        "/favorites — sevimlilar\n"
        "/watch 1 3000000 — 1-ID mahsulot narxini kuzatish\n"
        "/alerts — kuzatuvlar\n"
        "/unwatch 1 — 1-ID kuzatuvni o‘chirish\n"
        "/history 1 — narx tarixi va olish/kutish tahlili\n"
        "/barcode KOD — shtrix-kod bo‘yicha qidirish\n"
        "/catalog — mahsulot katalogi\n"
        "/basket 1,2,3,4,5 — ID’lardan eng arzon savatcha\n"
        "/ai MATN — katalogga asoslangan oddiy yordamchi\n"
        "/cancel — joriy kiritishni bekor qilish\n\n"
        "Kamera Mini App ichida ishlaydi. To‘lov, rasmni AI bilan aniqlash va hamkor do‘konlarning jonli API’lari hali ulanmagan."
    )


@router.message(Command("cancel"))
async def cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Asosiy menyu.", reply_markup=keyboard)


@router.message(Command("search"))
@router.message(F.text == "🔎 Mahsulot qidirish")
async def search_command(message: Message, state: FSMContext, api: Api):
    await state.clear()
    query = (message.text or "").partition(" ")[2].strip() if message.text.startswith("/") else ""
    if not query:
        await state.set_state(Flow.search)
        await message.answer("Mahsulot nomi yoki modelini yozing. Masalan: Samsung A55")
        return
    data = await api.call("GET", "/api/products", message.from_user.id, params={"q": query, "page_size": 6})
    await show_products(message, data["items"])


@router.message(Command("best"))
@router.message(F.text == "💰 Eng arzon mahsulotlar")
async def best(message: Message, state: FSMContext, api: Api):
    await state.clear()
    data = await api.call("GET", "/api/products", message.from_user.id, params={"sort": "price_asc", "page_size": 6})
    await show_products(message, data["items"], "Eng arzon mahsulotlar")


@router.message(Command("deals"))
@router.message(F.text == "🔥 Chegirmalar")
async def deals(message: Message, state: FSMContext, api: Api):
    await state.clear()
    data = await api.call("GET", "/api/products", message.from_user.id, params={"sort": "discount", "page_size": 100})
    products = [p for p in data["items"] if (p.get("discount_percent") or 0) > 0]
    await show_products(message, products, "Saqlangan narx tarixiga nisbatan arzonlashganlar")


@router.message(Command("favorites"))
@router.message(F.text == "❤️ Sevimlilarim")
async def favorites(message: Message, state: FSMContext, api: Api):
    await state.clear()
    products = await api.call("GET", "/api/favorites", message.from_user.id)
    await show_products(message, products, "Sevimlilarim")


@router.callback_query(F.data.startswith("fav:"))
async def favorite_callback(callback: CallbackQuery, api: Api):
    pid = int(callback.data.split(":")[1])
    await api.call("POST", f"/api/favorites/{pid}", callback.from_user.id)
    await callback.answer("Sevimlilarga saqlandi")


@router.message(Command("watch"))
async def watch(message: Message, state: FSMContext, api: Api):
    await state.clear()
    parts = (message.text or "").split()
    if len(parts) != 3 or not parts[1].isdigit() or not parts[2].isdigit() or int(parts[2]) <= 0:
        await message.answer("Format: <code>/watch MAHSULOT_ID NARX</code>\nMasalan: <code>/watch 1 3000000</code>")
        return
    await api.call("POST", "/api/alerts", message.from_user.id, json={"product_id": int(parts[1]), "target_price": int(parts[2])})
    await message.answer("🔔 Kuzatuv saqlandi. Narx belgilangan summaga tushsa, bot xabar beradi. Demo kuzatuvlar jonli narx emas.")


@router.message(Command("alerts"))
@router.message(F.text == "🔔 Narx kuzatuvlari")
async def alerts(message: Message, state: FSMContext, api: Api):
    await state.clear()
    rows = await api.call("GET", "/api/alerts", message.from_user.id)
    if not rows:
        await message.answer("Kuzatuvlar yo‘q. Qidiruvda mahsulot ID’sini oling, so‘ng /watch ID NARX yozing.")
        return
    lines = ["<b>Narx kuzatuvlari</b>"]
    for row in rows[:30]:
        title = row.get("product_name", f"Mahsulot {row.get('product_id')}")
        lines.append(f"{escape(title)}: {money(row.get('target_price'))}\nO‘chirish: <code>/unwatch {row['id']}</code>")
    await message.answer("\n\n".join(lines))


@router.message(Command("unwatch"))
async def unwatch(message: Message, state: FSMContext, api: Api):
    await state.clear()
    arg = (message.text or "").partition(" ")[2].strip()
    if not arg.isdigit():
        await message.answer("Format: <code>/unwatch KUZATUV_ID</code>")
        return
    await api.call("DELETE", f"/api/alerts/{int(arg)}", message.from_user.id)
    await message.answer("Kuzatuv o‘chirildi.")


@router.message(Command("history"))
@router.message(F.text == "📊 Narxlar tarixi")
async def history(message: Message, state: FSMContext, api: Api):
    await state.clear()
    arg = (message.text or "").partition(" ")[2].strip() if message.text.startswith("/") else ""
    if not arg.isdigit():
        await message.answer("Mahsulot ID’sini qidiruvdan oling: <code>/history 1</code>. Grafik Mini App mahsulot sahifasida mavjud.")
        return
    data = await api.call("GET", f"/api/products/{int(arg)}", message.from_user.id)
    insight = data["insight"]
    await message.answer(f"<b>{escape(data['name'])}</b>\n\n<b>{escape(insight['title'])}</b>\n{escape(insight['explanation'])}\n\nNamunalar: {insight.get('sample_count', 0)} ta · {insight.get('span_days', 0)} kun\n" + ("🧪 Demo tarix asosidagi tahlil." if insight.get("is_demo") else "Saqlangan tarix asosidagi statistik tahlil; kelajak narxi kafolatlanmaydi."))


@router.message(Command("barcode"))
@router.message(F.text == "📷 Shtrix-kod")
async def barcode_command(message: Message, state: FSMContext, api: Api):
    await state.clear()
    code = (message.text or "").partition(" ")[2].strip() if message.text.startswith("/") else ""
    if not code:
        await state.set_state(Flow.barcode)
        await message.answer("Shtrix-kod raqamlarini yuboring (EAN/GTIN). Kameradan skanerlash uchun Mini App’ni oching.", reply_markup=miniapp("scan"))
        return
    if not code.isascii() or not code.isdigit() or len(code) not in (8, 12, 13, 14):
        await message.answer("Kod 8, 12, 13 yoki 14 raqamdan iborat bo‘lishi kerak. Masalan: /barcode KOD")
        return
    data = await api.call("GET", f"/api/barcode/{code}", message.from_user.id)
    product = data.get("product", data)
    await show_products(message, [product], "Shtrix-kod bo‘yicha mos mahsulot")


@router.message(Command("ai"))
@router.message(F.text == "🤖 AI xarid yordamchisi")
async def assistant_command(message: Message, state: FSMContext, api: Api):
    await state.clear()
    text = (message.text or "").partition(" ")[2].strip() if message.text.startswith("/") else ""
    if not text:
        await state.set_state(Flow.assistant)
        await message.answer("🤖 Xarid yordamchisiga savolingizni yozing.\nMasalan: 3 million so‘mgacha telefon topib ber.\nYoki: Samsung va Redmi telefonlarini solishtir.\n\nSuhbatni davom ettirishingiz mumkin. Tugatish: /cancel")
        return
    await state.set_state(Flow.assistant)
    await state.update_data(history=[text])
    data = await api.call("POST", "/api/assistant", message.from_user.id, json={"message": text})
    await message.answer(escape(data.get("answer", data.get("message", "Katalogdan mos mahsulotlar tekshirildi."))))
    if data.get("products"):
        await show_products(message, data["products"], "Katalogdagi mos mahsulotlar")


@router.message(Command("basket"))
@router.message(F.text == "🧺 Eng arzon savatcha")
async def basket(message: Message, state: FSMContext, api: Api):
    await state.clear()
    text = message.text or ""
    argument = text.partition(" ")[2].strip() if text.startswith("/") else ""
    if argument:
        await calculate_basket(message, state, api, argument)
        return
    if miniapp("basket"):
        await open_app(message, "basket", "🧺 Katalogdan mahsulotlarni savatchaga qo‘shing (8 tagacha tur). Hisoblagich har bir do‘konning yetkazish haqini bir marta qo‘shib, eng arzon kombinatsiyani topadi.")
        return
    await state.set_state(Flow.basket)
    await message.answer(
        "🧺 Katalog yoki qidiruvdagi mahsulot ID’larini yozing.\n"
        "Masalan: <code>1,2,3,4,5</code>\n"
        "Bir mahsulotdan ikki dona: <code>1x2,3,5</code>\n"
        "8 tagacha tur, har biridan 20 tagacha dona. /cancel — bekor qilish."
    )


def parse_basket_items(text):
    tokens = re.split(r"[,\s]+", text.strip())
    if not text.strip() or len(tokens) > 8:
        raise ValueError("1–8 ta mahsulot ID’sini kiriting")
    quantities = {}
    for token in tokens:
        match = re.fullmatch(r"([0-9]{1,10})(?:[xX]([0-9]{1,2}))?", token)
        if not match:
            raise ValueError("Format: 1,2,3 yoki 1x2,3,5")
        pid, quantity = int(match[1]), int(match[2] or "1")
        if pid <= 0 or not 1 <= quantity <= 20:
            raise ValueError("Musbat ID va 1–20 dona kiriting")
        quantities[pid] = quantities.get(pid, 0) + quantity
        if quantities[pid] > 20:
            raise ValueError("Bir mahsulotdan ko‘pi bilan 20 dona")
    return [{"product_id": pid, "quantity": quantity} for pid, quantity in quantities.items()]


async def calculate_basket(message, state, api, text):
    try:
        items = parse_basket_items(text)
    except ValueError as exc:
        await state.set_state(Flow.basket)
        await message.answer(escape(str(exc)) + "\nMasalan: <code>1,2,3,4,5</code>. /cancel — bekor qilish.")
        return
    profile = await api.call("GET", "/api/profile", message.from_user.id)
    result = await api.call("POST", "/api/basket/optimize", message.from_user.id, json={"items": items, "region": profile.get("region", "tashkent")})
    lines = ["🧺 <b>Eng arzon savatcha</b>"]
    if result.get("is_demo"):
        lines.append("🧪 Demo narxlar va yetkazish shartlari. Haqiqiy buyurtma berilmadi.")
    for store in result["stores"]:
        lines.append("\n<b>" + escape(store["store_name"]) + "</b>")
        for item in result["items"]:
            if item["store_id"] == store["store_id"]:
                lines.append(f"• {escape(item['name'])} × {item['quantity']}: {money(item['subtotal'])}")
        lines.append(f"Yetkazish: {money(store['delivery_fee'])}")
        lines.append(f"Do‘kon jami: {money(store['total'])}")
    lines.append(f"\n<b>Yakuniy summa: {money(result['total'])}</b>")
    if result.get("single_store_total") is not None:
        lines.append(f"Bitta do‘kondan eng arzon: {money(result['single_store_total'])}")
        lines.append(f"Farq: {money(result.get('savings', 0))}")
    await message.answer("\n".join(lines))
    await state.clear()


@router.message(Command("catalog"))
@router.message(F.text == "🛍 Katalog")
async def catalog(message: Message, state: FSMContext, api: Api):
    await state.clear()
    if miniapp():
        await open_app(message)
        return
    text = message.text or ""
    argument = text.partition(" ")[2].strip() if text.startswith("/") else ""
    if argument and (not re.fullmatch(r"[0-9]{1,5}", argument) or int(argument) < 1):
        await message.answer("Format: <code>/catalog</code> yoki <code>/catalog 2</code>")
        return
    page = int(argument or "1")
    data = await api.call("GET", "/api/products", message.from_user.id, params={"page": page, "page_size": 6, "sort": "price_asc"})
    total = data.get("total", len(data["items"]))
    pages = max(1, (total + 5) // 6)
    await show_products(message, data["items"], f"Mahsulot katalogi · {page}/{pages}")
    if page < pages:
        await message.answer(f"Keyingi sahifa: <code>/catalog {page + 1}</code>\nSavatcha: <code>/basket 1,2,3,4,5</code> — o‘zingiz tanlagan ID’larni yozing.")


@router.message(F.text == "⚖️ AI bilan solishtirish")
async def compare(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(Flow.assistant)
    await message.answer("🤖 Qaysi mahsulotlarni solishtiray? Masalan: Samsung va Redmi telefonlarini solishtir.\nSavolni yuboring; keyin davom ettirishingiz mumkin. /cancel — chiqish.")


@router.message(F.text.in_({"👤 Profilim", "⚙️ Sozlamalar"}))
async def profile(message: Message, state: FSMContext, api: Api):
    await state.clear()
    data = await api.call("GET", "/api/profile", message.from_user.id)
    await message.answer(f"👤 Telegram ID: <code>{message.from_user.id}</code>\nTil: {escape(data.get('language', 'uz'))}\nHudud: {escape(data.get('region', 'tashkent'))}", reply_markup=miniapp("profile"))


@router.message(F.text == "🎁 Bonuslar")
async def bonuses(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Referral bonuslari va Premium obuna bu versiyada ulanmagan. Hozir to‘lov olinmaydi va bonus hisoblanmaydi.")


@router.message(F.photo | (F.text == "📸 Rasm bilan qidirish"))
async def photo(message: Message, state: FSMContext):
    await state.set_state(Flow.search)
    await message.answer("Rasmni AI bilan aniqlash hali ulanmagan. Mahsulot modeli yoki nomini yozing; katalogdan qidiraman.")


@router.message(Flow.barcode, F.text)
async def barcode_input(message: Message, state: FSMContext, api: Api):
    await state.clear()
    code = message.text.strip()
    if not code.isdigit() or len(code) not in (8, 12, 13, 14):
        await message.answer("Kod 8, 12, 13 yoki 14 raqamdan iborat bo‘lishi kerak. Qayta: /barcode KOD")
        return
    data = await api.call("GET", f"/api/barcode/{code}", message.from_user.id)
    await show_products(message, [data.get("product", data)])


@router.message(Flow.assistant, F.text)
async def assistant_input(message: Message, state: FSMContext, api: Api):
    text = (message.text or "")[:1000]
    session = await state.get_data()
    history = [h for h in session.get("history", []) if isinstance(h, str)][-4:]
    data = await api.call("POST", "/api/assistant", message.from_user.id, json={"message": text, "history": history})
    await state.update_data(history=(history + [text])[-4:])
    await message.answer(escape(data.get("answer", data.get("message", "Qidiruv yakunlandi."))))
    if data.get("products"):
        await show_products(message, data["products"], "AI tanlagan katalog takliflari")


@router.message(Flow.basket, F.text)
async def basket_input(message: Message, state: FSMContext, api: Api):
    await calculate_basket(message, state, api, message.text)


@router.message(F.text)
async def search_input(message: Message, state: FSMContext, api: Api):
    await state.clear()
    query = message.text.strip()
    if query.startswith("/"):
        await message.answer("Buyruq topilmadi. /help buyrug‘ini ko‘ring.")
        return
    if query.isdigit() and len(query) in (8, 12, 13, 14):
        data = await api.call("GET", f"/api/barcode/{query}", message.from_user.id)
        await show_products(message, [data.get("product", data)])
        return
    intent = re.search(r"arzon|narx|topib ber|solishtir|taqqosla|qaysi yaxsh|\bmln\b|million|\bbyudjet\b", query.casefold())
    if intent and len(query) >= 5:
        data = await api.call("POST", "/api/assistant", message.from_user.id, json={"message": query[:1000]})
        await message.answer(escape(data.get("answer", "Katalog tekshirildi.")))
        if data.get("products"):
            await show_products(message, data["products"], "Tanlangan takliflar")
        await state.set_state(Flow.assistant)
        await state.update_data(history=[query[:1000]])
        return
    data = await api.call("GET", "/api/products", message.from_user.id, params={"q": query[:200], "page_size": 6})
    await show_products(message, data["items"])


@router.errors()
async def error_handler(event: ErrorEvent):
    if isinstance(event.exception, ApiError):
        text = escape(str(event.exception))
        if event.update.message:
            await event.update.message.answer(text)
        elif event.update.callback_query:
            await event.update.callback_query.answer(str(event.exception)[:180], show_alert=True)
        return True
    log.exception("Bot handler failed", exc_info=event.exception)
    if event.update.message:
        await event.update.message.answer("So‘rovda xatolik yuz berdi. Qayta urinib ko‘ring yoki /cancel yozing.")
    return True


async def notification_loop(bot: Bot, api: Api):
    """Leased outbox: retry errors; backend de-duplicates alert price events."""
    while True:
        try:
            data = await api.call("POST", "/api/internal/notifications/claim")
            for item in data.get("items", []):
                delivered, error = False, None
                try:
                    await bot.send_message(chat_id=int(item["user_id"]), text=escape(item["text"]))
                    delivered = True
                except Exception as exc:
                    error = type(exc).__name__
                    log.warning("Telegram notification failed: %s", error)
                await api.call("POST", f"/api/internal/notifications/{item['id']}/ack", json={"delivered": delivered, "error": error})
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("Notification worker iteration failed: %s", type(exc).__name__)
        await asyncio.sleep(30)


async def main():
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s %(message)s")
    token = os.getenv("BOT_TOKEN", "").strip()
    internal_token = os.getenv("BOT_INTERNAL_TOKEN", "").strip()
    if not token:
        raise SystemExit("BOT_TOKEN sozlanmagan. Telegram botni ishga tushirish uchun BotFather tokenini .env fayliga saqlang. API va Mini App tokensiz demo rejimda ishlaydi.")
    if len(internal_token) < 32:
        raise SystemExit("BOT_INTERNAL_TOKEN kamida 32 belgili maxfiy qiymat bo‘lishi kerak. API va bot uchun bir xil bo‘lsin.")
    async with httpx.AsyncClient(base_url=os.getenv("API_BASE_URL", "http://127.0.0.1:8000"), timeout=20) as client:
        api = Api(client, internal_token)
        bot = Bot(token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        dp = Dispatcher()
        dp.include_router(router)
        dp["api"] = api
        await bot.set_my_commands([
            BotCommand(command="start", description="Asosiy menyu"),
            BotCommand(command="search", description="Mahsulot qidirish"),
            BotCommand(command="basket", description="Eng arzon savatcha"),
            BotCommand(command="alerts", description="Narx kuzatuvlari"),
            BotCommand(command="favorites", description="Sevimlilarim"),
            BotCommand(command="help", description="Yordam"),
            BotCommand(command="myid", description="Telegram ID raqamim"),
        ])
        markup = miniapp()
        if markup:
            await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(text="Katalog", web_app=markup.inline_keyboard[0][0].web_app))
        worker = asyncio.create_task(notification_loop(bot, api))
        try:
            await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
        finally:
            worker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await worker
            await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
