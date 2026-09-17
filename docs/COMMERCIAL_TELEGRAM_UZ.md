# Tariflar, AI hisobi va Telegram — 2026-09-17

## Tariflar

| Tarif | Oylik narx | 12% soliq | Jami | AI balansi (70%) | Platforma (30%) |
|---|---:|---:|---:|---:|---:|
| Start | $20 | $2.40 | $22.40 | $14 | $6 |
| Pro | $50 | $6 | $56 | $35 | $15 |
| Pro Max | $100 | $12 | $112 | $70 | $30 |
| Ultra | $200 | $24 | $224 | $140 | $60 |

Chegirma avval asosiy narxga qo‘llanadi; soliq chegirmadan keyingi narxga qo‘shiladi. 70/30 taqsimot soliqqa tatbiq etilmaydi. Ichki kredit $0.0001 ga teng: boshlang‘ich AI kreditlari 140 000 / 350 000 / 700 000 / 1 400 000. Bu provayderning matn tokeni bilan bir xil birlik emas. Matn uchun kirish/chiqish tokenlari, ovoz uchun belgilar, video uchun soniyalar va narx nusxasi alohida saqlanadi.

Stripe tasdiqlagan to‘langan invoice balansni bir marta to‘ldiradi. Qayta kelgan webhook va qisman/to‘liq refund hisobga olinadi. AI sarfi balansdan yechiladi, ish boshlashda xarajat rezerv qilinadi, ish tugaganda rezerv bo‘shaydi. Job uchun parallel pullik bosqichlar PostgreSQL advisory lock bilan cheklanadi. Yakunlangan video generatsiyasi qayta yuklab olinayotganda bir xil provider task ID ikkinchi marta hisobdan yechilmaydi.

Bu **ichki dollar ekvivalentidagi balans**, provayder hisobiga avtomatik bank o‘tkazmasi emas. Operator Runway va boshqa provayder hisoblarini o‘zi moliyalashtiradi. Platformaning 30 foizi sof foyda emas: undan infratuzilma va to‘lov komissiyalari ham qoplanadi. Ekotizim yaratib joylagan videolarning monetizatsiya daromadidan olinadigan 30% ulush bundan alohida hisobdir.

## Video modellari va narx manbasi

[Runway rasmiy API narxlari](https://docs.dev.runwayml.com/guides/pricing/) asosida katalogga quyidagilar qo‘shildi (tekshiruv: 2026-09-17):

| Model | API orqali | Narx / soniya | Tariflar |
|---|---|---:|---|
| Veo 3.1 Fast, audiosiz | Runway | $0.10 | Barchasi |
| Runway Gen-4.5 | Runway | $0.12 | Barchasi |
| Veo 3.1, audiosiz | Runway | $0.20 | Pro Max, Ultra |

Runway krediti $0.01. Ushbu narxlar Google’ning to‘g‘ridan-to‘g‘ri Gemini API narxlari emas. Ovoz alohida yaratiladi va alohida sarfga kiradi. Modelning ruxsat etilgan klip uzunligi bo‘yicha so‘rov yaxlitlanadi; sarf aynan so‘ralgan uzunlikdan hisoblanadi. Foydalanuvchi o‘z tarifidagi modelni tanlashi mumkin.

Video soni kafolatlangan natija emas: 4/10/20/40 — davr uchun himoya limiti; real ishlab chiqarish AI balansiga bog‘liq. Maksimal davomiylik 60/120/180/240 soniya, bir job uchun xarajat chegarasi $7/$17.50/$35/$70. Matn, ovoz, moderatsiya va qayta yaratish ham xarajat qiladi. Ayrim uzun/model kombinatsiyalari balans yoki job chegarasiga sig‘maydi va to‘xtatiladi.

Superadmin + 2FA orqali konfiguratsiya panelida tarif narxi, chegirma foizi/e’loni/tugash vaqti, davomiylik, model ro‘yxati, Stars narxi hamda provider birlik va kirish/chiqish token narxlari tahrirlanadi. Yangi narxlar yangi xaridlarga qo‘llanadi. Mavjud Stripe obunasining recurring narxi avtomatik almashtirilmaydi. Chegirma bilan yaratilgan recurring narx keyingi davrlarda ham saqlanadi; faqat birinchi oy promosi hozir alohida qo‘llanmagan.

## Telegram

1. Backend muhitida `TELEGRAM_BOT_TOKEN`, kuchli `TELEGRAM_WEBHOOK_SECRET`, `TELEGRAM_WEBHOOK_BASE_URL` va HTTPS `FRONTEND_BASE_URL` sozlanadi. Tokenlar admin panelga yoki Git’ga yozilmaydi.
2. Bot yopiq kanalga xabar joylash huquqli administrator qilib qo‘shiladi.
3. Superadmin panelida kanal ID kiritilib integratsiya faollashtiriladi. Server kanal huquqlari va HTTPS manzillarni tekshirib webhook va Mini App menyusini o‘rnatadi.
4. Foydalanuvchi billing sahifasidan bir martalik bot havolasi yoki Mini App imzolangan ma’lumoti bilan Telegram hisobini bog‘laydi. Mini App login `initData` imzosi va 5 daqiqalik muddatni tekshiradi. Xodimlar 2FA talabini Telegram login bilan chetlab o‘tolmaydi.
5. Moderatsiyadan o‘tgan tayyor videolar Creator ID va Video ID bilan kanalga avtomatik arxivlanadi. Faollashtirish avvalgi tasdiqlangan videolar uchun ham arxiv vazifalarini navbatga qo‘yadi. Katta fayllar 18 MiB qismlarga ajratiladi; asosiy fayl va qismlarning SHA-256 qiymatlari tekshiriladi.
6. Asosiy omborda fayl topilmasa va mos Telegram arxivi bo‘lsa, video ko‘rish endpointi fon tiklashni boshlaydi; UI tayyor bo‘lguncha holatni tekshiradi. Egaga tegishli ruxsat tekshiruvi saqlanadi. Telegram zaxira manbadir; oddiy ko‘rish asosiy ombordan ishlaydi.

[Telegram Bot API](https://core.telegram.org/bots/api) standart `getFile` uchun 20 MB cheklovi tufayli qismlarga ajratish ishlatilgan. Arxivga faqat moderatsiya tasdiqlagan yakuniy material yuboriladi; rad etilgan yoki tugallanmagan material yuborilmaydi.

Mini App ichidagi raqamli xizmat xaridi [Telegram Stars](https://core.telegram.org/bots/payments-stars) orqali; oddiy vebda Stripe orqali ishlaydi. Superadmin har tarif uchun XTR miqdorini va o‘z hisobiga haqiqatan tushadigan bir Star qiymatini USD’da kiritadi. Tasdiqlangan net kurs va yetarli narx bo‘lmasa xarid ochilmaydi. Universal yoki taxminiy Stars kursi avtomatik olinmaydi. Stars xaridi 30 kunlik davr beradi, avtomatik recurring obuna emas. To‘lovlar webhookdagi miqdor, valyuta, foydalanuvchi va buyurtma bo‘yicha tekshiriladi; qayta yuborilgan to‘lov balansni takroran oshirmaydi.

## Ishga tushirish va tekshiruv chegaralari

- Migratsiyalar: `python manage.py migrate`; backend, Celery worker va beat ishlashi zarur. PostgreSQL session advisory lock sabab pullik worker ulanishlari session rejimida bo‘lishi kerak (transaction-pooling bilan tekshirilmagan).
- `RUNWAY_API_KEY` va boshqa provayder kalitlarini serverda sozlab, narx/ovoz/model konfiguratsiyasini tekshirgach provider qatorlarini faollashtirish kerak. Yangi video providerlar kalitsiz holatda faol emas.
- Mahalliy sinov: 367 backend testi, 8 frontend testi; frontend build va lint (0 xato, 2 fast-refresh ogohlantirishi). Yangi bazadan migratsiya yo‘li tekshirildi. Bu jonli provider/Stripe/Telegram integratsiya sinovi emas.
- Tashqi provider so‘rovni qabul qilganidan so‘ng task ID bazaga yozilmasdan worker qulab tushadigan oraliq uchun upstream darajasidagi exactly-once kafolati yo‘q. Ishga tushirishdan oldin uzilish sinovi va provider reconciliation jarayoni kerak.
- Stars refund/support jarayoni, savdogar aloqa ma’lumotlari va to‘lovlar bilan haqiqiy E2E sinovi hali yakunlanmagan. Bot buyruqlari Mini App’ga olib kiradi; alohida to‘liq chat suhbatli boshqaruv qurilmagan.
- Barcha 30 interfeys tilining to‘liq tarjimasi va `myweb.uz` dizayniga piksel darajasida moslik haqidagi oldingi ochiq ishlar saqlanadi. Yangi tijoriy ekranlarda inglizcha matnlar bor. Ushbu yangilanish butun texnik vazifa mukammal yakunlandi degani emas.
