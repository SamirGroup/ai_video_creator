# Creator AI yordamchi va boshqaruv paneli

## Ishlaydigan oqim

- Birinchi kirishda creator `/assistant` sahifasiga yo‘naltiriladi. Profil saqlangach odatiy dashboard ochiladi.
- Profil maqsad, auditoriya hududi, suhbat tili va IANA vaqt zonasini saqlaydi. Nashr jadvali alohida `/preferences` orqali boshqariladi.
- Suhbat faqat shu foydalanuvchining kanallari, sozlamalari, rejalari, video holatlari va oxirgi 30 kunlik mavjud analitikasi bilan ishlaydi. Analitika manba va valyuta bo‘yicha ajratiladi.
- Haftalik reja mavjud content-plan API orqali yaratiladi. Model tanlovi, obuna, shartnoma, balans, kanal ruxsatlari va tasdiqlash tekshiruvlari saqlangan.
- AI suhbat javobi maslahatdir; javob matni hech qanday nashr yoki to‘lov amalini bajarmaydi. Mutatsiyalar mavjud forma va tasdiqlangan reja oqimi orqali ishlaydi.
- Generatsiya va nashr avvalgi Celery pipeline va moderatsiya tekshiruvlaridan foydalanadi.

## Admin

`/admin-dashboard`: real mijoz/kanal/topshiriq sonlari, 30 kunlik AI sarfi, provayder holati, kontent bosqichlari va yordamchi xatolari. Sozlamalar: yoqish/o‘chirish, har bir foydalanuvchi uchun so‘nggi 24 soatdagi xabar limiti, xizmat ko‘rsatish ko‘rsatmalari. O‘zgarish auditga yoziladi. Admin roli va mavjud 2FA siyosati majburiy.

## API

- `GET /api/v1/me/assistant`: profil, tenant konteksti va oxirgi 30 suhbat.
- `PATCH /api/v1/me/assistant`: o‘z profilini saqlash.
- `POST /api/v1/me/assistant`: `message` va UUID `request_key`; 202 qaytadi, Celery `q_script` javobni tayyorlaydi. Takroriy request_key ikkinchi pullik so‘rov yubormaydi.
- `GET/PATCH /api/v1/admin/assistant`: admin monitoring va siyosat.

## Xarajat va cheklovlar

So‘rovdan oldin taxminiy maksimal token xarajati mavjud AI wallet tizimida band qilinadi. Haqiqiy provayder sarfi API usage jurnaliga yozilib, wallet orqali hisoblanadi; band qilingan qoldiq bo‘shatiladi. Avvalgi 70% AI / 30% platforma siyosati ishlatiladi. AI budjeti yoqilmagan tariflarda mavjud wallet siyosatiga muvofiq xarajat platformaga tushadi; kunlik limit qo‘llanadi.

Bir foydalanuvchidan bir vaqtning o‘zida bitta suhbat ishlaydi. Xato javobda maxfiy provayder xabarlari ko‘rsatilmaydi. 180 soniya task chegarasi; 10 daqiqadan oshgan pending/running holati keyingi status o‘qishda failed deb belgilanadi. Bunday noaniq natija avtomatik qayta pullik yuborilmaydi.

## Haqiqiy faollashtirish uchun zarur

Tekshiruv paytida serverda AI provayder kalitlari yo‘q edi. Shuning uchun pullik AI ishlashi hali tasdiqlanmagan; UI bu holatni ochiq ko‘rsatadi.

1. Admin konfiguratsiyasida faol birlamchi LLM va narxlarini tekshiring. Claude uchun bevosita Anthropic API qo‘llanadi: `/admin/config` → Claude · Anthropic Direct → saqlash → API sinovi → asosiy AI sifatida yoqish. [To‘liq yo‘riqnoma](ANTHROPIC_DIRECT_UZ.md). OpenRouter ham alohida provayder sifatida saqlangan.
2. Moderatsiya provayderi kaliti, ovoz provayderi kaliti va tanlangan video provayderi kaliti/balansi kerak. Higgsfield katalogi uchun `python manage.py seed_higgsfield` faqat o‘chirilgan modellarni qo‘shadi. Aksiya narxlarini faollashtirishdan oldin qayta tekshiring.
3. Higgsfield API parametrlari va har bir model imkoniyatini haqiqiy testda tekshiring; kalit borligi xizmat ishlashining dalili emas.
4. Google OAuth, kanal ruxsatlari, YouTube quota va Analytics ulanishini tekshiring.
5. Sinov creator bilan profil → suhbat → reja → foydalanuvchi tasdig‘i → generatsiya → moderatsiya → test kanalda nashr → analitika tekshirilsin.

API kalitlari Git, frontend bundle yoki chatga yozilmasin. Migration `content_planning.0004` profil, siyosat va suhbat jadvallarini qo‘shadi; mavjud reja/video jadvallarini o‘zgartirmaydi.
