from fastapi import FastAPI

from .config import get_settings
from .routers import system

_settings = get_settings()

app = FastAPI(
    title="AI Report Studio – Dịch vụ phân tích dữ liệu",
    version="0.2.0",
    docs_url="/docs" if _settings.enable_docs else None,
    redoc_url=None,
    openapi_url="/openapi.json" if _settings.enable_docs else None,
)

app.include_router(system.router)
