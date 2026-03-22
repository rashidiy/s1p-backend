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
        details.append(_esc(f"{estimated_value:,.0f} {currency}"))

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
