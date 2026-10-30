# Haqiqiy mahsulot rasmlari va kunlik e’lonlar

## Manbalar va ishonchlilik
- Mini App real mahsulot rasmi mavjud bo‘lsa HTTPS manbadan ko‘rsatadi, bo‘lmasa «Rasm mavjud emas». Rasm chizib mahsulot suratidek ko‘rsatmaydi.
- Har kartada eng past kuzatilgan narx va original do‘kon havolasi chiqadi.
- Haqiqiy chegirma oldingi kamida 7 kun kuzatilgan narxlar bilan solishtirilgandagina ko‘rsatiladi.
- Telegram kanalida har mahsulot alohida fotosurat, narx va xarid tugmasi bilan chiqadi; rasmsiz mahsulot avtomatik foto postga olinmaydi.
- Asaxiy va OLX ochiq kataloglaridan robots.txt va cheklangan so‘rovlar asosida mahsulotlar olinadi. Uzum ochiq SPA katalogida yaroqli ma’lumot bo‘lmasa 0 ta mahsulot qaytadi. Uzum rasmiy Seller API butun bozor katalogi emas.
- Hamma do‘konning barcha chegirmalari kafolatlanmaydi. Soxta narx/rasm/havola yaratilmaydi.

## Render sozlash
Backend Eng-Arzon-Narxbot-2 Environment:

DEMO_MODE=false
COLLECTION_ENABLED=true
DAILY_POST_ENABLED=true
DAILY_CHANNEL_ID=@arzon_narx_topamiz
DAILY_POST_TIME=09:00
DAILY_MAX_ITEMS=10

BOT_TOKEN va BOT_INTERNAL_TOKEN mavjud maxfiy qiymatida qoladi. Mini App frontend VITE_API_BASE_URL backend serverga ulangan bo‘lishi kerak.

Uyg‘otish uchun .github/workflows/daily-catalog.yml har kuni UTC 04:05 da /api/health manziliga murojaat qiladi (Toshkent 09:05). GitHub Actions jadvali va bepul Render xizmatining uyg‘onishi vaqt kafolatini bermaydi.

## Ma’lumotlar saqlanishi
Render bepul Web Service lokal SQLite faylini redeploy yoki qayta ishga tushganda yo‘qotishi mumkin. Real katalog va daily_runs takroriy post nazorati uchun PostgreSQL DATABASE_URL zarur.
Render PostgreSQL -> Internal Database URL ni Render backend Environment ichida DATABASE_URL ga qo‘ying; SQLAlchemy uchun postgresql:// prefiksini postgresql+psycopg:// ga almashtiring. Maxfiy URLni GitHub yoki chatda oshkor qilmang.
Bepul PostgreSQL 30 kundan keyin tugaydi; doimiy foydalanishda uzluksiz bazaga o‘tish kerak.

## Nazorat
Render loglarida 'Daily collection scheduled' va 'Daily worker:' yozuvlarini tekshiring. DailyRun sent bo‘lsa barcha alohida rasmli postlar yuborilgan; source_report ning oxiridagi posted ro‘yxati message_id larni saqlaydi. Empty — yaroqli rasmli taklif yo‘q. Uncertain — Telegram natijasi noma’lum, takror jo‘natish xavfli.
