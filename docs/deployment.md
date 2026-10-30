# Botni Ubuntu serverda ishlatish

Quyidagi yo‘l yangi **Ubuntu 24.04 LTS VPS** uchun: Docker ilova va bazani ishlatadi, serverdagi Nginx esa domenni HTTPS bilan ochadi. Server ishlayotganida kompyuteringizni o‘chirishingiz mumkin. Oddiy PHP shared hosting ushbu Docker loyihasini ishlatish uchun mos emas.

Bu yo‘riqnomada `deployuser`, `203.0.113.10` va `bot.example.uz` — namuna. Ularni serverdagi SSH foydalanuvchingiz, haqiqiy IP va domen bilan almashtiring. Buyruqlar yangi o‘rnatish uchun; ishlayotgan serverni yangilash uchun pastdagi alohida bo‘limdan foydalaning.

## 1. Server va domenni tayyorlash

- Ubuntu 24.04 LTS VPS, SSH kirishi va `sudo` huquqi kerak. Boshlang‘ich resurs sifatida 2 vCPU, 2 GB RAM va 20 GB diskdan boshlash mumkin; yakuniy talab foydalanuvchi va katalog hajmiga bog‘liq.
- Domen DNS boshqaruvida `bot` subdomenining **A** yozuvini server IPv4 manziliga yo‘naltiring. Shunda manzil `bot.example.uz` bo‘ladi. Agar AAAA yozuvi bo‘lsa, u ham ayni serverning ishlaydigan IPv6 manzilini ko‘rsatishi kerak.
- Hosting firewallida haqiqiy SSH portingizni, TCP **80** va **443**ni ruxsat eting. PostgreSQL, 8000 va 8080 portlarini ommaga ochish kerak emas.
- Hozirgi `trycloudflare.com` manzili kompyuteringizdagi vaqtinchalik tunnel. Server uchun o‘z domeningiz ishlatiladi.

Windows PowerShell’dan serverga kiring:

```powershell
ssh deployuser@203.0.113.10
```

## 2. Docker va server dasturlarini o‘rnatish

Quyidagilar **serverning Ubuntu terminalida** bajariladi. Docker oldindan o‘rnatilgan bo‘lsa, avval `sudo docker version` va `sudo docker compose version` bilan tekshiring. Mavjud o‘rnatishni qayta o‘rnatmang. Yangi Ubuntu uchun [Docker’ning rasmiy apt yo‘riqnomasi](https://docs.docker.com/engine/install/ubuntu/) asosidagi buyruqlar:

```bash
sudo apt update
sudo apt install -y ca-certificates curl unzip nginx snapd openssl nano
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
sudo tee /etc/apt/sources.list.d/docker.sources > /dev/null <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker nginx
sudo docker run --rm hello-world
sudo docker compose version
```

Eski `docker.io`, `podman-docker` yoki boshqa Docker paketlari o‘rnatilgan serverda rasmiy yo‘riqnomaning moslik bo‘limini avval tekshiring.

## 3. ZIP faylni serverga yuborish

Yangi **Windows PowerShell** oynasida quyidagini bajaring. Bu loyiha ZIP’ini yuboradi; mahalliy `.env`, tokenlar va demo baza ZIP ichiga kiritilmagan.

```powershell
scp "C:\Users\tilla\Documents\Codex\2026-10-27\men-yana-qo-shishni-tavsiya-qiladigan\outputs\eng-arzon-bot-pro.zip" deployuser@203.0.113.10:~/
```

Endi **server terminalida**:

```bash
mkdir -p ~/apps
unzip ~/eng-arzon-bot-pro.zip -d ~/apps
cd ~/apps/eng-arzon-bot-pro
```

Keyingi Docker buyruqlarini aynan shu katalogdan bajaring. Serverda Node.js yoki Python’ni alohida o‘rnatish talab qilinmaydi: ular Docker image ichida tayyorlanadi.

## 4. Server `.env` faylini sozlash

Faqat birinchi o‘rnatishda:

```bash
umask 077
cp .env.example .env
chmod 600 .env
sed -i "s/^BOT_INTERNAL_TOKEN=.*/BOT_INTERNAL_TOKEN=$(openssl rand -hex 32)/" .env
sed -i "s/^ADMIN_TOKEN=.*/ADMIN_TOKEN=$(openssl rand -hex 32)/" .env
sed -i "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$(openssl rand -hex 32)/" .env
nano .env
```

`nano` ichida quyidagi qiymatlarni o‘zgartiring; uchta avtomatik yaratilgan maxfiy qiymatni saqlab qoling:

```dotenv
APP_ENV=production
DEMO_MODE=false
BOT_TOKEN=bu-yerga-oz-BotFather-tokeningizni-yozing
MINI_APP_URL=https://bot.example.uz
CORS_ORIGINS=https://bot.example.uz
```

Saqlash: `Ctrl+O`, `Enter`; chiqish: `Ctrl+X`. `BOT_TOKEN`ga kompyuteringizdagi ishlayotgan botning haqiqiy tokenini shaxsan kiriting. Uni chatga yoki frontend `VITE_` sozlamalariga yozmang. `.env`ni ommaviy repozitoriyga yubormang.

Compose API uchun PostgreSQL manzilini, bot uchun ichki API manzilini o‘zi belgilaydi. `DATABASE_URL`ning namunadagi SQLite qiymatini server Compose’da qo‘lda almashtirish shart emas. `POSTGRES_PASSWORD` dastlab baza yaratilganda qo‘llanadi; baza mavjud bo‘lgach uni faqat `.env`da almashtirish bazadagi parolni o‘zgartirmaydi.

## 5. Avval sayt va bazani ishga tushirish

Hozircha serverdagi Telegram botni yoqmang: kompyuteringizdagi bot hali ishlashi mumkin.

```bash
sudo docker compose up --build -d db api web
sudo docker compose --profile telegram build bot
sudo docker compose ps
curl -fsS http://127.0.0.1:8080/api/health
```

Birinchi build kutubxonalarni yuklaydi va bir necha daqiqa ketishi mumkin. `api` va `db` uchun `healthy`, `web` uchun `Up` holati kutiladi. Health so‘rovi xatosiz JSON qaytarishi kerak. Xato bo‘lsa:

```bash
sudo docker compose logs --tail 100 api db web
```

API ishga tushganda Alembic migratsiyasi qo‘llanadi. Baza Docker’ning `postgres_data` volume’ida saqlanadi. Lokal SQLite bazangizdagi foydalanuvchilar va sevimlilar ushbu yangi PostgreSQL bazasiga avtomatik ko‘chmaydi; eski fayllarni saqlab qo‘ying.

## 6. Domenni Nginx va HTTPS bilan ulash

Loyihada host Nginx uchun `infra/server.nginx.conf` namunasi bor. Uni alohida sayt sifatida o‘rnating:

```bash
sudo cp infra/server.nginx.conf /etc/nginx/sites-available/eng-arzon
sudo nano /etc/nginx/sites-available/eng-arzon
```

`server_name bot.example.uz;` qatoriga o‘z domeningizni yozing. Keyin:

```bash
sudo ln -s /etc/nginx/sites-available/eng-arzon /etc/nginx/sites-enabled/eng-arzon
sudo nginx -t
sudo systemctl reload nginx
curl -fsS http://bot.example.uz/api/health
```

Oxirgi so‘rov ishlashi, domen DNS’i esa serveringizga yo‘naltirilgan bo‘lishi kerak. Nginx namunasi so‘rovni faqat server ichida ochilgan `127.0.0.1:8080`ga uzatadi.

Keyin [Certbot’ning Nginx uchun rasmiy yo‘riqnomasi](https://certbot.eff.org/instructions?ws=nginx&os=snap) asosida sertifikat oling. Ushbu buyruqlar yangi, Certbot hali o‘rnatilmagan server uchun:

```bash
sudo snap install --classic certbot
sudo /snap/bin/certbot --nginx -d bot.example.uz --redirect
sudo /snap/bin/certbot renew --dry-run
curl -fsS https://bot.example.uz/api/health
```

Certbot so‘raganda aloqa e-mailingizni kiriting va shartlarni o‘qing. Sertifikat HTTP/HTTPS orqali domeningizga kirish mumkin bo‘lganda olinadi; 80/443 portlari hosting firewallida ham ochiq bo‘lsin. Yangilanish sinovi xatosiz tugashi kerak. Serverda oldin Certbot o‘rnatilgan bo‘lsa, paket turlarini aralashtirish o‘rniga uning mavjud usulidan foydalaning.

Brauzerda `https://bot.example.uz` ochilishini tekshiring. Production API Telegram sessiyasini talab qiladi, shuning uchun katalogni to‘liq tekshirish keyingi bosqichda Telegram ichida bajariladi. HTTPS’ni chetlab o‘tish uchun TLS tekshiruvini o‘chirmang.

## 7. Botni kompyuterdan serverga o‘tkazish

Bir token uchun bir vaqtda faqat **bitta polling jarayoni** ishlaydi. Bu [aiogram’ning polling qoidasi](https://docs.aiogram.dev/en/latest/dispatcher/long_polling.html). Server HTTPS tekshiruvi muvaffaqiyatli tugagach, kompyuteringizdagi botni to‘xtating.

**Windows PowerShell’da**:

```powershell
powershell -ExecutionPolicy Bypass -File "C:\Users\tilla\Documents\Codex\2026-10-27\men-yana-qo-shishni-tavsiya-qiladigan\outputs\eng-arzon-bot-pro\scripts\stop.ps1"
```

Bu lokal API, sayt, bot va vaqtinchalik tunnelni to‘xtatadi. So‘ng **server terminalida**:

```bash
cd ~/apps/eng-arzon-bot-pro
sudo docker compose --profile telegram up -d bot
sudo docker compose --profile telegram ps
sudo docker compose logs --tail 60 bot
```

Telegram’da `@arzonini_topamiz_bot`ni oching, `/start` yuboring va **🛍 Mini App’ni ochish** yoki pastdagi **Katalog** tugmasini bosing. Bot ishga tushganda menyu manzilini server `.env`idagi `MINI_APP_URL`ga yangilaydi. Eski xabardagi tugma eski tunnel URL’ini saqlashi mumkin, shuning uchun yangi `/start` xabaridan foydalaning.

Compose’dagi `restart: unless-stopped` xizmatlarni Docker/server qayta yoqilganda tiklaydi. Xizmatni qo‘lda to‘xtatsangiz, uni yana `up -d` bilan yoqing. Kompyuteringizdagi `start.ps1`ni bir xil token bilan qayta ishga tushirmang.

## 8. Haqiqiy mahsulot va narxlar

**Serverga yuklash do‘konlarning jonli narxlarini avtomatik ulamaydi.** `DEMO_MODE=false`da boshlang‘ich demo mahsulotlar ko‘rsatilmaydi; yangi production katalogining bo‘sh chiqishi kutiladigan holat.

1. Admin API orqali haqiqiy mahsulotlarni yarating: model, xotira, rang va GTIN aniq variantga tegishli bo‘lsin.
2. Do‘kon yetkazish haqi va bepul yetkazish chegarasini tasdiqlang.
3. Ruxsat etilgan haqiqiy takliflarni CSV orqali avval tekshiring, keyin import qiling. So‘rov misoli [API qo‘llanmasida](api.md#csv-import).
4. `OFFER_MAX_AGE_HOURS`dan eski takliflar tavsiyalardan chiqariladi. Narxlarni do‘kon bilan kelishilgan chastotada yangilang.

Asaxiy va OLX ochiq kataloglari uchun kunlik kollektor qo‘shilgan; serverda uni alohida yoqish tartibi [kunlik yig‘ish qo‘llanmasida](daily-collection.md). Uzum, Olcha va boshqa hamkor API adapterlari hali ulanmagan. “Olish/kutish” bahosi haqiqiy tarix yetarli bo‘lgach ishlaydi. Demo tarixini haqiqiy ma’lumotga aralashtirmang.

## 9. Ishlatish, backup va yangilash

Holat va oxirgi xatolar:

```bash
sudo docker compose --profile telegram ps
sudo docker compose logs --tail 100 api bot
```

Ma’lumotlar bazasining sanali zaxirasi:

```bash
umask 077
mkdir -p backups
sudo docker compose exec -T db pg_dump -U eng_arzon eng_arzon > "backups/catalog-$(date +%F-%H%M%S).sql"
```

Buyruq xatosiz tugaganini tekshiring. `.env`ning alohida himoyalangan nusxasini ham saqlang. Bazaning backup’ini davriy oling va serverdan tashqaridagi himoyalangan joyga ko‘chiring. Qayta tiklashni avval alohida bazada sinang; eski backup bilan amaldagi bazani almashtirish undan keyingi yozuvlarni yo‘qotadi.

Kodni yangilashda avval backup oling. Yangi manbalarni loyiha katalogiga ko‘chiring, mavjud `.env` va `backups/`ni saqlang. Keyin:

```bash
sudo docker compose --profile telegram up --build -d
sudo docker compose --profile telegram ps
curl -fsS https://bot.example.uz/api/health
```

`docker compose down -v` bazaning volume’ini ham o‘chiradi; oddiy yangilashda bu buyruq ishlatilmaydi. Faqat `.env` o‘zgarganda `restart` yetmaydi — `up -d` xizmatni yangi sozlama bilan qayta yaratadi. API healthcheck va takliflarning yangilanish vaqtiga monitoring ulang; token va Telegram `initData`ni logga yozmang.

MVP bitta API va bitta bot jarayoni uchun mo‘ljallangan. API so‘rov cheklovi xotirada ishlaydi; ko‘p replika qo‘shishdan oldin umumiy limiter va worker infratuzilmasi kerak. Telegram outbox uzilishda qayta urinadi; Telegram javobi bilan bazadagi tasdiq orasida uzilish bo‘lsa, xabar takror kelishi mumkin.

## Tez-tez uchraydigan xatolar

| Holat | Tekshirish |
|---|---|
| `TelegramConflictError` | Xuddi shu token bilan lokal bot yoki ikkinchi server bot ishlayaptimi? Faqat bittasini qoldiring. |
| Mini App eski tunnelni ochadi | Server `.env`dagi `MINI_APP_URL`ni tekshiring, `up -d bot` qiling va Telegram’da yangi `/start` yuboring. |
| Nginx `502 Bad Gateway` | `docker compose ps`, API logi va `curl http://127.0.0.1:8080/api/health`ni tekshiring. |
| Sertifikat olinmayapti | Domen A/AAAA yozuvi, hosting firewallidagi 80-port va HTTP manzilni tekshiring. |
| Katalog bo‘sh | Production demo mahsulotlarni yashiradi; haqiqiy katalog va takliflarni import qiling. |
| Brauzerda `401` | Katalogni Telegram Mini App orqali yangi sessiyada oching. |

## Rasmiy manbalar

- [Docker Engine: Ubuntu o‘rnatish](https://docs.docker.com/engine/install/ubuntu/)
- [Docker Compose](https://docs.docker.com/compose/)
- [Certbot: Nginx va snap](https://certbot.eff.org/instructions?ws=nginx&os=snap)
- [aiogram: long polling](https://docs.aiogram.dev/en/latest/dispatcher/long_polling.html)
- [Telegram Mini Apps: sessiyani tekshirish](https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app)

