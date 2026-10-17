import os
import time
import uuid

SECRET = "x" * 40
os.environ["AIAR_SHARED_SECRET"] = SECRET

from fastapi.testclient import TestClient  # noqa: E402

from app.auth import compute_signature  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)
PATH = "/api/v1/health"


def headers(ts=None, nonce=None, secret=SECRET, method="GET", path=PATH, query="", body=b""):
    ts = str(ts if ts is not None else int(time.time()))
    nonce = nonce or uuid.uuid4().hex
    sig = compute_signature(secret, ts, nonce, method, path, query, body)
    return {"X-AIAR-Timestamp": ts, "X-AIAR-Nonce": nonce, "X-AIAR-Signature": sig}


def test_healthz_public():
    assert client.get("/healthz").json() == {"status": "ok"}


def test_valid_signature():
    r = client.get(PATH, headers=headers())
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_missing_headers():
    assert client.get(PATH).status_code == 401


def test_wrong_secret():
    assert client.get(PATH, headers=headers(secret="y" * 40)).status_code == 401


def test_expired_timestamp():
    assert client.get(PATH, headers=headers(ts=int(time.time()) - 3600)).status_code == 401


def test_replay_rejected():
    h = headers()
    assert client.get(PATH, headers=h).status_code == 200
    assert client.get(PATH, headers=h).status_code == 401


def test_query_is_signed():
    h = headers(query="a=1")
    assert client.get(PATH + "?a=2", headers=h).status_code == 401
