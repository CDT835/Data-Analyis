"""Phân tích mở rộng: dự báo xu hướng, điểm sức khỏe tài chính, mô phỏng "nếu… thì…".

Nguyên tắc: chỉ dùng số liệu đã tính từ báo cáo; mọi giả định và giới hạn được nêu rõ trong kết quả.
Ngưỡng chấm điểm là ngưỡng tham khảo chung, không phải chuẩn của từng ngành.
"""
import math
from typing import Any, Dict, List, Optional

from . import finance
from .analytics import _f
from .loader import LoadError

# t hai phía 80% theo bậc tự do (1..30); trên 30 dùng 1.28
_T80 = {1: 3.078, 2: 1.886, 3: 1.638, 4: 1.533, 5: 1.476, 6: 1.440, 7: 1.415, 8: 1.397, 9: 1.383, 10: 1.372,
        11: 1.363, 12: 1.356, 13: 1.350, 14: 1.345, 15: 1.341, 16: 1.337, 17: 1.333, 18: 1.330, 19: 1.328, 20: 1.325}
FORECAST_KEYS = ("net_revenue", "gross_profit", "net_profit", "total_assets", "equity")


def _t80(df: int) -> float:
    return _T80.get(df, 1.31 if df <= 30 else 1.28)


def linear_forecast(values: List[float], horizon: int) -> Dict[str, Any]:
    """Hồi quy tuyến tính theo thời gian; khoảng dự báo 80% theo công thức khoảng dự đoán của OLS."""
    n = len(values)
    xs = list(range(n))
    mx, my = sum(xs) / n, sum(values) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, values)) / sxx
    icpt = my - slope * mx
    resid = [y - (icpt + slope * x) for x, y in zip(xs, values)]
    df = n - 2
    s = math.sqrt(sum(r * r for r in resid) / df) if df > 0 else 0.0
    t = _t80(df)
    pts = []
    for h in range(1, horizon + 1):
        x0 = n - 1 + h
        yhat = icpt + slope * x0
        half = t * s * math.sqrt(1 + 1 / n + (x0 - mx) ** 2 / sxx)
        pts.append({"step": h, "value": _f(yhat), "low": _f(yhat - half), "high": _f(yhat + half)})
    ss_tot = sum((y - my) ** 2 for y in values)
    r2 = None if ss_tot == 0 else _f(1 - sum(r * r for r in resid) / ss_tot)
    return {"slope": _f(slope), "points": pts, "r2": r2, "sigma": _f(s)}


def reliability(n: int, r2: Optional[float]) -> str:
    if n < 5:
        return "rất thấp"
    if n < 8 or (r2 is not None and r2 < 0.5):
        return "thấp"
    return "trung bình"


def forecast(analysis: Dict[str, Any], horizon: int = 3) -> Dict[str, Any]:
    horizon = max(1, min(4, int(horizon)))
    periods = analysis["periods"]
    labels = [p["label"] for p in periods]
    n = len(labels)
    if n < 3:
        raise LoadError(f"Báo cáo chỉ có {n} kỳ. Cần tối thiểu 3 kỳ liên tiếp để dự báo xu hướng; với 1–2 kỳ, mọi dự báo đều không có cơ sở.")
    if any(p["kind"] in ("start", "end") for p in periods):
        raise LoadError("Báo cáo chỉ có cột đầu kỳ/cuối kỳ nên không xác định được chuỗi kỳ để dự báo.")
    kinds = {p["kind"] for p in periods}
    if len(kinds) > 1:
        raise LoadError("Các kỳ không cùng loại (năm/quý/tháng) nên không dự báo được.")
    series = []
    for g in analysis.get("growth", []):
        if g["key"] not in FORECAST_KEYS:
            continue
        vals = g["values"]
        if any(v is None for v in vals):
            continue
        res = linear_forecast([float(v) for v in vals], horizon)
        series.append({"key": g["key"], "label": g["label"], "history": vals, "slope": res["slope"], "r2": res["r2"], "forecast": res["points"],
                       "reliability": reliability(n, res["r2"])})
    if not series:
        raise LoadError("Không có chỉ tiêu nào đủ số liệu liên tục ở mọi kỳ để dự báo.")
    next_labels = _next_labels(labels, periods[-1]["kind"], horizon)
    return {"horizon": horizon, "periods": labels, "next_periods": next_labels, "unit": analysis.get("unit"), "series": series,
            "method": "Hồi quy tuyến tính theo thời gian (bình phương tối thiểu), khoảng dự báo 80%.",
            "notes": [f"Chuỗi chỉ có {n} kỳ; độ tin cậy dự báo bị giới hạn bởi số kỳ ít. Khoảng dự báo cho biết mức bất định của chính mô hình tuyến tính, không bao gồm cú sốc kinh tế, thay đổi chính sách hay biến động mùa vụ.",
                      "Đây là phép ngoại suy xu hướng quá khứ, không phải cam kết hay kế hoạch kinh doanh."]}


def _next_labels(labels: List[str], kind: str, h: int) -> List[str]:
    """Nhãn kỳ kế tiếp: nếu nhãn là số nguyên (năm) thì cộng dần, ngược lại ghi 'kỳ +1'."""
    last = labels[-1].strip()
    digits = "".join(ch for ch in last if ch.isdigit())
    if kind in ("year", "date") and last.isdigit():
        return [str(int(last) + i) for i in range(1, h + 1)]
    if kind in ("year", "date") and digits and len(digits) == 4:
        return [last.replace(digits, str(int(digits) + i)) for i in range(1, h + 1)]
    return [f"Kỳ +{i}" for i in range(1, h + 1)]


# ====================================================================== điểm sức khỏe
def _lin(x: float, bad: float, good: float) -> float:
    """Ánh xạ tuyến tính x về 0..100; bad -> 0, good -> 100 (bad có thể lớn hơn good)."""
    if bad == good:
        return 50.0
    t = (x - bad) / (good - bad)
    return max(0.0, min(1.0, t)) * 100


# (khóa tỷ số, tên, bad, good, nhóm)
_RULES = [
    ("current_ratio", "Thanh toán hiện hành", 0.5, 1.5, "Thanh khoản"),
    ("quick_ratio", "Thanh toán nhanh", 0.3, 1.0, "Thanh khoản"),
    ("debt_to_equity", "Nợ phải trả / Vốn chủ sở hữu", 3.0, 0.5, "Đòn bẩy"),
    ("interest_coverage", "Khả năng trả lãi vay", 1.0, 5.0, "Đòn bẩy"),
    ("net_margin", "Biên lợi nhuận ròng", 0.0, 10.0, "Sinh lời"),
    ("roe", "ROE", 0.0, 15.0, "Sinh lời"),
    ("roa", "ROA", 0.0, 8.0, "Sinh lời"),
    ("asset_turnover", "Vòng quay tổng tài sản", 0.3, 1.5, "Hiệu quả hoạt động"),
]
_GROUP_W = {"Thanh khoản": 0.25, "Đòn bẩy": 0.25, "Sinh lời": 0.35, "Hiệu quả hoạt động": 0.15}


def health_score(analysis: Dict[str, Any]) -> Dict[str, Any]:
    ratios = {it["key"]: it for g in analysis["ratio_groups"] for it in g["items"] if it.get("available")}
    labels = [p["label"] for p in analysis["periods"]]
    n = len(labels)
    items, by_group = [], {}
    for key, name, bad, good, grp in _RULES:
        it = ratios.get(key)
        v = it["values"][n - 1] if it else None
        if v is None:
            continue
        sc = _lin(v, bad, good)
        items.append({"key": key, "label": name, "group": grp, "value": v, "unit": it["unit"], "score": _f(sc), "bad": bad, "good": good})
        by_group.setdefault(grp, []).append(sc)
    if analysis.get("growth") and n >= 2:
        g = next((x for x in analysis["growth"] if x["key"] == "net_revenue"), None)
        if g and g["yoy_pct"][-1] is not None:
            sc = _lin(g["yoy_pct"][-1], -10.0, 15.0)
            items.append({"key": "revenue_growth", "label": "Tăng trưởng doanh thu", "group": "Tăng trưởng", "value": g["yoy_pct"][-1], "unit": "%", "score": _f(sc), "bad": -10.0, "good": 15.0})
            by_group.setdefault("Tăng trưởng", []).append(sc)
    if not items:
        raise LoadError("Chưa đủ chỉ số để chấm điểm. Hãy kiểm tra ánh xạ khoản mục và chạy lại phân tích tài chính.")
    weights = dict(_GROUP_W, **{"Tăng trưởng": 0.15})
    groups = []
    tw = 0.0
    acc = 0.0
    for grp, scs in by_group.items():
        avg = sum(scs) / len(scs)
        w = weights.get(grp, 0.1)
        groups.append({"group": grp, "score": _f(avg), "weight": w, "n_items": len(scs)})
        acc += avg * w
        tw += w
    total = acc / tw
    grade = "Tốt" if total >= 75 else "Khá" if total >= 55 else "Trung bình" if total >= 40 else "Yếu"
    return {"period": labels[-1], "score": _f(total), "grade": grade, "groups": groups, "items": items,
            "notes": ["Điểm là tổng hợp có trọng số của các chỉ số kỳ gần nhất, mỗi chỉ số quy về thang 0–100 giữa hai ngưỡng tham khảo (kém → tốt).",
                      "Ngưỡng là ngưỡng tham khảo chung, không phải chuẩn của từng ngành; điểm chỉ dùng để nhìn nhanh, không thay thế đánh giá chuyên môn.",
                      "Nhóm nào thiếu số liệu thì bị bỏ ra và trọng số được chia lại cho các nhóm còn lại."]}


# ====================================================================== mô phỏng
SCENARIO_FIELDS = ("revenue_pct", "cogs_pct", "opex_pct", "fin_expense_pct")


def scenario(parsed: Dict[str, Any], overrides: Dict[str, Any], adj: Dict[str, Any]) -> Dict[str, Any]:
    """Mô phỏng kỳ gần nhất khi doanh thu/giá vốn/chi phí hoạt động/chi phí tài chính đổi theo tỷ lệ phần trăm."""
    mapping = finance.apply_overrides(parsed, finance.auto_mapping(parsed), overrides or {})
    periods, M, notes = finance.build_matrix(parsed, mapping)
    need = ("net_revenue", "cogs", "net_profit")
    miss = [finance.STD_BY_KEY[k][2] for k in need if k not in M]
    if miss:
        raise LoadError("Thiếu khoản mục để mô phỏng: " + ", ".join(miss) + ".")
    pid = periods[-1]["pid"]
    g = lambda k: (M.get(k) or {}).get(pid)
    rev, cogs, npf = g("net_revenue"), g("cogs"), g("net_profit")
    if rev is None or cogs is None or npf is None:
        raise LoadError("Kỳ gần nhất thiếu doanh thu, giá vốn hoặc lợi nhuận sau thuế.")
    vals = {}
    for f in SCENARIO_FIELDS:
        try:
            v = float(adj.get(f, 0) or 0)
        except (TypeError, ValueError):
            raise LoadError("Tỷ lệ thay đổi phải là số.")
        if not -90 <= v <= 300:
            raise LoadError("Tỷ lệ thay đổi nằm ngoài khoảng cho phép (từ −90% đến +300%).")
        vals[f] = v
    sell, adm, fin_e = g("selling_exp") or 0.0, g("admin_exp") or 0.0, g("fin_expense") or 0.0
    # các khoản còn lại (thu nhập tài chính, thu nhập/chi phí khác...) giữ nguyên: lấy phần dư làm "khoản khác"
    base_pretax_calc = rev - cogs - sell - adm - fin_e
    pbt = g("profit_before_tax")
    other = (pbt - base_pretax_calc) if pbt is not None else 0.0
    tax_rate = None
    if pbt:
        tax_rate = (pbt - npf) / pbt if pbt > 0 else 0.0
    if tax_rate is None or tax_rate < 0 or tax_rate > 0.5:
        tax_rate = 0.2
        notes.append("Không suy ra được thuế suất hợp lý từ báo cáo; dùng 20% làm giả định.")
    k = lambda f: 1 + vals[f] / 100
    rev2, cogs2 = rev * k("revenue_pct"), cogs * k("cogs_pct")
    sell2, adm2 = sell * k("opex_pct"), adm * k("opex_pct")
    fin2 = fin_e * k("fin_expense_pct")
    gp2 = rev2 - cogs2
    pbt2 = gp2 - sell2 - adm2 - fin2 + other
    np2 = pbt2 * (1 - tax_rate) if pbt2 > 0 else pbt2
    eq, ta = g("equity"), g("total_assets")

    def row(key, label, a, b, unit="đ"):
        return {"key": key, "label": label, "base": None if a is None else _f(a), "scenario": None if b is None else _f(b), "unit": unit,
                "change": None if a is None or b is None else _f(b - a), "change_pct": None if not a or b is None else _f((b / a - 1) * 100)}

    pct = lambda a, b: None if not b else a / b * 100
    rows = [row("net_revenue", "Doanh thu thuần", rev, rev2), row("gross_profit", "Lợi nhuận gộp", rev - cogs, gp2),
            row("profit_before_tax", "Lợi nhuận trước thuế", base_pretax_calc + other, pbt2), row("net_profit", "Lợi nhuận sau thuế (mô phỏng)", npf, np2),
            row("gross_margin", "Biên lợi nhuận gộp (%)", pct(rev - cogs, rev), pct(gp2, rev2), "%"),
            row("net_margin", "Biên lợi nhuận ròng (%)", pct(npf, rev), pct(np2, rev2), "%")]
    if eq:
        rows.append(row("roe_end", "ROE theo vốn cuối kỳ (%)", pct(npf, eq), pct(np2, eq), "%"))
    if ta:
        rows.append(row("roa_end", "ROA theo tổng tài sản cuối kỳ (%)", pct(npf, ta), pct(np2, ta), "%"))
    return {"period": periods[-1]["label"], "adjustments": vals, "rows": rows, "tax_rate_pct": _f(tax_rate * 100), "unit": next(iter({s["unit"] for s in parsed["statements"] if s["unit"]}), None),
            "notes": notes + ["Mô phỏng chỉ tính lại báo cáo kết quả kinh doanh của kỳ gần nhất; chi phí bán hàng và quản lý thay đổi cùng một tỷ lệ; các khoản còn lại (thu nhập tài chính, thu nhập/chi phí khác) giữ nguyên.",
                              "Thuế suất hiệu dụng suy ra từ báo cáo gốc. Bảng cân đối kế toán giữ nguyên nên ROE và ROA ở đây tính theo số cuối kỳ, không phải số bình quân; chỉ dùng so sánh giữa gốc và mô phỏng.",
                              "Đây là công cụ thử nhạy cảm, không phải dự báo."]}
