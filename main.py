import os
import sys
import copy

from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

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

# Read allowed CORS origins from env (comma-separated), default to localhost:3000
_cors_origins_raw = os.getenv("CORS_ORIGINS", "http://localhost:3000")
CORS_ORIGINS = [o.strip() for o in _cors_origins_raw.split(",") if o.strip()]
# Allow all *.localhost:3000 subdomains in development
CORS_ORIGIN_REGEX = r"^https?://[\w.-]+\.localhost(:\d+)?$"

limiter = Limiter(key_func=get_remote_address)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to every response"""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response

app = FastAPI(
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
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

app.add_middleware(SecurityHeadersMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_origin_regex=CORS_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Subdomain", "X-Forwarded-Host"],
)

os.makedirs("source/static/media/avatars", exist_ok=True)
app.mount("/media", StaticFiles(directory="source/static/media"), name="media")
app.mount("/illustrations", StaticFiles(directory="source/static/illustrations"), name="illustrations")

app.include_router(v1)
app.include_router(public_v1)


# ── Telegram webhook registration ──────────────────────────────────
@app.on_event("startup")
async def register_telegram_webhook():
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

        # Register bot commands
        commands = [
            BotCommand(command="today", description="Today's statistics"),
            BotCommand(command="search", description="Search contacts"),
            BotCommand(command="myleads", description="My assigned leads"),
            BotCommand(command="start", description="Start the bot"),
        ]
        await bot.set_my_commands(commands)

        info = await bot.get_webhook_info()
        await bot.session.close()
        print(f"[Telegram] Webhook registered: {info.url}, commands set")

        # Start daily digest scheduler
        try:
            from utils.tasks.telegram_digest import digest_scheduler
            import asyncio
            asyncio.create_task(digest_scheduler())
            print("[Telegram] Digest scheduler started")
        except Exception as e:
            print(f"[Telegram] Failed to start digest scheduler: {e}")

    except Exception as e:
        print(f"[Telegram] Failed to register webhook: {e}")

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


@app.get("/version", include_in_schema=False)
async def version():
    """Returns app version and environment info for deployment verification"""
    import subprocess
    try:
        git_hash = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        git_hash = "unknown"
    return {
        "app": "s1p-backend",
        "version": "1.0.0",
        "git": git_hash,
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
