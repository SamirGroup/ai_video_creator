# Ekotizimning aniqlashtirilgan mahsulot talablari

Sana: 2026-09-17. Manba: foydalanuvchining mahsulot tavsifi va alohida javobi: **30% faqat ekotizim yaratgan videolar daromadidan olinadi**. Bu hujjat talabni belgilaydi; undagi barcha funksiyalar hali implementatsiya qilingan deb hisoblanmaydi.

## Asosiy maqsad

Creator Google orqali yoki email/parol bilan ro‘yxatdan o‘tadi, mavjud YouTube kanalini OAuth orqali ulaydi. Tarifni tanlab, profilida AI vositalaridan foydalanadi. Ekotizim kanal va mavzuni tahlil qilib, reja tavsiya qiladi; creator tanlagan reja asosida original videolar yaratadi, mustaqil moderatsiyadan o‘tkazadi va ruxsat berilgan versiyani belgilangan vaqtda nashr qiladi.

Kontent va interfeys: 30 til/lokal variant. Asosiy til ruscha. Auditoriya tili/mamlakati foydalanuvchining moliyaviy rezidentligi va shaxsiy tasdiqlash ma’lumotlaridan alohida maydonlar.

## Foydalanuvchi oqimi

1. Email/parol yoki Google sign-in; profil ochish. Google login va kanalga nashr qilish OAuth roziligi alohida.
2. YouTube kanalini ulash. Kanal mavjud bo‘lmasa, Google/YouTube rasmiy yaratish oqimiga yo‘naltirish; foydalanuvchi paroli va SMS kodlarini platforma yig‘maydi.
3. Tarif tanlash: ruxsat etilgan AI modellari, video/Shorts soni, davomiyligi, tillar, parallel ishlar, qayta ishlash va xarajat limitlari oldindan ko‘rsatiladi. Obuna to‘lovi daromad ulushidan alohida.
4. Kontent menyusi: tematika, auditoriya, kontent tili, video/Shorts formati, creatorning o‘z uslubi, fakt manbalari, cheklangan mavzular va huquqi bor aktivlar.
5. YouTube tahlili: OAuth ruxsatidagi o‘z kanal statistikasi va API orqali olinadigan ochiq mavzu ma’lumotlari. Ko‘rilgan manba/video IDlari, tahlil sanasi, ma’lumot davri va cheklovlar saqlanadi. Boshqa creator videosi ko‘chirib qayta nashr qilinmaydi.
6. AI kunlik, haftalik, oylik reja variantlarini beradi. Har band: g‘oya, asos, sarlavha varianti, format, davomiylik, til, rejalashtirilgan sana/soat, vaqt mintaqasi, tavsiya ishonchliligi va taxminiy ishlab chiqarish xarajati. Ma’lumot yetishmasa tavsiya taxmin ekanligi ko‘rsatiladi; “eng yaxshi vaqt” kafolatlanmaydi.
7. Creator reja/bandlarni tanlaydi, tahrirlaydi, aniq versiyani tasdiqlaydi. Tasdiqlanmagan reja ishlab chiqarish yoki nashrga sabab bo‘lmaydi.
8. AI ssenariy, ovoz, ruxsatli vizuallar/musiqa, subtitr, thumbnail, sarlavha va tavsif yaratadi. Sifat, faktlar va original qiymat ustuvor.
9. Ekotizim moderatsiyasi ssenariy va tayyor videoni ko‘radi. Creator AI o‘z videosiga yakuniy ruxsat bera olmaydi.
10. Qaytarilgan videoga tuzatish topshirig‘i: qoida kodi, sabab, sahna/vaqt oralig‘i, matn bo‘lagi, qayta ishlanadigan bosqich va tavsiya etilgan aniq tuzatish. AI mos bosqichdan yangi versiya ishlab chiqib qayta topshiradi.
11. Moderatsiya tasdig‘i aynan video versiyasi va aktivlar hashiga bog‘lanadi. Tasdiqdan keyingi mazmun o‘zgarishi yangi moderatsiyani talab qiladi.
12. Ruxsat berilgan versiya YouTube Data API orqali yuklanadi, metadata/thumbnail/subtitr biriktiriladi, imkoniyatlarga mos holda nashr sanasi belgilanadi. Creator Studio UI tugmalarini bot bilan bosish ishlatilmaydi.
13. “Videolarim” va “Shortslarim”: holat, preview, reja va nashr vaqti, ko‘rishlar, layklar, so‘nggi statistik yangilanish, daromad manbasi va ishlab chiqarish xarajati. Ma’lumot mavjud bo‘lmasa 0 kabi uydirma raqam bilan almashtirilmaydi.
14. Oylik daromad hisoboti, 30/70 hisob-kitob, rozilikka asoslangan xizmat haqi va to‘lov tarixi.

## Moderatsiya va avtomatik qayta ishlash

Taklif etilgan holatlar:

`planned → plan_approved → generating → moderation_pending → changes_required → regenerating → moderation_pending → approved → upload_queued → scheduled_on_youtube → published`

Qo‘shimcha holatlar: `manual_review`, `budget_paused`, `canceled`, `failed`, `policy_blocked`.

- Creator kontent bo‘yicha “mijoz AI” va ekotizimning mustaqil reviewer qismi alohida vakolatga ega.
- Reviewer xavfsizlik, mualliflik huquqlari/litsenziya dalillari, fakt manbalari, originallik, takroriy shablonlar, sarlavha-thumbnailning mazmunga mosligi, subtitr va AI disclosure zaruratini tekshiradi.
- Ichki tekshiruv YouTube qabul qilishi yoki monetizatsiya berishini kafolatlamaydi. Monetizatsiya qarori YouTube’ga tegishli va kanal darajasidagi omillarga ham bog‘liq.
- Tuzatishlar sababga yo‘naltiriladi: mazmun o‘zgarmasdan filtrdan tasodifan o‘tishga qayta-qayta urinish emas. Jiddiy taqiqlangan talab yoki noaniq huquqlar `manual_review/policy_blocked`ga yuboriladi.
- “Ruxsat bo‘lmaguncha davom etish” nashr taqiqi bilan amalga oshiriladi. Xarajat/urinish limitiga yetganda ish pauzaga tushadi; avtomatik ruxsat yoki cheksiz pullik generatsiya bo‘lmaydi. Boshlang‘ich taklif: bir ishga 3 avtomatik tuzatish, tarif va tasdiqlangan byudjetga mos konfiguratsiya.
- Retry, qayta generatsiya va tarmoq qayta urinishi alohida sanaladi. Har yangi versiya, reviewer xulosasi va xarajat auditga yoziladi. Parallel workerlar bitta versiyani takror yuklay olmaydi.
- Tasdiq belgilangan vaqtdan kechiksa, video yashirincha darhol nashr qilinmaydi; oldindan ruxsat berilgan keyingi slot yoki creatorning qayta tanlovi ishlatiladi.

## AI va YouTube siyosati

AI vositasi ishlatilishi o‘z-o‘zidan umumiy monetizatsiya taqiqi emas. Takroriy, shablon asosida ommaviy tayyorlangan va original qiymati yo‘q kontent monetizatsiyaga mos kelmasligi mumkin. [YouTube monetizatsiya qoidalari](https://support.google.com/youtube/answer/1311392?hl=en).

Tabiiy nutq, original ssenariy, yaxshi montaj, mazmunga mos sarlavha va subtitrlar sifat uchun yaratiladi. AI kelib chiqishini yashirish, provenance ma’lumotlarini ataylab yo‘qotish yoki odam yaratgan degan yolg‘on da’vo berish maqsad qilinmaydi. YouTube talab qilgan AI belgilash saqlanadi; rasmiy hujjatga ko‘ra bu belgilashning o‘zi daromad olishga yaroqlilikni bekor qilmaydi. [GenAI disclosure](https://support.google.com/youtube/answer/14328491?hl=en).

Joriy koddagi `containsSyntheticMedia` belgilashi yashirish maqsadida o‘chirilmaydi.

## Akkaunt, shaxsni tasdiqlash va to‘lov usuli

- YouTube reklama daromadi uchun **AdSense for YouTube** kerak; Google Ads reklama xarid qilish xizmati bilan aralashtirilmaydi.
- Yangi AdSense for YouTube hisobini foydalanuvchi YouTube Studio ichidagi rasmiy oqimda yaratadi. Platforma uni kerakli bosqichga yo‘naltiradi va qaytgan holatni ko‘rsatadi. Takroriy hisob avtomatik yaratilmaydi. [Rasmiy AdSense ulash tartibi](https://support.google.com/youtube/answer/9914702?hl=en).
- Davlat/shaxsni noto‘g‘ri ko‘rsatish yoki verifikatsiyani chetlab o‘tish uchun virtual raqam sotish va SMS qabul qilish moduli kiritilmaydi. Mijoz o‘zi boshqaradigan telefon raqami va haqiqiy ma’lumotlari bilan rasmiy tasdiqlashdan o‘tadi. [YouTube telefon tasdiqlashi](https://support.google.com/youtube/answer/171664?hl=en).
- Bizga xizmat haqini to‘lash uchun creatorning alohida Stripe merchant hisobi bo‘lishi shart emas: Stripe orqali karta/bank to‘lov usuli ulanishi mumkin. Kelajakdagi yechish uchun tegishli rozilik va SetupIntent/mandate oqimi saqlanadi. [Stripe SetupIntents](https://docs.stripe.com/api/setup_intents).
- Platformadan creatorga payout yo‘nalishi keyinchalik talab qilinsa, qo‘llanadigan hududlarda Stripe Connect rasmiy onboarding ishlatiladi. Bu AdSense balansini avtomatik Stripe balansiga aylantirmaydi. [Stripe onboarding](https://docs.stripe.com/connect/hosted-onboarding).

## 30/70 hisob-kitob

**Tasdiqlangan qamrov: faqat platforma ishlab chiqargan, tegishli creator kanaliga biriktirilgan videolar. Mustaqil videolar, butun kanal yoki umumiy AdSense hisobidagi boshqa daromad qo‘shilmaydi.**

- Google o‘z to‘lov tartibida creator’ga to‘laydi. Platforma o‘ziga tegishli 30%ni alohida xizmat haqi sifatida hisoblaydi va saqlangan to‘lov usulidan rozilik doirasida undiradi.
- Hisob bazasi YouTube ulushi allaqachon ajratilgandan keyin creator uchun hisobotda ko‘rsatilgan tegishli video daromadi; reklama beruvchi sarflagan yalpi summa emas.
- Masalan, hisobga olinadigan video daromadi $100 bo‘lsa, xizmat haqi $30, creator ulushi $70. Obuna, soliq, valyuta farqi va protsessing xarajatlari alohida ko‘rsatiladi; $70ni barcha xarajatlardan keyingi kafolatlangan sof foyda deb yozib bo‘lmaydi.
- Estimated, qayta ko‘rib chiqilgan va haqiqiy to‘langan daromad farqlanadi. 72 soat o‘tganini Google yakuniy to‘lovni tasdiqladi deb talqin qilish mumkin emas.
- Joriy kod video bo‘yicha Analytics ma’lumotini ishlatadi; AdSense account daromadini videoga asossiz taqsimlamaslik kerak. Hisoblash bazasi va reconciliation tugatilmasdan production avtomatik undirish yoqilmaydi.
- Foizlar shartnoma versiyasidan olinadi. Eski imzolangan matn va foizlar saqlanadi. Yangi 30/70 kelishuvi va undirish roziligi alohida qayd etiladi; oldingi davrlar orqaga qarab yangi foiz bilan qayta hisoblanmaydi.
- Hisobot tasdiqlash/dispute muddati, correction, refund, SCA talab qilingan to‘lov va dunning holatlari bor. Webhook/event/invoice idempotency takror yechishga yo‘l qo‘ymaydi.

## Ma’lumotlar va API bo‘yicha keyingi implementatsiya

Yangi obyektlar: `channel_analysis_runs`, `content_plan_proposals`, `content_plan_items`, `plan_approvals`, `video_revisions`, `moderation_findings`, `regeneration_attempts`, `publication_attempts`.

Taklif etilgan API:

- `POST /channels/{id}/analysis`, `GET /analyses/{id}`.
- `POST /channels/{id}/content-plans/propose`, `GET /content-plans/{id}`.
- `PATCH /content-plans/{id}/items/{item_id}`, `POST /content-plans/{id}/approve`.
- `GET /videos/{id}/revisions`, `GET /videos/{id}/moderation-findings`.
- `POST /videos/{id}/regeneration/resume`, `POST /videos/{id}/cancel`.
- Video/Shorts filtrli `GET /videos`, statistikani yangilash holati bilan.

Mavjud APIlar bilan yakuniy nomlar implementatsiya vaqtida moslashtiriladi; yuqoridagi yangi endpointlar hali ishlaydi deb hisoblanmaydi.

## Ushbu aniqlashtirishda kodga kiritilgan o‘zgarishlar

- Yangi ContractVersion defaultlari 30/70, yangi statement default ulushi 30. Faqat field default migratsiyalari: tarixiy satrlar o‘zgarmaydi, eski 1.0 faol shartnoma avtomatik almashtirilmaydi.
- Umumiy `split_revenue` foizlar yig‘indisini va qiymatlarning to‘g‘riligini tekshiradi. Eski `split_50_50` import nomi moslik uchun saqlangan.
- Contract ekranini real current/history/sign/PDF APIlariga ulash, foizlarni serverdan ko‘rsatish va imzolashdagi xatolarni ko‘rsatish.
- Boshqa funksiyalar yuqorida talab va bajariladigan ish sifatida qayd etilgan. Real hisob, virtual telefon xaridi, video nashri yoki pul yechish bu o‘zgarishlarda bajarilmadi.


## Keyingi aniqlashtirish: yaratilgan VA ekotizim orqali joylangan videolar

Platforma ulushi 30%, creator ulushi 70%: ikkala shart ham bajarilishi kerak — video ekotizim ichida yaratilgan va ekotizim orqali YouTube kanaliga joylangan. Faqat yaratilgan/eksport qilingan video yoki kanalning qolgan daromadi yangi kelishuv bo‘yicha hisobga kirmaydi. 1.1 shartnoma migratsiyasi yangi matn va ushbu qamrovni faollashtiradi; oldingi imzolangan versiyalar saqlanadi.

Kirish sahifasi uchun `myweb.uz` vizual namunasi, dashboardlar uchun foydalanuvchi yuborgan ko‘k/binafsha dizayn va light/dark rejimlari belgilandi. Bajarilgan dizayn va cheklovlar `IMPLEMENTATION_STATUS_UZ.md`da qayd etilgan.
