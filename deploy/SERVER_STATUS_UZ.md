# arbitechglobal.com — 2026-09-17

Asosiy loyiha: /root/ai_video/ai_video_creator. Host Nginx saytni 127.0.0.1:13080 frontend va 127.0.0.1:18080 API orqali uzatadi. /internal/ ham APIga yo‘naltiriladi. Avvalgi /youtube-os/ yo‘li saqlangan. Boshqa xizmatlar o‘chirilmagan.

Ishlatiladigan Compose fayllari: docker-compose.yml, docker-compose.prod.yml, deploy/arbitech-live.yml. Uchinchi fayl persistent media, production settings, worker va frontend health-checklarni belgilaydi. Yangilashda uchalasi ham ishlatilishi shart; deploy.sh bunga moslangan.

Zaxira: /root/deploy-backups/arbitech-20260917 (cheklangan ruxsat). Oldingi Nginx konfiguratsiyasi, Git diff, muhit va database dump mavjud. Serverdagi oldindan mavjud frontend o‘zgarishlari saqlandi va yangi frontend image yig‘ildi. Ular GitHubga bu deploy davomida yuborilmadi.

4 GiB /swapfile-arbitech qo‘shildi, /etc/fstab orqali qayta yuklashda ulanadi. Worker concurrency=1; bu 2 GiB serverda video yuklamasi uchun quvvat kafolati emas.

Tekshiruv: host-resolver bilan aynan 104.207.75.103 ga HTTPS ulanib /, /login, /register 200; mobil brauzerda runtime xatosi yoki gorizontal overflow yo‘q. /api/health/ database/cache true. Migratsiyalar to‘liq qo‘llangan. Amaldagi sertifikat 2026-11-10 gacha.

DNS tekshiruvda arbitechglobal.com hali 162.213.255.22 edi. Namecheap A @ 104.207.75.103 va www CNAME arbitechglobal.com ga moslanishi kerak. DNSdan keyin odatiy HTTPS va certbot renewal dry-run qayta tekshiriladi.

Google OAuth, Stripe, Runway/ovoz/LLM/moderatsiya va Telegram kalitlari konteynerda yo‘q. EMAIL_BACKEND console — tasdiqlash xatlari foydalanuvchiga yuborilmaydi. Real SMTP hamda tashqi hisoblar sozlanmaguncha mijozlarni to‘liq onboard qilish, to‘lov, video yaratish yoki avtomatik nashr tayyor deb hisoblanmaydi. Mavjud superadmin hisobining paroli o‘zgartirilmadi. Maxfiy qiymatlar chat yoki Gitga yozilmaydi.
