"""Xoay khóa không gián đoạn, giới hạn tần suất và chặn dò chữ ký."""
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from app import auth
from app.main import app
from app.auth import compute_signature
from tests.test_datasets import SECRET

client = TestClient(app)
PATH = "/api/v1/health"


def send(secret, path=PATH, headers_extra=None, nonce=None):
    ts, nonce = str(int(time.time())), nonce or uuid.uuid4().hex
    h = {"X-AIAR-Timestamp": ts, "X-AIAR-Nonce": nonce,
         "X-AIAR-Signature": compute_signature(secret, ts, nonce, "GET", path, "", b"")}
    h.update(headers_extra or {})
    return client.get(path, headers=h)


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    auth.reset_limits()
    yield
    auth.reset_limits()


def _p():
    return PATH


def test_rotation_accepts_both_keys_then_only_new(monkeypatch):
    p = _p()
    new = "KHOA-MOI-" + "x" * 30
    monkeypatch.setenv("AIAR_SHARED_SECRET", new)
    monkeypatch.setenv("AIAR_SHARED_SECRET_PREVIOUS", SECRET)
    assert send(new, p).status_code == 200      # khóa mới
    assert send(SECRET, p).status_code == 200   # khóa cũ vẫn dùng được trong lúc chuyển đổi
    assert send("khoa-la-" + "y" * 30, p).status_code == 401
    monkeypatch.delenv("AIAR_SHARED_SECRET_PREVIOUS")
    assert send(new, p).status_code == 200
    assert send(SECRET, p).status_code == 401   # bỏ khóa cũ: khóa cũ hết hiệu lực


def test_rate_limit(monkeypatch):
    p = _p()
    monkeypatch.setenv("AIAR_RATE_PER_MIN", "5")
    codes = [send(SECRET, p).status_code for _ in range(7)]
    assert codes[:5] == [200] * 5 and codes[5:] == [429, 429]
    r = send(SECRET, p)
    assert r.status_code == 429 and r.headers.get("retry-after") == "60"


def test_signature_guessing_is_throttled_per_ip(monkeypatch):
    p = _p()
    monkeypatch.setenv("AIAR_AUTH_FAIL_PER_MIN", "4")
    bad = [send("sai" * 12, p, {"X-Forwarded-For": "9.9.9.9"}).status_code for _ in range(6)]
    assert bad[:4] == [401] * 4 and bad[4:] == [429, 429]
    assert send(SECRET, p, {"X-Forwarded-For": "9.9.9.9"}).status_code == 429   # địa chỉ đang bị chặn tạm
    assert send(SECRET, p, {"X-Forwarded-For": "8.8.8.8"}).status_code == 200   # địa chỉ khác không bị ảnh hưởng


def test_replay_still_rejected():
    n = uuid.uuid4().hex
    assert send(SECRET, PATH, nonce=n).status_code == 200
    assert send(SECRET, PATH, nonce=n).status_code == 401
