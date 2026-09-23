# Mahalliy Qwen / Ollama integratsiyasi

## Qaysi yo‘l kerak?

**Anthropic API bilan mijozlarga xizmat ko‘rsatish uchun GPU server sotib olish shart emas.** Model provayder serverida ishlaydi; kompaniya API hisobidagi xarajat token bo‘yicha hisoblanadi. Claude Pro/Max obunasi API billing o‘rnini bosmaydi.

O‘z modelimizni yuritish muqobil variant. Qwen3 4B Instruct (Q4_K_M, taxminan 2.5 GB model) lokal sinov uchun tanlandi. Apache 2.0 model litsenziyasi: https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507 . Ollama paketi: https://ollama.com/library/qwen3:4b-instruct . Bu matn modeli; video, ovoz, moderatsiya va YouTube OAuth integratsiyalari alohida qoladi.

## Mac lokal ishga tushirish

```sh
brew install ollama
OLLAMA_HOST=127.0.0.1:11434 OLLAMA_NO_CLOUD=1 OLLAMA_NUM_PARALLEL=1 ollama serve
```

Boshqa terminalda:

```sh
ollama pull qwen3:4b-instruct
```

`backend/.env` ichida `OLLAMA_BASE_URL=http://127.0.0.1:11434` qo‘ying. API gateway autentifikatsiyasi kerak bo‘lsa `OLLAMA_API_KEY` faqat backend muhitiga kiritiladi. Ollama standart lokal xizmatiga kalit kerak emas. Docker ichidagi backend uchun `localhost` konteynerning o‘zi: Mac hostga ulanishda `host.docker.internal` yoki bir xil xususiy Docker tarmog‘idagi xizmat nomidan foydalaning. Hostni internetga ochmang.

```sh
backend/.venv/bin/python backend/manage.py migrate
backend/.venv/bin/python backend/manage.py seed_local_llm
```

Haqiqiy matn va JSON sinovi (mijoz bazasi yoki asosiy provayderni o‘zgartirmaydi):

```sh
backend/.venv/bin/python backend/manage.py check_local_llm
```

`/admin/config` → **Ochiq model · Qwen / Ollama** → **Modelni tekshirish** → **Asosiy AI sifatida yoqish**. Tekshiruv haqiqiy JSON generatsiyasini bajaradi; natija bir soat amal qiladi. Model/endpoint o‘zgarsa yangidan tekshirish kerak. Seed komandasi mavjud primary provayderni o‘zgartirmaydi. Faqat 2FA yoqilgan superadmin yoqa oladi.

Suhbat, kontent reja va ssenariy mavjud yagona LLM factory orqali ishlaydi. Kontekst mijoz bo‘yicha alohida shakllanadi. Modelga alohida foydalanuvchi matnidan endpoint yoki kalit berilmaydi. Xususiy endpoint faqat operator environment orqali sozlanadi. JSON javoblar mavjud domen validatorlaridan o‘tadi. Moderatsiya va mijoz tasdig‘i chetlab o‘tilmaydi.

Xarajat jurnalida tokenlar va tashqi API xarajati `$0` qayd qilinadi. **Bu xizmatning umumiy tannarxi nol degani emas**: server/GPU, elektr, saqlash va xizmat ko‘rsatish xarajatlari alohida. 70/30 tarif siyosati va foydalanish limitlari saqlanadi; self-hosting tannarxi uchun alohida moliyaviy hisob kerak.

## Keyinchalik alohida AI server uchun rejalashtirish

2026-09-22 tekshiruvida mavjud sayt serveri: 2 vCPU, 2 GB RAM, GPU yo‘q, mavjud xizmatlardan tashqari taxminan 724 MB xotira. Unda production LLM o‘rnatilmadi.

Quyidagilar boshlang‘ich muhandislik tavsiyasi, kafolatlangan mijoz sig‘imi emas:

- Lokal funksional sinov: Apple Silicon 8 GB, Qwen3 4B Q4; bitta generatsiya. Boshqa ilovalar bilan xotira raqobatini tekshirish zarur.
- Alohida kichik pilot: NVIDIA 16–24 GB VRAM, kamida 32 GB tizim RAM, 8 vCPU, 100 GB NVMe; dastlab 1–2 parallel generatsiya. 8B/14B kvantlangan model va kontekst hajmiga qarab o‘lchanadi.
- Mijozlar ko‘payganda: navbat, rate limit, timeout, p95 javob vaqti va haqiqiy promptlar bilan yuklama testi asosida GPU soni/VRAM tanlanadi. "Nechta ro‘yxatdan o‘tgan mijoz" emas, bir vaqtdagi so‘rovlar muhim.

Ollama faqat xususiy tarmoq/loopbackda ishlasin. Boshqa serverdan kirish VPN yoki autentifikatsiyali TLS gateway orqali; 11434 portini ommaga ochmang. HTTP endpoint xususiy operator boshqaruviga mo‘ljallangan. Gateway kaliti log va frontendga chiqarilmasin.

Lokal servisni to‘xtatish: `ollama stop qwen3:4b-instruct`, keyin `ollama serve` terminalida Ctrl+C. Doimiy servis kerak bo‘lsa alohida ishga tushirish siyosatini belgilang.

Kontekst chegarasidan oshgan so‘rov yoki kesilgan javob qabul qilinmaydi. Uzoq suhbatlar va katta kontent rejalari kuchliroq model/server yoki kattaroq tekshirilgan kontekst talab qilishi mumkin. Lokal 4B model javoblari sifat jihatidan Claude darajasiga teng deb hisoblanmaydi.

## Ushbu tayyorlash natijasi — 2026-09-22

- Ollama 0.34.2 lokal Mac’ga o‘rnatildi; loopback API ishga tushishi tekshirildi. Avtomatik login servisi yoqilmadi.
- Qwen3 4B Instruct yuklash ikki urinishda CDN ulanishi `connection reset by peer` bilan tugadi. Model hali `ollama list` ro‘yxatida yo‘q; qisman yuklangan fayllar qayta urinish uchun saqlangan. Haqiqiy model javobi/sifati hali tekshirilmagan.
- Lokal Mac 8 GB RAM; tekshiruv vaqtida boshqa ilovalar bilan raqobat sabab Ollama 1.3 GB bo‘sh xotira ko‘rdi. Haqiqiy testdan oldin yetarli xotira bo‘shating; foydalanuvchining boshqa ilovalari yopilmadi.
- 447 backend testi, 10 frontend testi, TypeScript tekshiruvi va yangi fayllar lint tekshiruvlari o‘tdi. Provider transporti va faollashtirish testlari simulyatsiyalangan javoblar bilan bajarilgan.
- Ushbu ochiq model integratsiyasi faqat lokal kodda tayyorlandi. Production’da Qwen yoqilmadi, API provayder tanlovi o‘zgartirilmadi. Alohida so‘ralgan login/registratsiya havola tuzatishi production’ga joylandi va brauzerda tekshirildi.
