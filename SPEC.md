> **2026-09-17 — mahsulot oqimi yangilandi:** ustuvor aniqlashtirishlar [PRODUCT_REQUIREMENTS_UZ.md](./PRODUCT_REQUIREMENTS_UZ.md)da. AI YouTube tahlili va creator tanlaydigan kontent reja, mustaqil moderatsiya/qayta ishlash, video/Shorts statistikasi talab qilinadi. Yangi ulush: **faqat ekotizim yaratgan videolar daromadidan 30% platformaga / 70% creatorga**. Eski 50/50 yozuvlar tarixiy; imzolangan shartnomalarni retroaktiv o‘zgartirishga asos emas.

> **2026-09-17 — yangi ustuvor talab:** kontent **va interfeys** 30 ta til/lokal variantni qo‘llashi kerak; asosiy til — ruscha (`ru`). `backend/core/languages.json` ro‘yxati va `IMPLEMENTATION_STATUS_UZ.md` holati qo‘llanadi. Quyidagi eski Q3 “faqat inglizcha” va en/ru/uz bilan cheklanish qarorlari bu talab uchun bekor qilingan. Moliyaviy model haqidagi eski qarorlar avtomatik o‘zgartirilmagan.

# SPEC: AI YouTube Content Ecosystem

> Hujjat maqsadi: xom TZ'ni bir ma'noli, tekshiriladigan talablar to'plamiga aylantirish.
> Bu hujjat **NIMA** quriladi degan savolga javob beradi. **QANDAY** qurilishi — `solution-architect` va developer agentlar ishi.
> Versiya: 1.1 · Sana: 2026-09-06 · Holat: **barcha ochiq savollar (Q1-Q4) foydalanuvchi tomonidan javob berilgan va tasdiqlangan — quyida 12-bo'limda belgilangan**

---

## 0. USTUVOR CHEKLOVLAR (buzilishi mumkin emas)

Bu bo'lim SPEC'ning boshqa har qanday qismidan yuqori turadi. Ziddiyat bo'lsa — shu bo'lim g'olib.

- **C-1 (Akkaunt yaratish taqiqi).** Tizim hech qachon, hech qanday sharoitda foydalanuvchi nomidan Google yoki YouTube akkaunt/kanal **yaratmaydi**, virtual/soxta/vaqtinchalik telefon raqamlari bilan **faollashtirmaydi**, CAPTCHA aylanib o'tmaydi, akkaunt sotib olmaydi/sotmaydi. Har bir creator o'z kanalini o'zi, real ma'lumotlari bilan ochadi.
- **C-2 (Faqat OAuth).** Kanalga kirish faqat Google OAuth 2.0 (authorization code + PKCE) orqali. Parol so'rash, cookie/session ko'chirish, browser-automation (Selenium/Playwright) bilan YouTube UI'ni boshqarish **taqiqlanadi**. Barcha YouTube operatsiyalari faqat rasmiy API'lar orqali.
- **C-3 (ToS muvofiqligi).** YouTube API Services Terms of Service, YouTube Partner Program (YPP) siyosatlari, Google API Services User Data Policy (Limited Use), AdSense Program Policies — to'liq bajariladi. Ushbu siyosatlarga zid funksiya SPEC'ga kiritilmaydi.
- **C-4 (Tech stack qat'iy).** Backend = **Python Django + Django REST Framework**. Frontend = **React**. Bu foydalanuvchi tomonidan tasdiqlangan va o'zgartirilmaydi.
- **C-5 (Token maxfiyligi).** OAuth access/refresh tokenlar hech qachon plain-text saqlanmaydi, log'ga yozilmaydi, API javobida qaytarilmaydi, frontendga uzatilmaydi.
- **C-6 (Kontent originalligi).** Tizim mass-produced/takrorlanuvchi "AI slop" ishlab chiqarish uchun emas. Har video moderation va originallik tekshiruvidan o'tadi (batafsil: FR-45..FR-49, Risk R-2).

---

## 1. Maqsad

Content-creatorlar uchun SaaS platforma: creator o'z YouTube kanalini OAuth orqali ulaydi, tematika va nashr jadvalini tanlaydi, tizim esa AI bilan to'liq video (ssenariy → ovoz → vizual → montaj) ishlab chiqarib, creator ruxsati asosida uning kanaliga avtomatik joylaydi. Platforma reklama daromadini shaffof kuzatadi va kelishilgan 50/50 taqsimotni avtomatik hisob-kitob qiladi. Muammo: sifatli video ishlab chiqarish qimmat va sekin — creator g'oya va kanal egaligini saqlab, ishlab chiqarishni platformaga topshiradi.

---

## 2. Foydalanuvchilar va rollar

| Rol | Nima qila oladi |
|---|---|
| **Guest** | Landing sahifa, tariflar, ro'yxatdan o'tish/kirish. |
| **Creator** (asosiy rol) | Profil boshqarish; YouTube kanal ulash/uzish; AdSense ulash; tarif tanlash/o'zgartirish; tematika va jadval sozlash; video preview ko'rish, tasdiqlash/rad etish/tahrir so'rash; o'z daromadi va revenue-share hisobotlarini ko'rish; to'lov usulini boshqarish; shartnomani imzolash va versiyalarini ko'rish; ma'lumotlarini eksport/o'chirish so'rovi. |
| **Creator — Viewer (sub-user)** | *Faza 2.* Team a'zosi: faqat ko'rish (analytics, video statuslari), tasdiqlash huquqisiz. |
| **Moderator** (platforma xodimi) | Moderation navbatini ko'rish; flagged videolarni qo'lda ko'rib chiqish (approve/reject + sabab); moderation qoidalarini ko'rish. Moliyaviy ma'lumotga kirmaydi. |
| **Support** (platforma xodimi) | Foydalanuvchi/kanal/video statuslarini ko'rish, ticket ishlash, qayta urinish (retry) buyrug'i. Token'lar va shifrlangan ma'lumotlarga kirmaydi. |
| **Finance** (platforma xodimi) | Revenue records, revenue-share invoyslari, payout'lar, hisobotlar, eksport. Video kontentga kirmaydi. |
| **Admin** | Barcha yuqoridagilar + foydalanuvchi boshqaruvi, tarif/plan konfiguratsiyasi, AI provider konfiguratsiyasi, feature flag'lar, shartnoma shabloni versiyalash. |
| **System (avtomatik)** | Celery scheduler/worker'lar: jadval bo'yicha job yaratish, generation, upload, revenue sync, billing. Audit log'da `actor_type=system` sifatida yoziladi. |

**Rol modeli:** RBAC. Platforma xodimlari rollari kumulyativ emas — har biri alohida beriladi (bir foydalanuvchi bir nechta rolga ega bo'lishi mumkin).

---

## 3. Doira (Scope)

### 3.1 MVP (Faza 1 — birinchi ishlaydigan versiya)

1. **Auth:** email/parol (email verifikatsiya bilan) + "Sign in with Google" (faqat login uchun, `openid email profile`).
2. **YouTube kanal ulash:** alohida OAuth consent, scope: `youtube.upload`, `youtube.readonly`, `yt-analytics.readonly`, `yt-analytics-monetary.readonly`. Bitta creator = bitta kanal (MVP).
3. **AdSense ulash (Q2 — TASDIQLANGAN, MVP'ga qo'shildi):** creator "Connect AdSense" orqali AdSense Management API'ga (`adsense.readonly`) alohida OAuth consent beradi; `adsense_accounts` yozuvi yaratiladi va daromad ma'lumotlari YouTube Analytics bilan bir qatorda "AdSense-confirmed" manba sifatida Dashboard'da ko'rsatiladi. Ulash foydalanuvchi darajasida ixtiyoriy qoladi — ulanmasa tizim "estimated" belgisi bilan faqat YouTube Analytics'ga tayanadi (FR-20) — lekin *integratsiyaning o'zi* (OAuth flow, sync job, UI) MVP'da texnik jihatdan to'liq ishlab chiqiladi (FR-19 endi `[MVP]`).
4. **Tarif va obuna:** Free / Starter / Professional / Enterprise; Stripe Billing orqali; kvota (oyiga video soni, video uzunligi limiti) majburlanadi.
5. **Shartnoma:** versiyalangan shablon, e-sign (checkbox + timestamp + IP + user-agent + shablon hash), PDF snapshot saqlash; imzolash bilan bir vaqtda **saqlangan to'lov usuli (Stripe SetupIntent) majburiy** (Q1 — FR-70a).
6. **Content preferences:** tematika (niche), til (MVP: 1 til/kanal), video uzunligi, nashr chastotasi (kunlik/haftalik/oylik), nashr vaqti + timezone, privacy status (public/unlisted), tasdiqlash rejimi (`review_required` | `auto`).
7. **Video generation pipeline (bitta provider har bosqichda):** script (LLM via OpenRouter) → TTS → vizual (video-gen provider) → FFmpeg assembly (+ statik fon musiqasi kutubxonasidan) → moderation → (review) → upload.
8. **Tasdiqlash oqimi:** preview link (signed URL) + email bildirishnoma; approve / request-changes / reject; timeout siyosati (FR-38).
9. **YouTube'ga joylash:** `videos.insert` (resumable upload) + `thumbnails.set`; metadata (title, description, tags, category, `selfDeclaredMadeForKids`, **AI-generated content disclosure**).
10. **Daromad kuzatuvi:** YouTube Analytics API (+ AdSense API, ulangan bo'lsa) orqali kunlik sync (views, watch time, estimatedRevenue); Dashboard'da ko'rsatish.
11. **50/50 revenue share hisob-kitobi va billing (Q1 — TASDIQLANGAN: service-fee model):** oylik davr bo'yicha hisoblash, invoys generatsiyasi, saqlangan to'lov usulidan Stripe orqali avtomatik undirish; undirilmasa dunning + generation pauza (FR-70b).
12. **Creator Dashboard (React):** kanal holati, video jadvali/statuslari, daromad grafiklari, sozlamalar, billing, shartnoma.
13. **Admin Panel (React):** foydalanuvchilar, kanallar, video job'lar (+ retry), moderation navbati, moliyaviy hisobotlar, provider konfiguratsiyasi.
14. **Notification:** email (transaksion). In-app bildirishnomalar ro'yxati.
15. **Xavfsizlik/compliance:** AES-256-GCM token shifrlash, audit log, moderation bosqichi, GDPR-uslub eksport/o'chirish so'rovi, token revoke.
16. **Lokalizatsiya:** UI — **en / ru / uz** (uz/ru — standart bozor talabi, ixtiyoriy emas).
17. **Observability:** Sentry, Prometheus metrikalari, structured JSON logging, health/readiness endpointlar.

### 3.2 Faza 2 (keyingi bosqich — hozir EMAS)

- Ko'p provider + avtomatik failover/routing (video-gen, TTS uchun).
- AI musiqa generatsiyasi (Suno / MiniMax Music).
- Whisper orqali subtitr + DeepL/Google Translate orqali ko'p tilli subtitr va dublyaj.
- Voice cloning (Professional+ tarifda), custom brand voice.
- Thumbnail generatsiyasi + A/B test.
- Bir creator uchun bir nechta kanal; team/sub-user rollari.
- Push (web push) va Telegram bildirishnomalari.
- Stripe Connect orqali platformadan creator'ga to'lov (agar biznes modeli teskari yo'nalishni talab qilsa).
- Shorts / vertikal format optimizatsiyasi.
- Kubernetes'ga ko'chish, GPU worker autoscaling.
- Enterprise SLA dashboard, ustuvor navbat, dedicated support.
- Creator o'z ssenariysini yuklashi (script upload / human-in-the-loop editor).

### 3.3 Doiradan tashqari (hech qachon / bu loyihada qilinmaydi)

- Avtomatik Google/YouTube akkaunt yoki kanal yaratish (C-1).
- Virtual/soxta raqamlar bilan aktivatsiya, SMS-farm, CAPTCHA bypass (C-1).
- Browser automation orqali YouTube boshqaruvi (C-2).
- YouTube views/subscriber/watch-time sotib olish yoki sun'iy oshirish.
- Mualliflik huquqi bilan himoyalangan uchinchi tomon kontentini qayta yuklash (reupload).
- Mobil native ilovalar (iOS/Android).
- Boshqa platformalar (TikTok, Instagram, Facebook) — bu loyiha doirasidan tashqari.
- Creator'ning AdSense hisobidan platformaga to'g'ridan-to'g'ri pul o'tkazish mexanizmi (Google ToS taqiqlaydi — Risk R-1).

---

## 4. Funksional talablar

Har bir talab tekshiriladigan. `[MVP]` — Faza 1, `[F2]` — Faza 2.

### 4.1 Auth & Identity

- **FR-1** `[MVP]` Foydalanuvchi email + parol bilan ro'yxatdan o'ta oladi. Parol minimal 10 belgi, Django `AUTH_PASSWORD_VALIDATORS` (common/numeric/similarity) + HIBP-style oddiy blacklist tekshiruvi.
- **FR-2** `[MVP]` Ro'yxatdan o'tgach email verifikatsiya link yuboriladi (24 soat amal qiladi). Tasdiqlanmagan akkaunt kanal ulay olmaydi va obuna sotib ololmaydi.
- **FR-3** `[MVP]` "Sign in with Google" orqali kirish/ro'yxatdan o'tish (scope: `openid email profile`). Bu **login identity** — YouTube ruxsati EMAS; ikkalasi alohida consent.
- **FR-4** `[MVP]` JWT sessiya: access token (15 daqiqa) + refresh token (14 kun, rotatsiya bilan, reuse-detection). Refresh token **httpOnly + Secure + SameSite=Lax cookie**da.
- **FR-5** `[MVP]` Logout barcha yoki joriy qurilma sessiyasini bekor qiladi (refresh token blacklist Redis'da).
- **FR-6** `[MVP]` Parolni tiklash (email orqali, bir martalik 1 soatlik token).
- **FR-7** `[MVP]` Rate limiting: login 5/daqiqa/IP + 10/soat/account; registration 3/soat/IP; parol tiklash 3/soat/email.
- **FR-8** `[F2]` TOTP 2FA (Admin va Finance rollari uchun **majburiy**, MVP'da ham majburiy — quyi FR-9'ga qara).
- **FR-9** `[MVP]` Platforma xodimlari (Admin/Finance/Moderator/Support) uchun TOTP 2FA majburiy; admin panel alohida IP allowlist bilan himoyalanishi mumkin (konfiguratsiya).

### 4.2 YouTube kanal ulash (OAuth)

- **FR-10** `[MVP]` Creator "Connect YouTube" tugmasi orqali Google OAuth 2.0 authorization code flow (PKCE + `state` CSRF token) boshlaydi. `access_type=offline`, `prompt=consent` (refresh token olish uchun).
- **FR-11** `[MVP]` So'raladigan scope'lar aniq va minimal: `youtube.upload`, `youtube.readonly`, `yt-analytics.readonly`, `yt-analytics-monetary.readonly`. Har scope nima uchun kerakligi consent oldidan UI'da uz/ru/en tilida tushuntiriladi.
- **FR-12** `[MVP]` Callback'da tizim `channels.list(mine=true)` chaqirib kanal ID, title, handle, thumbnail, subscriber/video count'ni saqlaydi.
- **FR-13** `[MVP]` `access_token` va `refresh_token` **AES-256-GCM** bilan shifrlanib saqlanadi (kalit — KMS/env orqali, DB'da emas). Shifrlangan qiymat hech qachon API javobida qaytarilmaydi.
- **FR-14** `[MVP]` Token muddati tugashidan oldin avtomatik refresh; refresh muvaffaqiyatsiz bo'lsa (revoked/invalid_grant) kanal `status=disconnected` bo'ladi, creator'ga email yuboriladi, jadvaldagi barcha kutilayotgan job'lar `paused` bo'ladi.
- **FR-15** `[MVP]` Creator istalgan vaqt "Disconnect" qila oladi: tizim Google `revoke` endpoint'ini chaqiradi, saqlangan tokenlarni **o'chiradi** (soft-delete emas), audit log yozadi.
- **FR-16** `[MVP]` Bitta YouTube kanal bir vaqtning o'zida faqat bitta platforma akkauntiga bog'lanishi mumkin (unique constraint + tushunarli xato xabari).
- **FR-17** `[MVP]` Tizim kanalning YPP (monetizatsiya) holatini API orqali aniqlashga harakat qiladi; aniqlab bo'lmasa creator'dan self-declaration so'raydi va Dashboard'da "monetizatsiya holati tasdiqlanmagan" bannerini ko'rsatadi.
- **FR-18** `[F2]` Bir akkaunt ostida bir nechta kanal.

### 4.3 AdSense ulash

- **FR-19** `[MVP — Q2 TASDIQLANGAN]` Creator AdSense hisobini AdSense Management API orqali ulaydi (`adsense.readonly`), daromadni shaffof solishtirish uchun. Ulash foydalanuvchi uchun **ixtiyoriy**, lekin integratsiyaning o'zi (OAuth flow, `adsense_accounts`, kunlik sync) MVP'da to'liq ishlab chiqiladi; ulanmasa tizim faqat YouTube Analytics ma'lumotiga tayanadi.
- **FR-20** `[MVP]` Agar AdSense ulanmagan bo'lsa, Dashboard daromad ko'rsatkichlari "YouTube Analytics estimate" deb aniq belgilanadi (estimated ≠ final payout). Ulangan bo'lsa, manba `revenue_records.source='adsense'` sifatida ustuvor ko'rsatiladi va "AdSense-confirmed" deb belgilanadi.

### 4.4 Tarif, obuna va kvota

- **FR-21** `[MVP]` 4 ta tarif: Free ($0/oy), Starter ($50/oy), Professional ($100/oy), Enterprise ($599/6 oy). Har tarif uchun kvota va feature flag'lar DB'da konfiguratsiya qilinadi (kodda hardcode emas).
- **FR-22** `[MVP]` To'lov Stripe Billing (Checkout Session + Customer Portal) orqali. SCA/3DS qo'llab-quvvatlanadi.
- **FR-23** `[MVP]` Kvota real vaqtda majburlanadi: `videos_per_month`, `max_video_duration_sec`, `max_languages`, `voice_cloning_enabled`, `priority_queue`, `concurrent_jobs`. Kvota tugasa yangi job yaratilmaydi, creator'ga upgrade taklifi ko'rsatiladi.
- **FR-24** `[MVP]` Kvota hisoblagichi billing davri boshida reset bo'ladi (subscription period boundary, kalendar oy emas).
- **FR-25** `[MVP]` Stripe webhook'lar idempotent qayta ishlanadi (`invoice.paid`, `invoice.payment_failed`, `customer.subscription.updated/deleted`). Har event `webhook_events` jadvalida saqlanadi, takroriy `event_id` e'tiborsiz qoldiriladi. Signature verification majburiy.
- **FR-26** `[MVP]` To'lov muvaffaqiyatsiz bo'lsa: 3 ta retry (Stripe Smart Retries) → grace period 7 kun → obuna `past_due` → keyin `suspended` (generation to'xtaydi, ma'lumot saqlanadi 90 kun).
- **FR-27** `[MVP]` Tarif upgrade/downgrade: upgrade darhol (proration), downgrade joriy davr oxirida.

### 4.5 Shartnoma va rozilik

- **FR-28** `[MVP]` Shartnoma shabloni versiyalanadi (`contract_versions`). Yangi versiya chiqqanda mavjud creator'lardan qayta rozilik so'raladi (blocking modal, `effective_from` sanasidan keyin).
- **FR-29** `[MVP]` Rozilik yozuvi saqlaydi: user_id, contract_version_id, shablon **SHA-256 hash**, imzolangan vaqt (UTC), IP, user-agent, rendered PDF snapshot (S3).
- **FR-30** `[MVP]` Alohida, granular rozilik checkboxlari (bir "hammasiga roziman" emas): (a) 50/50 revenue share shartlari, (b) YouTube kanalga video joylash huquqi, (c) ma'lumotlardan foydalanish/AI processing, (d) marketing emaillari (**ixtiyoriy**, default OFF).
- **FR-31** `[MVP]` Creator imzolangan shartnomalar tarixini yuklab olishi mumkin (PDF).
- **FR-32** `[MVP]` Shartnomani imzolamagan creator uchun video generation **boshlanmaydi**.

### 4.6 Content planning va jadval

- **FR-33** `[MVP]` Creator tanlaydi: tematika (oldindan tayyorlangan niche ro'yxatidan + erkin matn brief), til, video uzunligi (30s–10min oralig'ida, tarif limiti bilan), chastota (daily/weekly/monthly), nashr vaqti + timezone, YouTube privacy status, tasdiqlash rejimi.
- **FR-34** `[MVP]` Creator "brand voice" matnli ko'rsatma bera oladi (ton, auditoriya, taqiqlangan mavzular, CTA) — bu script prompt'iga kiradi.
- **FR-35** `[MVP]` Celery Beat scheduler jadval bo'yicha `video_jobs` yozuvini `scheduled` statusda oldindan yaratadi (kamida generation vaqti + buffer oldin: default 24 soat).
- **FR-36** `[MVP]` Creator jadvalni pauza qilishi, alohida rejalashtirilgan job'ni bekor qilishi yoki qo'lda "Generate now" bosishi mumkin (kvota doirasida).
- **FR-37** `[MVP]` Tizim takroriylikni oldini olish uchun oxirgi N (default 20) ta video sarlavha/mavzusini script prompt'iga kontekst sifatida beradi va semantik o'xshashlik > 0.9 bo'lsa mavzuni qayta generatsiya qiladi (C-6, Risk R-2).

### 4.7 Tasdiqlash oqimi (approval)

- **FR-38** `[MVP]` `review_required` rejimida: video `awaiting_approval` statusiga o'tadi, creator'ga email + in-app bildirishnoma yuboriladi, preview signed URL (24 soat) beriladi. **48 soat** ichida javob bo'lmasa — sozlamaga qarab: `auto_publish_on_timeout=true` → joylanadi; `false` (default) → `expired` statusi, kvota qaytarilmaydi lekin creator qayta ishga tushira oladi.
- **FR-39** `[MVP]` Creator: **Approve** (→ upload navbati), **Request changes** (matnli izoh + qaysi bosqichdan qayta boshlash: script/voice/visual) — har job uchun maksimum 2 ta bepul qayta generatsiya, keyin kvotadan hisoblanadi. **Reject** (→ `rejected`, joylanmaydi).
- **FR-40** `[MVP]` `auto` rejimda video moderation'dan o'tgach to'g'ridan-to'g'ri upload'ga o'tadi; creator baribir "publish bo'ldi" bildirishnomasini oladi.
- **FR-41** `[MVP]` Creator sarlavha, tavsif, teglar va thumbnail'ni tasdiqlashdan oldin tahrirlashi mumkin.

### 4.8 Video generation pipeline

- **FR-42** `[MVP]` Pipeline bosqichlari ketma-ket, har biri alohida Celery task, har biri **idempotent** va **qayta boshlash mumkin** (checkpoint asosida): `script → voice → visuals → assembly → moderation`.
- **FR-43** `[MVP]` Har bosqich natijasi artefakt sifatida S3'ga saqlanadi va `video_assets`da qayd etiladi (bosqichni qaytadan bajarmasdan keyingisiga o'tish uchun).
- **FR-44** `[MVP]` Har bosqich uchun retry siyosati: 3 urinish, eksponensial backoff (30s/2min/8min). 3 martadan keyin `failed` + admin alert + creator bildirishnomasi. Provider xatosi bo'lsa kvota **qaytariladi**.
- **FR-45** `[MVP]` **Script moderation:** LLM natijasi OpenAI Moderation API (yoki ekvivalent) orqali tekshiriladi; kategoriya chegarasidan oshsa → `moderation_failed`.
- **FR-46** `[MVP]` **Vizual moderation:** yakuniy videodan keyframe'lar olinadi va rasm moderation (AWS Rekognition yoki ekvivalent) orqali tekshiriladi.
- **FR-47** `[MVP]` **Mualliflik huquqi himoyasi:** faqat litsenziyalangan/generatsiya qilingan aktivlar ishlatiladi. Musiqa — platforma litsenziyalangan kutubxonasidan (`music_tracks` jadvali, litsenziya turi qayd etilgan). Uchinchi tomon videosi ishlatilmaydi.
- **FR-48** `[MVP]` Moderation'dan o'tmagan video **hech qachon** avtomatik joylanmaydi; u moderator navbatiga tushadi (`moderation_logs` bilan) va Moderator qo'lda qaror qabul qiladi.
- **FR-49** `[MVP]` Yuklanadigan har videoda YouTube'ning **"altered or synthetic content"** disclosure bayrog'i to'g'ri o'rnatiladi (AI-generated kontent uchun majburiy).
- **FR-50** `[MVP]` Assembly bosqichi FFmpeg orqali: vizual segmentlar + voice-over + fon musiqasi (ducking bilan) + intro/outro + (F2: subtitr) → yakuniy MP4 (H.264/AAC, 1080p, default 16:9).
- **FR-51** `[MVP]` Har job uchun to'liq **xarajat kuzatuvi**: har provider chaqiruvi uchun token/sekund/kredit va USD qiymati `api_usage_logs`da yoziladi; job'ning umumiy cost'i `video_jobs.total_cost_usd`da yig'iladi.
- **FR-52** `[MVP]` Job uchun **cost ceiling**: konfiguratsiyalangan limitdan (default $X, admin sozlaydi) oshsa job to'xtaydi va admin alert chiqadi.
- **FR-53** `[MVP]` Pipeline umumiy timeout: default 3 soat; oshsa `failed(timeout)`.

### 4.9 YouTube'ga joylash

- **FR-54** `[MVP]` Upload YouTube Data API v3 `videos.insert` orqali, **resumable upload** protokoli bilan (uzilishda davom ettirish).
- **FR-55** `[MVP]` Upload'dan keyin `thumbnails.set` (thumbnail mavjud bo'lsa).
- **FR-56** `[MVP]` Upload muvaffaqiyatli bo'lgach `youtube_video_id`, URL, publish vaqti saqlanadi; status → `published`; creator'ga bildirishnoma.
- **FR-57** `[MVP]` YouTube processing/upload xatolari alohida ishlanadi: `quotaExceeded` → job navbatga qaytariladi va keyingi quota oynasiga (Pacific Time yarim tunda reset) rejalashtiriladi; `forbidden`/`invalid_grant` → kanal `disconnected`, creator'ga xabar.
- **FR-58** `[MVP]` **Quota budjeti:** tizim har Google Cloud loyihasi uchun kunlik upload va unit budjetini kuzatadi (`quota_usage` hisoblagichi Redis+DB). Budjet 80% bo'lganda admin ogohlantiriladi, 100%da yangi upload navbatga qo'yiladi. Scale uchun quota extension so'rovi va/yoki bir nechta loyiha zarur (Risk R-4).
- **FR-59** `[MVP]` YouTube video statusi (processing/succeeded/rejected/copyright claim) upload'dan keyin 24 soat davomida davriy tekshiriladi va `video_jobs`ga yoziladi. YouTube tomonidan rad etilgan video creator'ga darhol xabar qilinadi.
- **FR-60** `[MVP]` Platforma joylagan video creator tomonidan YouTube'da o'chirilsa/o'zgartirilsa — keyingi sync'da aniqlanadi va `deleted_on_youtube` deb belgilanadi (revenue hisob-kitobidan chiqariladi).

### 4.10 Daromad kuzatuvi

- **FR-61** `[MVP]` Kunlik Celery task har ulangan kanal uchun YouTube Analytics API'dan metrikalarni oladi: `views`, `estimatedMinutesWatched`, `estimatedRevenue`, `estimatedAdRevenue`, `cpm`, `playbackBasedCpm` (mavjud bo'lganicha), video va kanal darajasida.
- **FR-62** `[MVP]` Ma'lumotlar `revenue_records`da **kun + video (yoki kanal)** granularligida, idempotent upsert bilan saqlanadi (qayta sync duplikat yaratmaydi).
- **FR-63** `[MVP]` YouTube ma'lumotlari kechikadi va **revizyalanadi** (48–72 soat, oy oxirida yakuniy). Tizim har yozuv uchun `is_final` bayrog'ini yuritadi va oxirgi 35 kunni har kuni qayta sync qiladi.
- **FR-64** `[MVP]` Dashboard'da: kunlik/oylik daromad grafigi, top videolar, RPM, "platforma tomonidan yaratilgan videolar" vs "boshqa videolar" ajratmasi.
- **FR-65** `[MVP]` **Muhim:** revenue share hisob-kitobi faqat **platforma yaratgan va joylagan videolar** daromadidan hisoblanadi (creator'ning o'z eski videolari kirmaydi). Bu shartnomada ham aniq yozilishi shart.
- **FR-66** `[MVP]` Agar `estimatedRevenue` API orqali mavjud bo'lmasa (kanal monetizatsiya qilinmagan yoki scope rad etilgan), tizim daromadni **0** deb hisoblaydi va Dashboard'da sababni ko'rsatadi — taxminiy raqam **o'ylab topilmaydi**.

### 4.11 Revenue share va to'lovlar

- **FR-67** `[MVP]` Oylik yopilish (period close) task: har creator uchun `SUM(estimatedRevenue)` (faqat platforma videolari, `is_final=true` yozuvlar) → `platform_share = 50%`, `creator_share = 50%`. Yaxlitlash: cent darajasida, `ROUND_HALF_UP`, ayirma platforma zarariga.
- **FR-68** `[MVP]` Hisob-kitob natijasi `revenue_share_statements` sifatida saqlanadi: davr, jami daromad, video breakdown, platforma ulushi, creator ulushi, holat.
- **FR-69** `[MVP]` Statement creator'ga Dashboard'da va PDF sifatida ko'rsatiladi; e'tiroz (dispute) qilish imkoniyati 14 kun (holat → `disputed`, Finance qo'lda hal qiladi).
- **FR-70** `[MVP]` **Pul harakati yo'nalishi — Q1 TASDIQLANGAN QAROR (service-fee model).** Google creator'ga 100% to'laydi (AdSense), platforma esa creator'ga 50% ni **"revenue-share service fee"** invoysi sifatida chiqaradi va saqlangan to'lov usulidan Stripe orqali undiradi. Minimal invoys chegarasi (default $10) — undan past summa keyingi davrga o'tkaziladi.
- **FR-70a** `[MVP]` **Majburiy saqlangan to'lov usuli.** Shartnoma imzolash oqimida (FR-28..32 bilan bir vaqtda) creator Stripe `SetupIntent` orqali to'lov usulini (karta yoki bank) saqlashi **majburiy**; `subscriptions.default_payment_method_id` to'ldirilmaguncha shartnoma `active` holatga o'tmaydi va video generation boshlanmaydi (FR-32 kengaytmasi). Bu undirilmaslik riskini (Risk R-1/R-8) kamaytiradi.
- **FR-70b** `[MVP]` **Dunning va pauza siyosati.** Revenue-share invoysi (FR-70) muvaffaqiyatsiz undirilsa: Stripe Smart Retries (3 urinish) → 7 kunlik grace period (creator'ga email/in-app ogohlantirish) → hali to'lanmasa creator'ning **video generation va yangi nashr jadvali pauza qilinadi** (`is_paused=true`, mavjud kanal ulanishi va ma'lumotlari saqlanib qoladi) → 30 kundan keyin Finance roli qo'lda ko'rib chiqadi (`written_off` yoki huquqiy undirish). Har bosqich `audit_logs` va `ledger_entries`da qayd etiladi.
- **FR-71** `[F2 / shartli]` Teskari yo'nalish (platforma pul olib, creator'ga to'laydi) kerak bo'lsa — Stripe Connect Express connected account, KYC onboarding, `transfers` orqali payout. `stripe_connected_accounts` va `payouts` jadvallari MVP'da schema darajasida tayyorlanadi, lekin faollashtirilmaydi.
- **FR-72** `[MVP]` Barcha moliyaviy operatsiyalar o'zgarmas (append-only) `audit_logs` va `ledger_entries`da qayd etiladi. Moliyaviy yozuv hech qachon UPDATE/DELETE qilinmaydi — faqat korreksiya yozuvi qo'shiladi.
- **FR-73** `[MVP]` Finance roli davr bo'yicha hisobotni CSV/XLSX eksport qila oladi.

### 4.12 Bildirishnomalar

- **FR-74** `[MVP]` Email orqali yuboriladigan hodisalar: email verifikatsiya, parol tiklash, kanal ulandi/uzildi, video tasdiqlash kerak, video joylandi, video xato, moderation rad etdi, to'lov muvaffaqiyatli/muvaffaqiyatsiz, oylik statement tayyor, shartnoma yangilandi.
- **FR-75** `[MVP]` Har bildirishnoma `notifications` jadvalida saqlanadi (in-app markaz + o'qilgan/o'qilmagan).
- **FR-76** `[MVP]` Creator kanal bo'yicha bildirishnoma sozlamalarini boshqara oladi (transaksion va xavfsizlik xabarlaridan tashqari — ular o'chirilmaydi).
- **FR-77** `[MVP]` Email shablonlari en/ru/uz tillarida; foydalanuvchi tili bo'yicha tanlanadi.
- **FR-78** `[F2]` Web push va Telegram bildirishnomalari.

### 4.13 Admin panel

- **FR-79** `[MVP]` Foydalanuvchilar ro'yxati: qidiruv, filtr (tarif, holat), detal ko'rinish, akkauntni suspend/reactivate.
- **FR-80** `[MVP]` Video job'lar monitoringi: status bo'yicha filtr, bosqich davomiyligi, xato sababi, **retry** va **cancel** buyruqlari.
- **FR-81** `[MVP]` Moderation navbati: flagged videolar, moderation natijalari, qo'lda approve/reject + majburiy sabab.
- **FR-82** `[MVP]` Moliyaviy hisobotlar: MRR, obuna taqsimoti, revenue-share jami, undirilmagan invoyslar, per-creator P&L (AI xarajat vs daromad).
- **FR-83** `[MVP]` Tarif (plan) va kvota konfiguratsiyasi UI orqali.
- **FR-84** `[MVP]` AI provider konfiguratsiyasi: aktiv provider, model nomi, narx parametrlari, feature flag (`api_credentials_config`). API kalitlari **UI'da ko'rsatilmaydi**, faqat "set/rotate" amali.
- **FR-85** `[MVP]` Tizim salomatligi: navbat uzunligi, worker holati, provider xato darajasi, quota iste'moli.

### 4.14 Ma'lumot huquqlari (GDPR-uslub)

- **FR-86** `[MVP]` Creator o'z ma'lumotlarini eksport qila oladi (JSON + media manifest), so'rov 30 kun ichida bajariladi (avtomatik, odatda daqiqalarda).
- **FR-87** `[MVP]` Creator akkaunt o'chirishni so'ray oladi: darhol OAuth tokenlar revoke + o'chiriladi, shaxsiy ma'lumot 30 kun ichida anonimlashtiriladi. **Istisno:** moliyaviy yozuvlar (invoys, statement, ledger) qonuniy talab bo'yicha saqlanadi (default 7 yil, anonimlashtirilgan holda).
- **FR-88** `[MVP]` Google user data faqat SPEC'da aytilgan maqsadlar uchun ishlatiladi (**Limited Use**): reklama uchun ishlatilmaydi, uchinchi tomonga sotilmaydi, inson tomonidan o'qilmaydi (xavfsizlik/support holatlaridan tashqari, ular audit qilinadi).
- **FR-89** `[MVP]` Kanal uzilgandan keyin 30 kun ichida bog'liq YouTube ma'lumotlari o'chiriladi (agregatlangan moliyaviy yozuvlardan tashqari).

---

## 5. Ma'lumot modeli (to'liq DB schema)

**Umumiy konvensiyalar:**
- PK: `id UUID` (default `gen_random_uuid()`), `BIGSERIAL` faqat log/append-only jadvallarda.
- Har jadvalda `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`, `updated_at TIMESTAMPTZ NOT NULL`.
- Soft-delete: `deleted_at TIMESTAMPTZ NULL` (moliyaviy va audit jadvallarda YO'Q).
- Pul: `NUMERIC(14,4)` + `currency CHAR(3)` (default `USD`). Float ishlatilmaydi.
- Vaqt: hammasi UTC (`TIMESTAMPTZ`).
- Shifrlangan maydonlar: `BYTEA`, nomida `_enc` suffiksi, yoniga `key_version SMALLINT`.
- ENUM'lar: PostgreSQL native enum yoki Django `TextChoices` + `VARCHAR` + CHECK (architect qaror qiladi).

---

### 5.1 `users`
| Field | Type | Notes |
|---|---|---|
| id | UUID PK | |
| email | CITEXT UNIQUE NOT NULL | |
| password_hash | VARCHAR(255) NULL | Google-only foydalanuvchida NULL |
| full_name | VARCHAR(255) | |
| is_email_verified | BOOLEAN DEFAULT false | |
| email_verified_at | TIMESTAMPTZ NULL | |
| google_sub | VARCHAR(255) UNIQUE NULL | Google `sub` (login identity) |
| locale | VARCHAR(5) DEFAULT 'en' | `en` \| `ru` \| `uz` |
| timezone | VARCHAR(64) DEFAULT 'UTC' | IANA tz |
| status | ENUM | `active` \| `suspended` \| `pending_deletion` \| `deleted` |
| totp_secret_enc | BYTEA NULL | 2FA |
| is_totp_enabled | BOOLEAN DEFAULT false | |
| last_login_at | TIMESTAMPTZ NULL | |
| marketing_opt_in | BOOLEAN DEFAULT false | |
| created_at / updated_at / deleted_at | TIMESTAMPTZ | |

Indeks: `email`, `google_sub`, `status`.

### 5.2 `roles`, `user_roles`
`roles(id UUID PK, code VARCHAR(32) UNIQUE, name, description)` — `creator`, `moderator`, `support`, `finance`, `admin`.
`user_roles(id UUID PK, user_id FK→users, role_id FK→roles, granted_by FK→users NULL, granted_at, UNIQUE(user_id, role_id))`.

### 5.3 `youtube_channels`
| Field | Type | Notes |
|---|---|---|
| id | UUID PK | |
| user_id | UUID FK→users NOT NULL | |
| youtube_channel_id | VARCHAR(64) **UNIQUE** NOT NULL | FR-16 |
| channel_title | VARCHAR(255) | |
| channel_handle | VARCHAR(100) NULL | |
| thumbnail_url | TEXT NULL | |
| subscriber_count | BIGINT NULL | oxirgi sync |
| video_count | BIGINT NULL | |
| is_monetized | BOOLEAN NULL | NULL = noma'lum (FR-17) |
| monetization_source | ENUM | `api` \| `self_declared` \| `unknown` |
| access_token_enc | BYTEA NOT NULL | AES-256-GCM |
| refresh_token_enc | BYTEA NOT NULL | |
| token_key_version | SMALLINT NOT NULL DEFAULT 1 | kalit rotatsiyasi |
| token_expires_at | TIMESTAMPTZ | |
| granted_scopes | TEXT[] | haqiqatda berilgan scope'lar |
| status | ENUM | `connected` \| `disconnected` \| `revoked` \| `error` |
| last_error_code | VARCHAR(64) NULL | |
| connected_at / disconnected_at | TIMESTAMPTZ | |
| last_synced_at | TIMESTAMPTZ NULL | |
| created_at / updated_at | | |

Indeks: `user_id`, `status`, `youtube_channel_id`.

### 5.4 `adsense_accounts`
Struktura `youtube_channels`ga o'xshash: `id, user_id FK, adsense_account_id VARCHAR UNIQUE, access_token_enc, refresh_token_enc, token_key_version, token_expires_at, granted_scopes TEXT[], status ENUM(connected|disconnected|revoked|error), connected_at, last_synced_at, created_at, updated_at`.

### 5.5 `plans`
| Field | Type | Notes |
|---|---|---|
| id | UUID PK | |
| code | VARCHAR(32) UNIQUE | `free` \| `starter` \| `professional` \| `enterprise` |
| name | VARCHAR(100) | |
| price_amount | NUMERIC(14,4) | 0 / 50 / 100 / 599 |
| currency | CHAR(3) DEFAULT 'USD' | |
| billing_interval | ENUM | `month` \| `six_months` |
| stripe_price_id | VARCHAR(255) NULL | |
| videos_per_period | INT | Free uchun kichik (Q4) |
| max_video_duration_sec | INT | |
| max_languages | INT | |
| concurrent_jobs | INT | |
| voice_cloning_enabled | BOOLEAN | |
| priority_queue | BOOLEAN | |
| sla_hours | INT NULL | Enterprise |
| features | JSONB | kelajakdagi flag'lar |
| is_active | BOOLEAN DEFAULT true | |
| sort_order | INT | |

### 5.6 `subscriptions`
`id UUID PK, user_id FK, plan_id FK→plans, stripe_customer_id VARCHAR, stripe_subscription_id VARCHAR UNIQUE NULL, default_payment_method_id VARCHAR NULL (Stripe PaymentMethod ID, FR-70a — revenue-share auto-charge uchun majburiy), status ENUM(trialing|active|past_due|suspended|canceled|expired), current_period_start TIMESTAMPTZ, current_period_end TIMESTAMPTZ, cancel_at_period_end BOOLEAN DEFAULT false, canceled_at TIMESTAMPTZ NULL, grace_period_ends_at TIMESTAMPTZ NULL, revenue_share_paused BOOLEAN DEFAULT false (FR-70b), created_at, updated_at`.
Indeks: `user_id`, `status`, `current_period_end`.

### 5.7 `usage_counters`
`id UUID PK, user_id FK, subscription_id FK, period_start, period_end, videos_generated INT DEFAULT 0, videos_published INT DEFAULT 0, regenerations_used INT DEFAULT 0, total_cost_usd NUMERIC(14,4) DEFAULT 0, UNIQUE(subscription_id, period_start)`.

### 5.8 `contract_versions`
`id UUID PK, version VARCHAR(20) UNIQUE, title, body_markdown TEXT, body_sha256 CHAR(64), locale VARCHAR(5), revenue_share_platform_pct NUMERIC(5,2) DEFAULT 50.00, revenue_share_creator_pct NUMERIC(5,2) DEFAULT 50.00, effective_from TIMESTAMPTZ, is_active BOOLEAN, created_by FK→users, created_at`.

### 5.9 `contracts` (imzolangan rozilik)
`id UUID PK, user_id FK, contract_version_id FK, signed_at TIMESTAMPTZ, ip_address INET, user_agent TEXT, body_sha256 CHAR(64), pdf_s3_key TEXT, consent_revenue_share BOOLEAN, consent_publish_to_channel BOOLEAN, consent_data_processing BOOLEAN, consent_marketing BOOLEAN, status ENUM(active|superseded|terminated), terminated_at TIMESTAMPTZ NULL`.
Indeks: `user_id`, `status`. Append-only (UPDATE faqat `status`/`terminated_at` uchun).

### 5.10 `content_preferences`
| Field | Type | Notes |
|---|---|---|
| id | UUID PK | |
| user_id | UUID FK | |
| channel_id | UUID FK→youtube_channels | |
| niche | VARCHAR(64) | `travel`, `cooking`, `motivation`, `technology`, ... |
| custom_brief | TEXT NULL | erkin ko'rsatma (FR-34) |
| brand_voice | TEXT NULL | ton, auditoriya |
| banned_topics | TEXT[] | |
| language | VARCHAR(10) | kontent tili (MVP: 1 ta) |
| video_duration_sec | INT | |
| aspect_ratio | ENUM | `16:9` \| `9:16` (F2) |
| frequency | ENUM | `daily` \| `weekly` \| `monthly` |
| publish_time_local | TIME | |
| publish_timezone | VARCHAR(64) | |
| publish_days | SMALLINT[] NULL | weekly uchun (0–6) |
| youtube_privacy_status | ENUM | `public` \| `unlisted` \| `private` |
| youtube_category_id | VARCHAR(8) | default `22` |
| made_for_kids | BOOLEAN DEFAULT false | |
| approval_mode | ENUM | `review_required` (default) \| `auto` |
| auto_publish_on_timeout | BOOLEAN DEFAULT false | |
| voice_id | VARCHAR(128) NULL | TTS ovoz |
| music_style | VARCHAR(64) NULL | |
| is_paused | BOOLEAN DEFAULT false | |
| created_at / updated_at | | |

### 5.11 `video_jobs` (markaziy jadval)
| Field | Type | Notes |
|---|---|---|
| id | UUID PK | |
| user_id | UUID FK | |
| channel_id | UUID FK→youtube_channels | |
| preference_id | UUID FK→content_preferences NULL | |
| trigger | ENUM | `scheduled` \| `manual` \| `regeneration` |
| parent_job_id | UUID FK→video_jobs NULL | regeneration uchun |
| status | ENUM | 7-bo'limdagi status modeli |
| current_stage | ENUM | `script`\|`voice`\|`visuals`\|`assembly`\|`moderation`\|`upload` |
| scheduled_for | TIMESTAMPTZ | rejalashtirilgan nashr vaqti |
| title | VARCHAR(100) NULL | YouTube limiti |
| description | TEXT NULL | ≤5000 bayt |
| tags | TEXT[] | jami ≤500 belgi |
| script_text | TEXT NULL | |
| script_meta | JSONB | model, prompt hash, token count |
| topic_embedding | VECTOR(1536) NULL | takroriylik tekshiruvi (pgvector) |
| language | VARCHAR(10) | |
| duration_sec | INT NULL | yakuniy |
| final_video_s3_key | TEXT NULL | |
| thumbnail_s3_key | TEXT NULL | |
| preview_token | VARCHAR(64) NULL | signed preview URL |
| preview_expires_at | TIMESTAMPTZ NULL | |
| approval_requested_at | TIMESTAMPTZ NULL | |
| approved_at / rejected_at | TIMESTAMPTZ NULL | |
| approval_actor_id | UUID FK→users NULL | |
| rejection_reason | TEXT NULL | |
| regeneration_count | SMALLINT DEFAULT 0 | |
| youtube_video_id | VARCHAR(32) NULL | |
| youtube_url | TEXT NULL | |
| published_at | TIMESTAMPTZ NULL | |
| youtube_upload_status | VARCHAR(32) NULL | `uploaded`\|`processed`\|`rejected`\|`deleted` |
| youtube_rejection_reason | VARCHAR(64) NULL | copyright, tos, duplicate... |
| is_platform_generated | BOOLEAN DEFAULT true | revenue share uchun (FR-65) |
| deleted_on_youtube | BOOLEAN DEFAULT false | FR-60 |
| error_code / error_message | VARCHAR(64) / TEXT NULL | |
| retry_count | SMALLINT DEFAULT 0 | |
| total_cost_usd | NUMERIC(14,4) DEFAULT 0 | |
| started_at / completed_at | TIMESTAMPTZ NULL | |
| created_at / updated_at | | |

Indeks: `(user_id, status)`, `(channel_id, published_at)`, `status`, `scheduled_for`, `youtube_video_id`.

### 5.12 `video_job_steps` (bosqich tarixi, append-only)
`id BIGSERIAL PK, job_id FK→video_jobs, stage ENUM, attempt SMALLINT, status ENUM(started|succeeded|failed|skipped), provider VARCHAR(64), provider_request_id VARCHAR(128) NULL, started_at, finished_at, duration_ms INT, cost_usd NUMERIC(14,4), error_code VARCHAR(64) NULL, error_detail TEXT NULL, output_ref TEXT NULL`.
Indeks: `(job_id, stage, attempt)`.

### 5.13 `video_assets`
`id UUID PK, job_id FK, kind ENUM(script|audio_voice|audio_music|visual_clip|subtitle|thumbnail|final_video), s3_key TEXT, mime_type VARCHAR(64), size_bytes BIGINT, duration_ms INT NULL, checksum_sha256 CHAR(64), provider VARCHAR(64), license_ref VARCHAR(128) NULL, sequence_index INT NULL, metadata JSONB, created_at`.

### 5.14 `music_tracks` (litsenziyalangan kutubxona)
`id UUID PK, title, s3_key, duration_ms, mood VARCHAR(64), bpm INT NULL, license_type VARCHAR(64), license_document_url TEXT, attribution_required BOOLEAN, attribution_text TEXT NULL, is_active BOOLEAN`.

### 5.15 `moderation_logs`
`id BIGSERIAL PK, job_id FK→video_jobs, stage ENUM(script|audio|visual|final), provider VARCHAR(64), verdict ENUM(pass|flag|block), categories JSONB (kategoriya→score), threshold_config JSONB, raw_response JSONB, reviewed_by FK→users NULL, review_decision ENUM(approved|rejected) NULL, review_reason TEXT NULL, reviewed_at TIMESTAMPTZ NULL, created_at`.
Indeks: `(job_id)`, `(verdict, reviewed_at)`.

### 5.16 `revenue_records`
| Field | Type | Notes |
|---|---|---|
| id | BIGSERIAL PK | |
| user_id | UUID FK | |
| channel_id | UUID FK | |
| job_id | UUID FK→video_jobs NULL | NULL = kanal darajasidagi yozuv |
| youtube_video_id | VARCHAR(32) NULL | |
| source | ENUM | `youtube_analytics` \| `adsense` |
| date | DATE NOT NULL | |
| views | BIGINT DEFAULT 0 | |
| estimated_minutes_watched | BIGINT DEFAULT 0 | |
| estimated_revenue | NUMERIC(14,4) DEFAULT 0 | |
| estimated_ad_revenue | NUMERIC(14,4) DEFAULT 0 | |
| cpm / rpm | NUMERIC(14,4) NULL | |
| currency | CHAR(3) DEFAULT 'USD' | |
| is_final | BOOLEAN DEFAULT false | FR-63 |
| synced_at | TIMESTAMPTZ | |
| raw_payload | JSONB | audit uchun |

**UNIQUE**(`source`, `channel_id`, `youtube_video_id`, `date`) — idempotent upsert (FR-62).
Indeks: `(user_id, date)`, `(is_final, date)`.

### 5.17 `revenue_share_statements`
`id UUID PK, user_id FK, period_start DATE, period_end DATE, currency CHAR(3), gross_revenue NUMERIC(14,4), platform_share_pct NUMERIC(5,2), platform_share_amount NUMERIC(14,4), creator_share_amount NUMERIC(14,4), video_count INT, breakdown JSONB (video_id→revenue), contract_id FK→contracts, status ENUM(draft|finalized|invoiced|paid|disputed|written_off|carried_forward), finalized_at, disputed_at NULL, dispute_reason TEXT NULL, resolved_at NULL, carried_forward_from UUID NULL, created_at, updated_at`.
**UNIQUE**(`user_id`, `period_start`, `period_end`).

### 5.18 `invoices` (revenue-share fee, Q1 default yo'nalishi)
`id UUID PK, user_id FK, statement_id FK→revenue_share_statements NULL, subscription_id FK NULL, kind ENUM(subscription|revenue_share), amount NUMERIC(14,4), currency, stripe_invoice_id VARCHAR UNIQUE NULL, stripe_payment_intent_id VARCHAR NULL, status ENUM(draft|open|paid|failed|void|uncollectible), due_at, paid_at NULL, attempts SMALLINT DEFAULT 0, pdf_url TEXT NULL, created_at, updated_at`.

### 5.19 `stripe_connected_accounts` *(schema tayyor, MVP'da faol emas — FR-71)*
`id UUID PK, user_id FK UNIQUE, stripe_account_id VARCHAR UNIQUE, account_type ENUM(express|standard), country CHAR(2), default_currency CHAR(3), charges_enabled BOOLEAN, payouts_enabled BOOLEAN, details_submitted BOOLEAN, requirements JSONB, onboarding_status ENUM(pending|in_progress|complete|restricted), created_at, updated_at`.

### 5.20 `payouts` *(schema tayyor, MVP'da faol emas)*
`id UUID PK, user_id FK, connected_account_id FK, statement_id FK NULL, amount NUMERIC(14,4), currency, stripe_transfer_id VARCHAR UNIQUE NULL, status ENUM(pending|processing|paid|failed|reversed), failure_reason TEXT NULL, initiated_at, completed_at NULL`.

### 5.21 `ledger_entries` (append-only, moliyaviy haqiqat manbai)
`id BIGSERIAL PK, entry_uuid UUID UNIQUE, user_id FK NULL, ref_type ENUM(invoice|statement|payout|subscription|adjustment|refund), ref_id UUID, direction ENUM(debit|credit), amount NUMERIC(14,4), currency, description TEXT, occurred_at TIMESTAMPTZ, recorded_at TIMESTAMPTZ DEFAULT now(), reversal_of BIGINT NULL`.
**UPDATE/DELETE taqiqlanadi (DB trigger yoki app-level guard).**

### 5.22 `notifications`
`id UUID PK, user_id FK, type VARCHAR(64), channel ENUM(email|in_app|push|telegram), title, body TEXT, payload JSONB, related_job_id UUID NULL, status ENUM(queued|sent|failed|read), sent_at NULL, read_at NULL, error TEXT NULL, created_at`.
Indeks: `(user_id, status, created_at DESC)`.

### 5.23 `notification_preferences`
`id UUID PK, user_id FK, type VARCHAR(64), email_enabled BOOLEAN, in_app_enabled BOOLEAN, push_enabled BOOLEAN, UNIQUE(user_id, type)`.

### 5.24 `api_credentials_config` (provider konfiguratsiyasi)
`id UUID PK, service ENUM(llm|tts|video_gen|music|moderation|translation|stt), provider VARCHAR(64) (openrouter|elevenlabs|azure_tts|runway|veo|svd|suno|openai_moderation|aws_rekognition|deepl|whisper), display_name, model_name VARCHAR(128) NULL, is_primary BOOLEAN, is_active BOOLEAN, priority SMALLINT, config JSONB (non-secret parametrlar), unit_cost_usd NUMERIC(14,6) NULL, cost_unit VARCHAR(32) NULL (per_1k_tokens|per_char|per_second|per_clip), secret_ref VARCHAR(128) (env/KMS kaliti nomi — **kalitning o'zi emas**), rate_limit_per_min INT NULL, created_at, updated_at`.
Constraint: har `service` uchun faqat bitta `is_primary=true`.

### 5.25 `api_usage_logs` (xarajat kuzatuvi)
`id BIGSERIAL PK, job_id FK NULL, user_id FK NULL, service ENUM, provider VARCHAR(64), model VARCHAR(128) NULL, operation VARCHAR(64), units NUMERIC(14,4), unit_type VARCHAR(32), cost_usd NUMERIC(14,6), latency_ms INT, http_status INT NULL, success BOOLEAN, error_code VARCHAR(64) NULL, request_id VARCHAR(128) NULL, created_at`.
Indeks: `(job_id)`, `(provider, created_at)`, `(user_id, created_at)`.

### 5.26 `quota_usage` (YouTube API kvota)
`id BIGSERIAL PK, google_project_id VARCHAR(64), date_pt DATE, units_used INT DEFAULT 0, uploads_used INT DEFAULT 0, units_limit INT, uploads_limit INT, UNIQUE(google_project_id, date_pt)`.

### 5.27 `audit_logs` (append-only)
`id BIGSERIAL PK, actor_type ENUM(user|staff|system), actor_id UUID NULL, action VARCHAR(128) (masalan `oauth.granted`, `token.revoked`, `video.published`, `invoice.paid`, `plan.changed`, `staff.viewed_user`), resource_type VARCHAR(64), resource_id VARCHAR(64), ip_address INET NULL, user_agent TEXT NULL, before JSONB NULL, after JSONB NULL, metadata JSONB, created_at TIMESTAMPTZ DEFAULT now()`.
Indeks: `(resource_type, resource_id)`, `(actor_id, created_at)`, `(action, created_at)`. Saqlash: 24 oy (moliyaviy — 7 yil).

### 5.28 `consents`
`id UUID PK, user_id FK, consent_type VARCHAR(64) (oauth_youtube|oauth_adsense|data_processing|marketing|revenue_share), granted BOOLEAN, scope_details JSONB, granted_at, revoked_at NULL, ip_address INET, user_agent TEXT`.

### 5.29 `data_requests` (GDPR)
`id UUID PK, user_id FK, kind ENUM(export|deletion), status ENUM(pending|processing|completed|rejected), requested_at, completed_at NULL, export_s3_key TEXT NULL, export_expires_at NULL, rejection_reason TEXT NULL, processed_by FK→users NULL`.

### 5.30 `webhook_events` (idempotentlik)
`id BIGSERIAL PK, provider VARCHAR(32) (stripe|google), event_id VARCHAR(255) UNIQUE, event_type VARCHAR(64), payload JSONB, signature_verified BOOLEAN, status ENUM(received|processed|failed|ignored), processed_at NULL, error TEXT NULL, received_at`.

### 5.31 Munosabatlar (qisqacha)
```
users 1─N user_roles N─1 roles
users 1─N youtube_channels 1─N content_preferences
users 1─N adsense_accounts
users 1─1 subscriptions N─1 plans
users 1─N contracts N─1 contract_versions
youtube_channels 1─N video_jobs 1─N video_job_steps
video_jobs 1─N video_assets
video_jobs 1─N moderation_logs
video_jobs 1─N revenue_records
users 1─N revenue_share_statements 1─1 invoices
users 1─1 stripe_connected_accounts 1─N payouts   (F2)
* 1─N audit_logs / api_usage_logs / ledger_entries
```

---

## 6. API yuzasi (endpoint guruhlari va auth mexanizmi)

**Baza:** `/api/v1/`. Format: JSON. Django REST Framework. OpenAPI 3.1 schema avtomatik generatsiya (drf-spectacular).
**Auth:** `Authorization: Bearer <access_jwt>`; refresh — httpOnly cookie orqali `/auth/refresh`. Staff endpointlar qo'shimcha rol + 2FA talab qiladi.
**Umumiy:** kursor-based pagination, `X-Request-ID` correlation, RFC 7807 `application/problem+json` xato formati, `Idempotency-Key` header — barcha mutatsion moliyaviy endpointlarda majburiy.

| Guruh | Endpointlar (namuna) | Kirish |
|---|---|---|
| **Auth** | `POST /auth/register`, `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`, `POST /auth/verify-email`, `POST /auth/password/reset`, `POST /auth/google`, `POST /auth/2fa/enable\|verify` | public / creator |
| **Me** | `GET/PATCH /me`, `GET /me/sessions`, `DELETE /me/sessions/{id}`, `GET /me/consents` | creator |
| **OAuth (Google)** | `GET /oauth/youtube/authorize` (→ state+PKCE), `GET /oauth/youtube/callback`, `POST /oauth/youtube/revoke`, `GET /oauth/adsense/authorize`, `GET /oauth/adsense/callback`, `POST /oauth/adsense/revoke` | creator |
| **Channels** | `GET /channels`, `GET /channels/{id}`, `POST /channels/{id}/sync`, `DELETE /channels/{id}` | creator |
| **Preferences** | `GET/POST/PATCH /channels/{id}/preferences`, `POST /channels/{id}/preferences/pause\|resume` | creator |
| **Plans & Billing** | `GET /plans`, `GET /me/subscription`, `POST /billing/checkout-session`, `POST /billing/portal-session`, `GET /invoices`, `GET /invoices/{id}/pdf` | creator |
| **Contracts** | `GET /contracts/current`, `POST /contracts/sign`, `GET /contracts/history`, `GET /contracts/{id}/pdf` | creator |
| **Video jobs** | `GET /videos` (filter: status, date), `GET /videos/{id}`, `POST /videos/generate` (manual), `POST /videos/{id}/cancel`, `PATCH /videos/{id}/metadata`, `GET /videos/{id}/preview` (signed URL), `POST /videos/{id}/approve`, `POST /videos/{id}/request-changes`, `POST /videos/{id}/reject`, `GET /videos/{id}/steps` | creator |
| **Revenue** | `GET /revenue/summary?from&to`, `GET /revenue/daily`, `GET /revenue/by-video`, `GET /revenue/statements`, `GET /revenue/statements/{id}`, `GET /revenue/statements/{id}/pdf`, `POST /revenue/statements/{id}/dispute` | creator |
| **Payouts** *(F2)* | `POST /payouts/connect/onboarding-link`, `GET /payouts/connect/status`, `GET /payouts` | creator |
| **Notifications** | `GET /notifications`, `POST /notifications/{id}/read`, `POST /notifications/read-all`, `GET/PATCH /notifications/preferences` | creator |
| **Data rights** | `POST /me/data/export`, `GET /me/data/export/{id}`, `POST /me/data/delete`, `POST /me/data/delete/cancel` | creator |
| **Admin — users** | `GET /admin/users`, `GET /admin/users/{id}`, `POST /admin/users/{id}/suspend\|reactivate`, `POST /admin/users/{id}/roles` | admin |
| **Admin — jobs** | `GET /admin/videos`, `POST /admin/videos/{id}/retry`, `POST /admin/videos/{id}/cancel`, `GET /admin/queues` | admin/support |
| **Admin — moderation** | `GET /admin/moderation/queue`, `POST /admin/moderation/{job_id}/decide` | moderator/admin |
| **Admin — finance** | `GET /admin/finance/overview`, `GET /admin/finance/statements`, `POST /admin/finance/statements/{id}/finalize`, `GET /admin/finance/export` | finance/admin |
| **Admin — config** | `GET/PATCH /admin/plans`, `GET/PATCH /admin/providers`, `POST /admin/providers/{id}/rotate-secret`, `GET/POST /admin/contract-versions`, `GET/PATCH /admin/feature-flags` | admin |
| **Webhooks** | `POST /webhooks/stripe` (signature verify), `POST /webhooks/google/pubsub` (F2) | public+signature |
| **System** | `GET /health/live`, `GET /health/ready`, `GET /metrics` (Prometheus, internal-only) | internal |

**Rate limit (default):** creator 120 req/min; auth endpointlar FR-7 bo'yicha; admin 300 req/min; webhook cheklanmaydi (signature bilan himoyalangan).

---

## 7. Video generation pipeline va status modeli

### 7.1 Bosqichlar

| # | Bosqich | Kirish | Chiqish | Provider (MVP) | Timeout |
|---|---|---|---|---|---|
| 1 | **Script** | niche, brief, brand_voice, oxirgi 20 mavzu, til, davomiylik | title, description, tags, script (segmentlarga bo'lingan), topic embedding | OpenRouter (Claude/GPT) | 5 min |
| 2 | **Script moderation** | script matni | verdict | OpenAI Moderation | 1 min |
| 3 | **Voice (TTS)** | script segmentlari, voice_id, til | voice-over audio (WAV/MP3) + segment timing | ElevenLabs (Q3) | 15 min |
| 4 | **Visuals** | segment prompt'lari, timing | video kliplar (per-segment) | video-gen provider (Q3) | 60 min |
| 5 | **Assembly** | kliplar + voice + musiqa + intro/outro | yakuniy MP4 (1080p, H.264/AAC) + thumbnail | FFmpeg (o'z worker'i) | 30 min |
| 6 | **Final moderation** | keyframe'lar + audio | verdict | AWS Rekognition + Moderation API | 5 min |
| 7 | **Review** | preview URL | creator qarori | — | 48 soat |
| 8 | **Upload** | MP4 + metadata | youtube_video_id | YouTube Data API v3 (resumable) | 60 min |
| 9 | **Post-publish check** | video_id | processing/copyright holati | YouTube Data API | 24 soat davomida |

Har bosqich: alohida Celery task, alohida navbat (`q_script`, `q_voice`, `q_visual`, `q_render`, `q_upload`), alohida concurrency va **idempotency key = (job_id, stage, attempt)**. Bosqich natijasi S3'ga yozilgach checkpoint qo'yiladi — qayta urinishda oldingi bosqichlar qayta bajarilmaydi.

### 7.2 Status modeli (`video_jobs.status`)

```
draft
  └→ scheduled ──(vaqt keldi / manual)──→ queued
        queued → generating_script → script_ready
               → moderating_script
               → generating_voice → voice_ready
               → generating_visuals → visuals_ready
               → assembling → assembled
               → moderating_final
                    ├─ pass ─→ (approval_mode=review_required) → awaiting_approval
                    │          (approval_mode=auto)            → upload_queued
                    └─ flag/block ─→ moderation_review  ── moderator ──┬→ upload_queued / awaiting_approval
                                                                        └→ moderation_rejected [terminal]
        awaiting_approval ─┬→ approved → upload_queued
                           ├→ changes_requested → queued (tanlangan bosqichdan)
                           ├→ rejected [terminal]
                           └→ (48h timeout) → expired [terminal] | upload_queued
        upload_queued → uploading → uploaded → published [terminal-success]
                                             → youtube_rejected [terminal]
        (har qanday bosqichda) → retrying → ... → failed [terminal]
        (creator/admin) → canceled [terminal]
        published → deleted_on_youtube  (post-sync tomonidan belgilanadi)
```

**Terminal statuslar:** `published`, `rejected`, `moderation_rejected`, `youtube_rejected`, `expired`, `failed`, `canceled`.
**Kvota qoidasi:** kvota `queued`da band qilinadi; `failed` (tizim/provider xatosi) va `canceled` (generatsiya boshlanishidan oldin) holatlarida qaytariladi; `rejected`/`moderation_rejected`da qaytarilmaydi.

### 7.3 Kuzatiladigan metrikalar (har bosqich)
`stage_duration_seconds` (histogram), `stage_failures_total{stage,provider,error_code}`, `queue_depth{queue}`, `job_cost_usd` (histogram), `moderation_flag_rate`, `youtube_upload_success_rate`, `quota_units_used`.

---

## 8. Nofunksional talablar

### 8.1 Xavfsizlik
- **NFR-1** Barcha trafik HTTPS/TLS 1.2+ (HSTS, `Secure` cookie'lar).
- **NFR-2** OAuth tokenlar AES-256-GCM bilan application darajasida shifrlanadi; kalit KMS/Secrets Manager'da, `key_version` bilan rotatsiya qo'llab-quvvatlanadi. DB dump'i o'g'irlansa ham tokenlar ochilmasligi kerak.
- **NFR-3** Hech qanday secret (token, API key, parol) log'ga, Sentry event'iga, xato javobiga tushmaydi — logging filtri majburiy va testda tekshiriladi.
- **NFR-4** OAuth: PKCE (S256) + `state` (bir martalik, 10 daq TTL) + exact redirect URI matching.
- **NFR-5** Webhook signature verification (Stripe) majburiy; verifikatsiyadan o'tmagan so'rov 400 bilan rad etiladi va log'ga yoziladi.
- **NFR-6** Django ORM (SQL injection himoyasi), DRF serializer validatsiyasi, CSRF (cookie-based oqimlar uchun), CSP/X-Frame-Options/X-Content-Type-Options header'lari.
- **NFR-7** Preview/media URL'lar — vaqtinchalik signed URL (default 24 soat), public bucket YO'Q.
- **NFR-8** Staff kirish 2FA bilan; staff'ning har bir foydalanuvchi ma'lumotini ko'rishi audit log'ga yoziladi (FR-88 Limited Use).
- **NFR-9** Dependency scanning (pip-audit/Dependabot) va SAST CI'da; secret scanning (gitleaks) pre-commit + CI.
- **NFR-10** Har release'dan oldin OWASP ASVS L2 checklist; auth/billing o'zgarishlarida `security-auditor` gate.

### 8.2 Muvofiqlik (compliance)
- **NFR-11** Google API Services User Data Policy — **Limited Use** talablari (FR-88). Sensitive/restricted scope'lar uchun Google **OAuth verification + xavfsizlik audit** talab qilinishi mumkin — bu launch bloklovchi bo'lishi mumkin (Risk R-5). Privacy Policy va Terms of Service sahifalari publish qilinishi shart, homepage domeni verifikatsiya qilinishi kerak.
- **NFR-12** YouTube API Services ToS: ma'lumotlarni 30 kundan ortiq keshlamaslik (agregat statistikadan tashqari), attribution, foydalanuvchining ma'lumotni o'chirish huquqi.
- **NFR-13** AdSense Program Policies: AdSense daromadini uchinchi tomonga taqsimlash Google'ning yozma ruxsatisiz taqiqlanadi (Risk R-1).
- **NFR-14** GDPR-uslub huquqlar: access, rectification, erasure, portability, restriction (FR-86..FR-89). DPA/Privacy Policy, cookie consent banner.
- **NFR-15** PCI DSS: karta ma'lumotlari **hech qachon** platformada saqlanmaydi/o'tmaydi — faqat Stripe Checkout/Elements (SAQ-A).
- **NFR-16** Moliyaviy yozuvlar append-only, 7 yil saqlash. Soliq (VAT/sales tax) hisob-kitobi Stripe Tax orqali (Q4 doirasida).

### 8.3 Performance
- **NFR-17** API p95 < 300 ms (read), p95 < 800 ms (write) — tashqi provider chaqiruvlaridan tashqari.
- **NFR-18** Dashboard birinchi mazmunli render < 2.5 s (broadband), Lighthouse Performance ≥ 85.
- **NFR-19** Video generation end-to-end p50 < 45 daqiqa, p95 < 3 soat (5 daqiqalik video uchun).
- **NFR-20** Analytics/revenue sync: 1000 kanal < 60 daqiqada (batch + parallel worker).
- **NFR-21** Og'ir hisobotlar (revenue aggregate) materialized view yoki pre-aggregated jadval orqali; on-the-fly full scan yo'q.

### 8.4 Scalability va ishonchlilik
- **NFR-22** MVP maqsadi: **500 aktiv creator**, kuniga **~200 video**. Arxitektura 5000 creator / 2000 video-kun'ga gorizontal kengayishga to'siq qo'ymasligi kerak.
- **NFR-23** Backend stateless (Docker), gorizontal scale; Celery worker'lar navbat turi bo'yicha alohida scale qilinadi (render worker'lar CPU-og'ir).
- **NFR-24** Barcha tashqi API chaqiruvlari: timeout + retry (eksponensial backoff + jitter) + **circuit breaker**. Provider ishlamasa job `failed` emas, `retrying` bo'lib navbatga qaytadi.
- **NFR-25** Barcha Celery task'lar idempotent; `at-least-once` yetkazishda takroriy bajarish zarar qilmasligi kerak.
- **NFR-26** Availability maqsadi: 99.5% (MVP), Enterprise uchun 99.9% (F2 SLA).
- **NFR-27** RPO ≤ 1 soat, RTO ≤ 4 soat. PostgreSQL PITR + kunlik backup; backup restore har chorakda sinovdan o'tkaziladi. S3 versioning + cross-region replication (F2).
- **NFR-28** Graceful degradation: revenue sync ishlamasa Dashboard oxirgi ma'lum ma'lumotni "eskirgan" belgisi bilan ko'rsatadi.

### 8.5 Observability
- **NFR-29** Structured JSON logging + `request_id`/`job_id` correlation; log darajalari va PII maskalash.
- **NFR-30** Sentry (backend + frontend), release tracking, source map.
- **NFR-31** Prometheus metrikalari + Grafana dashboard'lari: API latency/error rate, queue depth, stage durations, provider error rate, YouTube quota, MRR/cost.
- **NFR-32** Alert'lar (default): queue depth > 100 (10 daq), job failure rate > 10% (15 daq), YouTube quota > 80%, Stripe webhook failure, provider error rate > 20%, DB connection saturation > 80%, kunlik AI xarajat budjetdan oshsa.
- **NFR-33** OpenTelemetry tracing (F2 uchun tavsiya, MVP'da ixtiyoriy).

### 8.6 Lokalizatsiya
- **NFR-34** UI to'liq **en / ru / uz** (django `gettext` + frontend `i18next`). Sana/vaqt/valyuta formatlash lokalga mos.
- **NFR-35** Email shablonlari uchala tilda.
- **NFR-36** **Kontent tili** (video ichidagi til) UI tilidan mustaqil; MVP'da kanal bo'yicha bitta til (Q3).

### 8.7 Sifat va jarayon
- **NFR-37** Backend test coverage ≥ 80% (billing, revenue, moderation, OAuth modullarida ≥ 90%).
- **NFR-38** Barcha tashqi provider'lar test muhitida mock/stub bilan; CI real API chaqirmaydi.
- **NFR-39** Migratsiyalar orqaga mos (backward-compatible), zero-downtime deploy.
- **NFR-40** Feature flag'lar orqali risklik funksiyalarni (auto-publish, yangi provider) bosqichma-bosqich yoqish.

---

## 9. Integratsiyalar

| Integratsiya | Maqsad | Faza | Muhim eslatma |
|---|---|---|---|
| **Google OAuth 2.0** | Login + YouTube/AdSense ruxsati | MVP | PKCE; sensitive scope → Google verification kerak |
| **YouTube Data API v3** | `videos.insert` (resumable), `thumbnails.set`, `channels.list`, `videos.list` | MVP | Kvota — asosiy scaling cheklovi (R-4). Upload kvotasi alohida byudjetda; loyihaga kvota kengaytirish so'rovi zarur |
| **YouTube Analytics API** | views, watch time, `estimatedRevenue` | MVP | `yt-analytics-monetary.readonly` scope shart; ma'lumot 48–72 soat kechikadi va revizyalanadi |
| **AdSense Management API** | Daromadni mustaqil tasdiqlash | MVP (Q2 — tasdiqlangan) | Foydalanuvchi uchun ulash ixtiyoriy; ToS cheklovlari (R-1) — faqat *o'qish* (`adsense.readonly`), taqsimot uchun ishlatilmaydi |
| **OpenRouter (Claude/GPT)** | Script generation | MVP | Model nomi konfiguratsiyada, kodda hardcode emas |
| **TTS (ElevenLabs / Azure Neural)** | Voice-over | MVP: 1 ta (Q3) | Voice cloning — Professional+ (F2); ovoz huquqlari tekshiriladi |
| **Video generation (Runway / Veo / SVD)** | Vizual segmentlar | MVP: 1 ta (Q3) | Eng qimmat va eng sekin bosqich — cost ceiling majburiy |
| **Music (Suno / MiniMax)** | Fon musiqasi | F2 | MVP'da litsenziyalangan `music_tracks` kutubxonasi |
| **FFmpeg** | Assembly/render | MVP | O'z worker'ida, S3 stream I/O |
| **Whisper** | Subtitr/timing | F2 | MVP'da TTS timing metadata yetarli |
| **DeepL / Google Translate** | Ko'p tilli kontent | F2 | |
| **OpenAI Moderation + AWS Rekognition** | Kontent xavfsizligi | MVP | Ikkalasi ham majburiy gate (FR-45, FR-46) |
| **Stripe Billing (Checkout + Portal + Tax)** | Obuna to'lovlari, revenue-share invoyslari | MVP | Webhook idempotentligi majburiy |
| **Stripe Connect (Express)** | Platformadan creator'ga to'lov | F2 (shartli) | Faqat Q1 javobiga qarab |
| **AWS S3 / GCP Storage** | Media saqlash | MVP | Private bucket + signed URL + lifecycle (xom aktivlar 30 kundan keyin o'chiriladi, yakuniy video 12 oy) |
| **Email (SendGrid/SES/Postmark)** | Transaksion email | MVP | SPF/DKIM/DMARC sozlanishi shart |
| **Sentry / Prometheus / Grafana** | Observability | MVP | |
| **Eskiz SMS** | SMS | **Doiradan tashqari** | Bu loyihada SMS oqimi yo'q (global auditoriya). Kerak bo'lsa Q4 doirasida qayta ko'riladi |

---

## 10. Acceptance criteria

Loyiha "MVP tayyor" deb hisoblanadi, qachonki quyidagilarning **hammasi** bajarilsa.

### AC-1 — Auth va onboarding
- **Given** yangi mehmon, **When** email/parol bilan ro'yxatdan o'tadi, **Then** verifikatsiya emaili keladi va tasdiqlangach Dashboard'ga kiradi.
- **Given** tasdiqlanmagan email, **When** kanal ulashga urinadi, **Then** 403 va tushunarli xabar (uz/ru/en).

### AC-2 — YouTube ulash
- **Given** verifikatsiyalangan creator, **When** "Connect YouTube" bosadi va Google consent'ni tasdiqlaydi, **Then** kanal ma'lumotlari ko'rinadi, `status=connected`, `consents` va `audit_logs`da yozuv paydo bo'ladi.
- **Given** ulangan kanal, **When** DB'ni tekshirsak, **Then** `access_token_enc`/`refresh_token_enc` shifrlangan (plain-text emas) va hech qanday API javobida token qaytarilmaydi.
- **Given** boshqa creator, **When** o'sha kanalni ulashga urinadi, **Then** aniq xato (kanal band).
- **Given** creator "Disconnect" bosadi, **Then** Google revoke chaqiriladi, tokenlar DB'dan o'chiriladi, rejalashtirilgan job'lar `paused`.

### AC-3 — Shartnoma va tarif
- **Given** shartnoma imzolanmagan, **When** generation boshlanishi kerak, **Then** job yaratilmaydi va creator'ga "shartnomani imzolang" bildirishnomasi boradi.
- **Given** creator Starter tarifini sotib oladi, **Then** Stripe webhook keladi, `subscriptions.status=active`, kvota Starter darajasida.
- **Given** kvota tugagan, **When** "Generate now" bosiladi, **Then** 402/409 va upgrade taklifi.

### AC-4 — Generation pipeline
- **Given** faol preference (weekly), **When** rejalashtirilgan vaqt keladi, **Then** `video_jobs` yaratiladi va bosqichlar ketma-ket bajarilib `awaiting_approval`ga yetadi; `video_job_steps`da har bosqich uchun yozuv, `api_usage_logs`da xarajat mavjud.
- **Given** TTS provider 500 qaytaradi, **When** task bajariladi, **Then** 3 marta backoff bilan qayta uriniladi; muvaffaqiyatsizlikda `failed`, admin alert, kvota qaytariladi, creator xabardor qilinadi.
- **Given** `assembled` video, **When** yuklab olib tekshiramiz, **Then** MP4 H.264/AAC, 1080p, davomiylik preference'dagi ±10% ichida, audio va vizual sinxron.

### AC-5 — Moderation
- **Given** ssenariy taqiqlangan kontent o'z ichiga oladi, **When** moderation bajariladi, **Then** job `moderation_review`ga tushadi, `moderation_logs` yoziladi va video **avtomatik joylanmaydi**.
- **Given** flagged job, **When** Moderator sabab bilan rad etadi, **Then** status `moderation_rejected`, creator xabardor, audit log mavjud.

### AC-6 — Tasdiqlash va joylash
- **Given** `awaiting_approval` job, **When** creator Approve bosadi, **Then** 15 daqiqa ichida upload boshlanadi va muvaffaqiyatda `youtube_video_id` + URL saqlanadi, status `published`.
- **Given** joylangan video, **When** YouTube'da ochamiz, **Then** sarlavha/tavsif/teglar mos, privacy status to'g'ri, **AI-generated content disclosure yoqilgan**.
- **Given** `quotaExceeded` xatosi, **Then** job `upload_queued`da qoladi va keyingi kvota oynasida avtomatik qayta uriniladi (job `failed` bo'lmaydi).
- **Given** 48 soat javob yo'q va `auto_publish_on_timeout=false`, **Then** job `expired`, video joylanmaydi.

### AC-7 — Daromad va revenue share
- **Given** joylangan videolar va monetizatsiya qilingan kanal, **When** kunlik sync ishlaydi, **Then** `revenue_records` to'ldiriladi va Dashboard grafiklari ko'rinadi; **When** sync ikki marta ishlatiladi, **Then** duplikat yozuv paydo bo'lmaydi.
- **Given** oy yopiladi, **When** statement generatsiya qilinadi, **Then** `platform_share_amount + creator_share_amount == gross_revenue` (cent aniqligida) va breakdown faqat `is_platform_generated=true` videolarni o'z ichiga oladi.
- **Given** statement `finalized`, **When** creator PDF yuklaydi, **Then** hujjatda davr, videolar, summalar va shartnoma versiyasi ko'rsatilgan.
- **Given** kanal monetizatsiya qilinmagan, **Then** daromad 0 ko'rsatiladi va sabab tushuntiriladi (taxminiy raqam ko'rsatilmaydi).

### AC-8 — Xavfsizlik va compliance
- **Given** to'liq log arxivi, **When** secret pattern bo'yicha qidiramiz, **Then** hech qanday token/kalit topilmaydi.
- **Given** creator ma'lumot o'chirishni so'raydi, **When** so'rov ishlanadi, **Then** tokenlar darhol revoke, PII 30 kun ichida anonimlashtiriladi, moliyaviy yozuvlar anonim holda saqlanib qoladi.
- **Given** noto'g'ri imzo bilan Stripe webhook, **Then** 400 qaytariladi va hech qanday holat o'zgarmaydi.
- **Given** har qanday moliyaviy o'zgarish, **Then** `audit_logs` + `ledger_entries`da mos yozuv mavjud.

### AC-9 — Lokalizatsiya va UX
- **Given** foydalanuvchi `uz` yoki `ru` tilini tanlaydi, **Then** butun UI va emaillar shu tilda (tarjimasiz string qolmaydi — CI'da i18n coverage tekshiruvi).

### AC-10 — Operatsion tayyorlik
- Docker Compose bilan lokal to'liq stack ko'tariladi; GitHub Actions'da lint + test + build o'tadi; staging'ga avtomatik deploy; Grafana dashboard'lari va NFR-32 alert'lari faol; runbook (incident + provider outage + quota exhaustion) yozilgan.

---

## 11. Qabul qilingan default'lar (assumptions)

Bular TZ'da aniq aytilmagan, men oqilona to'ldirdim. Foydalanuvchi rad etsa — o'zgartiriladi.

| # | Default | Sabab |
|---|---|---|
| A-1 | MVP'da **1 creator = 1 YouTube kanal** | Murakkablikni kamaytirish; F2'da ko'p kanal |
| A-2 | Tasdiqlash rejimi default = **`review_required`** | YouTube ToS va sifat riski; `auto` — ongli tanlov |
| A-3 | Tasdiqlash timeout = **48 soat**, timeout'da default **joylanmaydi** | Xavfsiz default |
| A-4 | Video default: **1080p, 16:9, H.264/AAC**; Shorts/vertikal — F2 | Standart YouTube formati |
| A-5 | Fon musiqasi MVP'da **litsenziyalangan kutubxona**dan (AI musiqa — F2) | Mualliflik huquqi riski |
| A-6 | Subtitr/tarjima — **F2** | MVP hajmini cheklash |
| A-7 | Platforma valyutasi **USD** | Stripe + AdSense standarti |
| A-8 | Revenue share **faqat platforma yaratgan videolar** daromadidan | Adolatli va huquqiy jihatdan mudofaa qilinadigan |
| A-9 | Statement davri = **kalendar oy**, yopilish keyingi oyning **10-kuni** (YouTube ma'lumot yakunlanishini kutib) | Ma'lumot revizyasi (FR-63) |
| A-10 | Minimal invoys chegarasi **$10**, undan past — keyingi davrga o'tkaziladi | Stripe komissiyasi mayda summalarni yeb qo'yadi |
| A-11 | Pul yo'nalishi: **platforma creator'ga invoys chiqaradi** (Google 100% ni creator'ga to'laydi) | Google AdSense ToS (Risk R-1); **✅ Q1 orqali TASDIQLANGAN QAROR (v1.1) — endi assumption emas** |
| A-12 | Stripe Connect schema tayyorlanadi, lekin MVP'da **faollashtirilmaydi** | **✅ Q1 orqali TASDIQLANGAN (v1.1)** |
| A-13 | JWT: access 15 daq / refresh 14 kun (rotatsiya + reuse detection) | Sanoat standarti |
| A-14 | Staff rollari uchun **2FA majburiy** | Moliyaviy va PII kirish |
| A-15 | Kontent moderation **ikki bosqichli** (script + final) va bloklovchi gate | C-6 |
| A-16 | Har video uchun YouTube **AI/synthetic content disclosure** yoqiladi | YouTube talabi |
| A-17 | UI tillari: **en (default) / ru / uz** | Bozor talabi (global + CIS) |
| A-18 | Xom aktivlar S3'da **30 kun**, yakuniy video **12 oy** saqlanadi | Xarajat optimizatsiyasi |
| A-19 | MVP hajmi: **500 creator / 200 video-kun** | Arxitektura sizing uchun asos |
| A-20 | Free tarif: **oyiga 2 video, maks 60 s, watermark bilan**, revenue share qo'llanmaydi | Abuse va xarajat nazorati |
| A-21 | Har job uchun **2 ta bepul regeneration**, keyin kvotadan | Cost nazorati |
| A-22 | SMS (Eskiz) va Telegram integratsiyasi **doiradan tashqari** | Auditoriya global; email yetarli |
| A-23 | Ma'lumot rezidenti: EU yoki US region (bitta), CDN — Cloudflare | Q4 bilan bog'liq |
| A-24 | Soliq hisob-kitobi **Stripe Tax** orqali | Ko'p mamlakatli sotuv |
| A-25 | Deploy: MVP'da **Docker Compose + bitta VPS/Cloud VM** (+ managed PostgreSQL), Kubernetes — F2 | Erta bosqichda soddalik |

---

## 12. Ochiq savollar — **BARCHASI YECHILDI (v1.1, 2026-09-06)**

> Bular chinakam bloklaydigan, biznes qaroriga bog'liq savollar edi. Foydalanuvchi javob berdi — qarorlar quyida **TASDIQLANGAN QAROR** sifatida qayd etilgan (savol matni tarix uchun saqlanadi).

### Q1 — 50/50 taqsimot qanday amalga oshiriladi? **(ENG MUHIM — huquqiy + arxitektura)** — ✅ YECHILDI: **(a) Service-fee model**

> **TASDIQLANGAN QAROR:** variant (a) tanlandi. Amalga oshirish: FR-70, FR-70a (majburiy saqlangan to'lov usuli), FR-70b (dunning/pauza siyosati). Bu hali ham Risk R-1 (Google ToS bo'yicha huquqiy noaniqlik) ostida qoladi — ishga tushirishdan oldin yuridik ko'rikdan o'tishi tavsiya etiladi, lekin arxitektura va MVP shu model asosida quriladi.
**Muammo:** TZ'da "Stripe Connect `application_fee_amount` orqali 50% platforma ulushi" deyilgan. Lekin YouTube reklama puli **Google → creator'ning AdSense hisobiga** to'g'ridan-to'g'ri boradi — u hech qachon platformaning Stripe hisobidan o'tmaydi. Stripe Connect'ning `application_fee` faqat platforma orqali o'tgan to'lovdan ushlab qolishi mumkin. Bundan tashqari, **Google AdSense siyosati publisher'ga daromadini uchinchi tomon bilan bo'lishishni Google'ning yozma ruxsatisiz taqiqlaydi**.

**Variantlar:**
- **(a) Service-fee model (tavsiya etilgan default, A-11):** Google creator'ga 100% to'laydi. Platforma oyiga bir marta 50% ni "AI production & revenue-share service fee" sifatida invoys qiladi va creator'ning saqlangan karta/bank usulidan Stripe orqali undiradi. Risk: undirilmaslik (creator to'lamasligi mumkin) → depozit/prepaid balans yoki avtomatik to'lov majburiyati kerak.
- **(b) AdSense for Platforms (AFP):** Google'ning rasmiy platforma dasturi orqali revenue share. Rasmiy va toza, lekin Google bilan alohida shartnoma/tasdiq talab qiladi va odatda YouTube kanallariga emas, saytlarga tegishli — qo'llanishini tekshirish kerak.
- **(c) MCN/CMS model:** Platforma YouTube Multi-Channel Network sifatida ro'yxatdan o'tadi — YouTube CMS orqali rasmiy revenue split. Eng "to'g'ri" yo'l, lekin YouTube tomonidan tasdiqlanishi qiyin va uzoq.
- **(d) Teskari model:** Kanal platformaga tegishli, creator "hissa qo'shuvchi" — lekin bu C-1/C-2 falsafasiga (creator o'z kanaliga ega) zid.

**TASDIQLANGAN QAROR:** variant **(a)**. `stripe_connected_accounts`/`payouts` schema'si kelajak (F2/reverse-model) uchun tayyorlab qo'yiladi, lekin faollashtirilmaydi. **Eslatma:** bu qaror hali ham yuridik maslahat talab qiladi — R-1 riski ochiq qoladi (huquqiy ko'rikdan o'tguncha "yumshatilgan", "yopilgan" emas).

### Q2 — AdSense integratsiyasi MVP'da kerakmi? — ✅ YECHILDI: **HA, MVP'dan boshlab**

YouTube Analytics API allaqachon `estimatedRevenue` beradi (monetary scope bilan). AdSense Management API qo'shimcha consent, qo'shimcha ToS riski va ish hajmi keltiradi, lekin ko'proq "shaffoflik" beradi.

> **TASDIQLANGAN QAROR:** taklif qilingan default (F2'ga qoldirish) rad etildi — foydalanuvchi AdSense integratsiyasini **MVP'dan boshlab** talab qildi. Amalga oshirish: FR-19 (`[MVP]`ga o'tkazildi), FR-20 yangilandi, 3.1-bo'lim MVP ro'yxatiga item 3 sifatida qo'shildi, integratsiyalar jadvali (9-bo'lim) yangilandi. **Ta'sir:** MVP hajmi kengaydi (qo'shimcha OAuth consent oqimi, `adsense_accounts` sync job, qo'shimcha ToS/consent UI matni) — Risk R-13 (scope creep)ga qarang.

### Q3 — MVP'da qaysi provider'lar birlamchi (video-gen, TTS) va kontent tili qamrovi qanday? — ✅ YECHILDI: **Runway + ElevenLabs + faqat ingliz tili**

Video generation eng qimmat va eng katta sifat farqini beruvchi bosqich (Runway / Veo / Stable Video Diffusion narx va sifat jihatidan keskin farq qiladi — bir 5 daqiqalik video $2 dan $40 gacha turishi mumkin, bu unit economics'ni butunlay o'zgartiradi).

> **TASDIQLANGAN QAROR:** video-gen — **Runway** (sifat/API barqarorligi), TTS — **ElevenLabs**, kontent tili — MVP'da **faqat ingliz tili** (UI esa en/ru/uz), Faza 2'da qo'shimcha tillar qo'shiladi. Bu taklif qilingan default bilan bir xil edi — foydalanuvchi tasdiqladi, endi "assumption" emas, "qaror".

### Q4 — Platformaning yuridik shaxsi va bozori qayerda? — ✅ YECHILDI: **US (Delaware), global bozor, inglizcha**

Bu bir vaqtning o'zida uchta narsani belgilaydi: (1) **Stripe mavjudligimi** — Stripe O'zbekistonda platforma akkaunti sifatida qo'llab-quvvatlanmaydi, ya'ni US/EU/UK yuridik shaxsi kerak bo'lishi mumkin; (2) soliq/VAT tartibi; (3) ma'lumot rezidenti (EU → GDPR to'liq qo'llanadi) va Google OAuth verification jarayoni.

> **TASDIQLANGAN QAROR:** Platforma yuridik shaxsi **US (Delaware)**, birlamchi bozor **global/ingliz tilida**, UI'da uz/ru qo'shimcha til sifatida; ma'lumot rezidenti (EU vs US) implementatsiya bosqichida (`solution-architect`) aniqlashtiriladi — GDPR-uslub himoya baribir to'liq qo'llanadi (NFR-14) global auditoriya tufayli.

---

## 13. Risklar

| # | Risk | Ta'sir | Ehtimol | Yumshatish |
|---|---|---|---|---|
| **R-1** | **AdSense daromadini uchinchi tomon bilan bo'lishish Google siyosati bo'yicha cheklangan** — 50/50 modelning huquqiy asosi shubhali. **Yangilanish (v1.1):** Q1 service-fee model (FR-70/70a/70b) sifatida qaror qilindi — bu Google pulini bevosita bo'lishmaydi (creator'ga "AI xizmat haqi" invoysi sifatida chiqadi), lekin amaliy-huquqiy chegara hali test qilinmagan | Kritik (biznes modeli) | Yuqori | Service-fee modeli (qaror qilindi); ishga tushirishdan oldin yuridik ko'rikdan o'tkazish (**hali bajarilmagan**); shartnomada "AI production & revenue-share service fee" sifatida aniq formulirovka (FR-70) |
| **R-2** | **YouTube "inauthentic content" siyosati (2025-yil iyul)** — mass-produced, takrorlanuvchi, AI-narrated kontent monetizatsiyadan chetlatiladi. Bu platformaning butun qiymat taklifiga tahdid | Kritik | Yuqori | Har video uchun original insight/kontekst talabi; takroriylik tekshiruvi (FR-37); sifat gate; per-kanal chastota cheklovi; creator brief majburiy; "sifat > hajm" pozitsiyalash |
| **R-3** | **Yangi kanal YPP shartlarini (1000 obunachi + 4000 soat) bajarmaguncha daromad = $0** — revenue share modeli birinchi oylarda ishlamaydi | Yuqori | Yuqori | Onboarding'da aniq tushuntirish; obuna to'lovi asosiy daromad manbai; YPP holatini kuzatish (FR-17); "monetizatsiya qilinmagan kanal" uchun alohida UX |
| **R-4** | **YouTube Data API kvotasi** — upload kvotasi loyiha darajasida cheklangan; scale'da yetmasligi mumkin | Yuqori | O'rta | Kvota kengaytirish so'rovi (audit talab qilinadi) erta boshlanadi; kvota budjeti (FR-58); upload'larni kun bo'ylab taqsimlash; zaxira: bir nechta Cloud loyihasi (ToS doirasida) |
| **R-5** | **Google OAuth verification/security assessment** — sensitive/restricted scope'lar uchun tashqi audit ($10k–$75k va oylar) talab qilinishi mumkin; tasdiqlanmasa 100 test foydalanuvchi cheklovi | Yuqori | O'rta-Yuqori | Verification jarayonini loyiha boshida boshlash; Privacy Policy/ToS/homepage/demo video tayyorlash; MVP'ni test users bilan pilot qilish |
| **R-6** | **AI generation xarajati daromaddan yuqori bo'lishi** — bir video $2–$40, obuna esa $50–100/oy | Yuqori | Yuqori | Per-job cost ceiling (FR-52); real vaqtda xarajat kuzatuvi (FR-51); kvota; tarif narxlarini unit economics bo'yicha qayta ko'rish |
| **R-7** | **Provider bog'liqligi va API o'zgarishi** (Runway/ElevenLabs/OpenRouter narx yoki API o'zgartirsa) | O'rta | Yuqori | Provider abstraction layer (`api_credentials_config`); F2'da multi-provider failover; kontraktli test'lar |
| **R-8** | **Creator kanalini uzib qo'yadi yoki videolarni o'chiradi, lekin daromad qarzi qoladi** | O'rta | O'rta | Shartnomada disconnect'dan keyingi majburiyatlar; disconnect'da yakuniy statement; saqlangan to'lov usuli |
| **R-9** | **Copyright/Content ID da'volari** AI vizual yoki musiqa tufayli | O'rta | O'rta | Faqat litsenziyalangan/generatsiya qilingan aktivlar (FR-47); litsenziya hujjatlarini saqlash; post-publish claim monitoring (FR-59) |
| **R-10** | **Revenue ma'lumotining kechikishi va revizyasi** noto'g'ri hisob-kitobga olib kelishi | O'rta | Yuqori | `is_final` bayrog'i; 35 kunlik qayta sync; statement'ni oyning 10-kuni yopish (A-9); korreksiya yozuvlari |
| **R-11** | **GDPR "right to erasure" vs moliyaviy saqlash majburiyati ziddiyati** | O'rta | O'rta | Anonimlashtirish strategiyasi (FR-87); huquqiy asos — "legal obligation" |
| **R-12** | **Video render infratuzilmasi (FFmpeg/GPU) narxi va scale'i** | O'rta | O'rta | Alohida worker pool; spot instance; navbat prioritizatsiyasi; render vaqti monitoringi |
| **R-13** | **Loyiha hajmi juda katta** — MVP kengayib ketishi (scope creep). **Yangilanish (v1.1):** Q2 javobi bilan AdSense integratsiyasi (qo'shimcha OAuth consent, sync job, UI) MVP'ga qo'shildi — bu hajmni yanada oshiradi | Yuqori | Yuqori | 3.1 bo'limi qat'iy MVP chegarasi; F2 ro'yxatiga tegilmaydi; har sprint'da SPEC'ga qaytish; AdSense integratsiyasi alohida, izolyatsiyalangan modul sifatida qurilib, MVP'ning boshqa qismlarini bloklamasligi kerak (parallel ishlab chiqilishi mumkin) |
| **R-14** | **Stripe O'zbekistonda platforma sifatida mavjud emas** | Yuqori | O'rta | Q4 orqali yuridik shaxs joyini erta hal qilish |

---

## Aloqador skill'lar

Rule #0 bo'yicha `C:\Users\Sharjah\.claude\skills` katalogidan topilganlar (TZ'da ko'rsatilgan `C:\Users\User\.agents\skills` yo'li mavjud emas; faktik yo'l — `C:\Users\Sharjah\.claude\skills`, 2900+ skill).

**Bevosita aloqador (implementatsiyada FAOL ishlatilsin):**
| Skill | Yo'l | Qayerda |
|---|---|---|
| `oauth-implementation` | `C:\Users\Sharjah\.claude\skills\oauth-implementation\SKILL.md` | FR-10..FR-18 (PKCE, state, token rotatsiya) |
| `oauth` | `C:\Users\Sharjah\.claude\skills\oauth\SKILL.md` | Auth service |
| `stripe-integration` | `C:\Users\Sharjah\.claude\skills\stripe-integration\SKILL.md` | Billing, webhook, subscription (FR-21..FR-27) |
| `adding-stripe` | `C:\Users\Sharjah\.claude\skills\adding-stripe\SKILL.md` | Stripe setup |
| `stripe-payments` / `stripe-automation` | `...\stripe-payments\SKILL.md`, `...\stripe-automation\SKILL.md` | Connect/payout (F2) |
| `gdpr-data-handling` | `C:\Users\Sharjah\.claude\skills\gdpr-data-handling\SKILL.md` | FR-86..FR-89, NFR-14 |
| `django-pro` / `django-python` | `...\django-pro\SKILL.md`, `...\django-python\SKILL.md` | Backend (C-4) |
| `django-rest-api-development` / `rest-api-django` | `...\django-rest-api-development\SKILL.md` | API yuzasi (6-bo'lim) |
| `django-access-review` | `...\django-access-review\SKILL.md` | RBAC audit |
| `django-perf-review` | `...\django-perf-review\SKILL.md` | NFR-17..NFR-21 |
| `youtube-automation` | `...\youtube-automation\SKILL.md` | YouTube API cheklovlari, quota, upload maydonlari (FR-54..FR-58). **Eslatma:** skill Rube MCP orqali ishlaydi — bizga to'g'ridan-to'g'ri Google API kerak; faqat quota/limit bilimlari olinadi |
| `youtube-seo` / `youtube-thumbnail-design` | `...\youtube-seo\SKILL.md` | Metadata sifati, thumbnail (F2) |
| `saas-multi-tenant` | `...\saas-multi-tenant\SKILL.md` | Tenant izolyatsiyasi, kvota |
| `saas-mvp-launcher` | `...\saas-mvp-launcher\SKILL.md` | MVP scope discipline (R-13) |
| `billing-automation` | `...\billing-automation\SKILL.md` | Invoys/statement avtomatizatsiyasi |
| `pci-compliance` | `...\pci-compliance\SKILL.md` | NFR-15 (SAQ-A) |
| `auditing-security` / `security-compliance-compliance-check` | `...\auditing-security\SKILL.md` | Security gate |
| `adding-auth` | `...\adding-auth\SKILL.md` | Auth skeleti |
| `adding-docker` / `setting-up-ci` | `...\adding-docker\SKILL.md`, `...\setting-up-ci\SKILL.md` | Infra (AC-10) |
| `adding-error-tracking` / `adding-analytics` | `...\adding-error-tracking\SKILL.md` | Sentry, NFR-30 |
| `writing-tests` / `python-tdd-with-uv` | `...\writing-tests\SKILL.md` | NFR-37 |
| `video-optimization` | `...\video-optimization\SKILL.md` | FFmpeg/encode parametrlari |
| `kubernetes-deploying` | `...\kubernetes-deploying\SKILL.md` | **F2** (A-25) |
| `incident-response` | `...\incident-response\SKILL.md` | Runbook (AC-10) |

---

## Hujjat tarixi
| Versiya | Sana | O'zgarish |
|---|---|---|
| 1.0 | 2026-09-06 | Birinchi versiya. 4 ta ochiq savol (Q1–Q4) javobini kutmoqda. |
| 1.1 | 2026-09-06 | Q1-Q4 javoblari asosida yangilandi: **Q1** — service-fee revenue model tasdiqlandi (FR-70/70a/70b: majburiy saqlangan to'lov usuli + dunning/pauza siyosati qo'shildi, `subscriptions` jadvaliga `default_payment_method_id`/`revenue_share_paused` maydonlari qo'shildi); **Q2** — AdSense Management API integratsiyasi F2'dan **MVP'ga ko'chirildi** (FR-19 endi `[MVP]`, 3.1-bo'limga yangi item qo'shildi, R-13 yangilandi); **Q3** — Runway/ElevenLabs/faqat-ingliz-tili tasdiqlandi (avvalgi default bilan bir xil); **Q4** — US (Delaware)/global bozor tasdiqlandi (avvalgi default bilan bir xil). Barcha ochiq savollar yopildi. |
