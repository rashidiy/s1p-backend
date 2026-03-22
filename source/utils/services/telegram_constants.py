"""
Telegram V2 constants — topic names, emoji prefixes, stage translations per locale.

Centralized here so telegram_i18n.py and telegram_service.py stay DRY.
"""

# Forum topic names per locale (V3: 3 topics instead of 5)
TOPIC_NAMES = {
    "ru": {
        "calls": "Звонки",
        "leads": "Лиды",
        "deals": "Сделки",
        "general": "Общее",
    },
    "en": {
        "calls": "Calls",
        "leads": "Leads",
        "deals": "Deals",
        "general": "General",
    },
    "uz": {
        "calls": "Qo'ng'iroqlar",
        "leads": "Lidlar",
        "deals": "Bitimlar",
        "general": "Umumiy",
    },
}

# Custom emoji IDs for forum topic icons (from Telegram's built-in "Topics" sticker set)
# These set the circular icon on the left of the topic name, not text emoji in the name.
# Retrieved via Bot API getForumTopicIconStickers.
TOPIC_ICON_EMOJI_ID = {
    "calls": "5409357944619802453",     # 📱
    "leads": "5373251851074415873",     # 📝
    "deals": "5350452584119279096",     # 💰
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
    "ru": {"inbound": "входящий", "outbound": "исходящий", "unknown": ""},
    "en": {"inbound": "inbound", "outbound": "outbound", "unknown": ""},
    "uz": {"inbound": "kiruvchi", "outbound": "chiquvchi", "unknown": ""},
}

# Lead source labels per locale
SOURCE_LABELS = {
    "ru": "Источник",
    "en": "Source",
    "uz": "Manba",
}

# Inline button labels per locale (with emoji for visual polish)
BUTTON_LABELS = {
    "ru": {
        "mark_handled": "✅ Обработано",
        "assign_lead": "👤 Назначить лид",
        "open_crm": "📋 CRM",
        "callback": "📞 Перезвонить",
        "create_contact": "➕ Контакт",
        "open_lead": "📝 Лид",
        "open_deal": "💼 Сделка",
        "listen_recording": "🎵 Запись",
    },
    "en": {
        "mark_handled": "✅ Handled",
        "assign_lead": "👤 Assign Lead",
        "open_crm": "📋 CRM",
        "callback": "📞 Callback",
        "create_contact": "➕ Contact",
        "open_lead": "📝 Lead",
        "open_deal": "💼 Deal",
        "listen_recording": "🎵 Recording",
    },
    "uz": {
        "mark_handled": "✅ Bajarildi",
        "assign_lead": "👤 Lid tayinlash",
        "open_crm": "📋 CRM",
        "callback": "📞 Qayta qo'ng'iroq",
        "create_contact": "➕ Kontakt",
        "open_lead": "📝 Lid",
        "open_deal": "💼 Bitim",
        "listen_recording": "🎵 Yozuv",
    },
}

# Default locale
DEFAULT_LOCALE = "ru"


def get_locale(lang: str | None) -> str:
    """Normalize language code to one of the supported locales."""
    if lang and lang[:2] in TOPIC_NAMES:
        return lang[:2]
    return DEFAULT_LOCALE
