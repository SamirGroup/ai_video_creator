# Virtual raqamlar — xizmat va provayder tanlash

Narx va yangi to‘lovlar uchun yangilangan qo‘llanma: [PAYMENTS_ONBOARDING_UZ.md](PAYMENTS_ONBOARDING_UZ.md). Tannarx + 18% ustama + 12% soliq, Stripe/Visa va PayPal oqimlari shu hujjatda. Quyidagi dastlabki release qaydlari tarixiy holatni ham o‘z ichiga oladi.

2026-09-22. Holat: dasturiy modul tayyor, real sotuv standart holatda o‘chirilgan.

## Qaysi kompaniyalar bilan gaplashish kerak?

Bu ro‘yxat ijtimoiy tarmoqlarning kodlari albatta kelishini kafolatlamaydi. Raqam/SMS infratuzilmasi va rasmiy B2B hamkorlik bo‘yicha muzokara uchun saralangan nomzodlar:

| Kompaniya | Nima uchun ko‘rib chiqiladi | Rasmiy havola |
| --- | --- | --- |
| Telnyx | Managed service provider modeli, raqam va messaging infratuzilmasi; reseller modeli haqida birinchi suhbat uchun | https://telnyx.com/use-cases/managed-service-providers ; https://telnyx.com/contact-us |
| Twilio | Raqam qidirish/boshqarish APIlari va SMS infratuzilmasi | https://www.twilio.com/docs/phone-numbers ; https://www.twilio.com/en-us/company/contact-sales |
| Vonage | Ijaraga olingan virtual raqamlarga inbound SMS webhooklari | https://developer.vonage.com/en/api/sms ; https://www.vonage.com/communications-apis/ |
| Plivo | Davlat, raqam turi va SMS imkoniyati bo‘yicha tanlanadigan raqamlar | https://www.plivo.com/docs/numbers ; https://www.plivo.com/phone-numbers/ |

WhatsApp oddiy VoIP raqamlarni qo‘llab-quvvatlamaydi: https://faq.whatsapp.com/684051319521343/?cms_platform=iphone&locale=en_US . Telegram mobil raqam talab qiladi va ba’zan kodni SMS o‘rniga mavjud Telegram sessiyasiga yuboradi: https://telegram.org/faq . YouTube raqam tasdiqlashi monetizatsiya yoki yashash davlatini tasdiqlash emas: https://support.google.com/youtube/answer/171664?hl=en ; https://support.google.com/youtube/answer/72851?hl=en .

Shu sababli hamkor oddiy VoIP raqam bersa, uni WhatsApp uchun reklama qilmaymiz. Operator darajasidagi mobil raqam va aynan uchinchi tomon OTPlarini qabul qilish imkoniyatini yozma tekshiramiz. Provayderning o‘z Verify APIsi orqali kod **yuborish** biz talab qilayotgan tashqi platforma kodini **qabul qilish** xizmatidan farq qiladi.

## Provayderga yuborish uchun tayyor so‘rov

Subject: Dedicated mobile number rental and inbound SMS reseller partnership

Hello,

We operate a creator services platform and want to offer dedicated, exclusively assigned phone number rentals with private inbound SMS inboxes to our customers under a formal reseller agreement.

Please confirm in writing:

1. Whether resale/subleasing to our end users is permitted, including customer identification, country restrictions, and applicable documentation.
2. Available countries and number types (carrier mobile versus VoIP), exclusive assignment, minimum rental term, renewal, portability, and number recycling policy.
3. Whether receiving third-party verification SMS from YouTube/Google, Telegram, and WhatsApp is permitted and technically supported for each number type and country. We understand each platform retains its own acceptance rules; please distinguish verified support from untested compatibility.
4. Inbound SMS API/webhook documentation, signature verification, unique message IDs, delivery timestamps, and data processing/retention terms.
5. Setup fees, monthly rental, inbound SMS charges, minimum commitments, SLA, support, and failed-service refund conditions.
6. A sandbox or small paid pilot before customer-facing launch.

We will provide our company registration jurisdiction, customer countries, anticipated volume, and business documentation during onboarding.

Thank you.

Bu matn yuborilmadi. Kompaniya yurisdiksiyasi va mijoz davlatlari hali aniqlanmagan; bu hujjat huquqiy xulosa emas. Shartnoma oldidan shu ma’lumotlar asosida provayder talablari tekshiriladi.

## Tayyor modul

- Mijoz: `/virtual-numbers`; admin: `/admin/virtual-numbers`.
- Admin davlat/xizmat/raqam turi/provayder/narx/muddat va shartnoma/moslik tasdig‘ini kiritadi. Narx USD, kamida $1; bir martalik ijara, avtomatik uzaytirish yo‘q.
- Har bir real raqam admin orqali oldindan zaxiraga kiritiladi. Raqam sotib olish APIsi hali hech bir provayderga ulanmagan.
- Stripe Checkout alohida bir martalik to‘lov oladi. AI balansiga tegmaydi. Brauzerning qaytishi to‘lov dalili hisoblanmaydi: imzolangan webhook tasdiqlaydi.
- Raqam buyurtma davomida band qilinadi. To‘langan raqam keyinchalik boshqa foydalanuvchiga qayta berilmaydi. Bitta raqamni bir necha xizmat paketiga qayta kiritish mumkin emas; bir mijozga ajratilgan inbox unga kelgan barcha SMSlarni ko‘rsatadi.
- Xizmat tanlovi moslik katalogidir; platformaga login, avtomatik kod kiritish, akkaunt yaratish yoki monetizatsiya yoqish amalga oshirilmaydi.
- SMS matni va jo‘natuvchi shifrlangan saqlanadi; faqat egasiga ko‘rinadi. Admin oynasi SMS matnini ochmaydi. Mijoz kabineti 10 soniyada yangilanadi. SMS kirishidan ko‘pi bilan 24 soat yoki ijara oxirigacha ko‘rinadi.
- Mijoz pul qaytarish sababini yuboradi, admin Stripe orqali to‘liq refund qiladi. Provayder tasdiqlamaguncha tizim pul qaytarildi deb ko‘rsatmaydi. Ijro tugagach raqam iste’foga chiqariladi, SMSlar o‘chiriladi. Stripe dashboarddagi to‘liq refund ham webhook orqali hisobga olinadi.
- Buyurtma ro‘yxatlari oxirgi 100 yozuvni ko‘rsatadi; keyingi bosqichda server pagination qo‘shish mumkin.

## Sotuvni yoqishdan oldingi real ulanish

Standart sozlamalar:

```
VIRTUAL_NUMBERS_ENABLED=false
VIRTUAL_NUMBERS_INGRESS_SECRET=
VIRTUAL_NUMBERS_STRIPE_WEBHOOK_SECRET=
```

`STRIPE_SECRET_KEY` mavjud to‘lov sozlamasidan olinadi. Sirlar faqat server muhiti/secret store orqali beriladi. `FIELD_ENCRYPTION_KEYS_RAW` kabi mavjud shifrlash sozlamalari ishlashi kerak.

1. Kompaniya yurisdiksiyasi, maqsadli davlatlar, narx/soliq/refund shartlarini shartnomada aniqlash.
2. Provayderni tanlash va shartnomani yakunlash. Har bir tarif bo‘yicha moslikni pilotda tekshirish; umumiy reklama bayonotiga suyanmaslik.
3. Tanlangan provayderning **asl imzosini tekshiradigan connector** yozish va quyidagi ichki ingress formatiga moslash. Bu release provider-native Twilio/Telnyx/Vonage/Plivo callbackini to‘g‘ridan-to‘g‘ri qabul qilmaydi; connector hali qo‘shilmagan.
4. Stripe’da `/api/v1/webhooks/virtual-numbers/stripe` endpointini ochish; `checkout.session.completed`, `checkout.session.expired`, `charge.refunded` eventlarini yuborish va uning alohida secretini sozlash.
5. Real raqamlarni oldindan olish, admin katalogiga kiritish, webhook testini o‘tkazish. KYC kerak bo‘lsa, uni sotuvdan oldingi oqimga qo‘shish; bu modul avtomatik KYC o‘tkazmaydi.
6. SMS tozalash vazifasini har 5 daqiqada ishga tushirish: `python manage.py maintain_virtual_numbers`. DB/backup retention siyosatini alohida kelishish: backupdagi ma’lumot jonli DBdan o‘chirilishi bilan yo‘qolmaydi.
7. Test to‘lovi, SMS yetkazilishi, ikki mijoz orasida izolyatsiya, expiry va refundni haqiqiy sandboxda tekshirish; so‘ng server flagini va tasdiqlangan taklif sotuvini yoqish.

### Ichki SMS ingress shartnomasi

POST `/api/v1/webhooks/virtual-numbers/sms`, `Content-Type: application/json`.

```json
{
  "event_id": "provider:unique-message-id",
  "provider_reference": "provider:unique-number-id",
  "to": "+447700900123",
  "sender": "Example",
  "body": "Your code: 123456",
  "received_at": "2026-09-22T12:00:00Z"
}
```

Bu faqat format namunasi, haqiqiy raqam yoki xabar emas. IDlar provayder nomi bilan prefikslansin. `received_at` provayder bergan asl qabul vaqti bo‘lsin.

`X-SMS-Timestamp`: joriy Unix sekund. `X-SMS-Signature`: hex HMAC-SHA256(secret, timestamp + `.` + **o‘zgarmagan request body bytes**). ±5 daqiqadan eski imzo rad etiladi. Qayta yuborilgan event ID SMSni ko‘paytirmaydi. Connector qayta urinishda yangi imzo va vaqt, lekin o‘sha event IDni ishlatadi. Faqat ajratilgan raqam, tegishli provider reference va faol ijara davriga mos xabar saqlanadi. Unknown/unassigned raqamlar 200 bilan e’tiborsiz qoldiriladi.

### Operatsion chegaralar

Pending Checkout 1 soatda Stripe’da tugaydi va expired webhook bo‘sh raqamni zaxiraga qaytaradi. Tarmoq xatosidan keyin aynan bir request key bilan qayta urinish bir xil Checkoutni tiklaydi. Checkout yaratish jarayoni 25 daqiqadan ortiq uzilib qolgan yoki webhook kelmagan rezervlar administrator tomonidan Stripe bilan solishtirilib tiklanishi kerak; ko‘r-ko‘rona zaxiraga qaytarilmaydi. Bir mijozda ko‘pi bilan 3 pending buyurtma.

Provayderdagi raqamni avtomatik sotib olish, ijara uzaytirish va raqamni provayderdan avtomatik ozod qilish bu release tarkibida emas. Provayder xarajatlari va ijara tugashini operator kuzatadi. Real sotuv connector, pilot va shartnoma tayyor bo‘lmaguncha o‘chiq qoladi.

## Joylash holati

2026-09-22: arbitechglobal.com serveriga modul joylandi, `virtual_numbers.0001_initial` migratsiyasi qo‘llandi. Backend va frontend healthy; DB/cache health tekshiruvi o‘tdi. Sotuv o‘chiq; haqiqiy tarif yoki raqamlar o‘ylab kiritilmadi. Systemd timer: `ai-video-virtual-numbers.timer` — 5 daqiqada expiry/tozalash (serverda cron faol emas). Oldingi source, database dump va image teglar: `/root/deploy-backups/virtual-numbers-20260922`, `before-virtual-numbers-20260922`.

Tekshiruv: 27 backend testi (15 yangi modul, 12 mavjud Stripe webhook regressiyasi), 2 frontend testi; TypeScript va production build o‘tdi. Provider-native SMS va haqiqiy to‘lov pilotlari hali bajarilmagan.
