# Virtual raqamlar: narx, Visa, Stripe, PayPal va allpay.net

Tekshirilgan sana: 2026-09-22. Qo‘llanma aynan virtual raqamlarni bir martalik ijaraga berish uchun. Mavjud AI tariflari, 70/30 AI budjeti, Stripe obunalari va ularning webhook oqimi o‘z tartibida ishlaydi. Yangi raqam savdosi AI balansidan pul yechmaydi.

## 1. Hozir nima tayyor?

| Yo‘nalish | Dasturdagi holat | Real ishga tushirish uchun qolgan qism |
| --- | --- | --- |
| Narx | Tannarx + 18% platforma ustamasi + 12% soliq; mijoz va admin uchun alohida satrlar; buyurtma narxi o‘zgarmas nusxada saqlanadi | Soliq hisoblash bazasini buxgalter bilan tasdiqlash |
| Visa / Mastercard | Stripe’ning himoyalangan Checkout sahifasi orqali | Tasdiqlangan Stripe merchant, kalit va webhook, pilot |
| Stripe | Checkout, imzoli webhook, idempotent faollashtirish va refund | Merchant hisob va test/live sozlamalari |
| PayPal | Orders v2, hosted approval, server capture, webhook verifikatsiyasi va refund | Business hisob, Client ID/Secret, Merchant ID, Webhook ID, sandbox va live pilot |
| allpay.net Gateway Plus | To‘lov usullari ro‘yxati, admin holati va adapter chegarasi tayyor; avtomatik to‘lov olish bloklangan | Merchant shartnomasi va rasmiy tranzaksiya/HMAC/refund spetsifikatsiyasi asosida native connectorni yozish va testlash |
| SMS provayder | Xususiy inbox, zaxira, imzolangan ichki ingress | Raqam provayderining shartnomasi va native SMS connectori |

**Real savdo hozir o‘chirilgan.** Kalitlar kiritilmaguncha Stripe/PayPal to‘lovlari ishga tushmaydi. allpay uchun kalitning o‘zi yetmaydi: provider-native protokol tasdiqlanishi kerak. Bu hujjat hech bir merchant hisob ochilganini, bank tekshiruvidan o‘tilganini yoki real pul qabul qilinganini anglatmaydi.

## 2. Narx formulasi

Dastlabki talabga mos standart: ikkala foiz ham provayder tannarxidan hisoblanadi.

```
Provayder tannarxi                       $100.00
Platforma ustamasi = $100 × 18%           $18.00
Soliq = $100 × 12%                       $12.00
Mijoz to‘laydigan jami                   $130.00
```

Admin taklif yaratishda tannarxni kiritadi; tizim jami summani o‘zi chiqaradi. Foizlar mos ravishda 18% va 12%. Soliq bazasini tanlash mumkin:

- `base` — 12% tannarxdan; standart $100 → $130.
- `subtotal` — 12% tannarx + ustamadan; $100 + $18 + $14.16 = $132.16.

Har bir pul komponenti Decimal bilan sentgacha ROUND_HALF_UP yaxlitlanadi, keyin qo‘shiladi. Mijoz yuborgan jami summa backend hisobiga mos bo‘lmasa to‘lov ochilmaydi: yangi narxni ko‘rishi talab qilinadi. Gatewayga server hisoblagan summa yuboriladi. Eski buyurtma yangi narx yoki soliq bazasiga qayta hisoblanmaydi. Eski taklifda tannarx bo‘lmasa, admin uni kiritmaguncha sotuv ochilmaydi; avvalgi sotuv narxi tannarx deb taxmin qilinmaydi.

18% **tannarxga ustama**, sof foyda marjasi emas. Stripe/PayPal/allpay komissiyasi, konvertatsiya, refund xarajatlari va boshqa xarajatlar platforma ulushidan chiqadi; hozir ular mijozga yashirin qo‘shilmaydi. 12% foydalanuvchi topshirig‘idagi tijoriy sozlama: qaysi mamlakatda qanday soliq qo‘llanishi, ro‘yxatdan o‘tish va soliq bazasi qonunan mosligini o‘zi tasdiqlamaydi. Kompaniya yurisdiksiyasi hali berilmagan; real savdodan oldin buxgalter tasdiqlashi kerak. Stripe Automatic Tax yoqilmagan — ayni soliqni ikkinchi marta qo‘shmaymiz.

## 3. Bizdan talab qilinadigan ma’lumotlar

Avval quyidagi paketni tayyorlang. Yakuniy ro‘yxat merchant davlatiga va provayder underwriting tekshiruviga qarab farq qiladi.

1. Kompaniyaning ro‘yxatdan o‘tgan davlati, yuridik nomi, ro‘yxat raqami va manzili.
2. Soliq raqami, mavjud bo‘lsa VAT/QQS ro‘yxati va soliq hisoblash bo‘yicha tasdiq.
3. Direktor/vakil hamda haqiqiy egalarga oid provayder so‘ragan shaxsni tasdiqlash hujjatlari. Hujjatlarni provayderning himoyalangan kabinetiga topshiring.
4. Korporativ bank hisobi: davlat, hisob egasi, provayder talab qilgan rekvizitlar, hisob valyutasi. Shaxsiy hisob mos keladi deb taxmin qilmang.
5. Sayt domeni `arbitechglobal.com`, ishlaydigan support kontaktlari, yuridik rekvizitlar, xizmat tavsifi, narxlar, foydalanish/maxfiylik/refund shartlari.
6. Biznes model: dedicated raqam ijarasi va xususiy SMS inbox, qanday davlatlar, o‘rtacha chek, oylik aylanma, raqam provayderi bilan qayta sotish shartnomasi.
7. Stripe/PayPal/allpay aynan shu faoliyatni qabul qilishini tasdiqlash. Umumiy payment hisob ochilishi mahsulotning o‘zi tasdiqlanganini anglatmaydi.
8. Texnik administrator: domen, HTTPS, server environment va webhook sozlash huquqi.

API Secret, Stripe secret key, PayPal secret, HMAC secret va bank hujjatlarini Git yoki chatga kiritmang. `.env.example` faqat nomlar; haqiqiy qiymatlar serverning `.env`/secret store’ida bo‘ladi. Admin holati API kalitlarni ko‘rsatmaydi.

## 4. Tavsiya etilgan ketma-ketlik

1. Kompaniya va hisob yurisdiksiyasini aniqlash; har bir provayderda **pul qabul qilish va chiqarish** imkoniyatini tasdiqlash.
2. Soliq bazasi, mijozga jami narx va refund shartlarini kelishish.
3. Raqam provayderi va to‘lov provayderlariga biznes modelni taqdim etish, tegishli shartnomalarni olish.
4. Avval Stripe/Visa sandbox oqimini, keyin PayPal sandbox oqimini ulash.
5. allpay’dan Gateway Plus va texnik spetsifikatsiyani olish; native adapterni shu hujjat asosida yakunlash.
6. Sandboxda to‘lov, rad etilish, dublikat webhook, network retry, SMS, ijara tugashi va refundni sinash.
7. Live merchantni tasdiqlash, live kalit/webhooklarni alohida kiritish va kichik real pilot.
8. Admin katalogiga haqiqiy tannarx va raqamlar kiritish. Faqat tasdiqlangan takliflarni sotuvga ochish.

## 5. Visa va Stripe — bosqichma-bosqich

Visa karta tarmog‘i; bu release’da uni Stripe orqali qabul qilamiz. Stripe kartalar hujjati Visa va Mastercard qo‘llanishini ko‘rsatadi: https://docs.stripe.com/payments/cards . Alohida Visa Direct pul yuborish APIsi kerak emas.

1. Kompaniya davlati Stripe merchant ro‘yxatida ekanini tekshiring: https://stripe.com/global . Mijoz davlati bilan kompaniya davlatini aralashtirmang. Soxta manzil/davlat bilan hisob ochilmaydi.
2. Stripe biznes hisobini ro‘yxatdan o‘tkazing yoki mavjud hisobdan foydalaning. Dashboard so‘ragan kompaniya, bank, vakil/egalar va sayt ma’lumotlarini yakunlang: https://docs.stripe.com/get-started/account/activate .
3. Test rejimida secret key oling. Raqam savdosi uchun alohida key ishlatmoqchi bo‘lsangiz `VIRTUAL_NUMBERS_STRIPE_SECRET_KEY`ga qo‘ying. Bo‘sh bo‘lsa mavjud `STRIPE_SECRET_KEY` ishlatiladi. Mavjud AI obunalari ishlatayotgan live keyni o‘zgartirmang.
4. Stripe’da yangi webhook destination yarating:
   `https://arbitechglobal.com/api/v1/webhooks/virtual-numbers/stripe`
5. Eventlar: `checkout.session.completed`, `checkout.session.expired`, `charge.refunded`.
6. Aynan shu destinationning signing secretini `VIRTUAL_NUMBERS_STRIPE_WEBHOOK_SECRET`ga kiriting. Eski `/api/v1/webhooks/stripe` AI obuna destinationi saqlanadi; uning secretini almashtirmang.
7. `NUMBER_PAYMENTS_STRIPE_ENABLED=true`. Global raqam sotuvini faqat SMS ulanishi ham tayyor bo‘lsa yoqing. Hosted Checkout karta ma’lumotlarini qabul qiladi; bizning server karta raqami/CVV saqlamaydi.
8. Test kartalari, muvaffaqiyatsiz to‘lov va 3DS holatlarini rasmiy test qo‘llanmasi bilan sinang: https://docs.stripe.com/testing .
9. Dashboard webhook deliveries’da 2xx javob, buyurtmada aynan kutilgan total va raqam faollashishini tekshiring. Brauzer qaytgan sahifa to‘lov dalili emas.
10. Kichik test refundi va takroriy eventni tekshiring. Live ishga tushirishda live key **va live webhook secret**ni kiriting; birini test, birini live qoldirmang.

Narx `price_data` orqali har bir buyurtmada hosil qilinadi; har bir raqam tarifi uchun alohida Stripe Price ID yaratish shart emas. Komissiya miqdorini merchant davlati va Stripe shartnomasi bo‘yicha oling: kodda universal komissiya o‘ylab belgilanmagan.

## 6. PayPal — bosqichma-bosqich

Rasmiy integratsiya: https://developer.paypal.com/docs/checkout . Merchant davlati va pul qabul qilish/yechish imkoniyatini PayPal bilan tekshiring: https://www.paypal.com/webapps/mpp/country-worldwide . Global saytda davlat borligi barcha merchant imkoniyatlari aynan bir xil degani emas.

1. Mos davlatda PayPal **Business** hisobini oching/tasdiqlang. Bank, yuridik nom, shaxs/egalar va biznes faoliyati bo‘yicha so‘ralgan tekshiruvlarni tugating.
2. Developer Dashboard’da Apps & Credentials orqali sandbox REST app yarating; Client ID va Secretni oling: https://developer.paypal.com/dashboard/ .
3. Sandbox Business (sotuvchi) va Personal (xaridor) test hisoblarini tayyorlang. Sotuvchi hisobning Merchant ID qiymatini oling; bu Client ID yoki email emas.
4. Server sozlamalari:

```
PAYPAL_ENABLED=true
PAYPAL_MODE=sandbox
PAYPAL_CLIENT_ID=<sandbox REST app client id>
PAYPAL_CLIENT_SECRET=<sandbox REST app secret>
PAYPAL_MERCHANT_ID=<sandbox sotuvchi merchant id>
PAYPAL_WEBHOOK_ID=<shu app webhook id>
```

5. Aynan shu sandbox app ichida webhook yarating:
   `https://arbitechglobal.com/api/v1/webhooks/virtual-numbers/paypal`
6. Eventlar: `CHECKOUT.ORDER.APPROVED`, `PAYMENT.CAPTURE.COMPLETED`, `PAYMENT.CAPTURE.REFUNDED`. Olingan webhook **ID**ni konfiguratsiyaga yozing; URL yoki secret bilan almashtirmang.
7. Mijoz PayPal usulini tanlaydi → server Orders v2 orqali buyurtma yaratadi → mijoz PayPal sahifasida tasdiqlaydi → qaytganda server capture qiladi. Imzolangan `CHECKOUT.ORDER.APPROVED` hodisasi ham capture’ni yakunlashga xizmat qiladi; foydalanuvchi oynani yopsa ham webhook ishlaydi.
8. Faollashtirishdan oldin server PayPal’dan orderni qayta oladi: order ID, bizning buyurtma ID, merchant ID, USD valyutasi, jami summa va `COMPLETED` capture tekshiriladi. `APPROVED` yoki `PENDING` holati xizmatni ochmaydi.
9. Webhook imzosi PayPal `verify-webhook-signature` orqali tekshiriladi. Takroriy event bir buyurtmaga ikki marta xizmat bermaydi. Manba: https://developer.paypal.com/api/webhooks/v1/verify-webhook-signature-post .
10. To‘liq refund admin orqali capture IDga qilinadi; PayPal tasdiqlamaguncha pul qaytarildi deb ko‘rsatilmaydi. Dashboarddan to‘liq refund ham webhook orqali hisobga olinadi. Qisman refund butun ijarani avtomatik bekor qilmaydi; admin ko‘rib chiqadi.
11. Test yakunlangach live REST app, live Business Merchant ID va live webhook IDni alohida oling. `PAYPAL_MODE=live` va live kalitlarni kiriting. Sandbox hisob IDlarini live’da ishlatmang.
12. Kichik live to‘lov, settlement va refundni tekshiring, keyin mijozlar uchun oching.

Capture API: https://developer.paypal.com/api/orders/v2/orders-capture . Create/capture/refund requestlari barqaror `PayPal-Request-Id` bilan yuboriladi. Credentials yoki API javoblaridagi shaxsiy ma’lumotlar logga chiqarilmaydi.

**Operatsion cheklov:** PayPal’da tark etilgan pending buyurtmaning raqami mahalliy vaqtga qarab ko‘r-ko‘rona boshqa mijozga berilmaydi. PayPal terminal holatini/real to‘lovni tekshirib reconciliation qilish kerak. Bir mijozda ko‘pi bilan uch pending rezerv mavjud. Bu release PayPal recurring subscriptions qo‘shmaydi; virtual raqam bir martalik ijara mahsuloti.

## 7. Aynan allpay.net — bosqichma-bosqich

Siz bergan havola **allpay Limited (UK)**. `allpay.to`, `allpayx.com` va Alipay boshqa tizimlar; ularning APIlari bilan almashtirilmadi.

Rasmiy Gateway Plus qo‘llanmasi hosted sahifa va Professional tier’da sozlanadigan iframe, domain ruxsati va HMAC imkoniyatini ta’riflaydi. HMAC texnik sozlamasini ularning texnik vakili bilan kelishish talab qilinadi: https://allpay.helpscoutdocs.com/article/380-gateway-plus-user-guide . Bu ochiq qo‘llanma tranzaksiya yaratish va refund uchun to‘liq dasturchi spetsifikatsiyasini bermaydi; shu bois kodda taxminiy API ishlatilmagan.

1. [Rasmiy kontakt](https://www.allpay.net/contact/) orqali biznes so‘rovi yuboring. Savdo: `salesteam@allpay.net`; onboarding: `implementation@allpay.net`. Xat biz tomondan yuborilmagan.
2. Kompaniya va bank davlati, raqam ijarasi/SMS biznes modeli, mijoz davlatlari, o‘rtacha chek, yillik tranzaksiya soni va aylanmasini ko‘rsating. Ular aynan shu yurisdiksiya/faoliyatni qabul qiladimi — yozma javob oling.
3. Gateway Plus tariflari bo‘yicha taklif/shartnoma so‘rang. Bizga faqat umumiy to‘lov sahifasi emas, buyurtma summasi va reference’ni o‘zgartirishdan himoyalash, server notification va refund zarur.
4. Payments Hub merchant/organisation hisobini, tegishli huquqlarni va sandboxni oling. Hosted Gateway URL va merchant identifikatorini olish usulini so‘rang.
5. Quyidagi **rasmiy texnik hujjatlar va namunalar**ni talab qiling:
   - Order/payment yaratish: HTTPS endpoint, autentifikatsiya, request/response, idempotency, amount minor units, currency va unique reference.
   - Checkout URL yoki iframe maydonlari, domain allowlist, mijoz summani o‘zgartira olmasligi.
   - Notification: to‘liq payload, HMAC algoritmi, canonical string/tartib/encoding, timestamp/replay cheklovi, headers, retry siyosati, event ID va test vektori.
   - Payment status query API, qaysi holat yakuniy `paid`/`settled` hisoblanishi.
   - Refund: endpoint, autentifikatsiya, partial/full, status va takroriy so‘rovlar.
   - USD’da qabul qilish mumkinmi, settlement valyutasi, FX, komissiyalar, reserve/payout muddatlari, dispute/chargeback talablari.
6. `arbitechglobal.com`ni ruxsat etilgan domen sifatida ro‘yxatga oldiring. Webhookning yakuniy pathi connector hujjati bilan belgilanadi; hozir native allpay webhook endpointi yo‘q.
7. `backend/virtual_numbers/gateways/allpay.py` chegarasida native adapterni shu hujjatga mos yakunlaymiz. Hozir u to‘lov/refundni ataylab bajarmaydi va readiness uni yoqishga yo‘l qo‘ymaydi.
8. Sandboxda noto‘g‘ri HMAC, noto‘g‘ri summa/valyuta/reference, dublikat callback, payment query va refund sinovlarini o‘tkazamiz.
9. Faqat shundan keyin live kalitlar, kichik pilot va allpay usulining mijoz uchun ochilishi.

**allpay’ga yuborish uchun matn:**

> Subject: Gateway Plus merchant onboarding and server integration specification
>
> Hello, we operate arbitechglobal.com and plan to sell dedicated phone number rentals with private inbound SMS inboxes under supplier agreements. Please confirm merchant eligibility for our company/bank jurisdiction and this business model. We need hosted checkout with server-controlled amount and order reference, verified real-time payment notifications, status reconciliation and refunds. Please provide your sandbox access, native transaction API documentation, HMAC signing/verification specification with test vectors, currency/settlement support (including USD), onboarding/KYB requirements and commercial terms. We can provide our incorporation details, customer countries and forecast transaction volumes during onboarding.

## 8. Server sozlash va deployment

- `.env`dagi maxfiy qiymatlar source sync bilan almashtirilmaydi. Lokal `backend/.env.example` va root `.env.example`da o‘zgaruvchi nomlari berilgan.
- `VIRTUAL_NUMBERS_ENABLED=false` xizmatning umumiy sotuv kaliti; pilot va shartnomalar tugamaguncha shu holatda qoladi.
- `VIRTUAL_NUMBERS_INGRESS_SECRET` — raqam provayderining ichki SMS connectori; PayPal/Stripe webhook secretiga teng emas.
- Admin holati: `/admin/virtual-numbers`; narxlar preview va payment readiness shu yerda.
- API: `/api/v1/admin/virtual-numbers/payments`, `/api/v1/admin/virtual-numbers/price-preview` — admin + 2FA talab qiladi.
- Mijoz: `/virtual-numbers`; buyurtma/xabar faqat egasiga ko‘rinadi.
- Server soati NTP bilan sinxron bo‘lsin; imzo timestamp tekshiruvlari vaqtga bog‘liq.
- Build/migration/recreate uchun uch Compose fayli birga ishlatiladi: `docker-compose.yml`, `docker-compose.prod.yml`, `deploy/arbitech-live.yml`.
- Narx va to‘lov migratsiyasi qo‘shimcha maydonlar qo‘shadi; mavjud buyurtmalarning summasi va provayderi saqlanadi, eski buyurtmalar Stripe sifatida qoladi.
- SMS retention/expiry: `ai-video-virtual-numbers.timer` har besh daqiqada ishlaydi.

## 9. Ishga tushirishni qabul qilish mezonlari

- $100 tannarx uchun tanlangan bazaga mos $130 yoki $132.16 ko‘rinadi, gateway aynan shu summani oladi.
- Narx, merchant, valyuta va order ID backend tomonidan tekshiriladi.
- Karta rad etilsa yoki capture pending bo‘lsa raqam ochilmaydi.
- Bir hodisa qayta yuborilganda ikkinchi marta xizmat yoki refund yaratilmaydi.
- Foydalanuvchi boshqa birovning raqami/SMSini ko‘ra olmaydi.
- To‘lovdan keyin real SMS keladi; expiry va refunddan keyin inbox yopiladi.
- Bankka settlement va provayder komissiyasi tekshirilgan; 18% ustamaning haqiqiy sof natijasi hisoblangan.
- Stripe, PayPal va allpay’ning native live pilotlari alohida tasdiqlanadi. Mock testlar bank yoki provayder tasdig‘ining o‘rnini bosmaydi.

## 10. Yakuniy tekshiruv va joylash qaydi

2026-09-22: lokal va serverning 547 ta version-controlled/yangi source fayli SHA-256 bilan solishtirildi va moslashtirildi. Serverdagi `.env`, amaldagi deployment override, baza va media saqlandi. Zaxira: `/root/deploy-backups/payments-sync-20260922`; eski image teglarida `before-payments-20260922` mavjud. Source bir xil; Git tarixining checkout refi va serverga xos maxfiy/runtime fayllar bu taqqoslashga kirmaydi.

`virtual_numbers.0002` migratsiyasi qo‘llandi. Backend, frontend, Celery worker/render/beat healthy; database/cache health tekshiruvi o‘tdi. HTTPS orqali `/`, `/login`, `/pricing`, `/virtual-numbers`, `/admin/virtual-numbers`, `/api/v1/plans` — 200; autentifikatsiyasiz xususiy katalog va admin payment API — 401. Tozalash timeri active, server NTP synchronized.

Yakuniy toza PostgreSQL bazasida **430 backend testi**, frontendda **10 test**, TypeScript va production build o‘tdi. Avvalgi kodning alohida toza bazadagi 400 testi ham o‘tib, regressiya solishtirildi. Dastlabki reuse-db tekshiruvi seed ma’lumotlari qolmagan test bazasi sabab xato bergan; toza bazada takrorlash bilan sabab ajratildi.

Serverda `sales_ready=false`; Stripe/Visa va PayPal credentials kutilmoqda, allpay shartnoma/API spetsifikatsiyasi kutilmoqda. Haqiqiy merchant/sandbox/live tashqi pilot bajarilmadi; karta yoki bankdan pul yechilmadi. Kompaniya/bank yurisdiksiyasi javobi va soliq bazasi tasdig‘i hali kerak.
