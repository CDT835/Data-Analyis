"""Xác thực yêu cầu từ plugin WordPress bằng HMAC-SHA256.

Chuỗi được ký (canonical string), mỗi thành phần cách nhau bằng '\n':
    timestamp, nonce, METHOD, path, query, sha256(body)
Phải khớp với AIAR_Python_Client::canonical() trong plugin PHP.
"""
import hashlib
import hmac
import threading
import time
from typing import Dict

from fastapi import HTTPException, Request

from .config import get_settings

_seen_nonces: Dict[str, float] = {}
_lock = threading.Lock()


def canonical(ts: str, nonce: str, method: str, path: str, query: str, body: bytes) -> str:
    return "\n".join([ts, nonce, method.upper(), path, query, hashlib.sha256(body).hexdigest()])


def compute_signature(secret: str, ts: str, nonce: str, method: str, path: str, query: str, body: bytes) -> str:
    msg = canonical(ts, nonce, method, path, query, body).encode("utf-8")
    return hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()


def _unauthorized(message: str) -> HTTPException:
    return HTTPException(status_code=401, detail=message)


async def verify_signature(request: Request) -> None:
    settings = get_settings()
    if not settings.shared_secret:
        raise HTTPException(status_code=503, detail="Dịch vụ chưa được cấu hình AIAR_SHARED_SECRET.")

    ts = request.headers.get("x-aiar-timestamp", "")
    nonce = request.headers.get("x-aiar-nonce", "")
    signature = request.headers.get("x-aiar-signature", "").lower()
    if not ts or not nonce or not signature:
        raise _unauthorized("Thiếu thông tin xác thực.")

    try:
        ts_int = int(ts)
    except ValueError:
        raise _unauthorized("Dấu thời gian không hợp lệ.")

    now = time.time()
    if abs(now - ts_int) > settings.max_skew_seconds:
        raise _unauthorized("Yêu cầu đã hết hạn hoặc đồng hồ máy chủ bị lệch.")

    body = await request.body()
    expected = compute_signature(
        settings.shared_secret, ts, nonce, request.method,
        request.url.path, request.url.query, body,
    )
    if not hmac.compare_digest(expected, signature):
        raise _unauthorized("Chữ ký không hợp lệ (kiểm tra khóa bí mật).")

    # Chống replay: mỗi nonce chỉ dùng một lần trong cửa sổ thời gian cho phép.
    with _lock:
        for key in [k for k, exp in _seen_nonces.items() if exp < now]:
            del _seen_nonces[key]
        if nonce in _seen_nonces:
            raise _unauthorized("Yêu cầu bị lặp lại.")
        _seen_nonces[nonce] = now + settings.max_skew_seconds
