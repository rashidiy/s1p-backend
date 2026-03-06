import os
import sys
import copy

from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

sys.path.append('source')

from fastapi import FastAPI, Query
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import JSONResponse, RedirectResponse

from api.v1.routers import router as v1


# Read allowed CORS origins from env (comma-separated), default to localhost:3000
_cors_origins_raw = os.getenv("CORS_ORIGINS", "http://localhost:3000")
CORS_ORIGINS = [o.strip() for o in _cors_origins_raw.split(",") if o.strip()]


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

app.add_middleware(SecurityHeadersMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

app.include_router(v1)

PATH_FILTERS = {
    "owner": lambda p: p.startswith("/api/v1/owner"),
    "company": lambda p: p.startswith("/api/v1/auth") or p.startswith("/api/v1/company"),
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


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse("/swagger?type=owner")
