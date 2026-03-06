"""
Locale dependency for FastAPI routes.

Resolves the current locale using the following priority:
1. ``Accept-Language`` request header (first supported language wins)
2. Authenticated user's ``language`` preference stored in the DB
3. Fallback to ``DEFAULT_LANGUAGE`` ("ru")

Usage in a route::

    @router.get("/example")
    async def example(locale: str = Depends(get_locale)):
        msg = get_text("some_key", locale)
        ...

The dependency also stores the resolved locale on ``request.state.locale``
so middleware or downstream code can access it without re-computation.
"""

from typing import Optional

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_session
from utils.i18n import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES
from utils.managers import JWTManager, TokenType

# Optional bearer — allows the dependency to work on both authenticated
# and unauthenticated routes without raising 403 on missing tokens.
_optional_bearer = HTTPBearer(auto_error=False)


async def get_locale(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_optional_bearer),
    session: AsyncSession = Depends(get_session),
) -> str:
    """
    Resolve the current request locale.

    Returns:
        Language code string (ru, en, or uz).
    """
    # 1. Accept-Language header
    accept_lang = request.headers.get("Accept-Language", "")
    if accept_lang:
        for part in accept_lang.split(","):
            lang_tag = part.split(";")[0].strip().lower()
            primary = lang_tag.split("-")[0]
            if primary in SUPPORTED_LANGUAGES:
                request.state.locale = primary
                return primary

    # 2. Authenticated user's language preference
    if credentials is not None:
        try:
            payload = JWTManager.verify(credentials.credentials, TokenType.ACCESS)
            # Import here to avoid circular imports at module level
            from db.models.user import User

            user = await User.get(id=payload.sub, session=session)
            if user and getattr(user, "language", None):
                lang = user.language
                if lang in SUPPORTED_LANGUAGES:
                    request.state.locale = lang
                    return lang
        except Exception:
            # Token invalid / expired / user not found — fall through
            pass

    # 3. Default
    request.state.locale = DEFAULT_LANGUAGE
    return DEFAULT_LANGUAGE
