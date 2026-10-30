# Yangi do‘konni ulash

## Hozirgi holat

`base.py`dagi hamkor API adapterlari hali `disconnected`. Alohida `collectors.py` Asaxiy va OLX’ning ochiq JSON-LD ma’lumotlarini cheklangan so‘rovlar bilan o‘qiydi. Asaxiy’da to‘liq mahsulot narxi va yangi holat, OLX’da faqat yangi deb belgilangan alohida e’lonlar olinadi. Batafsil sozlash: [kunlik yig‘ish](daily-collection.md). Kirish cheklovlari chetlab o‘tilmaydi; narxlar o‘zidan yaratilmaydi.

Uzum’ning ochiq HTML javoblarida mahsulot JSON-LD ma’lumoti topilmadi. Hozirgi HTTP kollektor Uzum narxlarini olmaydi; sahifaning oddiy brauzerda ko‘rinishi bu kollektor ham o‘qiydi degani emas. Tasdiqlangan rendered adapter yoki hamkor katalogi kerak. [Rasmiy seller API](https://api-seller.uzum.uz/api/seller-openapi/swagger/swagger-ui/swagger-ui/index.html)ni umumiy bozor qidiruv API’si sifatida ishlatmang.

Uzumning [rasmiy seller OpenAPI](https://api-seller.uzum.uz/api/seller-openapi/swagger/swagger-ui/webjars/swagger-ui/index.html)si sotuvchi do‘konlari, SKU va buyurtmalarini boshqarish uchun mavjud. Bunday API borligi butun marketplace katalogini olish huquqini anglatmaydi. Har do‘kon uchun aynan kerakli katalog ma’lumotidan foydalanish ruxsatini alohida tekshiring. Qolgan do‘konlarda API umuman yo‘q degan xulosa berilmagan; hamkorlik shartnomasi va tasdiqlangan hujjat olinmaguncha adapter yoqilmaydi.

## Ishlaydigan yo‘l: CSV

Admin interfeysidan yoki `/api/admin/import` orqali import qiling:

```csv
product_id,store_id,price,currency,in_stock,url
```

To‘ldirish uchun `docs/catalog-template.csv` fayli bor. Mahsulot va do‘kon bazada mavjud bo‘lsin. Demo mahsulotga haqiqiy taklif qo‘shilmaydi. Haqiqiy mahsulotni admin API orqali alohida yarating. Do‘konning yetkazish shartlari admin tasdiqlamaguncha import rad etiladi.

URL `https://` orqali aynan do‘kon domeniga tegishli bo‘lishi kerak. Domen `ALLOWED_STORE_DOMAINS` ro‘yxatida bo‘lsin. Importda server bu URL’ni yuklab olmaydi; u faqat tekshirilgan xarid havolasi sifatida saqlanadi.

Avval `commit=false` bilan tekshiring. Javobdagi `errors` bo‘sh bo‘lgach `commit=true` bilan qayta yuboring. Import to‘liq tranzaksiyada yoziladi; bitta xato bo‘lsa narxlar qisman saqlanmaydi.

## Hamkor adapteri

`backend/app/adapters/base.py`dagi `StoreAdapter` va `NormalizedOffer` kontraktidan foydalaning. Standart yozuv:

| Maydon | Talab |
|---|---|
| product_id | Aniq model/variantning katalog ID’si |
| store_id | Tasdiqlangan do‘kon ID’si |
| price | UZS musbat butun narx |
| currency | UZS |
| in_stock | Haqiqiy mavjudlik |
| url | Ruxsatli HTTPS mahsulot havolasi |
| observed_at | Manbadan olingan UTC vaqt |
| source_reference | Partner mahsulot ID’si yoki kuzatiladigan identifikator |

1. Do‘konning rasmiy API hujjati, autentifikatsiyasi, limitlari va foydalanish shartlarini oling.
2. API kalitini faqat backend environment’da saqlang; brauzerga chiqarmang.
3. HTTPX orqali timeout, limit va qayta urinish bilan adapter yozing. CAPTCHA va kirish cheklovlarini chetlab o‘tmang.
4. EAN/GTIN, ishlab chiqaruvchi kodi va variant atributlari asosida moslashtiring. 128GB bilan 256GBni birlashtirmang. Noaniq moslik admin tasdig‘ini kutsin.
5. Tashqi qiymatlarni import qoidalariga teng tekshiring, so‘ng `offers` va `price_history`ni bitta tranzaksiyada yangilang.
6. Xatoda mavjud narxning sanasini “yangi” qilib qo‘ymang. Eskirgan narxlar `OFFER_MAX_AGE_HOURS` orqali hisobdan chiqariladi.
7. Tayyor `daily_worker.py` va `collection-sources.json` sozlamasiga adapter ulang; do‘kon bilan kelishilgan yangilash chastotasi, haqiqiy tarix va kanal deduplikatsiyasini tekshiring. Joriy avtomatik import mahsulotlarni manba/SKU yoki e’lon ID’si bo‘yicha alohida saqlaydi, do‘konlararo avtomatik moslikni taxmin qilmaydi.

## Yetkazish va region

MVP’da do‘kon uchun bitta yetkazish haqi va bepul yetkazish chegarasi bor. Demo rejimdagi viloyat qo‘shimchasi faqat sinov ssenariysi. Haqiqiy partner regionga qarab tarif qilsa, `delivery()`ni ruxsatli tarif jadvali yoki API bilan kengaytiring. Noma’lum tarifni nol deb ko‘rsatmasdan foydalanuvchiga yetkazish hali tasdiqlanmaganini bildiring.
