"""en/ru/uz subject+body templates for every FR-74 event (NFR-35).

Keep them plain-text and `str.format`-safe. Placeholders come from the `ctx`
passed to `notifications.services.notify`. Missing placeholders render as "-"
instead of raising, so a template typo never blocks a business action.

Add a new type here first, then call `notify(user, "<type>", ctx=...)`.
"""
from __future__ import annotations

APP = "AI YouTube Content Ecosystem"

# FR-76: transactional/security notifications cannot be disabled by the user.
MANDATORY_TYPES = {
    "auth.email_verification",
    "auth.password_reset",
    "auth.password_changed",
    "auth.2fa_enabled",
    "channel.connected",
    "channel.disconnected",
    "contract.new_version",
    "contract.signed",
    "billing.payment_failed",
    "billing.payment_succeeded",
    "billing.generation_paused",
    "revenue.statement_ready",
    "revenue.invoice_issued",
    "data.export_ready",
    "data.deletion_requested",
    "admin.alert",
}

_T: dict[str, dict[str, tuple[str, str]]] = {
    "channel.connected": {
        "en": ("YouTube channel connected", "Your channel \"{channel_title}\" is now connected to {app}. Scheduled generation can start once your contract and plan are active."),
        "ru": ("YouTube-канал подключён", "Ваш канал \"{channel_title}\" подключён к {app}. Генерация по расписанию начнётся после активации договора и тарифа."),
        "uz": ("YouTube kanal ulandi", "\"{channel_title}\" kanalingiz {app} ga ulandi. Shartnoma va tarif faol bo'lgach jadval bo'yicha generatsiya boshlanadi."),
    },
    "channel.disconnected": {
        "en": ("YouTube channel disconnected", "Your channel \"{channel_title}\" was disconnected ({reason}). Scheduled videos are paused until you reconnect."),
        "ru": ("YouTube-канал отключён", "Ваш канал \"{channel_title}\" отключён ({reason}). Запланированные видео приостановлены до повторного подключения."),
        "uz": ("YouTube kanal uzildi", "\"{channel_title}\" kanalingiz uzildi ({reason}). Qayta ulanguningizcha rejalashtirilgan videolar pauza qilindi."),
    },
    "video.awaiting_approval": {
        "en": ("Your video is ready for review", "\"{title}\" is ready. Please review and approve it within 48 hours: {url}"),
        "ru": ("Видео готово к проверке", "\"{title}\" готово. Проверьте и подтвердите публикацию в течение 48 часов: {url}"),
        "uz": ("Video tasdiqlashga tayyor", "\"{title}\" tayyor. 48 soat ichida ko'rib chiqib tasdiqlang: {url}"),
    },
    "video.published": {
        "en": ("Your video is live on YouTube", "\"{title}\" was published: {youtube_url}"),
        "ru": ("Видео опубликовано на YouTube", "\"{title}\" опубликовано: {youtube_url}"),
        "uz": ("Video YouTube'da chiqdi", "\"{title}\" nashr qilindi: {youtube_url}"),
    },
    "video.failed": {
        "en": ("Video generation failed", "\"{title}\" could not be produced ({error_code}). Your quota for this video was restored; you can retry from the dashboard."),
        "ru": ("Ошибка генерации видео", "\"{title}\" не удалось создать ({error_code}). Квота за это видео возвращена; вы можете повторить попытку из панели."),
        "uz": ("Video generatsiyasi xato berdi", "\"{title}\" yaratib bo'lmadi ({error_code}). Bu video uchun kvota qaytarildi; dashboard'dan qayta urinib ko'ring."),
    },
    "video.moderation_rejected": {
        "en": ("Video rejected by moderation", "\"{title}\" was rejected by our moderation team: {reason}"),
        "ru": ("Видео отклонено модерацией", "\"{title}\" отклонено командой модерации: {reason}"),
        "uz": ("Video moderatsiyadan o'tmadi", "\"{title}\" moderatsiya jamoasi tomonidan rad etildi: {reason}"),
    },
    "video.youtube_rejected": {
        "en": ("YouTube rejected your video", "YouTube rejected \"{title}\" ({reason}). No further action is taken automatically."),
        "ru": ("YouTube отклонил видео", "YouTube отклонил \"{title}\" ({reason}). Автоматических действий не предпринимается."),
        "uz": ("YouTube videoni rad etdi", "YouTube \"{title}\" ni rad etdi ({reason}). Avtomatik ravishda boshqa harakat qilinmaydi."),
    },
    "video.auto_published_on_timeout": {
        "en": ("Your video was published automatically", "\"{title}\" was not reviewed within 48 hours, so it was published automatically as your preferences allow."),
        "ru": ("Видео опубликовано автоматически", "\"{title}\" не было проверено за 48 часов и было опубликовано автоматически согласно вашим настройкам."),
        "uz": ("Video avtomatik nashr qilindi", "\"{title}\" 48 soat ichida ko'rib chiqilmadi, shuning uchun sozlamalaringizga ko'ra avtomatik nashr qilindi."),
    },
    "video.expired": {
        "en": ("Approval window expired", "\"{title}\" was not approved within 48 hours and was not published. You can restart it from the dashboard."),
        "ru": ("Срок подтверждения истёк", "\"{title}\" не было подтверждено за 48 часов и не опубликовано. Вы можете перезапустить его из панели."),
        "uz": ("Tasdiqlash muddati tugadi", "\"{title}\" 48 soat ichida tasdiqlanmadi va nashr qilinmadi. Dashboard'dan qayta ishga tushirishingiz mumkin."),
    },
    "contract.new_version": {
        "en": ("Please review the updated agreement", "A new version ({version}) of the creator agreement takes effect on {effective_from}. Sign it to keep generation running."),
        "ru": ("Обновлённое соглашение", "Новая версия ({version}) соглашения вступает в силу {effective_from}. Подпишите её, чтобы генерация продолжалась."),
        "uz": ("Yangilangan shartnomani ko'rib chiqing", "Shartnomaning yangi versiyasi ({version}) {effective_from} dan kuchga kiradi. Generatsiya davom etishi uchun imzolang."),
    },
    "contract.signed": {
        "en": ("Agreement signed", "You signed agreement version {version} on {signed_at}. A PDF copy is available in your dashboard."),
        "ru": ("Соглашение подписано", "Вы подписали версию {version} {signed_at}. PDF-копия доступна в панели."),
        "uz": ("Shartnoma imzolandi", "Siz {version} versiyasini {signed_at} da imzoladingiz. PDF nusxasi dashboard'da mavjud."),
    },
    "billing.payment_succeeded": {
        "en": ("Payment received", "We received your payment of {amount} {currency}. Thank you!"),
        "ru": ("Платёж получен", "Мы получили ваш платёж на сумму {amount} {currency}. Спасибо!"),
        "uz": ("To'lov qabul qilindi", "{amount} {currency} miqdoridagi to'lovingiz qabul qilindi. Rahmat!"),
    },
    "billing.payment_failed": {
        "en": ("Payment failed", "Your payment of {amount} {currency} failed. Please update your payment method within {grace_days} days to avoid a pause."),
        "ru": ("Платёж не прошёл", "Платёж на сумму {amount} {currency} не прошёл. Обновите способ оплаты в течение {grace_days} дней, чтобы избежать приостановки."),
        "uz": ("To'lov amalga oshmadi", "{amount} {currency} miqdoridagi to'lov amalga oshmadi. Pauzaga tushmaslik uchun {grace_days} kun ichida to'lov usulini yangilang."),
    },
    "billing.generation_paused": {
        "en": ("Generation paused", "Video generation was paused because an invoice is overdue. Pay the outstanding balance to resume."),
        "ru": ("Генерация приостановлена", "Генерация видео приостановлена из-за просроченного счёта. Оплатите задолженность, чтобы возобновить."),
        "uz": ("Generatsiya pauza qilindi", "Muddati o'tgan invoys sababli video generatsiyasi pauza qilindi. Davom ettirish uchun qarzni to'lang."),
    },
    "revenue.statement_ready": {
        "en": ("Monthly revenue statement ready", "Your statement for {period} is ready: gross {gross} {currency}, your share {creator_share} {currency}. You have 14 days to dispute."),
        "ru": ("Ежемесячный отчёт готов", "Отчёт за {period} готов: всего {gross} {currency}, ваша доля {creator_share} {currency}. На оспаривание есть 14 дней."),
        "uz": ("Oylik daromad hisoboti tayyor", "{period} uchun hisobot tayyor: jami {gross} {currency}, sizning ulushingiz {creator_share} {currency}. E'tiroz uchun 14 kun bor."),
    },
    "revenue.invoice_issued": {
        "en": ("Service-fee invoice issued", "An invoice of {amount} {currency} for {period} was issued and will be charged to your saved payment method."),
        "ru": ("Выставлен счёт за услуги", "Счёт на {amount} {currency} за {period} выставлен и будет списан с сохранённого способа оплаты."),
        "uz": ("Xizmat haqi invoysi chiqarildi", "{period} uchun {amount} {currency} miqdorida invoys chiqarildi va saqlangan to'lov usulidan undiriladi."),
    },
    "data.export_ready": {
        "en": ("Your data export is ready", "Download your data export (valid for 7 days): {url}"),
        "ru": ("Экспорт данных готов", "Скачайте экспорт данных (действителен 7 дней): {url}"),
        "uz": ("Ma'lumotlar eksporti tayyor", "Ma'lumotlaringiz eksportini yuklab oling (7 kun amal qiladi): {url}"),
    },
    "data.deletion_requested": {
        "en": ("Account deletion requested", "We received your deletion request. Connected accounts were disconnected immediately; personal data will be anonymised within 30 days. Cancel from your dashboard if this was a mistake."),
        "ru": ("Запрос на удаление аккаунта", "Мы получили запрос на удаление. Подключённые аккаунты отключены; персональные данные будут анонимизированы в течение 30 дней. Отмените в панели, если это ошибка."),
        "uz": ("Akkauntni o'chirish so'rovi", "O'chirish so'rovingiz qabul qilindi. Ulangan akkauntlar darhol uzildi; shaxsiy ma'lumotlar 30 kun ichida anonimlashtiriladi. Xato bo'lsa dashboard'dan bekor qiling."),
    },
    "auth.2fa_enabled": {
        "en": ("Two-factor authentication enabled", "TOTP two-factor authentication is now active on your account."),
        "ru": ("Двухфакторная аутентификация включена", "TOTP двухфакторная аутентификация активирована для вашего аккаунта."),
        "uz": ("Ikki bosqichli autentifikatsiya yoqildi", "Akkauntingizda TOTP ikki bosqichli autentifikatsiya faollashtirildi."),
    },
    "admin.alert": {
        "en": ("[Admin alert] {subject}", "{message}"),
        "ru": ("[Admin alert] {subject}", "{message}"),
        "uz": ("[Admin alert] {subject}", "{message}"),
    },
    "generic": {
        "en": ("{subject}", "{message}"),
        "ru": ("{subject}", "{message}"),
        "uz": ("{subject}", "{message}"),
    },
}


class _SafeDict(dict):
    def __missing__(self, key):
        return "-"


def render(type_: str, locale: str, ctx: dict) -> tuple[str, str]:
    """Return (subject, body) for `type_` in `locale` (falls back to en, then generic)."""
    templates = _T.get(type_) or _T["generic"]
    subject, body = templates.get(locale) or templates["en"]
    data = _SafeDict(app=APP, **ctx)
    return subject.format_map(data), body.format_map(data)


def known_types() -> list[str]:
    return sorted(k for k in _T if k != "generic")
