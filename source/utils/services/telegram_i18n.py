"""
Telegram V2 i18n — notification message templates in ru/en/uz.

Each function takes a data dict and locale, returns MarkdownV2-escaped text.
All special chars are escaped for Telegram's MarkdownV2 parser.
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
    """Format duration as human-readable string."""
    m, s = divmod(seconds, 60)
    if lang == "ru":
        return f"{m}мин {s}с" if m else f"{s}с"
    elif lang == "uz":
        return f"{m}daq {s}s" if m else f"{s}s"
    return f"{m}m {s}s" if m else f"{s}s"


# ── Call completed ────────────────────────────────────────────────

_CALL_COMPLETED = {
    "ru": {
        "title": "{direction} звонок завершён",
        "caller": "Звонящий",
        "phone": "Телефон",
        "duration": "Длительность",
        "operator": "Оператор",
        "contact": "Контакт",
        "recording": "Запись",
    },
    "en": {
        "title": "{direction} Call Completed",
        "caller": "Caller",
        "phone": "Phone",
        "duration": "Duration",
        "operator": "Operator",
        "contact": "Contact",
        "recording": "Recording",
    },
    "uz": {
        "title": "{direction} qo'ng'iroq yakunlandi",
        "caller": "Qo'ng'iroqchi",
        "phone": "Telefon",
        "duration": "Davomiylik",
        "operator": "Operator",
        "contact": "Kontakt",
        "recording": "Yozuv",
    },
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
    """Build MarkdownV2 message for a completed call notification."""
    locale = get_locale(lang)
    t = _CALL_COMPLETED[locale]
    dir_label = DIRECTION_LABELS[locale].get(direction, direction)

    lines = [
        f"*{_esc(t['title'].format(direction=dir_label))}*",
        "",
        f"{_esc(t['caller'])}: {_esc(caller_display)}",
        f"{_esc(t['phone'])}: {_esc(phone)}",
        f"{_esc(t['duration'])}: {_esc(_duration(duration_sec, locale))}",
    ]
    if operator_name:
        lines.append(f"{_esc(t['operator'])}: {_esc(operator_name)}")
    if contact_name:
        lines.append(f"{_esc(t['contact'])}: {_esc(contact_name)}")
    if recording_url:
        btn = BUTTON_LABELS[locale]["listen_recording"]
        lines.append(f"\n[{_esc(btn)}]({recording_url})")

    return "\n".join(lines)


# ── Missed call ───────────────────────────────────────────────────

_MISSED_CALL = {
    "ru": {
        "title": "ПРОПУЩЕННЫЙ ЗВОНОК",
        "from": "От",
        "phone": "Телефон",
        "contact": "Контакт",
    },
    "en": {
        "title": "MISSED CALL",
        "from": "From",
        "phone": "Phone",
        "contact": "Contact",
    },
    "uz": {
        "title": "O'TKAZIB YUBORILGAN QO'NG'IROQ",
        "from": "Dan",
        "phone": "Telefon",
        "contact": "Kontakt",
    },
}


def missed_call_message(
    caller_display: str,
    phone: str,
    contact_name: str | None = None,
    lang: str = "ru",
) -> str:
    """Build MarkdownV2 message for a missed call notification."""
    locale = get_locale(lang)
    t = _MISSED_CALL[locale]

    lines = [
        f"*{_esc(t['title'])}*",
        "",
        f"{_esc(t['from'])}: {_esc(caller_display)}",
        f"{_esc(t['phone'])}: {_esc(phone)}",
    ]
    if contact_name:
        lines.append(f"{_esc(t['contact'])}: {_esc(contact_name)}")

    return "\n".join(lines)


# ── New lead ──────────────────────────────────────────────────────

_NEW_LEAD = {
    "ru": {
        "title": "Новый лид",
        "lead_title": "Название",
        "source": "Источник",
        "value": "Оценка",
        "contact": "Контакт",
    },
    "en": {
        "title": "New Lead Created",
        "lead_title": "Title",
        "source": "Source",
        "value": "Value",
        "contact": "Contact",
    },
    "uz": {
        "title": "Yangi lid yaratildi",
        "lead_title": "Sarlavha",
        "source": "Manba",
        "value": "Qiymat",
        "contact": "Kontakt",
    },
}


def new_lead_message(
    lead_title: str,
    source: str | None = None,
    estimated_value: float | None = None,
    currency: str = "USD",
    contact_name: str | None = None,
    lang: str = "ru",
) -> str:
    """Build MarkdownV2 message for a new lead notification."""
    locale = get_locale(lang)
    t = _NEW_LEAD[locale]

    lines = [
        f"*{_esc(t['title'])}*",
        "",
        f"{_esc(t['lead_title'])}: {_esc(lead_title)}",
    ]
    if source:
        lines.append(f"{_esc(t['source'])}: {_esc(source)}")
    if estimated_value:
        lines.append(f"{_esc(t['value'])}: {_esc(f'{estimated_value:,.0f} {currency}')}")
    if contact_name:
        lines.append(f"{_esc(t['contact'])}: {_esc(contact_name)}")

    return "\n".join(lines)


# ── Deal stage change ────────────────────────────────────────────

_DEAL_STAGE = {
    "ru": {
        "title": "Смена стадии сделки",
        "deal": "Сделка",
        "stage": "Стадия",
        "amount": "Сумма",
        "assigned_to": "Ответственный",
    },
    "en": {
        "title": "Deal Stage Changed",
        "deal": "Deal",
        "stage": "Stage",
        "amount": "Amount",
        "assigned_to": "Assigned to",
    },
    "uz": {
        "title": "Bitim bosqichi o'zgardi",
        "deal": "Bitim",
        "stage": "Bosqich",
        "amount": "Summa",
        "assigned_to": "Mas'ul",
    },
}


def deal_stage_message(
    deal_title: str,
    old_stage: str,
    new_stage: str,
    amount: float | None = None,
    assigned_to_name: str | None = None,
    lang: str = "ru",
) -> str:
    """Build MarkdownV2 message for a deal stage change notification."""
    locale = get_locale(lang)
    t = _DEAL_STAGE[locale]
    stages = STAGE_NAMES[locale]

    old_name = stages.get(old_stage, old_stage)
    new_name = stages.get(new_stage, new_stage)

    lines = [
        f"*{_esc(t['title'])}*",
        "",
        f"{_esc(t['deal'])}: {_esc(deal_title)}",
        f"{_esc(t['stage'])}: {_esc(old_name)} → {_esc(new_name)}",
    ]
    if amount:
        lines.append(f"{_esc(t['amount'])}: {_esc(f'{amount:,.0f}')}")
    if assigned_to_name:
        lines.append(f"{_esc(t['assigned_to'])}: {_esc(assigned_to_name)}")

    return "\n".join(lines)


# ── Callback responses ───────────────────────────────────────────

_HANDLED = {
    "ru": "Обработано {name}",
    "en": "Handled by {name}",
    "uz": "{name} tomonidan bajarildi",
}

_LEAD_ASSIGNED = {
    "ru": "Лид назначен → {name}",
    "en": "Lead assigned → {name}",
    "uz": "Lid tayinlandi → {name}",
}

_CONTACT_CREATED = {
    "ru": "Контакт создан: {phone}",
    "en": "Contact created: {phone}",
    "uz": "Kontakt yaratildi: {phone}",
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
        "title": "Дневной отчёт — {date}",
        "total_calls": "Всего звонков",
        "missed": "Пропущено",
        "avg_duration": "Ср. длительность",
        "new_leads": "Новые лиды",
        "deals_won": "Выигранные сделки",
        "deals_lost": "Проигранные сделки",
    },
    "en": {
        "title": "Daily Digest — {date}",
        "total_calls": "Total calls",
        "missed": "Missed",
        "avg_duration": "Avg duration",
        "new_leads": "New leads",
        "deals_won": "Deals won",
        "deals_lost": "Deals lost",
    },
    "uz": {
        "title": "Kunlik hisobot — {date}",
        "total_calls": "Jami qo'ng'iroqlar",
        "missed": "O'tkazib yuborilgan",
        "avg_duration": "O'rt. davomiylik",
        "new_leads": "Yangi lidlar",
        "deals_won": "Yutilgan bitimlar",
        "deals_lost": "Yo'qotilgan bitimlar",
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
    """Build MarkdownV2 message for the daily digest."""
    locale = get_locale(lang)
    t = _DIGEST[locale]

    lines = [
        f"*{_esc(t['title'].format(date=date))}*",
        "",
        f"{_esc(t['total_calls'])}: {total_calls}",
        f"{_esc(t['missed'])}: {missed_calls}",
        f"{_esc(t['avg_duration'])}: {_esc(_duration(avg_duration_sec, locale))}",
        f"{_esc(t['new_leads'])}: {new_leads}",
        f"{_esc(t['deals_won'])}: {deals_won}",
        f"{_esc(t['deals_lost'])}: {deals_lost}",
    ]

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
    "ru": "Результаты поиска: {query}",
    "en": "Search results: {query}",
    "uz": "Qidiruv natijalari: {query}",
}

_MY_LEADS_HEADER = {
    "ru": "Мои лиды",
    "en": "My Leads",
    "uz": "Mening lidlarim",
}


def no_data_text(lang: str = "ru") -> str:
    return _NO_DATA[get_locale(lang)]


def search_header(query: str, lang: str = "ru") -> str:
    return _SEARCH_HEADER[get_locale(lang)].format(query=query)


def my_leads_header(lang: str = "ru") -> str:
    return _MY_LEADS_HEADER[get_locale(lang)]
