# Amalga oshirish holati — 2026-09-17

## Eng yangi tijoriy yangilanish

Tariflar ($20/$50/$100/$200 + 12%), 70/30 AI balansi, Runway/Veo katalogi, superadmin narx/chegirma boshqaruvi va Telegram arxiv/Mini App kodi qo‘shildi. Tafsilotlar, sozlash tartibi va qolgan cheklovlar: [COMMERCIAL_TELEGRAM_UZ.md](docs/COMMERCIAL_TELEGRAM_UZ.md). Yangi bazadan 367 backend testi va 8 frontend testi o‘tdi. Quyidagi 346 testli hisobot oldingi bosqichga tegishli.

## Oldingi yangilanish — kod va lokal sinovlar

Google OAuth, AI provayderlari va Stripe hisoblari hali sozlanmagan; foydalanuvchi kod va lokal sinovlarni davom ettirishni tasdiqladi. Quyidagi holat eski bosqich yozuvlaridan ustun turadi.

- Dashboard, kanal, video, daromad, billing va asosiy admin ekranlari haqiqiy backend endpointlariga ulandi; demo grafiklar o‘rnida server ma’lumotlari ishlatiladi.
- Kunlik/haftalik/oylik kontent takliflari: YouTube tahlili, alohida reja yozuvi, sarlavha/brief/vaqt tahriri, tanlangan bandlarni tasdiqlash va rejalangan joblarga aylantirish. Tasdiqlanmagan reja video yaratmaydi. Job kontent sozlamalarining o‘sha paytdagi nusxasini saqlaydi.
- Google tugmasi login va registratsiyada, OAuth callback va 2FA challenge interfeysi qo‘shildi. Konfiguratsiya yo‘qligi aniq ko‘rsatiladi.
- Stripe karta saqlash Checkout oqimi qo‘shildi. `setup` yoki to‘lanmagan Checkout obunani faollashtirmaydi. Invoice/PDF endpointlari egasiga qarab ishlaydi.
- Yangi shartnomalar uchun faqat ekotizim yaratgan va o‘zi joylagan videolarning tasdiqlangan daromadi 30/70 hisobga kiradi. 72 soatdan keyin taxminiy daromadni avtomatik yakuniy qilish olib tashlandi. Moliyachi alohida video bo‘yicha manba dalilini kiritadi; hisob 14 kun ko‘rib chiqish uchun ochiq, e’tiroz avtomatik yakunlashni to‘xtatadi. Kanal umumiy daromadini video daromadiga taxminan taqsimlash amalga oshirilmaydi.
- Moderatsiya qaytargan videolar alohida jobda tuzatiladi; eski material va sabab saqlanadi. Qattiq bloklar inson tekshiruvida qoladi. Urinish va umumiy xarajat limitlari bor. Nashr ruxsati video baytlari va nom/tavsif/teglar bilan bog‘langan; metadata tahriri qayta moderatsiyani talab qiladi.
- Backend migratsiyalari va frontend tiplari yangilandi; hech qanday haqiqiy karta to‘lovi yoki YouTube nashri bajarilmadi.

**Joriy tekshiruv:** PostgreSQL bilan 346 backend testi o‘tdi. Frontend 8/8 test bitta worker bilan o‘tdi; parallel tekshiruvda kuzatilgan 5 soniyalik timeoutlar qayta tekshiruvda takrorlanmadi. Frontend TypeScript/build o‘tdi; ESLint xatosiz (bitta mavjud fast-refresh ogohlantirishi). Mobil brauzerda landing, dashboard, kontent reja va registratsiya sahifalari transport fixturelari bilan runtime xatosiz va gorizontal chiqishsiz ochildi. Yangi migratsiyalar izolyatsiyalangan lokal bazaga muvaffaqiyatli qo‘llandi; tekshiruvdan so‘ng faqat shu vaqtinchalik PostgreSQL jarayoni to‘xtatildi. `makemigrations --check` o‘tdi. Backend `E4,E7,E9,F` tekshiruvi o‘tdi; to‘liq Ruff tekshiruvi o‘tmagan. Tarjima katalogi: RU/EN/UZ 320/320; qolgan 27 lokal 59/320.

**Ochiq ishlar:** 27 lokal tarjimasi hali to‘liq emas (asosiy 59 kalit mavjud; qolganlari ruscha fallback). `myweb.uz` bilan piksel darajasidagi tenglik tasdiqlanmagan. Barcha 30 tilda ovoz/render sifati, jonli Google/Stripe integratsiyasi, provider uzilishidan tiklanish va takroriy uploadning oldini olish bo‘yicha to‘liq E2E tekshiruv qolgan. Shu sababli tizimni productionga to‘liq tayyor deb belgilash mumkin emas. Backendning keng Ruff qoidalari bo‘yicha ham uslub qarzdorligi mavjud.

Hisobotning quyidagi qismlari oldingi bosqichlarning tarixiy qaydlaridir; eski test sonlari va mock ekranlar haqidagi gaplar joriy holatni bildirmaydi.


Talab: video kontenti va interfeys 30 ta til/lokal variantda; asosiy til ruscha. Foydalanuvchi ikkala qamrovni tasdiqladi. Bu bosqich butun PDF bajarilganini yoki barcha tillarda yakuniy video sinovi o‘tganini anglatmaydi.

## Tayyorlangan kod

- Backend va frontend uchun bir xil 30 til reyestri; region kodi `ar-EG` saqlanadi, `AR_eg` kabi yozuvlar normalizatsiya qilinadi. `GET /api/v1/content/languages` autentifikatsiyalangan katalog endpointi.
- Kontent validatsiyasida eski inglizcha cheklov olib tashlandi. Profil lokalini 30 variantdan tanlash uchun `accounts.0004_expand_locales` migratsiyasi; yangi profil defaulti `ru`. Eski profil tanlovlari o‘zgartirilmaydi.
- UI til tanlovi, lokal saqlash, `<html lang>` va RTL/LTR yo‘nalishi; yon menyu va jadval tekislashlari moslashtirildi.
- Kontent sozlamalari mockdan haqiqiy APIga ulandi: kanal tanlash, GET, birinchi saqlash uchun POST, keyingilari uchun PATCH; til, vaqt mintaqasi, kunlar va server xatolari. Kanal ro‘yxatining paginatsiya javobi o‘qiladi.
- YouTube/AdSense authorization URL javob maydoni va password reset API yo‘llari moslashtirildi. Kanal ekranining o‘zi hali mock; bu tuzatish OAuthni UI bo‘ylab to‘liq yakunlamaydi.
- TTSni til/model imkoniyati bo‘yicha tanlash va Azure Speech REST adapteri. Tilga mos ovoz xaritasi, provider locale xaritasi; noma’lum imkoniyatni ishlaydi deb qabul qilmaydi.
- Video yakunidagi matn 30 lokal uchun yozildi. Render imagega Noto shriftlari va tilga mos shrift tanlash qo‘shildi. CJK/Thai davomiyligi faqat bo‘shliqlar asosida hisoblanmaydi; haqiqiy uzunlikni TTS/ffprobe belgilaydi.
- Yangi token yozuvlari AES-256-GCM: tasodifiy nonce, autentifikatsiyalangan kalit versiyasi, HKDF orqali alohida kalit. Eski Fernet tokenlari o‘qiladi, kalit almashinuvi tekshirildi.
- Oldindan mavjud 2FA, sessiyalar, ma’lumot eksporti/o‘chirish viewlari URLga ulandi; yetishmagan 2FA rate-limit qo‘shildi.

## Tarjimalar: aniq holat

`en`, `ru`, `uz`: **239/239** katalog kaliti.

Qolgan **27 lokalning har biri 59/239** kalit: asosiy menyu, boshqaruv tugmalari, til tanlovi va kontent sozlamalari. Qolgan **180 tadan matn hali tarjima qilinmagan**; ular vaqtincha ruscha fallback bilan ko‘rinadi. Bu 30 tilda to‘liq tarjima hisoblanmaydi. Yangi tarjimalar ona tilida so‘zlashuvchi muharrir tomonidan tekshirilmagan.

Tekshirish:

```sh
python3 scripts/check_locales.py
python3 scripts/check_locales.py --strict
```

`--strict` hozir yetishmayotgan tarjimalar sababli xato bilan tugashi kutiladi. Kalit yoki `{{name}}` kabi o‘zgaruvchi buzilishi ham aniqlanadi.

Tarjima to‘ldirish vositasi mavjud: `scripts/translate_locales.py`. U mavjud matnlarni saqlab, faqat yetishmagan UI matnlarini OpenRouter orqali tarjima qiladi; JSON kalitlari va interpolatsiya o‘zgaruvchilarini tekshirgandan keyin faylni atomik yozadi. `OPENROUTER_API_KEY` muhitda va `--model` aniq berilishi kerak. Ushbu ish davomida bu vosita bilan pullik API chaqiruvi bajarilmadi. Natijalar, ayniqsa rozilik/shartnoma matnlari, tahririy tekshiruvdan o‘tishi kerak.

## Ovoz xizmatlarini sozlash

Yangi migratsiya qilingan lokal bazada `check_language_readiness` 30 lokal uchun ham NOT READY qaytardi: seed provayderlari faol emas.

Model ro‘yxatining o‘zi konfiguratsiya va sifat tekshiruvi o‘rnini bosmaydi. [ElevenLabs rasmiy til ro‘yxati](https://elevenlabs.io/docs/help-center/other/what-languages-do-you-support) bo‘yicha v2 va v3 qamrovi farq qiladi. O‘zbek, tojik va turkman tillari uchun ushbu tekshirilgan v3 ro‘yxatiga tayanib ishlash kafolati berilmaydi. Misr arabchasining dialekt/ovoz mosligi alohida sozlanadi.

Provider DB konfiguratsiyasi qo‘shimcha maydonlari:

```json
{
  "supported_languages": ["uz"],
  "voices": {"uz": "uz-UZ-MadinaNeural"},
  "language_codes": {"uz": "uz-UZ"},
  "endpoint": "https://YOUR_REGION.tts.speech.microsoft.com/cognitiveservices/v1"
}
```

Bu Azure adapterining konfiguratsiya shakli; resurs hududi, mavjud ovoz, API kaliti va narx real hisobga moslab tekshiriladi. `secret_ref`ga faqat kalitning muhit o‘zgaruvchisi nomi yoziladi. [Azure Speech REST hujjati](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/rest-text-to-speech).

```sh
cd backend
.venv/bin/python manage.py migrate
.venv/bin/python manage.py check_language_readiness
```

Readiness komandasi barcha 30 lokal uchun faol model, ovoz va credential mavjudligini tekshiradi, APIga chiqmaydi. Hatto ushbu tekshiruv o‘tsa ham har tilda haqiqiy namuna, talaffuz, RTL, shrift, ovoz-video sinxronligi va moderatsiya sinovi zarur.

## Tekshirilgan natija

- PostgreSQL 16 bilan backend: **320 test o‘tdi** (mavjud 244 + yangi 76).
- Qo‘shimcha CJK davomiyligi va tilga mos shrift regressiya testlari ham o‘tdi; core tekshiruvi jami 74 test.
- Frontend: **6 test o‘tdi**; haqiqiy APIga create/update yuborish va xatoni ko‘rsatish mock transport bilan tekshirildi.
- Frontend TypeScript/build o‘tdi; lintda xato yo‘q, oldindan mavjud ThemeToggle fast-refresh ogohlantirishi bor.
- Django system check o‘tdi; yetishmayotgan model migratsiyasi topilmadi.
- Real AI, Google yoki Stripe operatsiyalari bajarilmadi. Docker image render sinovi bajarilmadi; Noto shrift yo‘llari image ichida keyingi integratsiya tekshiruvini talab qiladi.

Lokal test uchun backend `.venv`, frontend `node_modules` va Homebrew PostgreSQL 16 o‘rnatildi. Izolyatsiyalangan test DB `/tmp/ai-youtuber-test-pg`, port `55432`da ishlatildi; mavjud foydalanuvchi DBlariga tegilmadi. Tekshiruvdan so‘ng izolyatsiyalangan PostgreSQL jarayoni to‘xtatildi.

## Keyingi bajariladigan ishlar

1. Qolgan 27 lokalda 180 tadan matnni tarjima qilish, qattiq yozilgan UI matnlarini katalogga ko‘chirish; `check_locales.py --strict`ni o‘tkazish.
2. 30 tilning barchasi uchun ishlaydigan TTS provider/model/voice konfiguratsiyasi va real namuna sinovlari. Mavjud inactive seedlar avtomatik faollashtirilmadi.
3. Channel, video, billing, revenue va admin ekranlarini to‘liq haqiqiy APIga ulash; OAuth callback va 2FA frontend oqimini tugatish. Contract ekrani keyingi o‘zgarishda haqiqiy APIga ulandi (quyida).
4. Invoice endpointlari, daromad manbalarini solishtirish, PDFdagi moliyaviy model farqi, subtitr va musiqa integratsiyalari — auditdagi ochiq ishlar.
5. AES yozuvlari yoqilgan deployda eski va yangi workerlar aralashmasin: eski versiya yangi formatni o‘qimaydi. Backend va workerlarni muvofiqlashtirib yangilash, eski decryption kalitlarini saqlash kerak. Eski yozuvlar odatiy qayta saqlashda yangilanadi; ommaviy migratsiya bu bosqichda bajarilmadi.

## 2026-09-17: mahsulot talablari va 30/70 hisob-kitobi

Foydalanuvchi tasdiqladi: platformaning 30% ulushi faqat ekotizim yaratgan videolar daromadidan hisoblanadi. To‘liq aniqlashtirilgan oqim va hali bajarilmagan funksiyalar `PRODUCT_REQUIREMENTS_UZ.md`da yozildi.

- Yangi shartnoma va hisobot model defaultlari 30/70 qilindi. Migratsiyalar tarixiy foizlarni o‘zgartirmaydi; mavjud faol 1.0 shartnoma avtomatik almashtirilmadi.
- Hisob-kitob foizlarni tekshiradi va imzolangan shartnoma stavkasini ishlatadi. Regressiya testi: ekotizim videosi $100 va mustaqil video $900 bo‘lsa, hisobga faqat $100 kiradi, platformaga $30, creatorga $70 ajratiladi.
- Shartnoma sahifasi current/history/sign/PDF APIlariga ulandi; serverdagi foizlar va foydalanuvchi belgilagan roziliklar ishlatiladi.
- Yakuniy to‘liq backend tekshiruvi: **328 test o‘tdi**. Frontend: **8 test o‘tdi**. Build o‘tdi; lint xatosiz, mavjud ThemeToggle ogohlantirishi saqlangan. Build katta bundle haqida ogohlantiradi.
- Yangi migratsiyalar izolyatsiyalangan PostgreSQL bazasida o‘tdi; `makemigrations --check --dry-run` yangi farq topmadi. Lokalizatsiya kataloglarining oddiy tekshiruvi o‘tdi, to‘liq tarjima talabi hali bajarilmagan.
- Real Google/AI/Stripe operatsiyasi bajarilmadi. Avtomatik rejalash, moderatsiyadan qaytgan videoni qayta yaratish sikli va tasdiqlangan daromaddan production undirish hali tugallanmagan.


## 2026-09-17: kirish sayti, dashboard va shartnoma 1.1

- `/` ochiq tanishtiruv sahifasi bo‘ldi. `myweb.uz` buildidagi mahalliy Sentient shriftlari, qora/sariq palitra, kapsula menyu, katta serif sarlavhalar, nuqtali globus, kartalar va FAQ uslubi qayta yaratildi. Asl minifikatsiyalangan JS ko‘chirib ishlatilmadi; barcha animatsiya va bo‘limlarning piksel darajasida aynan nusxasi emas.
- Ekotizim haqida imkoniyatlar, jarayon, 30/70 shartlari va FAQ matnlari RU/UZ/EN kataloglariga qo‘shildi. Login va ro‘yxatdan o‘tish havolalari mavjud sahifalarga olib boradi. Rus tili asosiy til bo‘lib qoladi; qolgan 27 til uchun fallback mavjud, to‘liq tarjima tugallanmagan. Hozir RU/UZ/EN 286/286, qolganlari 59/286 kalit.
- Creator va admin umumiy shell ranglari yuborilgan screenshotga mos to‘q ko‘k, binafsha va moviy palitraga o‘tdi. Light/dark almashishi saqlanadi. Dashboardda chiziqli, ustunli va ulush grafiklari qo‘shildi. Ular mavjud dashboard kabi demo ma’lumotlari bilan ishlaydi va ekranda ochiq belgilangan.
- Shartnoma 1.1 migratsiyasi yangi faol 30/70 matnni yaratadi: faqat ekotizim ichida yaratilib, u orqali joylangan videolar daromadi. Eski 1.0 matni, foizlari va imzolari o‘zgarmaydi; yangi versiya qayta rozilik talab qiladi. Migratsiya hozir faqat izolyatsiyalangan lokal bazada bajarilgan.
- Yangi shartnomalar uchun `revenue_only_platform_published` belgisi: hisob-kitob upload muvaffaqiyati, YouTube video ID va nashr yozuvini talab qiladi. Tashqarida yaratilgan yoki faqat eksport qilinib tashqarida yuklangan video kirmaydi. Eski shartnomalar oldingi qamrovini saqlaydi.
- Regressiya: $100 ekotizim yaratgan va yuklagan, $900 mustaqil, $500 faqat yaratilgan/tashqarida yuklangan video bo‘lsa, yangi shartnoma uchun faqat $100 hisobga olinadi va platformaga $30 ajratiladi.
- Yangi test bazasida backend 328 test, frontend 8 test o‘tdi; build va lint xatosiz. Mavjud fast-refresh va bundle hajmi ogohlantirishlari bor. Migratsiya va model mosligi tekshirildi. Lokal Chromiumda sahifalar, FAQ, mobil o‘lcham va console xatolari tekshirildi.
- Ko‘rinishlar `docs/previews/`da saqlandi. Google, AI provayder yoki Stripe real operatsiyalari bajarilmadi.
