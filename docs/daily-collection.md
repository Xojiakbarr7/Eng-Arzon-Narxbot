# Har kuni mahsulot yig‘ish va kanalga joylash

Bot **yangi mahsulotlarni** manbalardan yig‘ib, Mini App katalogini yangilaydi va Telegram kanaliga kunlik bitta xulosa yuboradi. Boshlang‘ich vaqt — **09:00, Asia/Tashkent**. Avval narxlar yig‘iladi, keyin xabar tayyorlanadi; shu sabab xabar 09:00 dan keyin keladi.

Kanal: **@arzon_narx_topamiz**. Botning kanalda administratorligi va post yozish huquqi tasdiqlandi. **2026-10-30** kuni katalogga 95 ta haqiqiy yozuv kiritildi va [10 ta taklifli birinchi kunlik post](https://t.me/arzon_narx_topamiz/3) muvaffaqiyatli yuborildi. Mahalliy Windows muhitida avtomat yoqilgan; doimiy serverga joylash hali bajarilmadi. Kompyuter yoki tegishli jarayonlar to‘xtasa, lokal xizmatlar ham to‘xtaydi.

## Qaysi manbalar ishlaydi?

| Manba | Joriy imkoniyat |
|---|---|
| Asaxiy | Ochiq katalog va mahsulot sahifalaridagi `Product` JSON-LD ma’lumotidan to‘liq UZS narxi, mavjudlik va yangi holat olinadi. Oylik to‘lov asosiy narx sifatida olinmaydi. |
| OLX | Oltita tovar yo‘nalishining ochiq sahifalaridagi `AggregateOffer` ichidan alohida e’lonlar olinadi. Faqat `NewCondition` holati va musbat UZS narxi qabul qilinadi. Ishlatilganlikni bildiruvchi zid matnli e’lonlar ham chiqariladi. Bu sotuvchining holat haqidagi ma’lumotidir; mahsulot jismonan tekshirilmagan. |
| Uzum | Ochiq katalog sahifasiga tekshiruv so‘rovi bor, lekin hozirgi SPA javobida foydalaniladigan mahsulot JSON-LD ma’lumoti topilmadi: **0 ta mahsulot**. Uzum jonli narxlari ulangan deb hisoblanmaydi. Hamkor katalog yoki tekshirilgan boshqa ochiq manba adapteri hali kerak. |

Asaxiy uchun mavjud 10 ta asosiy kategoriya yo‘nalishini qamragan 17 ta boshlang‘ich havola sozlangan. OLX uchun elektronika, bolalar, uy-bog‘, qurilish materiallari, kiyim va sport/hobbi yo‘nalishlari mavjud. Ikkala manba birgalikda katalogning 11 ta asosiy kategoriyasiga moslangan, ammo har kuni har birida yaroqli taklif chiqishi kafolatlanmaydi. Boshlang‘ich havolalar va ularning kategoriya mosligi `backend/collection-sources.json`da; bu moslikni manba assortimenti o‘zgarganda tekshiring. Bitta e’lon keng va aniqroq kategoriya sahifasida ko‘rinsa, aniqroq yo‘nalish ustun turadi.

Standart chegaralar: **har bir manbaga 40 tagacha sahifa, 200 tagacha mahsulot, so‘rovlar orasida kamida 2 soniya**. Asaxiy’da havolalar bo‘yicha cheklangan topish mavjud; OLX’da sozlangan kategoriya sahifalari o‘qiladi. Bu butun saytning barcha mahsulotlari emas. `robots.txt` yopgan yo‘llar o‘qilmaydi; kirish cheklovi yoki CAPTCHA chetlab o‘tilmaydi. Sayt formati o‘zgarsa, parserni qayta tekshirish kerak.

Cheklangan jonli tekshiruvda Asaxiy va OLX’dan jami 12 ta mos yozuv olingan. Standart 40 sahifali konfiguratsiya tekshiruvida Asaxiy’dan 22 va OLX’dan 76 yozuv o‘qildi, Asaxiy’da bitta sahifa so‘rovi xatosi qayd etildi. Uzum 0 ta taklif qaytardi. Bu to‘liq bozor qamrovi yoki barcha kategoriyalar kafolati emas.

## Windows’da ishga tushirish

Amaldagi mahalliy `.env`da `COLLECTION_ENABLED=true`, `DAILY_POST_ENABLED=true`, `DAILY_CHANNEL_ID=@arzon_narx_topamiz`, `DAILY_POST_TIME=09:00` sozlangan. Demo rejimi o‘chirilgan; katalogni Telegram botidagi yangi `/start` xabari va **Katalog** tugmasi orqali oching. Bugungi post `daily_runs`da `sent` bo‘lgani sabab xizmat qayta yoqilganda yana yuborilmaydi.

Asosiy xizmatlarni, ular to‘xtatilganidan keyin, loyiha papkasidagi PowerShell’da yoqish:

```powershell
.\scripts\start.ps1 -WithBot -WithCollector -SkipInstall
```

`-SkipInstall` kutubxonalar tayyor bo‘lganda ishlatiladi. Kollektor tayyorligini skript logdan tasdiqlaydi. `scripts/stop.ps1` kollektorni ham to‘xtatadi. Ushbu skript kompyuter yoqilganda Windows bilan avtomatik boshlanmaydi. Vaqtinchalik HTTPS gateway/tunnel alohida ishlaydi; uning ulanishi to‘xtasa [Telegram HTTPS yo‘riqnomasi](telegram-connection.md) bo‘yicha qayta ulang. Doimiy 24/7 ishlash uchun quyidagi server yo‘li kerak.

## Serverda yoqish

Avval [serverga joylash qo‘llanmasi](deployment.md) bo‘yicha production `.env`, PostgreSQL, domen va HTTPS’ni tayyorlang. Tokenlar faqat server `.env`ida saqlanadi. Bir xil token bilan kompyuteringizdagi polling bot va serverdagi polling bot bir vaqtda ishlamasin.

`.env.example`da avtomatlashtirish o‘chirilgan:

```dotenv
COLLECTION_ENABLED=false
DAILY_POST_ENABLED=false
DAILY_CHANNEL_ID=@arzon_narx_topamiz
DAILY_POST_TIME=09:00
DAILY_MAX_ITEMS=10
COLLECTION_POLL_SECONDS=60
```

Loyiha katalogida, server Ubuntu terminalida avval API va saytni yangilang:

```bash
sudo docker compose up --build -d db api web
sudo docker compose --profile collection build collector
sudo docker compose ps
```

API ishga tushishda Alembic’ning **`0002_daily_runs`** migratsiyasini ham qo‘llaydi. `collector` API `healthy` bo‘lgandan keyin ishlaydi. Baza va kanalga yozmasdan manbalarni tekshirish:

```bash
sudo docker compose --profile collection run --rm collector python -m app.daily_worker --once --dry-run
```

`--dry-run` manbalarga so‘rov yuboradi va natija sonlarini ko‘rsatadi; katalogni o‘zgartirmaydi, `daily_runs`ga yozmaydi va Telegram xabari yubormaydi. Natijada ayrim manbalar uchun 0 ta mahsulot yoki manba xatosi ko‘rinishi mumkin. Manba ishlamasa uning eski narxi yangi deb belgilanmaydi.

Natijani tekshirgach, avtomatik katalog yangilanishi va kanal postini yoqish uchun serverdagi `.env`ni tahrirlang:

```dotenv
COLLECTION_ENABLED=true
DAILY_POST_ENABLED=true
DAILY_CHANNEL_ID=@arzon_narx_topamiz
DAILY_POST_TIME=09:00
DAILY_MAX_ITEMS=10
```

So‘ng ikkala profil bilan xizmatlarni ishga tushiring:

```bash
sudo docker compose --profile telegram --profile collection up --build -d
sudo docker compose --profile telegram --profile collection ps
sudo docker compose logs --tail 100 collector
```

Faqat Mini App katalogi yangilansin desangiz, `COLLECTION_ENABLED=true`, `DAILY_POST_ENABLED=false` qiling. `.env`ni o‘zgartirgach `up -d` orqali konteynerni yangi sozlama bilan qayta yarating; oddiy `restart` yangi environment qiymatini yuklamaydi.

`--once` jadval vaqtini kutmay, shu kunlik ishni bajaradi. **`DAILY_POST_ENABLED=true` bo‘lsa, u hozirning o‘zida kanalga yuborishi mumkin.** Sinash uchun `--dry-run` ishlating. Oddiy worker 09:00 dan keyin taxminan har 60 soniyada bajarilmagan bugungi ish borligini tekshiradi. Server kunning keyinroq vaqtida yoqilsa, bugungi ish bajarilishi mumkin; o‘tgan kunlar uchun xabarlar to‘ldirib yuborilmaydi.

## Katalog va xabardagi narx ma’nosi

- Faqat joriy yig‘ishda qabul qilingan, mavjud, yangi va demo bo‘lmagan takliflar xabarga nomzod bo‘ladi. Eski katalogdan tasodifiy mahsulotlar bilan bo‘sh yig‘ish to‘ldirilmaydi.
- Har bir kategoriyaning eng arzon kuzatilgan taklifi avval tanlanadi. Kategoriyalar tartibi kunlar bo‘yicha aylanadi; qolgan joylar shu kategoriyalarning keyingi arzon takliflari bilan to‘ldiriladi. Bitta xulosada ko‘pi bilan 10 ta mahsulot bor.
- Xabar **“Kuzatilgan takliflar ichida arzonlari”** deb nomlanadi. Bu O‘zbekistondagi yoki uchala saytning butun bozoridagi eng arzon narx degan xulosa emas. Turli kategoriyadagi arzon buyumlar bir xil mahsulot deb solishtirilmaydi.
- Bir manbadagi mahsulot `source + reference` orqali yangilanadi. Turli do‘konlardagi nomi o‘xshash mahsulotlar avtomatik birlashtirilmaydi. Aynan bir xil model/variantni do‘konlararo moslashtirish alohida tasdiqlanishi kerak.
- Noma’lum yetkazish haqi nol deb ko‘rsatilmaydi. Tafsilot oynasida u tasdiqlanmagani aytiladi. Yetkazish sharti admin tomonidan tasdiqlanmaguncha shu haqiqiy taklif bilan savatchaning yakuniy narxi hisoblanmaydi.
- Narx, mavjudlik va OLX holati manba kuzatilgan paytga tegishli. Xariddan oldin do‘kon yoki e’lon sahifasini ochib qayta tekshirish kerak.

## Qayta ishga tushirish va xatolar

`daily_runs` jadvali Toshkent sanasi va kanal bo‘yicha ish holatini saqlaydi. Xizmat qayta yoqilganda ayni kun/kanal uchun xabar avtomatik takror yuborilmaydi. Bir kunlik ish tugaganidan keyin `--once` ham uni qaytarmaydi.

| Holat | Ma’nosi va keyingi qadam |
|---|---|
| `ready` | Katalog yangilangan, xabar tayyor; shu ishda kanalga yuborish o‘chiq bo‘lgan. |
| `sent` | Telegram muvaffaqiyatli javob bergan, xabar ID’si saqlangan. |
| `empty` | Shu yig‘ishdan joylashga yaroqli mahsulot topilmagan. Manba hisobotini tekshiring. |
| `failed` | Yig‘ish/import yoki Telegramning aniq rad javobi sabab ish tugamagan. Log va sozlamalarni tekshiring. |
| `collecting` | Yig‘ish davom etmoqda. Jarayon uzilgan bo‘lsa, shu kunlik ishni qo‘lda ko‘rib chiqish kerak. |
| `sending` / `uncertain` | Xabarni yuborish boshlangan, lekin yakuniy natija noma’lum bo‘lishi mumkin. Avval kanalning o‘zini tekshiring. |

Telegram so‘rovi timeout bo‘lsa, xabar aslida yetgan bo‘lishi mumkin. `uncertain` holati ko‘r-ko‘rona qayta yuborilmaydi. Uzilgan `sending` holati 5 daqiqadan keyingi tekshiruvda `uncertain`ga o‘tadi. `daily_runs` yozuvini tekshirmay o‘chirish yoki qayta yuborish takroriy post chiqarishi mumkin.

`failed`, `empty`, uzilgan `collecting` va `uncertain` ishlar ayni kun/kanal uchun avtomatik qayta urinmaydi. Muammoni tekshirib tuzating; keyingi kun yangi ish bajariladi. Bugungi ishni qayta bajarish kerak bo‘lsa, avval kanaldagi haqiqiy natija va bazadagi holatni birga tekshirib, nazoratli tiklash qiling.

Holatlarni o‘qish:

```bash
sudo docker compose logs --tail 100 collector
sudo docker compose exec -T db psql -U eng_arzon -d eng_arzon -c "SELECT day, status, item_count, telegram_message_id, error FROM daily_runs ORDER BY id DESC LIMIT 10;"
```

Kanal huquqlari, serverdagi bot tokeni va kanal nomi o‘zgarsa, ularni qayta tekshiring. Kollektor va botdan bittadan jarayon ishlating; server bazasini [joylash qo‘llanmasi](deployment.md#9-ishlatish-backup-va-yangilash) bo‘yicha zaxiralab boring.
