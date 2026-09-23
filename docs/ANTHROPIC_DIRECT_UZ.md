# Claude — to‘g‘ridan-to‘g‘ri Anthropic API

1. [Anthropic konsolida](https://platform.claude.com/) API billing va balansni tayyorlang. Claude web obunasi API balansini almashtirmaydi.
2. Alohida loyiha/workspace uchun API key yarating; kalitni chatga yubormang.
3. Superadmin va 2FA bilan `/admin/config` oching. **Claude · Ulanish sozlamalari** → **Ulanish usulini tanlash** → **Anthropic Console · API key** orqali kalitni kiriting.
4. Model ID va 1 million input/output token narxlarini kiriting. Boshlang‘ich `claude-sonnet-4-5`: $3 input, $15 output; [rasmiy narxlar](https://platform.claude.com/docs/en/about-claude/pricing) bilan tekshiring. Model ID o‘zgartirilsa tariflarni ham yangilang.
5. **Saqlash**, keyin **API sinovi**: modelga kirish tekshiriladi va kichik pullik Messages so‘rovi yuboriladi. Sarf platforma API usage jurnaliga yoziladi.
6. Muvaffaqiyatli sinovdan so‘ng **Asosiy AI sifatida yoqish**. Shundan keyin suhbat, kontent reja va ssenariy yaratish Anthropic’ga bevosita yuboriladi.

API xarajati tokenlar va saqlangan tarifdan hisoblanadi; bu provayder invoice summasining o‘zi emas. Mavjud 70/30 wallet siyosati saqlanadi. Kalit saqlashning o‘zi ishga tushirish hisoblanmaydi. Faol konfiguratsiyani qayta saqlash Claude’ni qayta sinov/yoqishgacha to‘xtatadi. Sinov limit: bir superadmin uchun daqiqasiga 5 ta.

## Xavfsizlik va ekspluatatsiya

Kalit `providers_providersecret` jadvalida mavjud AES-GCM field encryption orqali shifrlanadi. Javoblar va audit kalitni qaytarmaydi; Django dumpdata ham kalit maydonini eksport qilmaydi. Ma’lumotlar bazasining shifrlangan zaxirasi bilan birga mavjud `FIELD_ENCRYPTION_KEYS` qiymatini maxfiy, alohida saqlang. Eski kalitni o‘chirib yuborish saqlangan credentiallarni o‘qishni buzadi. Backend hamda barcha Celery workerlar bir xil encryption konfiguratsiyasidan foydalanishi kerak.

`providers.0004_providersecret` migratsiyasi deploydan oldin bajariladi. Serverda doimiy encryption key bo‘lmasa sozlamani saqlash rad etiladi. Kalitlar brauzer localStorage, Git yoki frontend buildga yozilmaydi. API so‘rovlari faqat `https://api.anthropic.com/v1` ga yuboriladi; redirectlar kuzatilmaydi.

Bir API loyiha bir nechta mijozga xizmat qiladi; har mijozning konteksti, wallet sarfi va vazifalari alohida saqlanadi. Amaliy parallel ishlash Anthropic rate limitlari va Celery worker quvvatiga bog‘liq. Ushbu integratsiya video/ovoz/moderatsiya kalitlari yoki Google OAuth o‘rnini bosmaydi.

API: `GET /api/v1/admin/anthropic` kalitsiz holat; `POST` action `save`, `test`, `activate`. Yozish faqat superadmin va amaldagi 2FA siyosati orqali. Key/model o‘zgarganidan keyin avvalgi sinov yaroqsiz bo‘ladi. Autopublish va moderatsiya tekshiruvlari mavjud pipeline orqali davom etadi.

## Ulanish tanlov oynasi

API key varianti mavjud backend saqlash/sinash/faollashtirish oqimini ochadi. Claude.ai Subscription varianti rasmiy Claude hisobiga tashqi havola va Claude Code kirish yo‘lini ko‘rsatadi; bu ekotizim assistentining obuna bilan autentifikatsiyasi emas va hech qanday OAuth/session/subscription tokenini yig‘maydi. Bedrock/Foundry/Vertex varianti yo‘riqnoma: adapterlar hali ulanmagan. Obuna kirish yo‘llari: https://code.claude.com/docs/en/legal-and-compliance#authentication-and-credential-use .
