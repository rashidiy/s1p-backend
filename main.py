import os
import sys
import copy

from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

sys.path.append('source')

from fastapi import FastAPI, Query, Request
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import JSONResponse, RedirectResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy import text

from api.v1.routers import router as v1
from api.v1.routers.public import router as public_v1
from db import get_session

# Read allowed CORS origins from env (comma-separated), default to localhost:3000
_cors_origins_raw = os.getenv("CORS_ORIGINS", "http://localhost:3000")
CORS_ORIGINS = [o.strip() for o in _cors_origins_raw.split(",") if o.strip()]

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

app.add_middleware(SecurityHeadersMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

app.include_router(v1)
app.include_router(public_v1)

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
