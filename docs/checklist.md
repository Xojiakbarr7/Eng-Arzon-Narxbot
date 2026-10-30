# MVP tekshirish ro‘yxati

Quyidagi ro‘yxat qabul testi uchun. Belgilanmagan tashqi ulanishlar loyiha kodida tayyor bo‘lsa ham, haqiqiy hisob va serverda alohida sinaladi.

## Kalitsiz lokal sinov

- [ ] `scripts/start.ps1` API va Mini App’ni ochadi.
- [ ] Bosh sahifa, katalog va narxlarda Demo belgisi bor.
- [ ] Qidiruv nom, model, kirill va lotin kiritishda ishlaydi.
- [ ] Kategoriya, do‘kon va narx filtrlari natijaga ta’sir qiladi.
- [ ] 128GB va 256GB variantlari alohida ko‘rsatiladi.
- [ ] Mahsulot sahifasi do‘kon taklifi, yangilanish sanasi, yetkazish va yakuniy summani ko‘rsatadi.
- [ ] Demo mahsulotda haqiqiy “sotib olish” havolasi yo‘q.
- [ ] Sevimli va kuzatuv yangilagandan keyin ham saqlanadi.
- [ ] 5 ta mahsulotdan savatcha tuzilib, do‘konlar bo‘yicha eng arzon taqsimot chiqadi.
- [ ] Bepul yetkazish chegarasi o‘zgartirilganda natija mos o‘zgaradi.
- [ ] Omborda yo‘q yoki eskirgan taklif hisobga olinmaydi.
- [ ] GTIN to‘g‘ri nazorat raqami bilan topiladi; buzilgan kod xato beradi.
- [ ] Kamera bo‘lmasa yoki ruxsat rad etilsa, qo‘lda kod kiritish qoladi.
- [ ] Yetarli tarix bo‘lmasa olish/kutish xulosasi berilmaydi.
- [ ] Demo tarixga asoslangan xulosa aniq belgilangan.
- [ ] Profil tili, hududi va bildirishnoma sozlamalari saqlanadi.
- [ ] Admin tokensiz yopiq; xatoli CSV bazaga qisman yozilmaydi.
- [ ] Hisobni o‘chirish sevimli, kuzatuv va shaxsiy yozuvlarni o‘chiradi.

## Avtomatlashtirilgan tekshiruvlar

- [ ] `backend/` ichida `python -m pytest -q` o‘tadi.
- [ ] Loyiha ildizida `python -m pytest bot/tests -q` o‘tadi.
- [ ] `frontend/` ichida `pnpm run build` yoki `npm run build` o‘tadi.
- [ ] Alembic yangi bazada `upgrade head`ni bajaradi.
- [ ] PowerShell start, stop va backup skriptlari parserdan o‘tadi.

## Haqiqiy ishga tushirishdan oldin

- [ ] Domen va HTTPS sertifikat sozlangan.
- [ ] BotFather tokeni, Mini App domeni va menyu tekshirilgan.
- [ ] Production’da `DEMO_MODE=false`; demo profilga anonim kirish yo‘q.
- [ ] Haqiqiy kataloglardan foydalanish ruxsati tasdiqlangan.
- [ ] Do‘kon yetkazish shartlari va mahsulot havolalari tekshirilgan.
- [ ] Haqiqiy narx tushishi Telegramga yetkazilgan, takrorlash cheklovi sinalgan.
- [ ] Backup olinib alohida test bazasida tiklangan.
- [ ] Monitoring va loglar yoqilgan; maxfiy qiymatlar yozilmaydi.
- [ ] Mobil Android/iPhone Telegram kamera va initData bilan sinalgan.

## Keyingi bosqichlar

Kunlik avtomatni alohida tekshirish: [kunlik yig‘ish qo‘llanmasi](daily-collection.md). Serverda kollektor dry-run’i, yangi holat, manba qamrovi, kanal huquqi va `daily_runs` holatlari tekshirilsin. Asaxiy/OLX kollektoriga qaramay Uzum va boshqa hamkor API’lar hali ulanmagan.

Generativ AI, rasm bilan mahsulot aniqlash, to‘lov va Premium, referral bonus, barcha admin rollari, kengaytirilgan analitika hamda avtomatik hamkor kataloglari alohida integratsiya sifatida qo‘shiladi. Ular ushbu versiyada ishlayotgandek ko‘rsatilmaydi.
