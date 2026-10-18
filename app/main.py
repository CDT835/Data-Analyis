import json
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .config import get_settings
from .routers import analysis, datasets, system

_settings = get_settings()


def _warm_up() -> None:
    """Nạp trước scikit-learn ở luồng nền để lần gọi ML đầu tiên không bị chậm (gói miễn phí CPU rất yếu)."""
    try:
        import sklearn.cluster, sklearn.linear_model, sklearn.metrics, sklearn.preprocessing  # noqa: F401
    except Exception:
        pass


@asynccontextmanager
async def lifespan(_app):
    threading.Thread(target=_warm_up, daemon=True).start()
    yield


class BodyLimitMiddleware:
    """Từ chối yêu cầu quá lớn trước khi đọc hết vào bộ nhớ (gói miễn phí chỉ có 512 MB RAM)."""

    class _TooLarge(Exception):
        pass

    def __init__(self, app):
        self.app = app

    async def _reject(self, send):
        body = json.dumps({"detail": "Tệp gửi lên quá lớn so với giới hạn của dịch vụ."}).encode()
        await send({"type": "http.response.start", "status": 413,
                    "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        limit = get_settings().max_body_bytes
        length = dict(scope["headers"]).get(b"content-length")
        if length and length.isdigit() and int(length) > limit:
            return await self._reject(send)
        received = 0
        started = False

        async def limited_receive():
            nonlocal received
            msg = await receive()
            if msg["type"] == "http.request":
                received += len(msg.get("body", b""))
                if received > limit:
                    raise BodyLimitMiddleware._TooLarge()
            return msg

        async def tracking_send(msg):
            nonlocal started
            if msg["type"] == "http.response.start":
                started = True
            await send(msg)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except BodyLimitMiddleware._TooLarge:
            if not started:
                await self._reject(send)


app = FastAPI(
    title="AI Report Studio – Dịch vụ phân tích dữ liệu",
    version="0.4.0",
    docs_url="/docs" if _settings.enable_docs else None,
    redoc_url=None,
    openapi_url="/openapi.json" if _settings.enable_docs else None,
    lifespan=lifespan,
)
app.add_middleware(BodyLimitMiddleware)
app.include_router(system.router)
app.include_router(datasets.router)
app.include_router(analysis.router)

