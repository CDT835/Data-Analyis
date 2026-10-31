from app.services import privacy, ai


def test_mask_email_phone_url():
    t, n = privacy.mask("Liên hệ a.b@congty.vn hoặc 0901 234 567, +84 912345678, xem https://x.vn/abc")
    assert "@" not in t and "0901" not in t and "912345678" not in t and "https" not in t
    assert n == 4


def test_mask_long_digits_and_company():
    t, n = privacy.mask("MST 0312345678901 của Công ty TNHH Thương mại ABC và Ngân hàng Vietcombank")
    assert "0312345678901" not in t and "ABC" not in t and "Vietcombank" not in t
    assert n >= 3


def test_numbers_are_not_masked():
    s = "Doanh thu theo kỳ: 2021: 84.123.456; 2022: 1.234.567.890; ROE 12,5%; 0,85 lần; tăng 15,3%"
    t, n = privacy.mask(s)
    assert t == s and n == 0


def test_env_switch(monkeypatch):
    assert privacy.enabled()
    monkeypatch.setenv("AIAR_AI_MASK", "0")
    assert not privacy.enabled()


def test_prompt_masked_before_sending(monkeypatch):
    sent = {}

    def fake(key, model, system, user, **kw):
        sent["user"] = user
        return '{"summary":{"text":"ok","refs":["F1"]}}', {}

    monkeypatch.setattr(ai, "call_llm", fake)
    analysis = {"periods": [{"label": "2023"}, {"label": "2024"}], "unit": None, "growth": [{"label": "Doanh thu Công ty Alpha Beta", "values": [1.0, 2.0], "yoy_pct": [None, 100.0], "cagr_pct": None}],
                "ratio_groups": [], "vertical": {}, "alerts": [{"period": "2024", "title": "t", "message": "email x@y.vn"}], "notes": ["Liên hệ 0901234567"]}
    out = ai.generate_finance_commentary(analysis, None, "m", "k")
    assert "x@y.vn" not in sent["user"] and "0901234567" not in sent["user"] and "Alpha" not in sent["user"]
    assert out["masked"] >= 3
