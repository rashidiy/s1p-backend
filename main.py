import sys
import copy

from starlette.middleware.cors import CORSMiddleware

sys.path.append('source')

from fastapi import FastAPI, Query
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import JSONResponse, RedirectResponse

from api.v1.routers import router as v1
from api.v1.routers.public import router as public_v1

app = FastAPI(
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://[\w-]+\.(s1p\.com|localhost)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse("/swagger?type=owner")
