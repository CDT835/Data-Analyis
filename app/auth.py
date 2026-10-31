"""Xác thực yêu cầu từ plugin WordPress bằng HMAC-SHA256.

Chuỗi được ký (canonical string), mỗi thành phần cách nhau bằng '\n':
    timestamp, nonce, METHOD, path, query, sha256(body)
Phải khớp với AIAR_Python_Client::canonical() trong plugin PHP.
"""
import hashlib
import hmac
import threading
import time
from collections import deque
from typing import Deque, Dict

from fastapi import HTTPException, Request

from .config import get_settings

_seen_nonces: Dict[str, float] = {}
_lock = threading.Lock()
_hits: Deque[float] = deque()            # yêu cầu hợp lệ trong 60 giây gần nhất
_fails: Dict[str, Deque[float]] = {}     # yêu cầu sai xác thực theo địa chỉ


def reset_limits() -> None:
    """Dùng cho kiểm thử."""
    with _lock:
        _hits.clear()
        _fails.clear()
        _seen_nonces.clear()


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()[:45]
    return request.client.host if request.client else "?"


def _too_many(message: str) -> HTTPException:
    return HTTPException(status_code=429, detail=message, headers={"Retry-After": "60"})


def _prune(q: Deque[float], now: float) -> None:
    while q and q[0] < now - 60:
        q.popleft()


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

    ip = _client_ip(request)
    with _lock:  # chặn dò chữ ký: quá nhiều lần sai từ một địa chỉ thì từ chối luôn, chưa cần tính HMAC
        q = _fails.get(ip)
        if q is not None:
            _prune(q, now)
            if len(q) >= settings.auth_fail_per_min:
                raise _too_many("Quá nhiều yêu cầu xác thực sai. Hãy thử lại sau.")

    body = await request.body()
    secrets = [settings.shared_secret] + ([settings.shared_secret_previous] if settings.shared_secret_previous else [])
    ok = False
    for sec in secrets:  # so sánh hết các khóa để thời gian xử lý không lộ khóa nào khớp
        expected = compute_signature(sec, ts, nonce, request.method, request.url.path, request.url.query, body)
        ok = hmac.compare_digest(expected, signature) or ok
    if not ok:
        with _lock:
            _fails.setdefault(ip, deque()).append(now)
            if len(_fails) > 1000:  # không để bộ nhớ phình ra khi bị quét từ nhiều địa chỉ
                for k in [k for k, v in _fails.items() if not v or v[-1] < now - 60]:
                    del _fails[k]
        raise _unauthorized("Chữ ký không hợp lệ (kiểm tra khóa bí mật).")

    with _lock:
        # Chống replay: mỗi nonce chỉ dùng một lần trong cửa sổ thời gian cho phép.
        for key in [k for k, exp in _seen_nonces.items() if exp < now]:
            del _seen_nonces[key]
        if nonce in _seen_nonces:
            raise _unauthorized("Yêu cầu bị lặp lại.")
        # Giới hạn tần suất (gói miễn phí chỉ có 512 MB RAM, tránh bị dồn việc nặng)
        _prune(_hits, now)
        if len(_hits) >= settings.rate_per_min:
            raise _too_many("Dịch vụ đang quá tải, hãy thử lại sau ít phút.")
        _hits.append(now)
        _seen_nonces[nonce] = now + settings.max_skew_seconds
