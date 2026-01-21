import sys
sys.path.append('source')

from fastapi import FastAPI

from api.v1.routers import router as v1

app = FastAPI(
    docs_url='/',
    swagger_ui_parameters={"persistAuthorization": True}
)
app.include_router(v1)
