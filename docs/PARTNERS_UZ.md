# Hamkorlar va referral reklama banneri

Admin manzili: `/admin/partners`. `/admin/config` ichida ham shu bo‘limga havola bor. Boshqarish uchun admin roli va amaldagi ikki bosqichli himoya talab qilinadi. Login/signup fonidagi avvalgi logotiplar alohida saqlanadi.

1. Tashkilot nomi, HTTPS logotip manzili va HTTPS sayt/referral havolasini kiriting.
2. Ixtiyoriy qisqa tavsif va tartib raqamini belgilang. Referral dasturidan komissiya olinadigan havolada tegishli belgini yoqing.
3. Faol holatda saqlang. Bosh sahifani yangilaganda bannerda ko‘rinadi.
4. Banner sarlavhasi, tavsifi, ko‘rinishi, animatsiya vaqti (15–120 soniya) va harakatini alohida boshqaring.
5. Mavjud hamkorni tahrirlash, yashirish yoki tasdiqlab o‘chirish mumkin.

Banner bosh sahifada hero qismidan keyin chiqadi. Faol hamkorlar yo‘q yoki banner o‘chirilgan bo‘lsa, bo‘sh joy/reklama namunasi ko‘rsatilmaydi. Hech qanday tashkilot avtomatik hamkor deb belgilanmaydi. Logotip yuklanmasa tashkilot nomi saqlanadi. Yangi tabdagi havolalar `sponsored noopener noreferrer` bilan ochiladi. Referral URL parametrlari saqlanadi, havola qayta yo‘naltirish servisi orqali o‘tkazilmaydi. Komissiya to‘lovi hamkor dasturida hisoblanadi; bu modul komissiyani hisoblamaydi yoki pul tushishini kafolatlamaydi.

Logotiplar ekranga sig‘masa animatsiya ishlaydi; sig‘adigan qisqa ro‘yxat statik, markazlangan holda chiqadi. Sichqoncha yoki klaviatura fokusi banner ustida bo‘lsa, harakat to‘xtaydi. Alohida to‘xtatish tugmasi va `prefers-reduced-motion` qo‘llanadi. Referral havolalari borligi tashrifchiga ochiq ko‘rsatiladi. Banner matni admin kiritgan tilda ko‘rsatiladi.

API:
- `GET /api/v1/public/partners` — faol ro‘yxat va banner sozlamalari, autentifikatsiyasiz; cache `no-store`.
- `GET/POST /api/v1/admin/partners` — admin ro‘yxati va yaratish.
- `GET/PATCH/DELETE /api/v1/admin/partners/<id>` — tahrirlash/o‘chirish.
- `GET/PATCH /api/v1/admin/partners/banner` — banner sozlamalari.

`adminpanel.0002_partner_partnerbanner` yangi jadvallarni qo‘shadi. O‘zgarishlar audit jurnaliga yoziladi. Ochiq HTTP, credential saqlovchi URL va lokal/private IP manzillari rad etiladi. Logotiplar HTTPS manzili orqali kiritiladi; fayl yuklash bu modulga kiritilmagan.

Frontend banner `public/mw/partners.js` custom element orqali standalone va React landinglarda bir xil ishlaydi. Standalone bundle faqat `<creator-partners>` joylashuvini o‘z ichiga oladi. Foydalanuvchi matni HTML sifatida talqin qilinmaydi. Tashqi reklama skriptlari yoki tashrifchilarni kuzatish kodi qo‘shilmagan.

Banner bosh sahifadagi “Integratsiyalar va texnologiyalar” bo‘limida, texnologiyalar qatoridan oldin ko‘rsatiladi.
