# ENG ARZON NARX BOT PRO

O‘zbekiston bozori uchun ishga tushiriladigan MVP: **Telegram bot + React Mini App + FastAPI + ma’lumotlar bazasi**. Narxlar taqqoslash, savatcha optimallashtirish va statistik narx tahlili bitta loyihada.

GitHub’ga yuklash: [arxivni ochish va repository’ga joylash](GITHUB.md). Token va shaxsiy bazalar manba kodiga kiritilmaydi.

**Tekshiruv:** backend, bot, frontend build, Windows ishga tushirish va SQLite backup tekshirildi. PostgreSQL uchun yana 2 ta boshlang‘ich katalog testi CI’ga qo‘shildi; mahalliy qurilmada PostgreSQL mavjud emas. Test sonlari va tashqi tekshiruv chegaralari: [yakuniy tekshiruv hisoboti](docs/verification.md).

**Muhim holat:** boshlang‘ich katalog demo. Asaxiy va OLX ochiq sahifalaridan cheklangan avtomatik yig‘ish va kunlik kanal xulosasi qo‘shilgan; serverda alohida yoqiladi. Uzum tekshiruvda ishlatiladigan narx ma’lumotini bermadi va hali ulanmagan. Olcha, Texnomart, MediaPark hamkor API’lari ulanmagan. Demo yozuvlar haqiqiy narxlardan ajratiladi. Haqiqiy katalog CSV orqali ham qo‘shiladi.

**Kunlik avtomat:** yangi mahsulotlarni Mini App’ga kiritish, kategoriyalardagi arzon kuzatilgan takliflardan 10 tagachasini `@arzon_narx_topamiz` kanaliga yuborish, 09:00 Toshkent vaqti va qayta ishga tushganda postni takrorlamaslik mavjud. Yoqish va manbalar chegarasi: [kunlik yig‘ish qo‘llanmasi](docs/daily-collection.md). Turli do‘konlarning o‘xshash nomli mahsulotlari avtomatik birlashtirilmaydi.

## Ishlaydigan imkoniyatlar

- O‘zbekcha Mini App: qidiruv, kategoriya, saralash, filtrlar, mahsulot tafsiloti, do‘kon narxlari, saqlangan narx tarixi, sevimlilar va kuzatuvlar.
- **Eng arzon savatcha:** 8 tagacha mahsulot turi, har biridan 20 tagacha; do‘konlarning yetkazish haqi va bepul yetkazish chegarasi hisoblanadi. Algoritm barcha mumkin bo‘lgan do‘kon taqsimotlari orasidan eng arzon variantni aniq topadi.
- **Do‘konda shtrix-kod bilan tekshirish:** kamera qo‘llangan brauzerda skaner; aks holda kodni qo‘lda kiritish. GTIN nazorat raqami tekshiriladi, faqat katalogdagi aynan shu variant topiladi.
- **“Olish yoki kutish?”:** yetarli tarix bo‘lsa, bugungi narx avvalgi kunlar o‘rtachasiga taqqoslanadi. Yetarli ma’lumot bo‘lmasa, bu ochiq aytiladi. Bu generativ AI yoki kelajak narxini bashorat qilish emas.
- Admin: statistika, mahsulot/kategoriya API’lari, do‘kon shartlari, CSV tekshirish va atomar import, audit yozuvlari.
- Telegram bot: qidirish, narxlar, sevimlilar, kuzatuv yaratish/o‘chirish, narx tarixi, shtrix-kod, Mini App bo‘limlarini ochish.
- Telegram xabarlari: haqiqiy, yangi, omborda bor taklif narxi maqsadga tushganda outbox orqali yuborish; takrorlashni cheklash va qayta urinish.
- Telegram `initData` imzosi va muddati tekshiriladi; bot va admin uchun alohida server tokenlari.

Rasmni AI bilan aniqlash, generativ AI chat, Premium to‘lovi, referral mukofoti, murakkab admin rollari va barcha do‘konlarni avtomatik yangilash ushbu MVP’da yoqilmagan. Menyular bunga aniq izoh beradi. Katalog yordamchisi hozir qoidaviy qidiruvdan foydalanadi.

## Windows’da tez ishga tushirish

Python **3.11+**, Node.js **22+** va npm o‘rnatilgan bo‘lsin. Loyiha papkasida PowerShell oching:

```powershell
.\scripts\start.ps1
```

Skript `.env` yaratadi, lokal admin va bot server tokenlarini tasodifiy yaratib shu faylda saqlaydi, `.venv` hamda kutubxonalarni tayyorlaydi, TypeScript’ni tekshiradi, frontendni yig‘adi, API va tayyor Mini App’ni fon rejimida ochadi. Tokenlar terminalga chiqarilmaydi. Kodni tahrir qilgandan keyin to‘xtatib qayta ishga tushiring; rivojlantirish uchun `frontend/` ichida `pnpm run dev` mavjud.

- Mini App: [http://127.0.0.1:5173](http://127.0.0.1:5173)
- API hujjati: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- Holat: [http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health)

Python maxsus joyda bo‘lsa:

```powershell
.\scripts\start.ps1 -Python 'C:\Python312\python.exe'
```

Kutubxonalar oldin o‘rnatilgan bo‘lsa `-SkipInstall` ishlating. To‘xtatish:

```powershell
.\scripts\stop.ps1
```

Loglar `run/` ichida. Bitta loyihani bir portda takror ishga tushirmang. Birinchi ishga tushishda internet kerak.

## Qo‘lda ishga tushirish

```powershell
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt -r bot/requirements.txt
Set-Location backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Boshqa terminalda loyiha ichida:

```powershell
Set-Location frontend
npm install
npm run dev
```

Lokal demo autentifikatsiyasiz bitta demo profil orqali ishlaydi. Uni ochiq internetga chiqarmang. `.env` faylida `ADMIN_TOKEN` bo‘sh bo‘lsa admin API o‘chiq; admin uchun kamida 32 belgili tasodifiy token belgilang.

## Telegram botni ulash

1. BotFather orqali bot yarating; tokenni `.env` faylidagi `BOT_TOKEN`ga saqlang.
2. Mini App’ni HTTPS domeningizga joylang; `.env`dagi `MINI_APP_URL`ga to‘liq HTTPS manzilni kiriting.
3. `BOT_INTERNAL_TOKEN` API va botda bir xil, kamida 32 ta tasodifiy belgi bo‘lsin. Frontendga hech bir server tokenini bermang.
4. BotFather’da Mini App domeni va menyu tugmasini sozlang. Bot ishga tushganda ham menyu tugmasini qo‘yadi.
5. Ishga tushirish:

```powershell
.\scripts\start.ps1 -WithBot
# yoki API allaqachon ishlayotganida:
.\.venv\Scripts\python.exe -m bot.main
```

`BOT_TOKEN` bo‘lmasa bot aniq xabar bilan to‘xtaydi; API va Mini App demo rejimda ishlayveradi. Mini App tugmasi HTTPS manzilsiz ko‘rsatilmaydi. Botning matnli qidiruvi API mavjud bo‘lsa HTTPS Mini App’siz ham ishlaydi.

HTTPS hali ulanmagan bo‘lsa ham **Katalog** tugmasi mahsulotlarni Telegram xabarida ko‘rsatadi; `/catalog 2` keyingi sahifani ochadi. `/basket 1,2,3,4,5` mahsulot ID’lari bo‘yicha haqiqiy hisobni bajaradi; `1x2,3` birinchi mahsulotdan ikki dona va uchinchi mahsulotdan bir dona degani. Grafik interfeysni ulash: [Telegram HTTPS kirishi](docs/telegram-connection.md).

## Docker

Docker Desktop yoki Docker Engine + Compose kerak. `.env` yarating va `POSTGRES_PASSWORD`ni alfanumerik tasodifiy qiymatga sozlang (`start.ps1` uni ham yaratadi):

```powershell
docker compose up --build -d
# Telegram botni ham qo‘shish:
docker compose --profile telegram up --build -d
```

Ilova `http://localhost:8080`da ochiladi. PostgreSQL Docker volume’da saqlanadi. `web` faqat `127.0.0.1`ga bog‘lanadi; ommaviy HTTPS uchun [joylash qo‘llanmasi](docs/deployment.md)ga qarang. Docker ichida SQLite ishlatilmaydi: API PostgreSQLga ulanadi.

## Arxitektura va fayllar

```text
backend/
  app/             FastAPI, SQLAlchemy modellar, xavfsizlik, katalog servislar
    adapters/      do‘konlar uchun standart adapter shartnomasi
  alembic/         migratsiyalar
  tests/           biznes qoidalari va API testlari
frontend/
  src/             React + TypeScript Mini App va admin interfeysi
bot/
  main.py          aiogram 3 long-polling bot va bildirishnoma jo‘natuvchi
infra/             Dockerfile’lar va Nginx
scripts/           Windows start, stop, backup
docs/              API, joylash, integratsiya va tekshirish qo‘llanmalari
.github/workflows/ci.yml
docker-compose.yml
.env.example
```

Backendning asosiy jadvallari: users, categories, products, stores, offers, price_history, favorites, price_alerts, notification_history, search_history, audit_logs, import_jobs. Har bir `products` yozuvi bitta aniq model/variantni bildiradi; masalan 128GB va 256GB alohida mahsulot. To‘liq PRO jadval va tijoriy modullarini keyingi migratsiyalar bilan kengaytirish mumkin.

SQLite lokal ishga tushishda avtomatik tayyorlanadi. Serverda migratsiya:

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m alembic upgrade head
```

## Hisoblash qoidalari

Savatcha mahsulotning eng past individual narxini shunchaki yig‘maydi. U har do‘kon savatining oraliq summasi, yetkazish haqi va bepul yetkazish chegarasini hisoblaydi. Bir turdagi mahsulotning barcha miqdori bitta do‘konga biriktiriladi. Yaroqsiz, eskirgan va omborda yo‘q takliflar hisobga olinmaydi. Kerakli mahsulot uchun taklif topilmasa, to‘liq savatchaga uydirma narx chiqarilmaydi.

Narx tahlili bugungi kunni bazaviy o‘rtachadan chiqaradi. Kamida **14 ta alohida kun narxi va 14 kunlik davr** kerak. Narx tarix o‘rtachasidan 7% yoki ko‘proq past bo‘lsa “qulay”, 7% yoki ko‘proq yuqori bo‘lsa “kutib kuzatish mumkin”, qolganida “odatiy” deyiladi. Chegirma ko‘rsatkichi saqlangan avvalgi narxlardan hisoblanadi. Grafikda kuzatilmagan kunlarga nuqta yaratilmaydi.

Toshkent va viloyatlar tanlanadi. Demo rejimida Toshkentdan tashqariga qo‘shimcha yetkazish haqi — sinov ssenariysi. Haqiqiy tarifni hamkor do‘kondan tasdiqlab admin sozlamasiga kiriting; region bo‘yicha murakkab jonli tarif API’si hozir ulanmagan.

## Test va backup

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m pytest -q
Set-Location ..\frontend
npm run build
Set-Location ..
.\.venv\Scripts\python.exe -m pytest bot/tests -q
.\scripts\backup.ps1
# Docker PostgreSQL:
.\scripts\backup.ps1 -Postgres
```

Backup fayllari maxfiy ma’lumotlarni o‘z ichiga olishi mumkin; `backups/` Git’dan chiqarilgan. Avtomatik jadvalni serverda cron yoki Windows Task Scheduler bilan `backup.ps1`ga belgilang. Backup’ni davriy qayta tiklab tekshiring.

Keyingi ma’lumotlar: [API](docs/api.md), [do‘kon ulash](docs/integrations.md), [joylash](docs/deployment.md), [MVP tekshirish ro‘yxati](docs/checklist.md).
