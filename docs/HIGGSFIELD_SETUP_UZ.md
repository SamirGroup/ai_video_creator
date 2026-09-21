# Higgsfield integratsiyasi

2026-09-21: rasmiy model API sahifalari asosida Kling 3.0 Standard, Pro va 4K text-to-video qo‘llandi. Standart va Pro barcha to‘rt tijoriy tarifga; 4K Pro Max va Ultra tariflariga qo‘shiladi. Ovoz `on`, 3–15 soniya, 16:9 / 9:16 / 1:1. Image-to-video va boshqa oilalar ushbu adapterda hali qo‘llanmaydi.

## Sozlash

1. Backend muhitida `python manage.py seed_higgsfield` bajaring. Idempotent: mavjud admin narxlarini va faollik holatini o‘zgartirmaydi. Yangi modellar faol emas.
2. `HF_KEY=KEY_ID:KEY_SECRET` qiymatini backendning himoyalangan muhit fayliga joylang, repozitoriyga yoki frontendga yozmang.
3. Superadmin provayder sozlamalarida model narxi va API sxemasini tekshiring, so‘ng faollashtiring. Backend/worker muhitini qayta yuklang.
4. Tarifdagi `features.video_models` ruxsat ro‘yxatiga mos modelni tanlang. Pulli sinovdan keyin haqiqiy invoice bilan sarfni solishtiring.

Narxlar: $0.063/$0.084/$0.21 per second — 2026-09-21 rasmdagi launch offer uchun boshlang‘ich qiymatlar. Doimiy narx kafolati emas. Variantlar (sound, resolution) narxga ta’sir qilishi mumkin. Manba: https://open.higgsfield.ai/pricing
API sxemasi: https://open.higgsfield.ai/models/kling-video/v3.0/pro/text-to-video/api-reference (std/4k variantlari ham tekshirildi).
Lifecycle: https://docs.higgsfield.ai/docs/concepts/requests

## Hisob va kontent reja

$20/$50/$100/$200 bazaviy tariflar o‘zgarmaydi. 12% soliq alohida; sof to‘lovning 70% AI balansiga, 30% platformaga. Mavjud tasdiqlangan to‘lov webhooki balansni to‘ldiradi. Kredit model tokeni emas: 1 kredit = $0.0001. Higgsfield hisobini avtomatik bank orqali to‘ldirish amalga oshirilmagan; API provayder balansini operator ta’minlaydi.

`GET /api/v1/video-models` ochiq narx jadvali. `/pricing` ochiq sahifa va billing ichidagi jadval shu manbadan foydalanadi. Narx sanasi, tariflar va ulanish holati ko‘rsatiladi.
`GET /api/v1/me/planning-budget` — mavjud, band qilinmagan AI balansi / har video uchun maksimal xarajat chegarasi, tarifning qolgan kvotasi va 30 kunlik chegaraning minimumi. Konservativ hisob, video soni kafolati emas. Kontent reja yaratishda ham, tasdiqlashda ham qayta tekshiriladi; model tanlovi ishga uzatiladi. Generatsiya vaqtida mavjud atomik wallet/quota nazoratlari ishlaydi. Reja kelajakdagi oylik to‘lovlarni oldindan sarflamaydi.

## Sinov chegarasi

API kaliti berilmagan. Haqiqiy Higgsfield generatsiyasi va Stripe to‘lovi end-to-end tekshirilmagan. HTTP mock bilan autentifikatsiya, polling, request ID qayta ishlatilishi, moderatsiya rad javobi, noma’lum holatlar va begona status URL bloklanishi sinovdan o‘tkazildi. Backend budjet, entitlement, idempotent katalog va mavjud kontent reja/to‘lov hisobi sinovlari ishlatiladi.
