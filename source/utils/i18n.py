"""
Internationalization (i18n) utility for API-facing strings.

Loads JSON translation files from source/locale/{lang}.json on startup.
Supports three languages: Russian (ru), English (en), Uzbek (uz).

Fallback chain: requested lang -> 'en' -> return key itself.
"""

import json
import logging
import os
from typing import NoReturn, Optional

from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)

# Supported languages
SUPPORTED_LANGUAGES = ("ru", "en", "uz")
DEFAULT_LANGUAGE = "ru"

# In-memory translation cache: {lang: {key: value}}
_translations: dict[str, dict[str, str]] = {}


def _load_translations() -> None:
    """Load all translation JSON files into memory (called once on import)."""
    locale_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "locale")

    for lang in SUPPORTED_LANGUAGES:
        file_path = os.path.join(locale_dir, f"{lang}.json")
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                _translations[lang] = json.load(f)
            logger.info("Loaded %d translation keys for '%s'", len(_translations[lang]), lang)
        except FileNotFoundError:
            logger.warning("Translation file not found: %s", file_path)
            _translations[lang] = {}
        except json.JSONDecodeError as e:
            logger.error("Invalid JSON in %s: %s", file_path, e)
            _translations[lang] = {}


# Load translations on module import (once per process)
_load_translations()


def get_text(key: str, lang: str = "en", **kwargs) -> str:
    """
    Get a translated string by key.

    Fallback chain: requested lang -> 'en' -> return key itself.

    Args:
        key: Translation key (e.g. "contact_not_found")
        lang: Language code (ru, en, uz). Defaults to 'en'.
        **kwargs: Format parameters for string interpolation (e.g. limit=5, role="admin")

    Returns:
        Translated string, or the key if no translation found.
    """
    # Try requested language
    text = _translations.get(lang, {}).get(key)

    # Fallback to English
    if text is None and lang != "en":
        text = _translations.get("en", {}).get(key)

    # Fallback to key itself
    if text is None:
        text = key

    # Apply format parameters if provided
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError):
            pass  # Return unformatted text if parameters don't match

    return text


# Alias for get_text — matches the interface name used in task specs
translate = get_text


def raise_translated_error(
    status_code: int,
    key: str,
    locale: str = "en",
    **params,
) -> NoReturn:
    """
    Raise an HTTPException with a translated detail message.

    This is a convenience wrapper so callers don't need to import both
    HTTPException and get_text everywhere.

    Args:
        status_code: HTTP status code (e.g. 404, 403).
        key: Translation key (e.g. "contact_not_found").
        locale: Language code for the message (ru, en, uz).
        **params: Interpolation parameters forwarded to get_text().

    Raises:
        HTTPException: Always raised with the translated detail string.
    """
    raise HTTPException(
        status_code=status_code,
        detail=get_text(key, locale, **params),
    )


def get_language_from_request(request: Request, user_language: Optional[str] = None) -> str:
    """
    Extract language preference from the request context.

    Priority:
    1. Accept-Language header (first supported language found)
    2. User's language field from the authenticated user
    3. Default: 'ru'

    Args:
        request: FastAPI Request object
        user_language: User's language preference from DB/JWT (optional)

    Returns:
        Language code string (ru, en, or uz)
    """
    # 1. Check Accept-Language header
    accept_lang = request.headers.get("Accept-Language", "")
    if accept_lang:
        # Parse Accept-Language: could be "ru", "en-US,en;q=0.9,ru;q=0.8", etc.
        for part in accept_lang.split(","):
            # Strip quality value (e.g., "en;q=0.9" -> "en")
            lang_tag = part.split(";")[0].strip().lower()
            # Extract primary language subtag (e.g., "en-US" -> "en")
            primary = lang_tag.split("-")[0]
            if primary in SUPPORTED_LANGUAGES:
                return primary

    # 2. Check user's language preference
    if user_language and user_language in SUPPORTED_LANGUAGES:
        return user_language

    # 3. Default
    return DEFAULT_LANGUAGE
