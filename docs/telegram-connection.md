# Telegram katalogini ulash

Botning matnli qidiruvi `BOT_TOKEN` bilan ishlaydi. Telegram ichidagi Mini App uchun internetdan ochiladigan HTTPS manzil kerak. `127.0.0.1` faqat ilova ishlayotgan kompyuterga tegishli.

## Himoyalangan sinov kirishi

Loyihadagi `app.public_app:app` yig‘ilgan `frontend/dist/` fayllarini va API’ni bitta portdan beradi. Demo mahsulotlarni ko‘rishga ruxsat saqlanadi, lekin tashqi API kirishi faqat haqiqiy Telegram `initData` imzosidan keyin ochiladi. Admin va botning ichki API yo‘llari bu kirishda yopiq.

Backend papkasida:

```powershell
..\.venv\Scripts\python.exe -m uvicorn app.public_app:app --host 127.0.0.1 --port 8010
```

Cloudflare’ning [rasmiy yuklab olish sahifasidan](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/downloads/) `cloudflared` oling. Alohida terminalda:

```powershell
cloudflared tunnel --url http://127.0.0.1:8010 --no-autoupdate --protocol http2
```

Chop etilgan `https://....trycloudflare.com` manzilni loyiha ildizida ulang:

```powershell
.\.venv\Scripts\python.exe scripts\configure_miniapp.py https://SIZNING-MANZILINGIZ.trycloudflare.com
```

Skript HTTPS xizmatini, anonim kirish yopilganini va Telegram menyusini tekshiradi. So‘ng manzilni `.env`ga saqlaydi. Token terminalga chiqarilmaydi.

Telegram’da botni qayta ochib, pastdagi **Katalog** menyusini bosing. Mini App tashqi brauzerda oddiy havola bilan ochilsa, Telegram sessiyasi bo‘lmagani sabab katalog API’si 401 qaytaradi; bot ichidan oching.

Bu vaqtinchalik sinov ulanishi: kompyuter, himoyalangan API va tunnel ishlashi kerak. Tunnel qayta ishga tushganda manzil o‘zgaradi va yangi manzilni qayta ulash talab qilinadi. Doimiy ishlash uchun domen va server kerak. [Cloudflare Quick Tunnels hujjati](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/).

## Windows’da kunlik kollektor

`.env`da `COLLECTION_ENABLED=true` sozlang. Kanalga yuborish kerak bo‘lsa `DAILY_POST_ENABLED=true`, `DAILY_CHANNEL_ID=@arzon_narx_topamiz` va `BOT_TOKEN` ham sozlangan bo‘lsin. API va sayt allaqachon ishlayotgan bo‘lsa, avval ularni `scripts\stop.ps1` bilan to‘xtating. Keyin loyiha ildizidan:

```powershell
.\scripts\start.ps1 -WithBot -WithCollector
```

`-WithCollector` alohida so‘ralgandagina kollektor ochiladi; kompyuter avtomatik yoqilishiga vazifa o‘rnatilmaydi. API tayyor bo‘lgach kollektor ishlaydi, `run\collector.err.log`da tayyorlik va ish natijalari ko‘rinadi. `scripts\stop.ps1` kollektorni ham to‘xtatadi. Kompyuter o‘chsa kunlik yig‘ish ishlamaydi; doimiy ish uchun [serverdagi kollektor](daily-collection.md)dan foydalaning.
