import logging
import os
import sys
import copy
import time
from contextlib import asynccontextmanager

from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

sys.path.append('source')

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from api.v1.routers import router as v1
from api.v1.routers.public import router as public_v1
from db import get_session
from db.base import AsyncDatabaseSession

logger = logging.getLogger("s1p")

# Read allowed CORS origins from env (comma-separated), default to localhost:3000
_cors_origins_raw = os.getenv("CORS_ORIGINS", "http://localhost:3000")
CORS_ORIGINS = [o.strip() for o in _cors_origins_raw.split(",") if o.strip()]
# Allow origin regex from env; defaults to *.localhost subdomains for development
CORS_ORIGIN_REGEX = os.getenv(
    "CORS_ORIGIN_REGEX",
    r"^https?://[\w.-]+\.localhost(:\d+)?$",
)

limiter = Limiter(key_func=get_remote_address)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to every response"""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log method, path, status code, and duration for every request"""

    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "%s %s %s %.0fms",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response

# ── Startup security checks ──────────────────────────────────────
_INSECURE_JWT_DEFAULTS = {
    "your-super-secret-jwt-key-min-32-chars-long-change-in-production",
    "change-me",
}

_jwt_key = os.getenv("JWT_SIGNING_KEY", "")
if _jwt_key in _INSECURE_JWT_DEFAULTS:
    logger.critical(
        "JWT_SIGNING_KEY is set to a known insecure default. "
        "Change it immediately in production!"
    )
elif len(_jwt_key) < 32:
    logger.critical(
        "JWT_SIGNING_KEY is shorter than 32 characters (%d). "
        "Use a longer key for adequate security.",
        len(_jwt_key),
    )

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup and shutdown logic."""
    # ── Startup ──
    await _register_telegram_webhook()

    yield

    # ── Shutdown ──
    await _shutdown_cleanup()


app = FastAPI(
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)

app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "Too many requests. Please try again later."},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Catch-all for unhandled exceptions — never leak stack traces to client"""
    import traceback
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError):
    """Handle DB constraint violations gracefully"""
    error_msg = str(exc.orig) if exc.orig else str(exc)
    if "unique" in error_msg.lower() or "duplicate" in error_msg.lower():
        return JSONResponse(status_code=409, content={"detail": "Resource already exists"})
    if "foreign" in error_msg.lower():
        return JSONResponse(status_code=400, content={"detail": "Referenced resource not found"})
    return JSONResponse(status_code=400, content={"detail": "Database constraint violation"})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Return user-friendly validation errors"""
    errors = []
    for error in exc.errors():
        field = " → ".join(str(loc) for loc in error["loc"] if loc != "body")
        errors.append({"field": field, "message": error["msg"]})
    return JSONResponse(status_code=422, content={"detail": "Validation error", "errors": errors})

# Middleware stack (last added = outermost):
# ProxyHeaders → CORS → SecurityHeaders → RequestLogging → App
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_origin_regex=CORS_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Subdomain", "X-Forwarded-Host"],
)

# Trust X-Forwarded-For/Proto from reverse proxy so rate limiter sees real client IP
_trusted_hosts_raw = os.getenv("TRUSTED_PROXY_HOSTS", "127.0.0.1")
TRUSTED_HOSTS = [h.strip() for h in _trusted_hosts_raw.split(",") if h.strip()]
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=TRUSTED_HOSTS)

os.makedirs("source/static/media/avatars", exist_ok=True)
app.mount("/media", StaticFiles(directory="source/static/media"), name="media")
app.mount("/illustrations", StaticFiles(directory="source/static/illustrations"), name="illustrations")

app.include_router(v1)
app.include_router(public_v1)


# ── Telegram webhook registration ──────────────────────────────────
async def _register_telegram_webhook():
    """Register the Telegram bot webhook URL on startup."""
    from core.config import TelegramConfig

    if not TelegramConfig.ENABLED:
        return
    if not TelegramConfig.BOT_TOKEN:
        return

    webhook_base = os.getenv("TELEGRAM_WEBHOOK_URL", os.getenv("BASE_URL", ""))
    if not webhook_base:
        return

    webhook_url = f"{webhook_base}/api/v1/webhooks/telegram/{TelegramConfig.WEBHOOK_SECRET}"

    try:
        from aiogram import Bot
        from aiogram.types import BotCommand
        bot = Bot(token=TelegramConfig.BOT_TOKEN)
        await bot.set_webhook(url=webhook_url)

        # Register bot commands — English (default)
        from aiogram.types import BotCommandScopeDefault
        commands_en = [
            BotCommand(command="today", description="📊 Today's statistics"),
            BotCommand(command="search", description="🔍 Search contacts"),
            BotCommand(command="myleads", description="📝 My assigned leads"),
            BotCommand(command="help", description="❓ Available commands"),
            BotCommand(command="start", description="🚀 Start the bot"),
        ]
        await bot.set_my_commands(commands_en)

        # Russian commands
        commands_ru = [
            BotCommand(command="today", description="📊 Статистика за сегодня"),
            BotCommand(command="search", description="🔍 Поиск контактов"),
            BotCommand(command="myleads", description="📝 Мои лиды"),
            BotCommand(command="help", description="❓ Команды"),
            BotCommand(command="start", description="🚀 Запуск бота"),
        ]
        try:
            await bot.set_my_commands(commands_ru, scope=BotCommandScopeDefault(), language_code="ru")
        except Exception:
            pass

        # Uzbek commands
        commands_uz = [
            BotCommand(command="today", description="📊 Bugungi statistika"),
            BotCommand(command="search", description="🔍 Kontakt qidirish"),
            BotCommand(command="myleads", description="📝 Mening lidlarim"),
            BotCommand(command="help", description="❓ Buyruqlar"),
            BotCommand(command="start", description="🚀 Botni ishga tushirish"),
        ]
        try:
            await bot.set_my_commands(commands_uz, scope=BotCommandScopeDefault(), language_code="uz")
        except Exception:
            pass

        # Bot description — shown in "What can this bot do?"
        try:
            await bot.set_my_description(
                description="S1P CRM — manage calls, contacts, leads, and deals right from Telegram. Get real-time notifications, search your CRM, and open the Mini App for full access."
            )
            await bot.set_my_description(
                description="S1P CRM — управляйте звонками, контактами, лидами и сделками прямо в Telegram. Мгновенные уведомления, поиск по CRM и полный доступ через мини-приложение.",
                language_code="ru",
            )
            await bot.set_my_description(
                description="S1P CRM — qo'ng'iroqlar, kontaktlar, lidlar va bitimlarni to'g'ridan-to'g'ri Telegram orqali boshqaring. Tezkor bildirishnomalar, CRM qidirish va mini ilova.",
                language_code="uz",
            )
            # Short description — shown in bot profile and inline search
            await bot.set_my_short_description(
                description="CRM for call centers — calls, leads, deals in Telegram"
            )
            await bot.set_my_short_description(
                description="CRM для колл-центров — звонки, лиды, сделки в Telegram",
                language_code="ru",
            )
            await bot.set_my_short_description(
                description="Qo'ng'iroq markazlari uchun CRM — Telegramda",
                language_code="uz",
            )
        except Exception:
            pass  # Description is optional

        # Set Mini App as menu button
        try:
            from aiogram.types import MenuButtonWebApp, WebAppInfo
            frontend_url = os.getenv("FRONTEND_URL", "").rstrip("/")
            if frontend_url and frontend_url.startswith("https://"):
                await bot.set_chat_menu_button(
                    menu_button=MenuButtonWebApp(
                        text="📋 CRM",
                        web_app=WebAppInfo(url=f"{frontend_url}/miniapp"),
                    )
                )
        except Exception:
            pass  # Menu button is optional — skip if it fails

        info = await bot.get_webhook_info()
        await bot.session.close()
        print(f"[Telegram] Webhook registered: {info.url}, commands + menu button set")

        # Start daily digest scheduler
        try:
            from utils.tasks.telegram_digest import digest_scheduler
            import asyncio
            asyncio.create_task(digest_scheduler())
            print("[Telegram] Digest scheduler started")
        except Exception as e:
            print(f"[Telegram] Failed to start digest scheduler: {e}")

        # Start missed call escalation scheduler
        try:
            from utils.tasks.missed_call_escalation import escalation_scheduler
            asyncio.create_task(escalation_scheduler())
            print("[Telegram] Missed call escalation scheduler started")
        except Exception as e:
            print(f"[Telegram] Failed to start escalation scheduler: {e}")

        # Start orphan call cleanup scheduler
        try:
            from utils.tasks.orphan_call_cleanup import orphan_cleanup_scheduler
            asyncio.create_task(orphan_cleanup_scheduler())
            print("[Calls] Orphan call cleanup scheduler started")
        except Exception as e:
            print(f"[Calls] Failed to start orphan cleanup scheduler: {e}")

    except Exception as e:
        print(f"[Telegram] Failed to register webhook: {e}")


# ── Graceful shutdown ─────────────────────────────────────────────
async def _shutdown_cleanup():
    """Close DB engine, Redis, and HTTP client pool on shutdown"""
    # DB engine
    try:
        await AsyncDatabaseSession._engine.dispose()
        print("[Shutdown] DB engine disposed")
    except Exception as e:
        print(f"[Shutdown] DB engine dispose failed: {e}")

    # Cache / Redis
    try:
        from utils.services.cache_service import get_cache
        cache = get_cache()
        if hasattr(cache, '_cache') and hasattr(cache._cache, 'close'):
            await cache._cache.close()
            print("[Shutdown] Redis cache closed")
    except Exception as e:
        print(f"[Shutdown] Cache close failed: {e}")

    # HTTP client pool (telephony)
    try:
        from utils.services.telephony.http_client import cleanup_http_client
        await cleanup_http_client()
        print("[Shutdown] HTTP client pool closed")
    except Exception as e:
        print(f"[Shutdown] HTTP client cleanup failed: {e}")


PATH_FILTERS = {
    "owner": lambda p: p.startswith("/api/v1/owner"),
    "company": lambda p: p.startswith("/api/v1/auth") or p.startswith("/api/v1/company"),
    "public": lambda p: p.startswith("/api/public/v1"),
}


def _filtered_openapi(type_filter: str) -> dict:
    schema = copy.deepcopy(app.openapi())
    path_filter = PATH_FILTERS.get(type_filter)
    if path_filter:
        schema["paths"] = {p: ops for p, ops in schema["paths"].items() if path_filter(p)}
        schema["info"]["title"] = f"S1P - {type_filter.title()} API"
    return schema


@app.get("/openapi.json", include_in_schema=False)
async def openapi_filtered(type: str = Query("owner")):
    return JSONResponse(_filtered_openapi(type))


@app.get("/swagger", include_in_schema=False)
async def swagger_ui(type: str = Query("owner")):
    return get_swagger_ui_html(
        openapi_url=f"/openapi.json?type={type}",
        title=f"S1P - {type.title()} API",
        swagger_ui_parameters={"persistAuthorization": True},
    )


# Compute git hash once at import time (not on every request)
import subprocess as _subprocess
try:
    _GIT_HASH = _subprocess.check_output(
        ["git", "rev-parse", "--short", "HEAD"], text=True
    ).strip()
except Exception:
    _GIT_HASH = "unknown"


@app.get("/version", include_in_schema=False)
async def version():
    """Returns app version and environment info for deployment verification"""
    return {
        "app": "s1p-backend",
        "version": "1.0.0",
        "git": _GIT_HASH,
        "env": os.getenv("ENV", "production"),
    }


@app.get("/health", include_in_schema=False)
async def health_check():
    """Health check endpoint — verifies DB and Redis connectivity"""
    db_status = "ok"
    redis_status = "ok"

    # Check database
    try:
        async for session in get_session():
            await session.execute(text("SELECT 1"))
    except Exception:
        db_status = "error"

    # Check Redis
    try:
        import redis.asyncio as aioredis
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        r = aioredis.from_url(redis_url)
        await r.ping()
        await r.aclose()
    except Exception:
        redis_status = "error"

    healthy = db_status == "ok" and redis_status == "ok"
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={"status": "healthy" if healthy else "unhealthy", "db": db_status, "redis": redis_status},
    )


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse("/swagger?type=owner")
