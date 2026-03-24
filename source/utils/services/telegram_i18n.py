"""
Telegram V2 i18n — notification message templates in ru/en/uz.

Each function takes data and locale, returns MarkdownV2-escaped text.
All special chars are escaped for Telegram's MarkdownV2 parser.

Design: compact, scannable, emoji-rich. Managers glance at their phone
and need to understand the situation in 1 second.
"""

from utils.services.telegram_constants import (
    STAGE_NAMES, DIRECTION_LABELS, BUTTON_LABELS, get_locale,
)


def _esc(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2."""
    special = r'_*[]()~`>#+-=|{}.!'
    result = []
    for ch in str(text):
        if ch in special:
            result.append('\\')
        result.append(ch)
    return ''.join(result)


def _duration(seconds: int, lang: str) -> str:
    """Format duration as compact string."""
    m, s = divmod(seconds, 60)
    if m:
        return f"{m}:{s:02d}"
    return f"0:{s:02d}"


def _phone_link(phone: str) -> str:
    """Format phone as tappable tel: link in MarkdownV2."""
    import re
    clean = phone.strip()
    # Sanitize for tel: URI — only allow digits, +, -, spaces
    safe_tel = re.sub(r'[^+\d\- ]', '', clean)
    return f"[`{_esc(clean)}`](tel:{safe_tel})"


# ── Call completed ────────────────────────────────────────────────
# Compact format: Contact → Operator, then details on one line

_CALL_COMPLETED_TITLE = {
    "ru": "📞 Звонок",
    "en": "📞 Call",
    "uz": "📞 Qo'ng'iroq",
}

_CALL_COMPLETED_UNKNOWN = {
    "ru": "Неизвестный",
    "en": "Unknown",
    "uz": "Noma'lum",
}


def call_completed_message(
    direction: str,
    caller_display: str,
    phone: str,
    duration_sec: int,
    operator_name: str | None = None,
    contact_name: str | None = None,
    recording_url: str | None = None,
    lang: str = "ru",
) -> str:
    """Build compact MarkdownV2 message for a completed call."""
    locale = get_locale(lang)
    dir_label = DIRECTION_LABELS[locale].get(direction, "")
    dur = _duration(duration_sec, locale)

    # Line 1: Contact → Operator (or just contact if no operator)
    caller = _esc(contact_name or caller_display)
    if operator_name:
        line1 = f"*{_esc(_CALL_COMPLETED_TITLE[locale])}*  {caller}  →  {_esc(operator_name)}"
    else:
        line1 = f"*{_esc(_CALL_COMPLETED_TITLE[locale])}*  {caller}"

    # Line 2: phone · duration · direction
    parts = [_phone_link(phone), _esc(dur)]
    if dir_label:
        parts.append(_esc(dir_label))
    line2 = " · ".join(parts)

    lines = [line1, line2]

    if recording_url:
        btn = BUTTON_LABELS[locale]["listen_recording"]
        lines.append(f"\n[{_esc(btn)}]({recording_url})")
    elif duration_sec > 0:
        # T108: Recording may not be ready yet (Sipuni async delay)
        _rec_processing = {"ru": "⏳ Запись обрабатывается", "en": "⏳ Recording processing", "uz": "⏳ Yozuv qayta ishlanmoqda"}
        lines.append(f"\n_{_esc(_rec_processing[locale])}_")

    return "\n".join(lines)


# ── Missed call ───────────────────────────────────────────────────
# Urgent style: 🚨 prefix, short and action-first

_MISSED_TITLE = {
    "ru": "🚨 Пропущен",
    "en": "🚨 Missed",
    "uz": "🚨 O'tkazib yuborildi",
}


def missed_call_message(
    caller_display: str,
    phone: str,
    contact_name: str | None = None,
    lang: str = "ru",
) -> str:
    """Build compact MarkdownV2 message for a missed call."""
    locale = get_locale(lang)

    line1 = f"*{_esc(_MISSED_TITLE[locale])}*"
    parts = [_phone_link(phone)]
    if contact_name:
        parts.insert(0, _esc(contact_name))

    return f"{line1}  {' · '.join(parts)}"


# ── New lead ──────────────────────────────────────────────────────

_NEW_LEAD_TITLE = {
    "ru": "📝 Новый лид",
    "en": "📝 New Lead",
    "uz": "📝 Yangi lid",
}


def new_lead_message(
    lead_title: str,
    source: str | None = None,
    estimated_value: float | None = None,
    currency: str = "USD",
    contact_name: str | None = None,
    lang: str = "ru",
) -> str:
    """Build compact MarkdownV2 message for a new lead."""
    locale = get_locale(lang)

    line1 = f"*{_esc(_NEW_LEAD_TITLE[locale])}*  {_esc(lead_title)}"

    details = []
    if contact_name:
        details.append(_esc(contact_name))
    if source:
        details.append(_esc(source))
    if estimated_value:
        # T87: Use thousands separator (space for readability); UZS uses no decimals
        formatted = f"{estimated_value:,.0f}".replace(",", " ")
        details.append(_esc(f"{formatted} {currency}"))

    lines = [line1]
    if details:
        lines.append(" · ".join(details))

    return "\n".join(lines)


# ── Deal stage change ────────────────────────────────────────────

_DEAL_TITLE = {
    "ru": "💼 Сделка",
    "en": "💼 Deal",
    "uz": "💼 Bitim",
}


def deal_stage_message(
    deal_title: str,
    old_stage: str,
    new_stage: str,
    amount: float | None = None,
    assigned_to_name: str | None = None,
    lang: str = "ru",
) -> str:
    """Build compact MarkdownV2 message for a deal stage change."""
    locale = get_locale(lang)
    stages = STAGE_NAMES[locale]

    old_name = stages.get(old_stage, old_stage)
    new_name = stages.get(new_stage, new_stage)

    line1 = f"*{_esc(_DEAL_TITLE[locale])}*  {_esc(deal_title)}"
    line2 = f"{_esc(old_name)} → {_esc(new_name)}"

    details = []
    if amount:
        details.append(_esc(f"{amount:,.0f}"))
    if assigned_to_name:
        details.append(_esc(assigned_to_name))

    lines = [line1, line2]
    if details:
        lines.append(" · ".join(details))

    return "\n".join(lines)


# ── Callback responses ───────────────────────────────────────────

_HANDLED = {
    "ru": "✅ {name}",
    "en": "✅ {name}",
    "uz": "✅ {name}",
}

_LEAD_ASSIGNED = {
    "ru": "👤 Лид → {name}",
    "en": "👤 Lead → {name}",
    "uz": "👤 Lid → {name}",
}

_CONTACT_CREATED = {
    "ru": "➕ Контакт: {phone}",
    "en": "➕ Contact: {phone}",
    "uz": "➕ Kontakt: {phone}",
}

_LINK_TELEGRAM = {
    "ru": "Привяжите Telegram в настройках CRM",
    "en": "Link your Telegram in CRM settings",
    "uz": "CRM sozlamalarida Telegram ni ulang",
}


def handled_text(name: str, lang: str = "ru") -> str:
    locale = get_locale(lang)
    return _HANDLED[locale].format(name=name)


def lead_assigned_text(name: str, lang: str = "ru") -> str:
    locale = get_locale(lang)
    return _LEAD_ASSIGNED[locale].format(name=name)


def contact_created_text(phone: str, lang: str = "ru") -> str:
    locale = get_locale(lang)
    return _CONTACT_CREATED[locale].format(phone=phone)


def link_telegram_text(lang: str = "ru") -> str:
    locale = get_locale(lang)
    return _LINK_TELEGRAM[locale]


# ── Daily digest ─────────────────────────────────────────────────

_DIGEST = {
    "ru": {
        "title": "📊 Итоги дня — {date}",
        "calls": "📞 Звонки",
        "missed": "🚨 Пропущено",
        "duration": "⏱ Среднее",
        "leads": "📝 Лиды",
        "won": "🏆 Выиграно",
        "lost": "❌ Проиграно",
    },
    "en": {
        "title": "📊 Daily Summary — {date}",
        "calls": "📞 Calls",
        "missed": "🚨 Missed",
        "duration": "⏱ Avg",
        "leads": "📝 Leads",
        "won": "🏆 Won",
        "lost": "❌ Lost",
    },
    "uz": {
        "title": "📊 Kun yakuni — {date}",
        "calls": "📞 Qo'ng'iroqlar",
        "missed": "🚨 O'tkazilgan",
        "duration": "⏱ O'rtacha",
        "leads": "📝 Lidlar",
        "won": "🏆 Yutilgan",
        "lost": "❌ Yo'qotilgan",
    },
}


def daily_digest_message(
    date: str,
    total_calls: int,
    missed_calls: int,
    avg_duration_sec: int,
    new_leads: int,
    deals_won: int,
    deals_lost: int,
    lang: str = "ru",
) -> str:
    """Build compact MarkdownV2 message for the daily digest."""
    locale = get_locale(lang)
    t = _DIGEST[locale]
    dur = _duration(avg_duration_sec, locale)

    lines = [
        f"*{_esc(t['title'].format(date=date))}*",
        "",
        f"{t['calls']}  `{total_calls}`    {t['missed']}  `{missed_calls}`",
        f"{t['duration']}  `{_esc(dur)}`",
        f"{t['leads']}  `{new_leads}`",
    ]

    if deals_won or deals_lost:
        lines.append(f"{t['won']}  `{deals_won}`    {t['lost']}  `{deals_lost}`")

    return "\n".join(lines)


# ── Smart grouping ───────────────────────────────────────────────

_GROUPED_SUFFIX = {
    "ru": "(x{count})",
    "en": "(x{count})",
    "uz": "(x{count})",
}


# ── Escalation templates ──────────────────────────────────────

_ESCALATION_TIER1 = {
    "ru": "⚠️ Напоминание: пропущен звонок от {phone}, {time_ago} мин назад",
    "en": "⚠️ Reminder: missed call from {phone} {time_ago} min ago",
    "uz": "⚠️ Eslatma: {phone} dan o'tkazib yuborilgan qo'ng'iroq, {time_ago} min oldin",
}

_ESCALATION_TIER2 = {
    "ru": "🔴 Срочно: пропущен звонок от {phone}, без ответа уже {time_ago} мин",
    "en": "🔴 Urgent: missed call from {phone} still unanswered after {time_ago} min",
    "uz": "🔴 Shoshilinch: {phone} dan qo'ng'iroq {time_ago} min javobsiz",
}

_ESCALATION_TIER3 = {
    "ru": "🚨 Критично: пропущен звонок от {phone}, без ответа {time_ago} мин — требуется немедленное внимание",
    "en": "🚨 Critical: missed call from {phone} unanswered for {time_ago} min — needs immediate attention",
    "uz": "🚨 Juda muhim: {phone} dan qo'ng'iroq {time_ago} min javobsiz — zudlik bilan e'tibor kerak",
}

_ESCALATION_OPERATOR = {
    "ru": "Оператор",
    "en": "Operator",
    "uz": "Operator",
}


def escalation_message(
    phone: str,
    operator_name: str | None,
    time_ago: str,
    tier: int,
    lang: str = "ru",
) -> str:
    """Build MarkdownV2 escalation message based on tier."""
    import re
    locale = get_locale(lang)

    templates = {1: _ESCALATION_TIER1, 2: _ESCALATION_TIER2, 3: _ESCALATION_TIER3}
    template = templates.get(tier, _ESCALATION_TIER1)

    clean_phone = phone.strip()
    safe_tel = re.sub(r'[^+\d\- ]', '', clean_phone)
    phone_link = f"[`{_esc(clean_phone)}`](tel:{safe_tel})"

    # Escape the template text (except placeholders) for MarkdownV2
    raw_text = _esc(template[locale].format(phone="\x00PHONE\x00", time_ago=time_ago))
    # Replace escaped placeholder with the phone link
    text = raw_text.replace("\x00PHONE\x00", phone_link)

    lines = [f"*{text}*"]
    if operator_name:
        op_label = _ESCALATION_OPERATOR[locale]
        lines.append(f"{_esc(op_label)}: {_esc(operator_name)}")

    return "\n".join(lines)


def grouped_suffix(count: int, lang: str = "ru") -> str:
    """Return the suffix to append when grouping repeated notifications."""
    locale = get_locale(lang)
    return _GROUPED_SUFFIX[locale].format(count=count)


# ── Bot command responses ────────────────────────────────────────

_NO_DATA = {
    "ru": "Нет данных",
    "en": "No data",
    "uz": "Ma'lumot yo'q",
}

_SEARCH_HEADER = {
    "ru": "🔍 {query}",
    "en": "🔍 {query}",
    "uz": "🔍 {query}",
}

_MY_LEADS_HEADER = {
    "ru": "📝 Мои лиды",
    "en": "📝 My Leads",
    "uz": "📝 Mening lidlarim",
}


def no_data_text(lang: str = "ru") -> str:
    return _NO_DATA[get_locale(lang)]


def search_header(query: str, lang: str = "ru") -> str:
    return _SEARCH_HEADER[get_locale(lang)].format(query=query)


def my_leads_header(lang: str = "ru") -> str:
    return _MY_LEADS_HEADER[get_locale(lang)]


# ── Webhook handler messages (login / register / callback / commands) ──

_LOGIN_LINK_EXPIRED = {
    "ru": "Эта ссылка для входа истекла. Запросите новую на странице входа.",
    "en": "This login link has expired. Please request a new one from the login page.",
    "uz": "Bu kirish havolasi muddati tugagan. Kirish sahifasidan yangi havolani so'rang.",
}

_NO_ACCOUNT_FOUND = {
    "ru": "Аккаунт для этого Telegram не найден в данной компании.",
    "en": "No account found for this Telegram account in this company.",
    "uz": "Bu Telegram akkaunt uchun kompaniyada hisob topilmadi.",
}

_ACCOUNT_SUSPENDED = {
    "ru": "Ваш аккаунт приостановлен. Свяжитесь с администратором.",
    "en": "Your account is suspended. Contact your administrator.",
    "uz": "Sizning hisobingiz to'xtatilgan. Administratoringizga murojaat qiling.",
}

_OTP_RATE_LIMITED = {
    "ru": "Подождите перед запросом нового кода.",
    "en": "Please wait before requesting another code.",
    "uz": "Yangi kod so'rashdan oldin kuting.",
}

_ACCOUNT_LOCKED = {
    "ru": "Аккаунт временно заблокирован. Попробуйте позже.",
    "en": "Account temporarily locked. Try again later.",
    "uz": "Hisob vaqtincha bloklangan. Keyinroq urinib ko'ring.",
}

_REGISTER_LINK_INVALID = {
    "ru": "Эта ссылка недействительна.",
    "en": "This link is invalid.",
    "uz": "Bu havola yaroqsiz.",
}

_REGISTER_LINK_USED = {
    "ru": "Эта ссылка уже использована.",
    "en": "This link has already been used.",
    "uz": "Bu havola allaqachon ishlatilgan.",
}

_REGISTER_LINK_EXPIRED = {
    "ru": "Эта ссылка истекла.",
    "en": "This link has expired.",
    "uz": "Bu havola muddati tugagan.",
}

_ALREADY_REGISTERED = {
    "ru": "Этот Telegram аккаунт уже зарегистрирован в этой компании.",
    "en": "This Telegram account is already registered in this company.",
    "uz": "Bu Telegram akkaunt allaqachon ushbu kompaniyada ro'yxatdan o'tgan.",
}

_TELEGRAM_CONNECTED = {
    "ru": "✅ Telegram подключен\\!\n\nВернитесь на страницу регистрации *{company}*, чтобы завершить регистрацию\\.",
    "en": "✅ Telegram connected\\!\n\nReturn to the *{company}* registration page to complete signup\\.",
    "uz": "✅ Telegram ulandi\\!\n\nRo'yxatdan o'tishni yakunlash uchun *{company}* ro'yxatdan o'tish sahifasiga qayting\\.",
}

_REGISTER_INSTRUCTIONS = {
    "ru": "Для завершения регистрации откройте ссылку и введите код приглашения:\n\n`{url}`\n\nНажмите на ссылку, чтобы скопировать\\.",
    "en": "To complete registration, open this link and enter your invite code:\n\n`{url}`\n\nTap to copy\\.",
    "uz": "Ro'yxatdan o'tishni yakunlash uchun havolani oching va taklif kodini kiriting:\n\n`{url}`\n\nNusxalash uchun bosing\\.",
}

_BOT_NOT_CONFIGURED = {
    "ru": "Бот не настроен для этого чата",
    "en": "Bot not configured for this chat",
    "uz": "Bot bu chat uchun sozlanmagan",
}

_SEARCH_USAGE = {
    "ru": "Использование: /search <телефон или имя>",
    "en": "Usage: /search <phone or name>",
    "uz": "Foydalanish: /search <telefon yoki ism>",
}

_LEAD_NOT_FOUND = {
    "ru": "Лид не найден",
    "en": "Lead not found",
    "uz": "Lid topilmadi",
}

_UNKNOWN_ACTION = {
    "ru": "Неизвестное действие",
    "en": "Unknown action",
    "uz": "Noma'lum amal",
}

_ERROR_PROCESSING = {
    "ru": "Ошибка обработки запроса",
    "en": "Error processing request",
    "uz": "So'rovni qayta ishlashda xato",
}

_INVALID_PHONE = {
    "ru": "Неверный номер телефона",
    "en": "Invalid phone number",
    "uz": "Noto'g'ri telefon raqami",
}

_CONTACT_ALREADY_EXISTS = {
    "ru": "Контакт уже существует",
    "en": "Contact already exists",
    "uz": "Kontakt allaqachon mavjud",
}

_OPEN_IN_CRM = {
    "ru": "📋 Открыть в CRM",
    "en": "📋 Open in CRM",
    "uz": "📋 CRM da ochish",
}

_LEGACY_MARKED_HANDLED = {
    "ru": "Обработано",
    "en": "Marked as handled",
    "uz": "Bajarildi",
}

_LEGACY_USE_CRM = {
    "ru": "Назначьте лид через CRM",
    "en": "Use CRM to assign leads",
    "uz": "Lidlarni CRM orqali tayinlang",
}


def login_link_expired_text(lang: str = "ru") -> str:
    return _LOGIN_LINK_EXPIRED[get_locale(lang)]


def no_account_found_text(lang: str = "ru") -> str:
    return _NO_ACCOUNT_FOUND[get_locale(lang)]


def account_suspended_text(lang: str = "ru") -> str:
    return _ACCOUNT_SUSPENDED[get_locale(lang)]


def otp_rate_limited_text(lang: str = "ru") -> str:
    return _OTP_RATE_LIMITED[get_locale(lang)]


def account_locked_text(lang: str = "ru") -> str:
    return _ACCOUNT_LOCKED[get_locale(lang)]


def register_link_invalid_text(lang: str = "ru") -> str:
    return _REGISTER_LINK_INVALID[get_locale(lang)]


def register_link_used_text(lang: str = "ru") -> str:
    return _REGISTER_LINK_USED[get_locale(lang)]


def register_link_expired_text(lang: str = "ru") -> str:
    return _REGISTER_LINK_EXPIRED[get_locale(lang)]


def already_registered_text(lang: str = "ru") -> str:
    return _ALREADY_REGISTERED[get_locale(lang)]


def telegram_connected_text(company: str, lang: str = "ru") -> str:
    return _TELEGRAM_CONNECTED[get_locale(lang)].format(company=_esc(company))


def register_instructions_text(url: str, lang: str = "ru") -> str:
    return _REGISTER_INSTRUCTIONS[get_locale(lang)].format(url=url)


def bot_not_configured_text(lang: str = "ru") -> str:
    return _BOT_NOT_CONFIGURED[get_locale(lang)]


def search_usage_text(lang: str = "ru") -> str:
    return _SEARCH_USAGE[get_locale(lang)]


def lead_not_found_text(lang: str = "ru") -> str:
    return _LEAD_NOT_FOUND[get_locale(lang)]


def unknown_action_text(lang: str = "ru") -> str:
    return _UNKNOWN_ACTION[get_locale(lang)]


def error_processing_text(lang: str = "ru") -> str:
    return _ERROR_PROCESSING[get_locale(lang)]


def invalid_phone_text(lang: str = "ru") -> str:
    return _INVALID_PHONE[get_locale(lang)]


def contact_already_exists_text(lang: str = "ru") -> str:
    return _CONTACT_ALREADY_EXISTS[get_locale(lang)]


def open_in_crm_text(lang: str = "ru") -> str:
    return _OPEN_IN_CRM[get_locale(lang)]


def legacy_marked_handled_text(lang: str = "ru") -> str:
    return _LEGACY_MARKED_HANDLED[get_locale(lang)]


def legacy_use_crm_text(lang: str = "ru") -> str:
    return _LEGACY_USE_CRM[get_locale(lang)]
