from fastapi import FastAPI

from api.v1.routers import router as v1

app = FastAPI(docs_url='/')
app.include_router(v1)
