# Yakuniy tekshiruv natijalari

Sana: **2026-10-30**, Asia/Tashkent. Hisobot mahalliy demo sinovlari va haqiqiy katalogni ishga tushirish natijalarini qayd etadi.

## O‘tgan tekshiruvlar

| Tekshiruv | Natija |
|---|---|
| Backend unit va integration testlari | 60 ta o‘tdi; PostgreSQL talab qiladigan 2 ta holat mahalliy muhitda o‘tkazib yuborildi |
| Telegram botning tarmoqqa chiqmaydigan testlari | 24 ta o‘tdi |
| Savatcha optimizatori | 32 tasodifiy holatda mustaqil to‘liq sanash algoritmi bilan bir xil natija |
| TypeScript va Vite production build | O‘tdi |
| Windows `start.ps1 -SkipInstall` | API va yig‘ilgan Mini App ochildi; ikkala HTTP javob 200 |
| Windows start, stop, backup sintaksisi | Parser xatosi yo‘q |
| SQLite migration | Upgrade, schema check, downgrade, qayta upgrade o‘tdi |
| PostgreSQL migration | Offline SQL muvaffaqiyatli yaratildi |
| SQLite backup | `backup.ps1` ishladi; `integrity_check=ok`, 20 mahsulot tiklanadigan nusxada bor |

Backend testida Starlette’ning HTTPX TestClient integratsiyasi uchun eskirish ogohlantirishi chiqadi; bu testlarni yiqitmaydi. Sinovlar ajratilgan vaqtinchalik bazalarda bajariladi.

## Server uchun tayyorgarlik

- PostgreSQL’da kategoriya ID’larini qo‘lda 1–11 qilib kiritish avtomatik ID ketma-ketligini siljitmas edi. Bu birinchi ishga tushishda takroriy ID xatosini keltirib chiqarishi mumkin edi. Kategoriya, do‘kon va demo mahsulot ID’lari endi bazaning o‘zida ajratiladi; bog‘lanishlar shu haqiqiy ID’lardan foydalanadi.
- Yangi testlar production va demo katalogining birinchi ishga tushishini, qayta chaqirishda yozuvlar takrorlanmasligini va keyin yangi yozuv qo‘shilishini tekshiradi. PostgreSQL holatlarida ketma-ketliklar 101, 201, 301 dan boshlanib, bog‘lanishlar 1 dan boshlanishga qaram emasligi tekshiriladi.
- GitHub CI konfiguratsiyasiga PostgreSQL 16 xizmati qo‘shildi. Ushbu o‘zgarishdan keyingi CI yoki haqiqiy PostgreSQL serveri hali ishga tushirilmadi; mahalliy SQLite holatlari o‘tdi.
- [Serverga joylash qo‘llanmasi](deployment.md) Ubuntu, Docker, domen, HTTPS va Telegram botni kompyuterdan serverga ko‘chirish tartibini beradi.

## Kunlik katalog va kanal

- `collectors.py`, `collection_ingest.py`, `daily_worker.py` hamda `0002_daily_runs` migratsiyasi qo‘shildi. Docker’da `collection` profili mavjud.
- Kunlik boshlanish 09:00 Asia/Tashkent, ko‘pi bilan 10 taklifli bitta kanal xulosasi. Holat bazada saqlanadi; uzilgan yoki natijasi noma’lum Telegram so‘rovi avtomatik takror yuborilmaydi.
- `@arzon_narx_topamiz` uchun bot administrator va `can_post_messages=true` ekani Bot API orqali tekshirildi. 2026-10-30 kuni 95 ta haqiqiy mahsulot va narx import qilinib, [10 ta taklifli birinchi post](https://t.me/arzon_narx_topamiz/3) yuborildi. Telegram muvaffaqiyatli javobi va xabar ID’si bazada saqlandi. Qayta ishga tushgan kollektor `previous=sent` qaytarib, takror yubormadi.
- Mahalliy `.env`da demo rejimi o‘chirildi va ikkala kunlik flag yoqildi. O‘zgartirishdan oldin SQLite va `.env`ning zaxirasi `backups/`ga olindi; ular ZIP’ga kiritilmaydi. Release `.env.example`ida avtomat hali ham o‘chiq — serverda alohida sozlanadi.
- `start.ps1 -WithBot -WithCollector -SkipInstall` haqiqiy ishga tushdi. API, web, bot, kollektor, public gateway va tunnel jarayonlari tekshiruv paytida ishlayotgan edi. Bot polling va kollektorning tayyorlik logi tasdiqlandi. PowerShell skriptlarining parser tekshiruvi va kollektor konfiguratsiyasi uchun oltita ajratilgan holat o‘tdi.
- HTTPS sahifa, JS, CSS va health javoblari 200; anonim katalog 401, public admin va ichki yo‘llar 404. Telegram imzoli katalog so‘rovi 200 va **95 ta** haqiqiy yozuv qaytardi. Mahalliy bazadagi eski demo yozuvlar foydalanuvchi katalogida ko‘rsatilmaydi.
- Baza va Telegramga yozmaydigan jonli `--dry-run`: cheklangan sinovda Asaxiy 1, OLX 11, Uzum 0 taklif. Standart konfiguratsiya sinovida Asaxiy 40 sahifadan 22 taklif (bir sahifa xatosi), OLX beshta yo‘nalishdan 76 taklif. Keyin qo‘shilgan qurilish materiallari yo‘nalishi alohida tekshiruvda 17 ta yangi taklif qaytardi. Bu sonlar turli sinov vaqtiga tegishli, ularni yagona umumiy katalog soni deb qo‘shmang.
- Uzum kategoriya va aniq SKU sahifasiga oddiy HTTPS so‘rovlarida foydalaniladigan JSON-LD topilmadi; Uzum narxlari hali ulangan emas. Oddiy Chrome/Playwright render sinovi bu Windows muhitida brauzerni ishga tushirishni tasdiqlamadi; himoyani chetlab o‘tish ishlatilmadi. Asaxiy va OLX natijalari manba ko‘rsatgan narx va holat bo‘yicha olinadi.
- Testlar to‘liq narxni oylik to‘lovdan ajratish, `AggregateOffer.lowPrice`ni mahsulot sifatida olmaslik, ishlatilgan/nosoz e’lonlarni chiqarish, URL va robots cheklovlari, sahifa limiti, SKU/e’lon ID’si bilan identifikatsiya, kategoriya ustunligi, qayta import, qo‘lda tasdiqlangan GTIN/atributlarni saqlash, noma’lum yetkazish, kunlik deduplikatsiya, timeout va uzoq yig‘ish holatlarini tekshiradi.
- SQLite’da `0002` upgrade, Alembic schema check, `0001`gacha downgrade va qayta upgrade o‘tdi. Haqiqiy PostgreSQL/Docker va doimiy server hali tekshirilmadi. Kanal yetkazishi yuqoridagi mahalliy ishga tushishda tasdiqlandi.
- [Kunlik yig‘ishni yoqish va qamrov chegaralari](daily-collection.md).

## Botni ulashdagi tuzatishlar

- BotFather tokeni Telegram `getMe` orqali tekshirildi: `@arzonini_topamiz_bot`.
- Yangilangan bot qayta ishga tushirildi; polling boshlangani va API sog‘lomligi tasdiqlandi. Xatolik, token rad etilishi yoki ikkinchi poller to‘qnashuvi aniqlanmadi.
- HTTPS bo‘lmaganda katalog xabarlar orqali ishlaydi; savatcha ID va miqdorlar bilan hisoblanadi. Bu jarayonlar 24 ta bot testiga kiritilgan.
- Band port sabab o‘lgan jarayon PID’sini saqlab, eski serverni yangi deb ko‘rsatish xatosi tuzatildi. Band portdagi sinovda skript ishni rad etdi va mavjud PID fayllari o‘zgarmadi.
- Tashqi HTTPS kirishi foydalanuvchi ruxsati bilan ishga tushirildi. Telegram menyusining `web_app` manzili Bot API orqali qayta o‘qilib tasdiqlandi. HTTPS sahifa, JS, CSS va health javoblari 200; anonim katalog so‘rovi 401; admin/ichki API 404. Telegram imzoli katalog so‘rovi 200 va 20 ta demo mahsulot qaytardi.
- Cloudflare Quick Tunnel vaqtinchalik: ulanish jarayoni to‘xtasa yoki kompyuter o‘chsa, manzil ishlamaydi. Doimiy serverga joylash alohida bajariladi.

## Brauzerda sinalgan jarayonlar

- Katalogda 20 ta demo mahsulot va kategoriya tugmalari ko‘rindi; API’da 97 ta kategoriya bor.
- `samsung a55` qidiruvi 128 GB va 256 GB variantlarini alohida qaytardi.
- Mahsulot oynasida beshta do‘kon taklifi, sana, yetkazish va saqlangan tarix ochildi.
- Sevimli va maqsadli narx kuzatuvi saqlandi; sahifa qayta ochilganda saqlangan holat qaytdi.
- Besh xil mahsulot savatchaga qo‘shildi. Demo hisob: **7 668 000 so‘m**, ikki do‘kon; eng arzon yagona do‘kon bilan solishtirganda **116 700 so‘m** farq.
- Demo GTIN `2000000000022` Samsung Galaxy A55 128 GB’ni topdi. Kiritilgan 4 000 000 so‘mlik do‘kon narxi bilan farq **410 000 so‘m** bo‘ldi. Bu kod hamda narxlar faqat sinov uchun.
- Hudud va bildirishnoma sozlamalari UI orqali o‘zgartirildi va API’da saqlangani tekshirildi. Qorong‘i mavzu almashtirildi.
- Brauzer kengligiga mos yig‘ilgan interfeys vizual ko‘rildi; qisqargan menyudagi belgi tugmalariga accessibility nomlari qo‘shildi.

## Tashqi muhitda alohida sinaladigan ishlar

- Haqiqiy Telegram akkaunti, BotFather tokeni va HTTPS domen bilan botni ulash.
- Android va iPhone’dagi Telegram Mini App kamera ruxsati va fizik shtrix-kodni skanerlash. Qo‘lda GTIN kiritish yuqorida sinaldi.
- Haqiqiy narx pasayishi xabarini Telegram tarmog‘iga yetkazish. Navbat va takrorlash chegaralari lokal testlarda tekshirildi.
- PostgreSQL serverida Docker Compose’ni ishga tushirish; ushbu qurilmada Docker mavjud bo‘lmagani uchun konteynerlar ishga tushirilmagan.
- Hamkor katalogi va API ulanishlarini olish. Ochiq sahifa kollektorining joriy ishlaydigan manbalari Asaxiy va OLX; bu do‘konlarning rasmiy hamkor API integratsiyasi emas.
- Generativ AI, rasmni aniqlash, Premium to‘lovi va referral mukofotlari bu MVP’da ulanmagan. Narx bo‘yicha maslahat kalitsiz statistik hisobdan foydalanadi.

ZIP ichiga `.env`, tokenlar, shaxsiy baza, loglar, virtual muhit yoki `node_modules` kiritilmaydi. Tayyor frontend `frontend/dist/` ichida qo‘shiladi; Windows skripti uni manbadan qayta yig‘adi.
