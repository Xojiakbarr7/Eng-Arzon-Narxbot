# GitHub’ga yuklash

1. `eng-arzon-bot-pro-github.zip`ni kompyuteringizda oching.
2. Ichidagi `eng-arzon-bot-pro` papkasiga kiring.
3. GitHub’da yangi bo‘sh repository yarating; bu bosqichda alohida README yoki `.gitignore` qo‘shmang, ular loyiha ichida bor.
4. Shu papkaning **ichidagi fayl va papkalarni repository ildiziga** yuklang. ZIP faylning o‘zini yuklash kodni alohida fayllar sifatida ochmaydi.
5. `.github/`, `.gitignore`, `.dockerignore` va `.env.example` ham yuklanganini tekshiring. GitHub sahifasida `README.md`, `backend/`, `frontend/`, `bot/` va `docker-compose.yml` bir xil darajada turishi kerak.

Bu arxiv faqat manba kodini o‘z ichiga oladi. Haqiqiy `.env`, bot tokeni, bazalar, loglar, zaxiralar, `.venv`, `node_modules` va yig‘ilgan `frontend/dist` qo‘shilmagan. Frontend ishga tushirishda yoki Docker build vaqtida qayta yig‘iladi. Kutubxonalar versiyalari uchun lock fayllari kiritilgan.

## Git orqali yuklash

ZIP’dan ochilgan loyiha papkasida terminal oching. Quyidagi manzilni o‘zingiz yaratgan repository manzili bilan almashtiring:

```bash
git init
git add .
git status --short
git commit -m "Initial project"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPOSITORY.git
git push -u origin main
```

Commitdan oldin `git status` ro‘yxatida haqiqiy `.env`, tokenli fayl yoki shaxsiy baza yo‘qligini tekshiring. Login kerak bo‘lsa Git’ning autentifikatsiya oynasidan foydalaning; tokenni remote URL yoki kod ichiga yozmang.

`.github/workflows/ci.yml` backend, PostgreSQL boshlang‘ich katalogi, bot va frontend tekshiruvlari uchun sozlangan. Birinchi push’dan keyin GitHub Actions natijasini ko‘ring; bu ZIP tayyorlash vaqtida GitHub’da ishga tushirilmagan.

## Ishga tushirish

Repository’ni yuklash botni serverda avtomatik ishga tushirmaydi. Ishlatiladigan kompyuter yoki serverda `.env.example`dan shaxsiy `.env` yarating va tokenlarni o‘sha faylda sozlang.

- [Asosiy yo‘riqnoma](README.md)
- [Serverga joylash](docs/deployment.md)
- [Kunlik katalog va kanal](docs/daily-collection.md)

Hozir Asaxiy va OLX ochiq sahifalari uchun cheklangan kollektor mavjud. Uzum ulanishi hali tayyor emas. Kunlik xabarlar va haqiqiy katalog alohida konfiguratsiya bilan yoqiladi.
