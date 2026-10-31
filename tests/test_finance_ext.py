"""Dự báo xu hướng, điểm sức khỏe, mô phỏng và hỏi đáp trên báo cáo."""
import copy
import json
import re

import pytest

from app.services import finance_ext as fx
from tests import mock_groq
from tests.test_ai import KEY
from tests.test_datasets import call
from tests.test_finance import CLEAN, parse


@pytest.fixture(scope="module")
def clean():
    return parse(CLEAN)


def test_linear_forecast_exact_line():
    r = fx.linear_forecast([10, 20, 30, 40, 50], 2)
    assert [p["value"] for p in r["points"]] == [60.0, 70.0]
    assert r["sigma"] == 0 and r["points"][0]["low"] == r["points"][0]["high"] == 60.0
    assert r["r2"] == 1.0


def test_linear_forecast_interval_widens_with_noise_and_horizon():
    r = fx.linear_forecast([10, 14, 11, 16, 15, 19], 3)
    w = [p["high"] - p["low"] for p in r["points"]]
    assert w[0] > 0 and w[0] < w[1] < w[2]
    assert all(p["low"] < p["value"] < p["high"] for p in r["points"])


def test_reliability_levels():
    assert fx.reliability(3, 1.0) == "rất thấp" and fx.reliability(5, 0.9) == "thấp" and fx.reliability(8, 0.9) == "trung bình" and fx.reliability(9, 0.2) == "thấp"


def test_forecast_endpoint(clean):
    r = call("/api/v1/finance/forecast", {"analysis": clean["analysis"], "horizon": 2})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["next_periods"] == ["2026", "2027"] and len(d["periods"]) == 5
    keys = {s["key"] for s in d["series"]}
    assert {"net_revenue", "net_profit"} <= keys
    s = next(x for x in d["series"] if x["key"] == "net_revenue")
    assert len(s["forecast"]) == 2 and s["reliability"] in ("thấp", "rất thấp") and any("5 kỳ" in n or "chỉ có" in n for n in d["notes"])


def test_forecast_refuses_short_series(clean):
    a = copy.deepcopy(clean["analysis"])
    a["periods"] = a["periods"][:2]
    r = call("/api/v1/finance/forecast", {"analysis": a})
    assert r.status_code == 422 and "3 kỳ" in r.json()["detail"]


def test_health_score(clean):
    r = call("/api/v1/finance/health-score", {"analysis": clean["analysis"]})
    assert r.status_code == 200, r.text
    d = r.json()
    assert 0 <= d["score"] <= 100 and d["grade"] in ("Tốt", "Khá", "Trung bình", "Yếu")
    assert abs(sum(g["score"] * g["weight"] for g in d["groups"]) / sum(g["weight"] for g in d["groups"]) - d["score"]) < 0.01
    assert all(0 <= i["score"] <= 100 for i in d["items"]) and any("ngưỡng tham khảo" in n for n in d["notes"])


def test_lin_mapping_directions():
    assert fx._lin(1.5, 0.5, 1.5) == 100 and fx._lin(0.5, 0.5, 1.5) == 0 and fx._lin(0.0, 0.5, 1.5) == 0
    assert fx._lin(0.5, 3.0, 0.5) == 100 and fx._lin(4, 3.0, 0.5) == 0  # nợ càng thấp càng tốt


def test_scenario_identity_and_effect(clean):
    base = {"parsed": clean["parsed"], "overrides": {}}
    r0 = call("/api/v1/finance/scenario", {**base, "adjustments": {}})
    assert r0.status_code == 200, r0.text
    for row in r0.json()["rows"]:
        assert row["base"] == pytest.approx(row["scenario"], abs=0.01), row["key"]
    r = call("/api/v1/finance/scenario", {**base, "adjustments": {"revenue_pct": -10}})
    rows = {x["key"]: x for x in r.json()["rows"]}
    assert rows["net_revenue"]["scenario"] == pytest.approx(rows["net_revenue"]["base"] * 0.9, rel=1e-6)
    assert rows["net_profit"]["scenario"] < rows["net_profit"]["base"]
    r2 = call("/api/v1/finance/scenario", {**base, "adjustments": {"cogs_pct": -5}})
    rows2 = {x["key"]: x for x in r2.json()["rows"]}
    assert rows2["net_profit"]["scenario"] > rows2["net_profit"]["base"]
    assert any("không phải dự báo" in n for n in r.json()["notes"])


def test_scenario_validation(clean):
    base = {"parsed": clean["parsed"], "overrides": {}}
    assert call("/api/v1/finance/scenario", {**base, "adjustments": {"revenue_pct": -95}}).status_code == 422
    assert call("/api/v1/finance/scenario", {**base, "adjustments": {"revenue_pct": "abc"}}).status_code == 422


# ---------------------------------------------------------------- hỏi đáp
def ask(monkeypatch, clean, responder, question="Biên lợi nhuận gộp thay đổi thế nào qua các kỳ?"):
    srv, url, log = mock_groq.start(lambda m, k, b: mock_groq.ok(json.dumps(responder(b), ensure_ascii=False)))
    monkeypatch.setenv("AIAR_AI_BASE_URL", url)
    try:
        r = call("/api/v1/ai/ask", {"analysis": clean["analysis"], "checks": clean["checks"], "question": question, "api_key": KEY})
    finally:
        srv.shutdown()
    return r, log


def good(prompt):
    facts = dict(re.findall(r"^(F\d+): (.*)$", prompt, flags=re.M))
    fid = next(f for f, t in facts.items() if re.search(r"\d[\d.,]*\d", t))
    num = re.findall(r"\d[\d.,]*\d", facts[fid])[0]
    return {"answerable": True, "answer": f"Theo dữ kiện {fid}, số liệu là {num}.", "refs": [fid]}


def test_ask_success_and_prompt_shape(monkeypatch, clean):
    r, log = ask(monkeypatch, clean, lambda body: good(body["messages"][1]["content"]))
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["answerable"] and d["refs"] and not d["unverified_numbers"] and d["facts"]
    sent = log[0]["body"]["messages"][1]["content"]
    assert "<<<" in sent and "Biên lợi nhuận gộp" in sent and log[0]["key"] == KEY and KEY not in r.text


def test_ask_flags_invented_numbers(monkeypatch, clean):
    r, _ = ask(monkeypatch, clean, lambda body: {"answerable": True, "answer": "Biên là 987654,3 theo dữ kiện F1.", "refs": ["F1", "F999"]})
    d = r.json()
    assert d["unverified_numbers"] and d["bad_refs"] == ["F999"]


def test_ask_not_answerable_and_validation(monkeypatch, clean):
    r, _ = ask(monkeypatch, clean, lambda body: {"answerable": False, "answer": "Dữ kiện chưa cho biết nguyên nhân.", "refs": []})
    d = r.json()
    assert d["answerable"] is False and d["no_refs"] is False
    r2, _ = ask(monkeypatch, clean, lambda body: good(body["messages"][1]["content"]), question="ab")
    assert r2.status_code == 422
    r3, _ = ask(monkeypatch, clean, lambda body: good(body["messages"][1]["content"]), question="x" * 400)
    assert r3.status_code == 422


def test_ask_masks_question(monkeypatch, clean):
    seen = {}

    def responder(body):
        seen["p"] = body["messages"][1]["content"]
        return good(seen["p"])
    ask(monkeypatch, clean, responder, question="Gửi kết quả cho a@b.vn và 0901234567 giúp tôi, biên gộp ra sao?")
    assert "a@b.vn" not in seen["p"] and "0901234567" not in seen["p"]
