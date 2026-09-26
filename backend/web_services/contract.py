"""Website-service contracts: one template per customer type.

* `resident` — an individual resident of the Republic of Uzbekistan (Uzbek).
* `non_resident` — an individual who is a foreign citizen (English).

`build()` returns a structured document (sections of numbered clauses plus
requisites tables). It is frozen into the order at acceptance and hashed, so
what the customer accepted can always be shown again word for word. The page
layer only lays it out; it never supplies contract wording.

The wording is a commercial template, not legal advice: it must be reviewed by
a lawyer before live sales, in particular the currency clauses for residents.
"""

import hashlib
import json
from decimal import Decimal

CONTRACT_VERSION = "2026-09-26"
CONTRACT_TYPES = ("resident", "non_resident")

PACKAGES = {
    "starter": {
        "uz": {
            "name": "Start — landing sahifa",
            "features": [
                "Bir sahifali landing sayt (6 tagacha kontent bloki)",
                "Individual dizayn: brendingiz asosida 1 ta konsepsiya",
                "Telefon, planshet va kompyuterga moslashuvchan (adaptiv) sahifa",
                "Ariza shakli, arizalarni Telegram va e-mailga yuborish",
                "Asosiy SEO sozlamalari: meta-teglar, sitemap.xml, robots.txt",
                "Domen, hosting va SSL sertifikatini ulashda yordam",
            ],
        },
        "en": {
            "name": "Start — landing page",
            "features": [
                "One-page landing site with up to 6 content sections",
                "Custom design: one concept based on your brand",
                "Responsive layout for phones, tablets and desktops",
                "Contact form with delivery to Telegram and e-mail",
                "Basic SEO: meta tags, sitemap.xml, robots.txt",
                "Help connecting the domain, hosting and SSL certificate",
            ],
        },
    },
    "business": {
        "uz": {
            "name": "Business — korporativ sayt",
            "features": [
                "Korporativ sayt: asosiy va ichki sahifalar",
                "Asosiy va ichki sahifalar uchun individual dizayn",
                "Kontentni boshqarish paneli (admin panel)",
                "Yangiliklar yoki blog bo‘limi",
                "Google Analytics va Yandex Metrica ulash",
                "Har bir sahifa uchun asosiy SEO sozlamalari",
                "Aloqa shakllari va xarita",
            ],
        },
        "en": {
            "name": "Business — corporate website",
            "features": [
                "Corporate website with home and inner pages",
                "Custom design for the home and inner pages",
                "Content management (admin) panel",
                "News or blog section",
                "Google Analytics and Yandex Metrica connection",
                "Basic SEO for every page",
                "Contact forms and a map",
            ],
        },
    },
    "pro": {
        "uz": {
            "name": "Pro — internet-do‘kon",
            "features": [
                "Internet-do‘kon: kategoriya va filtrlarga ega katalog",
                "Savat, buyurtma rasmiylashtirish va 1 ta onlayn to‘lov tizimi",
                "Mahsulotlar, buyurtmalar va mijozlarni boshqarish paneli",
                "Tezlikni optimallashtirish (Core Web Vitals)",
                "Buyurtmalar haqida Telegram va e-mail xabarnomalari",
                "Kengaytirilgan SEO va analitika",
            ],
        },
        "en": {
            "name": "Pro — online store",
            "features": [
                "Online store: catalogue with categories and filters",
                "Cart, checkout and one online payment gateway",
                "Admin panel for products, orders and customers",
                "Speed optimisation (Core Web Vitals)",
                "Order notifications to Telegram and e-mail",
                "Extended SEO and analytics",
            ],
        },
    },
    "enterprise": {
        "uz": {
            "name": "Enterprise — veb-platforma",
            "features": [
                "Texnik topshiriq asosida individual veb-platforma",
                "Foydalanuvchi kabinetlari, rollar va kirish huquqlari",
                "Tashqi tizimlar bilan 3 tagacha integratsiya (CRM, 1C, to‘lovlar, Telegram-bot)",
                "Xavfsizlikni kuchaytirish va yuklama testi",
                "Texnik hujjatlar va jamoangizni o‘qitish",
                "Ustuvor texnik qo‘llab-quvvatlash",
            ],
        },
        "en": {
            "name": "Enterprise — web platform",
            "features": [
                "Custom web platform built from a technical specification",
                "User accounts, roles and access rights",
                "Up to 3 integrations with external systems (CRM, 1C, payments, Telegram bot)",
                "Security hardening and load testing",
                "Technical documentation and training for your team",
                "Priority technical support",
            ],
        },
    },
}


# --- Amounts in words -----------------------------------------------------------

_EN_ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
_EN_TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()
_UZ_ONES = ["nol", "bir", "ikki", "uch", "to‘rt", "besh", "olti", "yetti", "sakkiz", "to‘qqiz"]
_UZ_TENS = ["", "o‘n", "yigirma", "o‘ttiz", "qirq", "ellik", "oltmish", "yetmish", "sakson", "to‘qson"]


def _en_below_thousand(n):
    words = []
    if n >= 100:
        words += [_EN_ONES[n // 100], "hundred"]
        n %= 100
    if n >= 20:
        words.append(_EN_TENS[n // 10] + (f"-{_EN_ONES[n % 10]}" if n % 10 else ""))
    elif n:
        words.append(_EN_ONES[n])
    return words


def _uz_below_thousand(n):
    words = []
    if n >= 100:
        words += [_UZ_ONES[n // 100], "yuz"]
        n %= 100
    if n >= 10:
        words.append(_UZ_TENS[n // 10])
        n %= 10
    if n:
        words.append(_UZ_ONES[n])
    return words


def integer_words(n, language):
    if n == 0:
        return "zero" if language == "en" else "nol"
    below = _en_below_thousand if language == "en" else _uz_below_thousand
    scales = ["", "thousand", "million"] if language == "en" else ["", "ming", "million"]
    words, scale = [], 0
    while n:
        n, chunk = divmod(n, 1000)
        if chunk:
            words = below(chunk) + ([scales[scale]] if scales[scale] else []) + words
        scale += 1
    return " ".join(words)


def amount_words(amount, language):
    amount = Decimal(amount).quantize(Decimal("0.01"))
    dollars, cents = int(amount), int(amount * 100) % 100
    if language == "en":
        return f"{integer_words(dollars, 'en')} US dollars {cents:02d} cents"
    return f"{integer_words(dollars, 'uz')} AQSh dollari {cents:02d} sent"


# --- Document -------------------------------------------------------------------


def _dash(value):
    return value if value not in (None, "") else "—"


def delivery(package, language):
    """1–2 soat / 1 kun / 2 kun; English: 1–2 hours / 1 day / 2 days."""
    low, high = package.get("delivery_hours_min"), package["delivery_hours"]
    if high % 24 == 0 and not low:
        days = high // 24
        if language == "uz":
            return f"{days} kun"
        return f"{days} day" if days == 1 else f"{days} days"
    span = f"{low}–{high}" if low else str(high)
    if language == "uz":
        return f"{span} soat"
    return f"{span} hour" if span == "1" else f"{span} hours"


def _limit(value, language):
    if value:
        return str(value)
    return "texnik topshiriq bo‘yicha" if language == "uz" else "as per the specification"


def _executor_rows(executor, language):
    labels = (
        [
            ("Nomi", executor["legal_name"]),
            ("Manzil", executor["address"]),
            ("STIR", executor["tin"]),
            ("Bank", executor["bank_name"]),
            ("Hisob raqami", executor["bank_account"]),
            ("Bank kodi (MFO)", executor["bank_code"]),
            ("SWIFT", executor["swift"]),
            ("Telefon", executor["phone"]),
            ("E-mail", executor["email"]),
        ]
        if language == "uz"
        else [
            ("Name", executor["legal_name"]),
            ("Address", executor["address"]),
            ("Taxpayer ID (TIN)", executor["tin"]),
            ("Bank", executor["bank_name"]),
            ("Account", executor["bank_account"]),
            ("Bank code", executor["bank_code"]),
            ("SWIFT", executor["swift"]),
            ("Phone", executor["phone"]),
            ("E-mail", executor["email"]),
        ]
    )
    return [[label, _dash(value)] for label, value in labels]


def _date(iso):
    year, month, day = iso.split("-")
    return f"{day}.{month}.{year}"


def _customer_rows(kind, customer):
    passport = (
        f"{customer['passport_number']}, {customer['passport_issued_by']}, "
        f"{_date(customer['passport_issued_at'])}"
    )
    if kind == "resident":
        return [
            ["F.I.Sh.", customer["full_name"]],
            ["Tug‘ilgan sana", _date(customer["date_of_birth"])],
            ["Pasport", passport],
            ["JShShIR", customer["pinfl"]],
            ["Manzil", f"{customer['address']}, {customer['city']}"],
            ["Telefon", customer["phone"]],
            ["E-mail", customer["email"]],
        ]
    return [
        ["Full name", customer["full_name"]],
        ["Date of birth", _date(customer["date_of_birth"])],
        ["Citizenship", customer["citizenship"]],
        ["Passport", passport],
        ["Tax ID", _dash(customer.get("tax_id"))],
        ["Address", f"{customer['address']}, {customer['city']}, {customer['country']}"],
        ["Phone", customer["phone"]],
        ["E-mail", customer["email"]],
    ]


def _resident(ctx):
    e, c, p = ctx["executor"], ctx["customer"], ctx["package"]
    text = PACKAGES[p["code"]]["uz"]
    price = f"{ctx['price']} AQSh dollari ({amount_words(ctx['price'], 'uz')})"
    return {
        "title": "VEB-SAYT ISHLAB CHIQISH XIZMATLARINI KO‘RSATISH SHARTNOMASI",
        "city": e["city"] or "Toshkent shahri",
        "preamble": (
            f"{e['legal_name']} (keyingi o‘rinlarda — «Ijrochi») nomidan {e['acting_basis']} asosida "
            f"ish yurituvchi {e['director_name']} bir tomondan, va O‘zbekiston Respublikasi rezidenti "
            f"bo‘lgan jismoniy shaxs {c['full_name']} (pasport {c['passport_number']}, JShShIR {c['pinfl']}) "
            "(keyingi o‘rinlarda — «Buyurtmachi») ikkinchi tomondan, birgalikda «Tomonlar» deb ataluvchilar, "
            "quyidagilar haqida ushbu Shartnomani tuzdilar:"
        ),
        "sections": [
            {
                "title": "SHARTNOMA PREDMETI",
                "clauses": [
                    f"Ijrochi Buyurtmachining topshirig‘iga binoan «{text['name']}» paketi doirasida sun’iy "
                    "intellekt texnologiyalaridan foydalangan holda veb-sayt ishlab chiqish xizmatlarini "
                    "ko‘rsatish, Buyurtmachi esa ushbu xizmatlarni qabul qilish va ularning haqini to‘lash "
                    "majburiyatini oladi.",
                    f"Loyiha nomi: «{ctx['project']['name']}». Loyiha tavsifi ushbu Shartnomaning 1-ilovasida "
                    "(Texnik topshiriq) keltirilgan va uning ajralmas qismi hisoblanadi.",
                    {"text": "Paket tarkibi:", "items": text["features"]},
                    {
                        "text": "Xizmatlar hajmi:",
                        "items": [
                            f"sahifalar (shablonlar) soni — {_limit(p['page_limit'], 'uz')};",
                            f"sayt tillari soni — {p['languages']};",
                            f"tuzatish bosqichlari — {p['revision_rounds']};",
                            f"bajarish muddati — {delivery(p, 'uz')};",
                            f"bepul texnik qo‘llab-quvvatlash — {p['support_months']} oy.",
                        ],
                    },
                    "Paket tarkibiga kirmagan ishlar (matn yozish, fotosuratga olish, pullik plagin va "
                    "shriftlar, domen va hosting uchun to‘lovlar) Tomonlar tomonidan alohida kelishiladi.",
                ],
            },
            {
                "title": "XIZMATLAR NARXI VA TO‘LOV TARTIBI",
                "clauses": [
                    f"Xizmatlarning umumiy narxi: {price}. {e['vat_note']}".strip(),
                    "To‘lov 100% oldindan, Ijrochining platformasida Payoneer to‘lov tizimi orqali bank "
                    "kartasi bilan amalga oshiriladi.",
                    "To‘lov O‘zbekiston Respublikasining valyuta qonunchiligi talablariga muvofiq amalga "
                    "oshiriladi. Bank va to‘lov tizimi komissiyalarini har bir Tomon o‘z tariflari bo‘yicha "
                    "mustaqil to‘laydi.",
                    "Pul mablag‘lari Payoneer tomonidan muvaffaqiyatli qabul qilingan kun to‘lov kuni hisoblanadi.",
                ],
            },
            {
                "title": "BAJARISH MUDDATLARI",
                "clauses": [
                    f"Xizmatlarni ko‘rsatish muddati — {delivery(p, 'uz')}. Muddat to‘lov qabul "
                    "qilingan va Buyurtmachi ishni boshlash uchun zarur materiallarni (matnlar, logotip, "
                    "rasmlar, kirish ma’lumotlari) taqdim etgan kundan boshlab hisoblanadi.",
                    "Buyurtmachi materiallar yoki fikr-mulohazalarni kechiktirgan muddatga bajarish muddati "
                    "mutanosib ravishda uzaytiriladi.",
                ],
            },
            {
                "title": "TOMONLARNING HUQUQ VA MAJBURIYATLARI",
                "clauses": [
                    "Ijrochi xizmatlarni sifatli va belgilangan muddatda ko‘rsatish, Buyurtmachini ish "
                    "bosqichlari haqida xabardor qilish, tayyor saytni topshirish va uni boshqarish bo‘yicha "
                    "yo‘riqnoma berish majburiyatini oladi.",
                    "Buyurtmachi zarur materiallarni o‘z vaqtida taqdim etish, oraliq natijalarni 5 (besh) ish "
                    "kuni ichida ko‘rib chiqish va taqdim etgan materiallarga tegishli huquqlarga ega ekanini "
                    "kafolatlash majburiyatini oladi.",
                    "Ijrochi xizmatlarni ko‘rsatishga uchinchi shaxslarni jalb qilishi mumkin; ularning "
                    "harakatlari uchun Buyurtmachi oldida Ijrochi javob beradi.",
                ],
            },
            {
                "title": "TOPSHIRISH-QABUL QILISH TARTIBI",
                "clauses": [
                    "Ijrochi natijani sinov manzilida yoki Buyurtmachining serverida taqdim etadi va bu "
                    "haqda platforma yoki e-mail orqali xabar beradi.",
                    f"Paket doirasida {p['revision_rounds']} bosqich tuzatish kiritiladi. Qo‘shimcha "
                    "tuzatishlar alohida kelishiladi.",
                    "Buyurtmachi natijani 5 (besh) ish kuni ichida qabul qiladi yoki asoslantirilgan "
                    "e’tirozlarini yozma ravishda yuboradi. Shu muddatda e’tiroz bildirilmasa, xizmatlar "
                    "to‘liq hajmda qabul qilingan hisoblanadi.",
                    "Topshirish-qabul qilish dalolatnomasi elektron shaklda rasmiylashtirilishi mumkin.",
                ],
            },
            {
                "title": "INTELLEKTUAL MULK",
                "clauses": [
                    "To‘liq to‘lovdan so‘ng saytning yakuniy dizayni va Ijrochi tomonidan maxsus yozilgan "
                    "dastur kodiga bo‘lgan mutlaq mulkiy huquqlar Buyurtmachiga o‘tadi.",
                    "Ochiq kodli kutubxonalar, freymvorklar va uchinchi shaxslar komponentlaridan ularning "
                    "litsenziyalari shartlarida foydalaniladi.",
                    "Buyurtmachi yozma ravishda qarshi bo‘lmasa, Ijrochi bajarilgan ishni o‘z portfoliosida "
                    "ko‘rsatishi mumkin.",
                ],
            },
            {
                "title": "KAFOLAT VA TEXNIK QO‘LLAB-QUVVATLASH",
                "clauses": [
                    f"Topshirilgan kundan boshlab {p['support_months']} oy davomida Ijrochi o‘zi yo‘l qo‘ygan "
                    "xatolarni bepul tuzatadi.",
                    "Kafolat Buyurtmachi yoki uchinchi shaxslar kodga kiritgan o‘zgartirishlar, hosting "
                    "nosozliklari va uchinchi shaxslar xizmatlarining ishlamay qolishiga taalluqli emas.",
                ],
            },
            {
                "title": "MAXFIYLIK VA SHAXSGA DOIR MA’LUMOTLAR",
                "clauses": [
                    "Tomonlar bir-biridan olingan tijorat va texnik ma’lumotlarni oshkor qilmaslik "
                    "majburiyatini oladi.",
                    "Buyurtmachining shaxsga doir ma’lumotlari O‘zbekiston Respublikasining «Shaxsga doir "
                    "ma’lumotlar to‘g‘risida»gi Qonuniga muvofiq faqat ushbu Shartnomani bajarish maqsadida "
                    "qayta ishlanadi.",
                ],
            },
            {
                "title": "TOMONLARNING JAVOBGARLIGI",
                "clauses": [
                    "Majburiyatlar bajarilmaganligi yoki lozim darajada bajarilmaganligi uchun Tomonlar "
                    "O‘zbekiston Respublikasi qonunchiligiga muvofiq javobgar bo‘ladi.",
                    "Muddat Ijrochining aybi bilan buzilganda Buyurtmachi har bir kechiktirilgan kun uchun "
                    "narxning 0,1 foizi miqdorida, biroq narxning 10 foizidan oshmagan penya talab qilishga haqli.",
                    "Ijrochining umumiy javobgarligi Buyurtmachi to‘lagan summa bilan cheklanadi.",
                ],
            },
            {
                "title": "FORS-MAJOR",
                "clauses": [
                    "Tomonlar yengib bo‘lmaydigan kuch holatlari (tabiiy ofatlar, urush, davlat organlarining "
                    "qarorlari, ommaviy aloqa uzilishlari) natijasida majburiyatlarni bajarmaganlik uchun "
                    "javobgar bo‘lmaydi. Bunday holat haqida ikkinchi Tomon 5 (besh) kun ichida xabardor qilinadi.",
                ],
            },
            {
                "title": "SHARTNOMANI BEKOR QILISH VA PULNI QAYTARISH",
                "clauses": [
                    "Ish boshlanishidan oldin Buyurtmachi Shartnomadan voz kechsa, to‘langan summa to‘liq "
                    "qaytariladi (to‘lov tizimi komissiyalari bundan mustasno).",
                    "Ish boshlangandan keyin voz kechilsa, Ijrochi haqiqatda bajarilgan ishlar qiymatini "
                    "ushlab qolib, qolgan summani qaytaradi.",
                    "Pul mablag‘lari to‘lov qilingan usul orqali 14 (o‘n to‘rt) ish kuni ichida qaytariladi.",
                ],
            },
            {
                "title": "NIZOLARNI HAL QILISH",
                "clauses": [
                    "Nizolar muzokaralar yo‘li bilan hal qilinadi. Talabnoma olingan kundan boshlab 30 kun "
                    "ichida kelishuvga erishilmasa, nizo O‘zbekiston Respublikasi qonunchiligiga muvofiq "
                    "Ijrochi joylashgan yerdagi sudda ko‘rib chiqiladi.",
                ],
            },
            {
                "title": "YAKUNIY QOIDALAR",
                "clauses": [
                    "Shartnoma Buyurtmachi platformada uning shartlarini qabul qilgan (aksept) paytda tuzilgan "
                    "hisoblanadi, to‘lov amalga oshirilgan kundan kuchga kiradi va majburiyatlar to‘liq "
                    "bajarilgunga qadar amal qiladi.",
                    "Shartnoma elektron shaklda tuzilgan. Aksept sanasi va vaqti, IP-manzil hamda hujjatning "
                    "nazorat summasi Ijrochi tizimida saqlanadi; Tomonlar bu bilan yozma shaklga rioya "
                    "qilinganini tan oladilar.",
                    "Shartnoma o‘zbek tilida tuzilgan. 1-ilova — Texnik topshiriq — uning ajralmas qismidir.",
                ],
            },
        ],
        "annex_title": "1-ILOVA. TEXNIK TOPSHIRIQ",
        "annex_rows": [
            ["Paket", text["name"]],
            ["Loyiha nomi", ctx["project"]["name"]],
            ["Mavjud sayt", _dash(ctx["project"].get("reference_url"))],
        ],
        "annex_label": "Loyiha tavsifi",
        "labels": {
            "requisites": "TOMONLARNING REKVIZITLARI VA IMZOLARI",
            "executor": "IJROCHI",
            "customer": "BUYURTMACHI",
            "signature": "Imzo",
            "stamp": "M.O‘.",
            "number": "№",
            "acceptance": "Elektron aksept",
            "accepted_at": "Aksept sanasi",
            "ip": "IP-manzil",
            "hash": "Hujjat nazorat summasi (SHA-256)",
            "draft": "LOYIHA — hali qabul qilinmagan",
            "price": "Shartnoma narxi",
            "package": "Paket",
        },
        "package_name": text["name"],
    }


def _non_resident(ctx):
    e, c, p = ctx["executor"], ctx["customer"], ctx["package"]
    text = PACKAGES[p["code"]]["en"]
    price = f"USD {ctx['price']} ({amount_words(ctx['price'], 'en')})"
    return {
        "title": "WEBSITE DEVELOPMENT SERVICES AGREEMENT",
        "city": e["city_en"] or "Tashkent, Republic of Uzbekistan",
        "preamble": (
            f"{e['legal_name']}, represented by {e['director_name']} acting on the basis of "
            f"{e['acting_basis_en']} (the «Contractor»), on the one part, and {c['full_name']}, a citizen of "
            f"{c['citizenship']}, an individual who is not a resident of the Republic of Uzbekistan "
            f"(passport {c['passport_number']}) (the «Customer»), on the other part, together the «Parties», "
            "have concluded this Agreement as follows:"
        ),
        "sections": [
            {
                "title": "SUBJECT OF THE AGREEMENT",
                "clauses": [
                    f"The Contractor undertakes to provide website development services under the "
                    f"«{text['name']}» package on the Customer's instructions, using artificial intelligence "
                    "technologies, and the Customer undertakes to accept and pay for these services.",
                    f"Project name: «{ctx['project']['name']}». The project description is set out in "
                    "Annex 1 (Specification), which forms an integral part of this Agreement.",
                    {"text": "The package includes:", "items": text["features"]},
                    {
                        "text": "Scope of services:",
                        "items": [
                            f"number of pages (templates) — {_limit(p['page_limit'], 'en')};",
                            f"website languages — {p['languages']};",
                            f"revision rounds — {p['revision_rounds']};",
                            f"delivery time — {delivery(p, 'en')};",
                            f"free technical support — {p['support_months']} month(s).",
                        ],
                    },
                    "Work outside the package (copywriting, photography, paid plugins and fonts, domain "
                    "and hosting fees) is agreed separately.",
                ],
            },
            {
                "title": "PRICE AND PAYMENT",
                "clauses": [
                    f"The total price of the services is {price}.",
                    "Payment is made 100% in advance in US dollars by bank card through the Payoneer "
                    "payment system on the Contractor's platform.",
                    "Each Party bears its own bank and payment-system fees. The Customer is responsible for "
                    "any taxes, duties and currency-control requirements that apply in the Customer's own "
                    "country; the Contractor pays its taxes under the laws of the Republic of Uzbekistan.",
                    "The payment date is the date on which Payoneer successfully receives the funds.",
                ],
            },
            {
                "title": "TIMING",
                "clauses": [
                    f"The services are delivered within {delivery(p, 'en')}, counted from the "
                    "later of receipt of payment and receipt of the materials needed to start (texts, logo, "
                    "images, access credentials).",
                    "Any delay by the Customer in providing materials or feedback extends the delivery time "
                    "accordingly.",
                ],
            },
            {
                "title": "RIGHTS AND OBLIGATIONS OF THE PARTIES",
                "clauses": [
                    "The Contractor shall deliver the services with due quality and on time, keep the "
                    "Customer informed of progress, hand over the finished website and provide instructions "
                    "for managing it.",
                    "The Customer shall provide the required materials on time, review interim results "
                    "within 5 (five) business days and warrants that it holds the rights to all materials "
                    "it provides.",
                    "The Contractor may engage subcontractors and remains responsible to the Customer for "
                    "their work.",
                ],
            },
            {
                "title": "DELIVERY AND ACCEPTANCE",
                "clauses": [
                    "The Contractor presents the result on a staging address or on the Customer's server and "
                    "notifies the Customer through the platform or by e-mail.",
                    f"The package includes {p['revision_rounds']} revision round(s). Further revisions are "
                    "agreed separately.",
                    "The Customer accepts the result or sends reasoned objections in writing within 5 (five) "
                    "business days. If no objections are received in that time, the services are deemed "
                    "accepted in full.",
                    "The acceptance certificate may be executed electronically.",
                ],
            },
            {
                "title": "INTELLECTUAL PROPERTY",
                "clauses": [
                    "Upon full payment, the exclusive property rights to the final design and to the code "
                    "written specifically by the Contractor pass to the Customer.",
                    "Open-source libraries, frameworks and third-party components are used under their own "
                    "licences.",
                    "Unless the Customer objects in writing, the Contractor may show the work in its portfolio.",
                ],
            },
            {
                "title": "WARRANTY AND SUPPORT",
                "clauses": [
                    f"For {p['support_months']} month(s) after delivery, the Contractor fixes its own defects "
                    "free of charge.",
                    "The warranty does not cover changes made to the code by the Customer or third parties, "
                    "hosting failures, or outages of third-party services.",
                ],
            },
            {
                "title": "CONFIDENTIALITY AND PERSONAL DATA",
                "clauses": [
                    "Each Party shall keep confidential the commercial and technical information received "
                    "from the other.",
                    "The Customer consents to the processing of its personal data, including its transfer to "
                    "and storage in the Republic of Uzbekistan, solely for performing this Agreement and in "
                    "accordance with the Law of the Republic of Uzbekistan «On Personal Data».",
                ],
            },
            {
                "title": "LIABILITY",
                "clauses": [
                    "The Parties are liable for non-performance or improper performance of their obligations "
                    "under the governing law.",
                    "If the deadline is missed through the Contractor's fault, the Customer may claim a "
                    "penalty of 0.1% of the price per day of delay, capped at 10% of the price.",
                    "The Contractor's total liability is limited to the amount paid by the Customer.",
                ],
            },
            {
                "title": "FORCE MAJEURE",
                "clauses": [
                    "Neither Party is liable for failure to perform caused by force majeure (natural "
                    "disasters, war, acts of public authorities, large-scale communication outages). The "
                    "affected Party shall notify the other within 5 (five) days.",
                ],
            },
            {
                "title": "TERMINATION AND REFUNDS",
                "clauses": [
                    "If the Customer withdraws before work starts, the amount paid is refunded in full, less "
                    "payment-system fees.",
                    "If the Customer withdraws after work has started, the Contractor retains the value of "
                    "the work actually performed and refunds the balance.",
                    "Refunds are made to the original payment method within 14 (fourteen) business days.",
                ],
            },
            {
                "title": "GOVERNING LAW AND DISPUTES",
                "clauses": [
                    "This Agreement is governed by the laws of the Republic of Uzbekistan.",
                    "Disputes are settled by negotiation. If no settlement is reached within 30 days of a "
                    "written claim, the dispute is referred to the competent court at the Contractor's "
                    "location in the Republic of Uzbekistan.",
                ],
            },
            {
                "title": "FINAL PROVISIONS",
                "clauses": [
                    "The Agreement is concluded when the Customer accepts its terms on the platform, enters "
                    "into force on the date of payment and remains in force until the obligations are fully "
                    "performed.",
                    "The Agreement is concluded electronically. The date and time of acceptance, the IP "
                    "address and the document checksum are stored in the Contractor's system, and the "
                    "Parties recognise this as satisfying the written form.",
                    "The Agreement is made in English. Annex 1 (Specification) forms an integral part of it.",
                ],
            },
        ],
        "annex_title": "ANNEX 1. SPECIFICATION",
        "annex_rows": [
            ["Package", text["name"]],
            ["Project name", ctx["project"]["name"]],
            ["Existing website", _dash(ctx["project"].get("reference_url"))],
        ],
        "annex_label": "Project description",
        "labels": {
            "requisites": "ADDRESSES AND SIGNATURES OF THE PARTIES",
            "executor": "CONTRACTOR",
            "customer": "CUSTOMER",
            "signature": "Signature",
            "stamp": "Seal",
            "number": "No.",
            "acceptance": "Electronic acceptance",
            "accepted_at": "Accepted at",
            "ip": "IP address",
            "hash": "Document checksum (SHA-256)",
            "draft": "DRAFT — not yet accepted",
            "price": "Contract price",
            "package": "Package",
        },
        "package_name": text["name"],
    }


def build(*, kind, executor, customer, package, price, project, number="", date=""):
    """Assemble the document. `package` is a dict of the package's terms."""
    if kind not in CONTRACT_TYPES:
        raise ValueError("Unknown contract type.")
    ctx = {
        "executor": executor,
        "customer": customer,
        "package": package,
        "price": str(Decimal(price).quantize(Decimal("0.01"))),
        "project": project,
    }
    body = _resident(ctx) if kind == "resident" else _non_resident(ctx)
    return {
        "version": CONTRACT_VERSION,
        "type": kind,
        "language": "uz" if kind == "resident" else "en",
        "number": number,
        "date": date,
        "price": ctx["price"],
        "currency": "USD",
        "annex_description": project["description"],
        "executor_rows": _executor_rows(executor, "uz" if kind == "resident" else "en"),
        "customer": customer,
        "customer_rows": _customer_rows(kind, customer),
        "executor_signatory": executor["director_name"],
        "customer_signatory": customer["full_name"],
        **body,
    }


def checksum(document):
    canonical = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()
