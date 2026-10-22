import json
import re

import pytest

from app.services import ai
from tests import mock_gemini
from tests.test_datasets import call
from tests.test_finance import CLEAN, FLAWED, parse

KEY = "AIzaSy-test-key-should-never-leak-1234567"


@pytest.fixture(scope="module")
def clean():
    return parse(CLEAN)


def faithful(prompt: str, extra_text="", extra_refs=("F2",)):
    """Giả lập mô hình trung thực: chỉ trích số có trong dữ kiện."""
    facts = dict(re.findall(r"^(F\d+): (.*)$", prompt, flags=re.M))
    nums = {fid: re.findall(r"\d[\d.,]*\d", t) for fid, t in facts.items()}
    pick = [fid for fid, n in nums.items() if n][:5]
    item = lambda i: {"text": f"Dữ kiện {pick[i]} cho thấy số liệu {nums[pick[i]][0]} cần được theo dõi." + extra_text, "refs": [pick[i]]}
    return {"summary": {"text": f"Báo cáo có số liệu {nums[pick[0]][0]}.", "refs": [pick[0]]},
            "highlights": [item(0), item(1)], "trends": [item(2)], "risks": [item(3)], "recommendations": [item(4)],
            "next_analyses": [{"text": "Nên đối chiếu thêm với báo cáo lưu chuyển tiền tệ.", "refs": [pick[0]]}]}


def prompt_of(body):
    return body["contents"][0]["parts"][0]["text"]


def run(monkeypatch, responder, clean, **extra):
    srv, url, log = mock_gemini.start(responder)
    monkeypatch.setenv("AIAR_AI_BASE_URL", url)
    payload = {"analysis": clean["analysis"], "checks": clean["checks"], "model": "gemini-2.5-flash", "api_key": KEY, **extra}
    try:
        r = call("/api/v1/ai/finance-commentary", payload)
    finally:
        srv.shutdown()
    return r, log


def test_facts_are_aggregates_only(clean):
    r = call("/api/v1/ai/facts", {"analysis": clean["analysis"], "checks": clean["checks"]}).json()
    facts = r["facts"]
    text = " ".join(f["text"] for f in facts)
    assert len(facts) >= 20 and facts[0]["id"] == "F1" and "5 kỳ" in facts[0]["text"] and "triệu đồng" in facts[0]["text"]
    assert any(f["kind"] == "alert" for f in facts) and any(f["kind"] == "dupont" for f in facts)
    for secret in ("An Phát", "xlsx", "Ghi chú", "Bảng cân đối kế toán", "bao_cao"):
        assert secret not in text  # không có tên công ty, tên tệp, tên sheet
    assert r["facts_hash"] == call("/api/v1/ai/facts", {"analysis": clean["analysis"], "checks": clean["checks"]}).json()["facts_hash"]


def test_number_verification_helpers():
    assert [v for _, v in ai.parse_numbers("Doanh thu 137.120 triệu, biên 21,0% và 0,80 lần; F12")] == [137120.0, 21.0, 0.8]
    allowed = ai.allowed_numbers([{"id": "F1", "text": "Biên 21,04% và doanh thu 137.120"}])
    assert ai.verify_text("khoảng 21,0% và 137.120", allowed) == []
    assert ai.verify_text("tăng 97,3%", allowed) == ["97,3"]


def test_commentary_success_and_request_shape(monkeypatch, clean):
    r, log = run(monkeypatch, lambda m, k, b: mock_gemini.ok(json.dumps(faithful(prompt_of(b)), ensure_ascii=False)), clean)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["verification"]["n_numbers_unverified"] == 0 and d["verification"]["n_numbers"] > 5
    assert d["commentary"]["summary"]["refs"] and set(d["commentary"]) >= {"summary", "highlights", "trends", "risks", "recommendations", "next_analyses"}
    assert d["usage"]["prompt_tokens"] == 900 and d["model"] == "gemini-2.5-flash"
    req = log[0]
    assert req["key"] == KEY and not req["query"]  # khóa nằm ở tiêu đề, không nằm trên URL
    assert req["model"] == "gemini-2.5-flash" and req["body"]["generationConfig"]["responseMimeType"] == "application/json"
    assert "QUY TẮC BẮT BUỘC" in req["body"]["systemInstruction"]["parts"][0]["text"]
    prompt = prompt_of(req["body"])
    assert "F1:" in prompt and "xlsx" not in prompt and "An Phát" not in prompt
    assert KEY not in r.text  # khóa không bị trả lại


def test_hallucinated_numbers_and_bad_refs_are_flagged(monkeypatch, clean):
    def bad(prompt):
        out = faithful(prompt)
        out["highlights"][0] = {"text": "Doanh thu tăng 97,3% nhờ chiến dịch quảng cáo lớn.", "refs": ["F1"]}
        out["trends"][0] = {"text": "Xu hướng ổn định.", "refs": ["F999"]}
        return out
    r, _ = run(monkeypatch, lambda m, k, b: mock_gemini.ok(json.dumps(bad(prompt_of(b)), ensure_ascii=False)), clean)
    d = r.json()
    hl = d["commentary"]["highlights"][0]
    assert hl["unverified_numbers"] == ["97,3"] and d["verification"]["n_numbers_unverified"] == 1 and d["verification"]["n_items_with_unverified"] == 1
    tr = d["commentary"]["trends"][0]
    assert tr["no_refs"] and tr["bad_refs"] == ["F999"] and d["verification"]["n_items_without_refs"] == 1


def test_code_fence_and_retry_on_bad_json(monkeypatch, clean):
    calls = {"n": 0}

    def resp(m, k, b):
        calls["n"] += 1
        if calls["n"] == 1:
            return mock_gemini.ok("Đây là nhận xét của tôi: không phải JSON")
        return mock_gemini.ok("```json\n" + json.dumps(faithful(prompt_of(b)), ensure_ascii=False) + "\n```")
    r, log = run(monkeypatch, resp, clean)
    assert r.status_code == 200 and len(log) == 2 and "không phải JSON hợp lệ" in prompt_of(log[1]["body"])


@pytest.mark.parametrize("status,body,expect", [
    (400, {"error": {"message": "API key not valid. Please pass a valid API key."}}, "Khóa API Gemini không hợp lệ"),
    (403, {"error": {"message": "denied"}}, "không có quyền"),
    (404, {"error": {"message": "model not found"}}, "Không tìm thấy mô hình"),
    (429, {"error": {"message": "quota"}}, "vượt hạn mức"),
])
def test_provider_errors_are_translated_without_leaking_key(monkeypatch, clean, status, body, expect):
    r, _ = run(monkeypatch, lambda m, k, b: (status, body), clean)
    assert r.status_code == 422 and expect in r.json()["detail"] and KEY not in r.text


def test_server_error_retries_once_then_reports(monkeypatch, clean):
    monkeypatch.setattr("app.services.ai.time.sleep", lambda s: None)
    r, log = run(monkeypatch, lambda m, k, b: (503, {"error": {"message": "overloaded"}}), clean)
    assert r.status_code == 422 and "mã 503" in r.json()["detail"] and len(log) == 2


def test_blocked_prompt_and_empty_response(monkeypatch, clean):
    r, _ = run(monkeypatch, lambda m, k, b: (200, {"promptFeedback": {"blockReason": "SAFETY"}}), clean)
    assert r.status_code == 422 and "bộ lọc an toàn" in r.json()["detail"]
    r, _ = run(monkeypatch, lambda m, k, b: (200, {"candidates": []}), clean)
    assert r.status_code == 422 and "không trả về nội dung" in r.json()["detail"]


def test_missing_key_uses_environment_fallback(monkeypatch, clean):
    srv, url, log = mock_gemini.start(lambda m, k, b: mock_gemini.ok(json.dumps(faithful(prompt_of(b)), ensure_ascii=False)))
    monkeypatch.setenv("AIAR_AI_BASE_URL", url)
    try:
        monkeypatch.delenv("AIAR_AI_API_KEY", raising=False)
        no_key = call("/api/v1/ai/finance-commentary", {"analysis": clean["analysis"], "checks": clean["checks"]})
        assert no_key.status_code == 422 and "Chưa cấu hình khóa API" in no_key.json()["detail"]
        monkeypatch.setenv("AIAR_AI_API_KEY", "env-key-xyz")
        ok = call("/api/v1/ai/finance-commentary", {"analysis": clean["analysis"], "checks": clean["checks"]})
        assert ok.status_code == 200 and log[-1]["key"] == "env-key-xyz"
    finally:
        srv.shutdown()


def test_validation_of_inputs(monkeypatch, clean):
    assert call("/api/v1/ai/finance-commentary", {"analysis": clean["analysis"], "model": "../../etc", "api_key": KEY}).status_code == 422
    assert call("/api/v1/ai/finance-commentary", {"analysis": {"bad": 1}, "api_key": KEY}).status_code == 422
    assert call("/api/v1/ai/finance-commentary", {"analysis": clean["analysis"], "api_key": KEY, "detail": "x"}).status_code == 422
    monkeypatch.setenv("AIAR_AI_BASE_URL", "http://evil.example.com")
    r = call("/api/v1/ai/finance-commentary", {"analysis": clean["analysis"], "api_key": KEY})
    assert r.status_code == 422 and "không hợp lệ" in r.json()["detail"]  # chỉ cho phép https hoặc localhost


def test_connection_test_endpoint(monkeypatch):
    srv, url, log = mock_gemini.start(lambda m, k, b: mock_gemini.ok("OK"))
    monkeypatch.setenv("AIAR_AI_BASE_URL", url)
    try:
        d = call("/api/v1/ai/test", {"model": "gemini-2.5-flash", "api_key": KEY}).json()
    finally:
        srv.shutdown()
    assert d["ok"] and d["model"] == "gemini-2.5-flash" and "elapsed_ms" in d and log[0]["key"] == KEY


def test_flawed_data_is_surfaced_in_facts():
    r = parse(FLAWED)
    facts = call("/api/v1/ai/facts", {"analysis": r["analysis"], "checks": r["checks"]}).json()["facts"]
    chk = next(f for f in facts if f["kind"] == "checks")
    assert "7 phép cộng/cân đối bị lệch" in chk["text"] and "4 lỗi gốc" in chk["text"] and "Tổng cộng tài sản kỳ 2023 lệch 500" in chk["text"]
