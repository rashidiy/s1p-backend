"""
Telegram V2 constants — topic names, emoji prefixes, stage translations per locale.

Centralized here so telegram_i18n.py and telegram_service.py stay DRY.
"""

# Forum topic names per locale
TOPIC_NAMES = {
    "ru": {
        "calls": "Звонки",
        "missed": "Пропущенные",
        "leads": "Лиды",
        "deals": "Сделки",
        "general": "Общее",
    },
    "en": {
        "calls": "Calls",
        "missed": "Missed",
        "leads": "Leads",
        "deals": "Deals",
        "general": "General",
    },
    "uz": {
        "calls": "Qo'ng'iroqlar",
        "missed": "O'tkazib yuborilgan",
        "leads": "Lidlar",
        "deals": "Bitimlar",
        "general": "Umumiy",
    },
}

# Emoji prefixes for topic names (used when creating forum topics)
TOPIC_EMOJI = {
    "calls": "\U0001F4DE",      # 📞
    "missed": "\U0000260E",     # ☎
    "leads": "\U0001F4CB",      # 📋
    "deals": "\U0001F4B0",      # 💰
    "general": "\U0001F4AC",    # 💬
}

# Deal stage display names per locale
STAGE_NAMES = {
    "ru": {
        "prospecting": "Поиск",
        "qualification": "Квалификация",
        "proposal": "Предложение",
        "negotiation": "Переговоры",
        "closed_won": "Закрыта (выигрыш)",
        "closed_lost": "Закрыта (проигрыш)",
    },
    "en": {
        "prospecting": "Prospecting",
        "qualification": "Qualification",
        "proposal": "Proposal",
        "negotiation": "Negotiation",
        "closed_won": "Closed Won",
        "closed_lost": "Closed Lost",
    },
    "uz": {
        "prospecting": "Qidiruv",
        "qualification": "Kvalifikatsiya",
        "proposal": "Taklif",
        "negotiation": "Muzokaralar",
        "closed_won": "Yopildi (yutildi)",
        "closed_lost": "Yopildi (yo'qotildi)",
    },
}

# Call direction labels per locale
DIRECTION_LABELS = {
    "ru": {"inbound": "Входящий", "outbound": "Исходящий", "unknown": "Неизвестный"},
    "en": {"inbound": "Inbound", "outbound": "Outbound", "unknown": "Unknown"},
    "uz": {"inbound": "Kiruvchi", "outbound": "Chiquvchi", "unknown": "Noma'lum"},
}

# Lead source labels per locale
SOURCE_LABELS = {
    "ru": "Источник",
    "en": "Source",
    "uz": "Manba",
}

# Inline button labels per locale
BUTTON_LABELS = {
    "ru": {
        "assign_lead": "Назначить лид",
        "mark_handled": "Обработано",
        "open_crm": "Открыть в CRM",
        "callback": "Перезвонить",
        "create_contact": "Создать контакт",
        "open_lead": "Открыть лид",
        "open_deal": "Открыть сделку",
        "listen_recording": "\U0001F3B5 Запись",
    },
    "en": {
        "assign_lead": "Assign Lead",
        "mark_handled": "Mark Handled",
        "open_crm": "Open in CRM",
        "callback": "Callback",
        "create_contact": "Create Contact",
        "open_lead": "Open Lead",
        "open_deal": "Open Deal",
        "listen_recording": "\U0001F3B5 Recording",
    },
    "uz": {
        "assign_lead": "Lid tayinlash",
        "mark_handled": "Bajarildi",
        "open_crm": "CRM da ochish",
        "callback": "Qayta qo'ng'iroq",
        "create_contact": "Kontakt yaratish",
        "open_lead": "Lidni ochish",
        "open_deal": "Bitimni ochish",
        "listen_recording": "\U0001F3B5 Yozuv",
    },
}

# Default locale
DEFAULT_LOCALE = "ru"


def get_locale(lang: str | None) -> str:
    """Normalize language code to one of the supported locales."""
    if lang and lang[:2] in TOPIC_NAMES:
        return lang[:2]
    return DEFAULT_LOCALE
