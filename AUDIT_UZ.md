# PDF va 30 ta til talabi bo‘yicha kod auditi

Sana: 2026-09-17. Asos: `AI_YouTube_Ekotizim_Prompt.pdf` to‘liq matni, loyiha hujjatlari, backend va frontend kodining asosiy funksional yo‘llari.

## Xulosa

Hozirgi kod PDF va foydalanuvchining 30 ta til haqidagi yangi talabiga **to‘liq javob bermaydi**. Backendda katta hajmdagi implementatsiya mavjud, lekin frontend integratsiyasi tugallanmagan, ayrim endpointlar ulanmagan va kontent faqat ingliz tiliga cheklangan. Bu statik audit; real xizmatlarda muvaffaqiyatli ishlash tasdig‘i emas.

Ichki `SPEC.md:788–792` faqat inglizcha kontent va en/ru/uz interfeysni eski qaror sifatida ko‘rsatadi. Foydalanuvchining hozirgi 30 til talabi ushbu cheklovdan ustun. SPECda “tasdiqlangan” yozilgani bu suhbatda yangi tasdiq olinganini anglatmaydi.

## Talablar va dalillar

| Talab | Kod holati | Dalil / yetishmayotgan qism |
|---|---|---|
| Email/parol, JWT, Google login | Backend mavjud, UI qisman | `backend/accounts/views.py`, `frontend/src/pages/auth/LoginPage.tsx`: Google tugmasi ulanmagan |
| YouTube va AdSense OAuth | Backend mavjud, UI namuna | `backend/channels/services.py`, `channels/urls.py`; `frontend/src/pages/creator/ChannelPage.tsx` mock ma’lumot ishlatadi |
| Tematika, jadval, avtomatik ish yaratish | Backend mavjud, UI saqlashi mock | `backend/content_planning/services.py`, `tasks.py`; `PreferencesPage.tsx:36–62` |
| 30 tilda kontent | Bajarilmagan | `backend/config/settings/base.py:399`: `SUPPORTED_CONTENT_LANGUAGES = ["en"]`; serializer boshqa tillarni rad etadi |
| Ko‘p tilli interfeys | Faqat 3 til | `frontend/src/i18n/index.ts:10`: en/ru/uz; fallback inglizcha |
| Til tanlash | UI tugallanmagan | `PreferencesPage.tsx` forma sxemasida ham, maydonlarida ham kontent tili tanlovi yo‘q |
| Ssenariy → ovoz → video → montaj | Servislar va Celery zanjiri mavjud | `backend/video_pipeline/tasks.py`, `services/`; READMEning stub haqidagi umumiy izohlari eskirgan |
| Ishga tayyor AI konfiguratsiyasi | Boshlang‘ich sozlamalar yetarli emas | `providers/migrations/0002_seed_default_providers.py`: TTS va video-gen inactive/non-primary; ovoz IDsi sozlanmagan. Ishlayotgan DB holati tekshirilmagan |
| Moderatsiya va tasdiq | Ssenariy va final video yo‘llari mavjud | `script_moderation.py`, `visual_moderation.py`, `approval.py`; bu mualliflik huquqining to‘liq tekshirilishini isbotlamaydi |
| YouTube upload, thumbnail, til metama’lumoti | Backend mavjud | `services/youtube_upload.py`: upload, thumbnail, defaultLanguage/defaultAudioLanguage |
| AI musiqa, Whisper, tarjima integratsiyasi | PDFdagi hajm bajarilmagan | Montaj litsenziyalangan MusicTrack kutubxonasiga tayangan; Suno/MiniMax, Whisper, DeepL/Translate ishchi oqimi topilmadi. SPEC bularni keyingi bosqichga surgan |
| Tarif, obuna, Stripe webhook | Backend mavjud, UI qisman/mock | `backend/billing/services.py`; `BillingPage.tsx`; invoice list/PDF endpointlari 501 |
| Stripe Connect orqali 50/50 payout | PDFga mos emas | `billing/services.py:347` creator uchun xizmat haqi invoice yaratadi; `revenue/services/statements.py` hisob-kitob qiladi. Connected account/payout sxemasi bor, faol Connect payout oqimi yo‘q |
| Daromad monitoringi | Backend mavjud, cheklovli | Analytics/AdSense sync bor; UI mock, real vaqt moliyaviy natijasi tasdiqlanmagan |
| Shartnoma va audit | Backend mavjud, UI mock | `backend/contracts/`, `backend/audit/`; `ContractPage.tsx` haqiqiy APIga ulanmagan |
| Token AES-256 shifrlash | Mos emas | `backend/core/crypto.py:1–4` Fernet/AES-128-CBC ishlatadi; PDF AES-256, SPEC AES-256-GCM talab qiladi |
| Ma’lumot eksport/o‘chirish | Kod bor, ommaviy APIga ulanmagan | `accounts/data_rights.py` viewlari `accounts/urls.py` va asosiy URL daraxtiga qo‘shilmagan |
| 2FA, sessiyalar | Kod bor, route stub | `accounts/twofactor.py`, `sessions.py` mavjud; `accounts/urls.py` esa tegishli endpointlarda 501 qaytaradi |
| Creator/Admin dashboard | Katta qismi demo | `frontend/src/pages/` va `hooks/`da mockFetch/fixtures importlari va chaqiruvlari mavjud |
| Docker, CI, monitoring | Qisman | Docker Compose, GitHub Actions, Sentry konfiguratsiyasi bor; Prometheus/Grafana ishlaydigan stack konfiguratsiyasi topilmadi |

## Qo‘shimcha kod xavflari

- `revenue/services/adsense.py` AdSense qatorlariga bo‘sh video ID beradi; `services/sync.py` bunday qatorni job bilan bog‘lamaydi. `services/statements.py:64` esa `job__isnull=False` talab qiladi. Natijada hozirgi import yo‘li bilan AdSense qatorlari statementdagi “AdSense ustuvor” tanloviga kirmaydi.
- AdSense query filtri rad etilsa umumiy account summasiga fallback bor. Buni kanal/video daromadi deb tenglashtirishdan oldin alohida taqqoslash va manba tekshiruvi zarur.
- `content_planning/services.py:177` va `video_pipeline/services/youtube_upload.py:142` `django.utils.timezone.utc`ga murojaat qiladi. Loyiha pinlagan Django versiyasida moslikni runtime tekshirish va standart `datetime.timezone.utc`ga o‘tish kerak.
- `script_generation.py:214–216` davomiylikni bo‘shliq bilan ajratilgan so‘zlardan baholaydi; bu xitoycha kabi matnlarga moslashtirilmagan. `prompts.py` ham barcha tillarga bir xil 150 so‘z/minut taxminini beradi.
- `assembler.py` yakuniy matnni inglizcha `Thanks for watching`dan boshlaydi. Tilga qarab shrift tanlash, RTL va subtitr qamrovi qabul sinovlari bilan tasdiqlanmagan.
- `tts_client.py:105` til kodini faqat `send_language_code` sozlamasi yoqilganda yuboradi. Tillar bo‘yicha provider/model/voice imkoniyati reyestri va fallback marshrutlash yo‘q. Model nomidagi “multilingual” yozuvi 30 til uchun ishlash kafolati emas.

## 30 til uchun ishchi ro‘yxat

Bu mavjud implementatsiya emas, talabni aniq kodlarga aylantirish uchun taklif. Provayderlarning bugungi imkoniyatlari bu auditda onlayn tekshirilmagan.

| № | Til | Kod |
|---|---|---|
| 1 | Rus | ru |
| 2 | Ingliz | en |
| 3 | Fransuz | fr |
| 4 | Xitoy, mandarin | zh |
| 5 | Koreys | ko |
| 6 | Nemis | de |
| 7 | Arab, standart | ar |
| 8 | Turk | tr |
| 9 | O‘zbek | uz |
| 10 | Fors | fa |
| 11 | Hindi | hi |
| 12 | Urdu — Pokiston uchun taklif | ur |
| 13 | Qirg‘iz | ky |
| 14 | Qozoq | kk |
| 15 | Tojik | tg |
| 16 | Turkman | tk |
| 17 | Ozarbayjon | az |
| 18 | Gruzin — Kavkaz uchun taklif | ka |
| 19 | Ispan | es |
| 20 | Misr arabchasi | ar-EG |
| 21 | Hausa — Nigeriya uchun taklif | ha |
| 22 | Portugal | pt |
| 23 | Italyan | it |
| 24 | Yapon | ja |
| 25 | Indonez | id |
| 26 | Bengal | bn |
| 27 | Vetnam | vi |
| 28 | Tailand | th |
| 29 | Polyak | pl |
| 30 | Ukrain | uk |

“Pokiston”, “Nigeriya”, “Misr” davlat nomlari, “Kavkaz” mintaqa nomi. Yuqoridagi mosliklar foydalanuvchi tasdig‘i sifatida talqin qilinmasin. Nigeriya uchun Yoruba/Igbo yoki Kavkaz uchun boshqa til ham kerak bo‘lishi mumkin. Bu ro‘yxat 30 ta til/lokal variantdan iborat: standart arabcha va Misr arabchasi alohida variant hisoblangan. Agar aynan 30 ta mustaqil til talab qilinsa, Misr arabchasini arab tilining varianti qilib saqlab, yana bir mustaqil til qo‘shish lozim.

## Qabul mezonlari va tuzatish ketma-ketligi

1. Til/mintaqa nomlari va kontent hamda UI tarjimalari qamrovini aniqlash; yangi talabni SPECga kiritish.
2. Ulanmagan frontend APIlari, data-rights/2FA/session/invoice routelarini tugatish; demo ma’lumotlar bilan haqiqiy natijalarni aralashtirmaslik.
3. Har til uchun LLM, TTS model/ovoz, talaffuz, shrift, yozuv yo‘nalishi va YouTube til kodlarini reyestrga kiritish. Provider imkoniyatini tekshirmasdan dropdownni kengaytirish yetarli emas.
4. Har bir tilda qisqa namuna yaratish: ssenariy → audio → render → moderatsiya → preview. Matn va ovoz tili, talaffuz, belgilar, davomiylik, tarjima va RTLni tekshirish.
5. PDF bilan farq qilayotgan moliyaviy model va shifrlashni alohida yakunlash; shifrlash almashtirilsa eski tokenlarni o‘qish/migratsiya qilishni saqlash.
6. PostgreSQL bilan backend testlari, frontend lint/build/test, sozlangan provayderlar bilan integratsiya sinovi. YouTube nashri va haqiqiy to‘lovlar alohida aniq ruxsatli test muhitida bajariladi.

## Tekshiruv chegarasi

217 ta Python fayli AST orqali sintaksis tekshiruvidan o‘tdi. Bu import, DB migratsiya yoki biznes-logika testi emas. Ushbu lokal Python muhitida Django va pytest o‘rnatilmagan; frontend node_modules mavjud emas, Docker buyrug‘i topilmadi. Shuning uchun backend testlari va frontend build bajarilgani da’vo qilinmaydi. Tashqi APIlar chaqirilmadi, video nashr qilinmadi, pul operatsiyasi bajarilmadi. Amaliy kod o‘zgartirilmadi; faqat ushbu audit hujjati qo‘shildi.
