# API qo‘llanmasi

OpenAPI sxemasi: `/openapi.json`, interaktiv hujjat: `/docs`. API prefiksi `/api`.

## Autentifikatsiya

- Lokal `DEMO_MODE=true`: bitta demo profil, Telegram kalitisiz ko‘rish va sinash.
- Telegram Mini App: `X-Telegram-Init-Data` sarlavhasida `window.Telegram.WebApp.initData`ning aynan xom qiymati. Backend HMAC va `auth_date`ni tekshiradi; `initDataUnsafe`ga ishonilmaydi.
- Server bot: `X-Bot-Token` + `X-Telegram-User-Id`. Bu sarlavhalarni foydalanuvchi brauzeridan yubormang; token faqat serverlarda saqlanadi.
- Admin: `Authorization: Bearer ADMIN_TOKEN`. Kamida 32 belgili tasodifiy token. Tokenni query stringga qo‘ymang.

## Asosiy marshrutlar

| Metod | Yo‘l | Vazifa |
|---|---|---|
| GET | `/api/health` | Xizmat holati |
| GET | `/api/categories` | Daraxt kategoriyalar |
| GET | `/api/stores` | Do‘konlar va ulanish holati |
| GET | `/api/products` | Qidiruv va filtrlar |
| GET | `/api/products/{id}` | Takliflar, tarix va statistik tavsiya |
| GET | `/api/barcode/{code}` | GTIN nazorat raqami va katalogdan aniq variant |
| GET/POST/DELETE | `/api/favorites`, `/api/favorites/{id}` | Sevimlilar |
| GET/POST | `/api/alerts` | Narx kuzatuvlari |
| PATCH/DELETE | `/api/alerts/{id}` | Kuzatuvni o‘zgartirish yoki o‘chirish |
| POST | `/api/basket/optimize` | Yetkazish bilan optimal savatcha |
| POST | `/api/assistant` | Katalogga asoslangan qoidaviy yordamchi |
| GET/PATCH/DELETE | `/api/profile` | Profil, til, hudud, ma’lumotlarni o‘chirish |
| GET | `/api/admin/stats` | Admin statistika |
| POST | `/api/admin/import` | CSV tekshirish va import |
| POST | `/api/internal/notifications/claim` | Bot uchun navbatni ijara bilan olish |
| POST | `/api/internal/notifications/{id}/ack` | Yuborish natijasi |

Qidiruv natijasi `{items,total,page,page_size}`. Har bir mahsulotda `id`, `name`, `brand`, `model`, `attributes`, `barcode`, `min_price`, `store_count`, `is_demo`, `discount_percent` bor. `min_price=null` yangi, mavjud taklif yo‘qligini bildiradi; nol narx emas.

Taklifda `delivery_fee` va `total_price` qiymati `null` bo‘lsa, tanlangan hudud uchun yetkazish haqi tasdiqlanmagan. `shipping_notice` sababini tushuntiradi. Noma’lum xarajat bepul deb hisoblanmaydi. Haqiqiy import uchun hozir Toshkent shahrining admin tasdiqlagan yetkazish shartlari qo‘llanadi; boshqa hududlarda savatcha hisoblash xatosi ochiq ko‘rsatiladi. Demo hududlaridagi shartlar faqat sinov ssenariysi.

## Savatcha misoli

```json
{
  "items": [
    {"product_id": 1, "quantity": 1},
    {"product_id": 2, "quantity": 2}
  ],
  "region": "tashkent"
}
```

1–8 tur, har biridan 1–20 dona. API noto‘liq savatcha uchun `409` qaytaradi. Yetkazish har foydalanilgan do‘kon uchun bir marta hisoblanadi. Bir turdagi birliklar bir do‘kondan olinadi.

## Kuzatuv misoli

```json
{"product_id": 1, "target_price": 3000000, "enabled": true}
```

Demo takliflar Telegram bildirishnomasini yaratmaydi. Haqiqiy taklif eskirgan yoki mavjud emas bo‘lsa ham xabar yuborilmaydi. Outbox muvaffaqiyatli yuborishni belgilaydi va xatolikdan so‘ng qayta urinadi. Telegramning xabarni qabul qilgani bilan bazadagi tasdiq orasida uzilish bo‘lsa, kamdan-kam takror xabar bo‘lishi mumkin; tashqi tarmoqqa mutlaq bir marta yetkazish va’da qilinmaydi.

Har kuzatuv uchun bir UTC kunida ko‘pi bilan bitta yangi bildirishnoma voqeasi yaratiladi. Yuborish xatolari besh martagacha qayta sinanadi; ishchi olgan yozuvning ijara muddati besh daqiqa. SQLite uchun bitta API va bitta bot jarayonidan foydalaning. PostgreSQL’da navbat olish tranzaksiya qulfi bilan ketma-ket bajariladi.

## CSV import

Admin token bilan `POST /api/admin/import`:

```json
{
  "csv_text": "product_id,store_id,price,currency,in_stock,url\n21,1,3200000,UZS,true,https://uzum.uz/uz/product/HAQIQIY-ID\n",
  "commit": false
}
```

Avval haqiqiy mahsulot yarating va do‘konning yetkazish shartlarini tasdiqlang. Yuqoridagi ID va havolani haqiqiy ma’lumotga almashtirish shart. `commit=false` faqat tekshiradi; xatolar bartaraf etilgach `commit=true` yuboriladi. Bitta xato bo‘lsa butun import yozilmaydi. Ko‘pi bilan 1000 qator; ruxsatli HTTPS do‘kon domeni, UZS valyuta, musbat butun narx va mavjud mahsulot/do‘kon ID talab qilinadi. Demo mahsulotga haqiqiy narx aralashtirish taqiqlangan.

## Xatolar

`401` — sessiya yoki token yaroqsiz; `404` — topilmadi; `409` — savatchada mavjud taklif yo‘q; `422` — format yoki biznes qoida xatosi; `429` — so‘rovlar chegarasi. Frontend xatoni ko‘rsatadi va qayta urinadi. Server tokenlari hamda to‘liq `initData`ni logga yozmang.
