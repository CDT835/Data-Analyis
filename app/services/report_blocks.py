"""Dựng báo cáo thành danh sách "khối" dùng chung cho xem trước, Word, PDF và Excel.

Các loại khối:
  title    {text, subtitle}
  heading  {level 1|2, text, num}        (num do hệ thống đánh số tự động)
  para     {text}
  bullets  {items}
  table    {headers, rows, caption?, raw?, nf?, num_cols?}
  chart    {kind: line|bar|stacked, title, labels, series:[{name, values}], unit}
  kpis     {items:[{label, value, delta}]}
  callout  {kind: info|warn|ok, text}
Mọi con số đều lấy từ kết quả phân tích đã tính; không có con số nào do AI hoặc mẫu tự thêm.
"""
import datetime as _dt
import re
from typing import Any, Dict, List, Optional, Tuple

from . import ai as aimod
from .ai import vn, vnum, vpct
from .loader import LoadError
from .report_catalog import NEEDS_LABEL, ORDER, SECTIONS, TEMPLATES, available_statements

MAX_CHARTS = 10
AI_KEYS = ("highlights", "trends", "risks", "recommendations", "next_analyses")
AI_TITLES = {"highlights": "Điểm nổi bật", "trends": "Xu hướng tăng giảm", "risks": "Rủi ro và điểm cần lưu ý",
             "recommendations": "Khuyến nghị có căn cứ", "next_analyses": "Phân tích nên làm tiếp"}
SEVERITY = {"high": "Nghiêm trọng", "warn": "Cảnh báo", "info": "Lưu ý"}


class Skip(Exception):
    """Phần này không dựng được; mang theo lý do hiển thị cho người dùng."""


def _fmt(unit: str, v: Optional[float]) -> str:
    if v is None:
        return "—"
    if unit == "%":
        return vpct(v)
    return vn(v, 0 if unit == "ngày" else 2)


def _nf(unit: str) -> str:
    return {"%": '0.0"%"', "ngày": "0", "money": "#,##0"}.get(unit, "0.00")


def _clean(text: Any, limit: int) -> str:
    s = "".join(ch for ch in str(text or "") if ch >= " " or ch in "\n\t").strip()
    return s[:limit]


class _Ctx:
    def __init__(self, analysis, checks, mapping, std_items, statements, ai, meta):
        self.a = analysis
        self.checks = checks or {}
        self.mapping = mapping or {}
        self.std = std_items or []
        self.statements = statements or []
        self.ai = ai
        self.meta = meta
        self.labels = [p["label"] for p in analysis["periods"]]
        self.unit = analysis.get("unit")
        self.money = f"{self.unit}" if self.unit else "đơn vị báo cáo"
        self.have = available_statements(mapping, statements)

    def group(self, name: str) -> Dict[str, Any]:
        for g in self.a.get("ratio_groups", []):
            if g["name"] == name:
                return g
        raise Skip("Không có nhóm chỉ số này trong kết quả phân tích.")

    def ratio_table(self, name: str, caption: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        g = self.group(name)
        ok = [i for i in g["items"] if i.get("available")]
        bad = [i for i in g["items"] if not i.get("available")]
        if not ok:
            raise Skip("Chưa tính được chỉ số nào trong nhóm này" + (": " + "; ".join(f"{i['label']} ({i.get('reason') or 'thiếu số liệu'})" for i in bad) if bad else "") + ".")
        rows, raw, nf = [], [], []
        for it in ok:
            u = it["unit"]
            rows.append([f"{it['label']} ({u})" if u not in ("%",) else f"{it['label']} (%)"] + [_fmt(u, v) for v in it["values"]])
            raw.append([None] + list(it["values"]))
            nf.append(_nf(u))
        blocks: List[Dict[str, Any]] = [{"t": "table", "caption": caption, "headers": ["Chỉ số"] + self.labels, "rows": rows, "raw": raw, "nf": nf}]
        blocks.append({"t": "bullets", "items": [f"{i['label']} = {i['formula']}" for i in ok]})
        if bad:
            blocks.append({"t": "callout", "kind": "info", "text": "Chưa tính được: " + "; ".join(f"{i['label']} ({i.get('reason') or 'thiếu số liệu'})" for i in bad) + "."})
        return ok, blocks  # type: ignore[return-value]


def _line_chart(title, labels, items, unit):
    return {"t": "chart", "kind": "line", "title": title, "labels": labels, "unit": unit,
            "series": [{"name": i["label"], "values": list(i["values"])} for i in items]}


# ====================================================================== các phần
def s_info(c: _Ctx, tpl: Dict[str, Any]):
    m = c.meta
    rows = [["Tên báo cáo", m["title"]], ["Đơn vị lập báo cáo", m["org"] or "—"], ["Mẫu báo cáo", tpl["name"]], ["Ngày lập", m["date"]],
            ["Đơn vị tính", c.unit or "Báo cáo không ghi đơn vị tính"], ["Số kỳ phân tích", str(len(c.labels))], ["Các kỳ", ", ".join(c.labels)]]
    return [{"t": "table", "headers": ["Mục", "Nội dung"], "rows": rows}]


def _count(st: Dict[str, Any], key: str, alt: str) -> Any:
    if isinstance(st.get(key), int):
        return st[key]
    v = st.get(alt)
    return len(v) if isinstance(v, list) else ""


def s_scope(c: _Ctx, tpl):
    rows = []
    for st in c.statements:
        if isinstance(st, dict):
            rows.append([_clean(st.get("type_label") or st.get("sheet"), 80), _clean(st.get("sheet"), 80), _clean(st.get("unit") or "—", 40), str(_count(st, "n_periods", "periods")), str(_count(st, "n_rows", "rows"))])
    out: List[Dict[str, Any]] = [{"t": "para", "text": f"Báo cáo gồm {len(c.labels)} kỳ: {', '.join(c.labels)}. Mọi con số trong báo cáo này được hệ thống tính từ số liệu gốc; trường hợp thiếu số liệu thì ghi rõ và không ước đoán."}]
    if rows:
        out.append({"t": "table", "caption": "Các báo cáo đã đọc từ tệp dữ liệu", "headers": ["Báo cáo", "Sheet", "Đơn vị tính", "Số kỳ", "Số dòng"], "rows": rows})
    return out


def s_data_checks(c: _Ctx, tpl):
    ck = c.checks
    if not ck or "n_checked" not in ck:
        raise Skip("Chưa có kết quả kiểm tra số liệu.")
    n, f, root = ck.get("n_checked", 0), ck.get("n_failed", 0), ck.get("n_root_failed", 0)
    out: List[Dict[str, Any]] = []
    if f:
        out.append({"t": "para", "text": f"Đã kiểm tra {n} phép cộng và cân đối; {f} phép bị lệch, trong đó {root} lỗi gốc và {f - root} hệ quả của các lỗi gốc."})
        out.append({"t": "callout", "kind": "warn", "text": "Số liệu có sai lệch. Các chỉ số liên quan có thể bị ảnh hưởng cho tới khi số liệu gốc được sửa; hãy kiểm tra lại báo cáo gốc."})
        rows = [[x.get("title", ""), str(x.get("period", "")), vnum(x.get("diff")), "Hệ quả" if x.get("cascade") else "Lỗi gốc"] for x in ck.get("failed", [])[:40]]
        out.append({"t": "table", "caption": "Các phép kiểm tra bị lệch", "headers": ["Phép kiểm tra", "Kỳ", f"Chênh lệch ({c.money})", "Loại"], "rows": rows, "num_cols": [2]})
    else:
        out.append({"t": "para", "text": f"Đã kiểm tra {n} phép cộng và cân đối; tất cả đều khớp."})
        out.append({"t": "callout", "kind": "ok", "text": "Không phát hiện sai lệch trong các phép kiểm tra."})
    if ck.get("not_checked"):
        out.append({"t": "para", "text": "Chưa kiểm tra được:"})
        out.append({"t": "bullets", "items": [_clean(x, 300) for x in ck["not_checked"][:15]]})
    if ck.get("data_issues"):
        out.append({"t": "para", "text": "Vấn đề về dữ liệu đầu vào:"})
        out.append({"t": "bullets", "items": [_clean(x.get("message", "") if isinstance(x, dict) else x, 400) for x in ck["data_issues"][:15]]})
    return out


def s_kpis(c: _Ctx, tpl):
    latest = c.a.get("latest") or {}
    if not latest:
        raise Skip("Chưa tính được chỉ tiêu chính.")
    items = []
    for k, it in latest.items():
        if "unit" in it:
            delta = f"kỳ trước: {_fmt(it['unit'], it.get('prev'))}" if it.get("prev") is not None else ""
            val = _fmt(it["unit"], it["value"]) + ("" if it["unit"] == "%" else f" {it['unit']}")
        else:
            y = it.get("yoy_pct")
            delta = (f"{'+' if y >= 0 else ''}{vn(y, 1)}% so với kỳ trước" if y is not None else "")
            val = f"{vnum(it['value'])} {c.unit or ''}".strip()
        items.append({"label": it["label"], "value": val, "delta": delta})
    return [{"t": "para", "text": f"Các chỉ tiêu chính của kỳ {c.labels[-1]}:"}, {"t": "kpis", "items": items}]


def _growth(c: _Ctx, key: str):
    for g in c.a.get("growth", []):
        if g["key"] == key:
            return g
    return None


def s_revenue_profit_chart(c: _Ctx, tpl):
    series = []
    for key in ("net_revenue", "net_profit"):
        g = _growth(c, key)
        if g:
            series.append({"name": g["label"], "values": list(g["values"])})
    if not series:
        raise Skip("Không có doanh thu thuần hoặc lợi nhuận sau thuế trong dữ liệu.")
    return [{"t": "chart", "kind": "bar", "title": f"Doanh thu thuần và lợi nhuận sau thuế ({c.money})", "labels": c.labels, "series": series, "unit": c.unit or ""}]


def s_liquidity(c: _Ctx, tpl):
    ok, blocks = c.ratio_table("Khả năng thanh toán", "Các chỉ số thanh toán")
    return blocks + [_line_chart("Chỉ số thanh toán qua các kỳ (lần)", c.labels, ok, "lần")]


def s_leverage(c: _Ctx, tpl):
    ok, blocks = c.ratio_table("Cơ cấu vốn và đòn bẩy", "Các chỉ số cơ cấu vốn và đòn bẩy")
    ch = [i for i in ok if i["key"] in ("debt_to_assets", "debt_to_equity")]
    return blocks + ([_line_chart("Nợ trên tài sản và nợ trên vốn chủ sở hữu (lần)", c.labels, ch, "lần")] if ch else [])


def s_profitability(c: _Ctx, tpl):
    ok, blocks = c.ratio_table("Khả năng sinh lời", "Các chỉ số sinh lời")
    ch = [i for i in ok if i["unit"] == "%" and i["key"] in ("gross_margin", "net_margin", "roa", "roe")]
    return blocks + ([_line_chart("Biên lợi nhuận, ROA và ROE (%)", c.labels, ch, "%")] if ch else [])


def s_efficiency(c: _Ctx, tpl):
    return c.ratio_table("Hiệu quả hoạt động", "Các chỉ số hiệu quả hoạt động")[1]


def s_dupont(c: _Ctx, tpl):
    dp = c.a.get("dupont")
    if not dp or not dp.get("rows"):
        raise Skip("Chưa đủ số liệu để phân tích DuPont.")
    rows = [[r["period"], vpct(r["net_margin_pct"]), vn(r["asset_turnover"], 2), vn(r["equity_multiplier"], 2), vpct(r["roe_pct"])] for r in dp["rows"]]
    return [{"t": "table", "caption": "Phân tích DuPont", "headers": ["Kỳ", "Biên lợi nhuận ròng (%)", "Vòng quay tổng tài sản (vòng)", "Hệ số nhân vốn (lần)", "ROE (%)"], "rows": rows},
            {"t": "para", "text": _clean(dp.get("note"), 400)}]


def s_growth(c: _Ctx, tpl):
    gs = c.a.get("growth") or []
    if not gs:
        raise Skip("Chưa có dữ liệu tăng trưởng.")
    rows = [[f"{g['label']} ({c.money})"] + [vnum(v) for v in g["values"]] for g in gs]
    raw = [[None] + list(g["values"]) for g in gs]
    yoy = [[g["label"]] + ["—"] + [vpct(v) for v in g["yoy_pct"][1:]] + [vpct(g["cagr_pct"]) if g.get("cagr_pct") is not None else "—"] for g in gs]
    return [{"t": "table", "caption": "Giá trị các chỉ tiêu chính theo kỳ", "headers": ["Chỉ tiêu"] + c.labels, "rows": rows, "raw": raw, "nf": ["#,##0"] * len(rows)},
            {"t": "table", "caption": "Tăng trưởng so với kỳ trước (%) và tăng trưởng kép", "headers": ["Chỉ tiêu"] + c.labels + ["Tăng trưởng kép"], "rows": yoy}]


def s_vertical(c: _Ctx, tpl):
    vt = c.a.get("vertical") or {}
    out: List[Dict[str, Any]] = []
    names = {"assets": "Cơ cấu tài sản (% tổng tài sản)", "capital": "Cơ cấu nguồn vốn (% tổng nguồn vốn)", "income": "Cơ cấu kết quả kinh doanh (% doanh thu thuần)"}
    for key in ("assets", "capital", "income"):
        items = [i for i in (vt.get(key) or {}).get("items", []) if any(p is not None for p in i["pct"])]
        if not items:
            continue
        out.append({"t": "table", "caption": names[key], "headers": ["Khoản mục"] + c.labels, "rows": [[i["label"]] + [vpct(p) for p in i["pct"]] for i in items],
                    "raw": [[None] + list(i["pct"]) for i in items], "nf": ['0.0"%"'] * len(items)})
        if key == "capital":
            parts = [i for i in items if i["key"] != "total_liabilities"]  # bỏ dòng tổng nợ để các cột chồng không bị tính hai lần
            if parts:
                out.append({"t": "chart", "kind": "stacked", "title": "Cơ cấu nguồn vốn qua các kỳ (%)", "labels": c.labels, "unit": "%",
                            "series": [{"name": i["label"], "values": [p or 0.0 for p in i["pct"]]} for i in parts]})
    if not out:
        raise Skip("Chưa đủ số liệu để phân tích cơ cấu.")
    return out


def s_alerts(c: _Ctx, tpl):
    al = c.a.get("alerts") or []
    if not al:
        return [{"t": "callout", "kind": "ok", "text": "Hệ thống không phát hiện cảnh báo nào theo các ngưỡng tham khảo đã dùng."}]
    return [{"t": "para", "text": "Các cảnh báo dưới đây dựa trên ngưỡng tham khảo; mức phù hợp còn phụ thuộc ngành và bối cảnh của đơn vị."},
            {"t": "bullets", "items": [f"{SEVERITY.get(a.get('severity'), 'Lưu ý')} – kỳ {a['period']} – {a['title']}: {a['message']}" for a in al[:40]]}]


def s_mapping(c: _Ctx, tpl):
    if not c.mapping and not c.std:
        raise Skip("Chưa có thông tin ánh xạ khoản mục.")
    std = c.std or [{"key": k, "label": k} for k in c.mapping]
    rows = []
    for it in std:
        m = c.mapping.get(it["key"])
        rows.append([it.get("label", it["key"]), (m or {}).get("code") or "—", _clean((m or {}).get("name"), 120) or "Chưa chọn", (m or {}).get("source") or "—"])
    return [{"t": "table", "caption": "Khoản mục chuẩn và dòng được lấy từ báo cáo", "headers": ["Khoản mục chuẩn", "Mã số", "Dòng trong báo cáo", "Nhận diện theo"], "rows": rows}]


# ---------------------------------------------------------------- phần AI
def _ai_items(c: _Ctx) -> Dict[str, Any]:
    ai = c.ai
    if not ai or not isinstance(ai, dict):
        raise Skip("Chưa có nhận xét AI cho phân tích này. Hãy tạo ở trang AI nhận xét và gợi ý.")
    edited = ai.get("edited") if isinstance(ai.get("edited"), dict) else None
    orig = ai.get("commentary") if isinstance(ai.get("commentary"), dict) else None
    src = edited or orig
    if not src or not (src.get("summary") or {}).get("text"):
        raise Skip("Chưa có nhận xét AI cho phân tích này. Hãy tạo ở trang AI nhận xét và gợi ý.")
    allowed = aimod.allowed_numbers(ai.get("facts") or []) if ai.get("facts") else None

    def one(raw: Dict[str, Any]) -> Dict[str, Any]:
        text = _clean(raw.get("text"), 700)
        if allowed is not None and (edited is not None):
            bad = aimod.verify_text(text, allowed)  # bản đã sửa được đối chiếu lại
        else:
            bad = list(raw.get("unverified_numbers") or [])
        refs = [r for r in (raw.get("refs") or []) if isinstance(r, str) and len(r) <= 5]
        return {"text": text + (f" (Dẫn chứng: {', '.join(refs)})" if refs else "") + (" (có số liệu chưa đối chiếu được với số liệu đã tính: " + ", ".join(bad) + ")" if bad else ""), "bad": bool(bad)}

    out = {"summary": one(src["summary"]), "edited": edited is not None, "model": ai.get("model"), "stale": bool(ai.get("stale")),
           "disclaimer": ai.get("disclaimer") or "", "n_bad": 0}
    for k in AI_KEYS:
        out[k] = [one(x) for x in (src.get(k) or []) if isinstance(x, dict) and x.get("text")]
    out["n_bad"] = sum(1 for k in ("summary",) + AI_KEYS for x in ([out[k]] if k == "summary" else out[k]) if x["bad"])
    return out


def _ai_head(a: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if a["stale"]:
        out.append({"t": "callout", "kind": "warn", "text": "Nhận xét AI được tạo từ một phiên bản phân tích cũ hơn; hãy tạo lại nhận xét nếu số liệu đã thay đổi."})
    if a["edited"]:
        out.append({"t": "callout", "kind": "info", "text": "Nội dung dưới đây là bản đã được người dùng chỉnh sửa."})
    if a["n_bad"]:
        out.append({"t": "callout", "kind": "warn", "text": f"Có {a['n_bad']} nhận định chứa số liệu chưa đối chiếu được với số liệu đã tính; các nhận định này được ghi chú ngay trong nội dung."})
    return out


def s_ai_summary(c: _Ctx, tpl):
    a = _ai_items(c)
    return _ai_head(a) + [{"t": "para", "text": a["summary"]["text"]}]


def s_ai_detail(c: _Ctx, tpl):
    a = _ai_items(c)
    out: List[Dict[str, Any]] = []
    for k in ("highlights", "trends", "risks"):
        if a[k]:
            out += [{"t": "heading", "level": 2, "text": AI_TITLES[k]}, {"t": "bullets", "items": [x["text"] for x in a[k]]}]
    if not out:
        raise Skip("Nhận xét AI không có nội dung ở các mục này.")
    return out


def s_ai_reco(c: _Ctx, tpl):
    a = _ai_items(c)
    out: List[Dict[str, Any]] = []
    for k in ("recommendations", "next_analyses"):
        if a[k]:
            out += [{"t": "heading", "level": 2, "text": AI_TITLES[k]}, {"t": "bullets", "items": [x["text"] for x in a[k]]}]
    if not out:
        raise Skip("Nhận xét AI không có nội dung ở các mục này.")
    return out


def s_notes(c: _Ctx, tpl):
    items = [_clean(n, 500) for n in (c.a.get("notes") or [])]
    items.append("Báo cáo này do hệ thống tạo tự động từ số liệu đã nhập; các chỉ số và cảnh báo mang tính tham khảo, cần được người có chuyên môn đọc lại trước khi sử dụng chính thức.")
    if c.ai and isinstance(c.ai, dict) and (c.ai.get("commentary") or c.ai.get("edited")):
        items.append(_clean(c.ai.get("disclaimer"), 500) or "Nhận xét AI do mô hình ngôn ngữ tạo từ các số liệu đã tính.")
    return [{"t": "bullets", "items": items}]


BUILDERS = {"info": s_info, "scope": s_scope, "data_checks": s_data_checks, "kpis": s_kpis, "revenue_profit_chart": s_revenue_profit_chart,
            "liquidity": s_liquidity, "leverage": s_leverage, "profitability": s_profitability, "efficiency": s_efficiency, "dupont": s_dupont,
            "growth": s_growth, "vertical": s_vertical, "alerts": s_alerts, "mapping": s_mapping, "ai_summary": s_ai_summary,
            "ai_detail": s_ai_detail, "ai_reco": s_ai_reco, "notes": s_notes}
assert set(BUILDERS) == set(SECTIONS)


# ====================================================================== ghép báo cáo
def today_vn() -> str:
    d = _dt.datetime.now(_dt.timezone(_dt.timedelta(hours=7)))
    return d.strftime("%d/%m/%Y")


_CAP_RE = re.compile(r"^\s*(Bảng|Hình)\s+\d+\.\s*")


def number_blocks(blocks: List[Dict[str, Any]]) -> None:
    """Đánh số mục (1, 1.1), bảng ("Bảng 1.") và hình ("Hình 1.") theo thứ tự xuất hiện. Chạy lại nhiều lần vẫn ra cùng kết quả."""
    h1 = h2 = nt = nf = 0
    for b in blocks:
        t = b.get("t")
        if t == "heading":
            if b.get("level") == 2:
                h2 += 1
                b["num"] = f"{h1}.{h2}" if h1 else str(h2)
            else:
                h1 += 1
                h2 = 0
                b["num"] = str(h1)
        elif t == "table" and b.get("caption"):
            nt += 1
            b["caption"] = f"Bảng {nt}. " + _CAP_RE.sub("", b["caption"])
        elif t == "chart":
            nf += 1
            b["fig"] = f"Hình {nf}. " + _CAP_RE.sub("", b.get("title", ""))


def build_report(template: str, sections: Optional[List[str]], title: str, org: str, analysis: Dict[str, Any], checks: Optional[Dict[str, Any]] = None,
                 mapping: Optional[Dict[str, Any]] = None, std_items: Optional[List[Dict[str, Any]]] = None, statements: Optional[List[Dict[str, Any]]] = None,
                 ai: Optional[Dict[str, Any]] = None, date: Optional[str] = None, fragment: bool = False) -> Dict[str, Any]:
    """fragment=True: chỉ trả các khối của những phần đã chọn (không có tiêu đề báo cáo, không có mục "bỏ qua",
    không đánh số) để trình soạn thủ công chèn vào tài liệu; việc đánh số do number_blocks làm khi xuất."""
    if template not in TEMPLATES:
        raise LoadError("Mẫu báo cáo không tồn tại.")
    tpl = TEMPLATES[template]
    have = available_statements(mapping, statements)
    if tpl["needs"] and not have.get(tpl["needs"]):
        raise LoadError(f"Mẫu này cần {NEEDS_LABEL[tpl['needs']]}, nhưng dữ liệu chưa có báo cáo đó. Hãy chọn mẫu khác.")
    if not analysis.get("periods"):
        raise LoadError("Chưa có kết quả phân tích tài chính. Hãy chạy phân tích tài chính trước.")
    if sections is None:
        chosen = [s for s in tpl["sections"] if s not in tpl["default_off"]]
    else:
        bad = [s for s in sections if s not in tpl["sections"]]
        if bad:
            raise LoadError("Có phần không thuộc mẫu đã chọn.")
        chosen = [s for s in tpl["sections"] if s in set(sections)]
    if not chosen:
        raise LoadError("Hãy chọn ít nhất một phần của báo cáo.")
    title = _clean(title, 200) or tpl["name"]
    meta = {"title": title, "org": _clean(org, 200), "date": _clean(date, 20) or today_vn()}
    c = _Ctx(analysis, checks, mapping, std_items, statements, ai, meta)

    blocks: List[Dict[str, Any]] = [] if fragment else [{"t": "title", "text": title, "subtitle": (meta["org"] + " – " if meta["org"] else "") + tpl["name"]}]
    included, skipped = [], []
    n_charts, h1 = 0, 0
    for slug in chosen:
        need = SECTIONS[slug]["needs"]
        try:
            if need and not have.get(need):
                raise Skip(f"Cần {NEEDS_LABEL[need]}, dữ liệu chưa có báo cáo này.")
            body = BUILDERS[slug](c, tpl)
        except Skip as e:
            skipped.append({"section": slug, "title": SECTIONS[slug]["title"], "reason": str(e)})
            continue
        kept: List[Dict[str, Any]] = []
        for b in body:
            if b["t"] == "chart":
                if n_charts >= MAX_CHARTS:
                    continue
                n_charts += 1
            kept.append(b)
        h1 += 1
        blocks.append({"t": "heading", "level": 1, "text": SECTIONS[slug]["title"], "num": str(h1)})
        h2 = 0
        for b in kept:
            if b["t"] == "heading":
                h2 += 1
                b["num"] = f"{h1}.{h2}"
            blocks.append(b)
        included.append(slug)
    if skipped and not fragment:
        blocks.append({"t": "heading", "level": 1, "text": "Các phần đã bỏ qua", "num": str(h1 + 1)})
        blocks.append({"t": "para", "text": "Các phần sau được chọn nhưng không đưa vào báo cáo vì thiếu dữ liệu hoặc điều kiện:"})
        blocks.append({"t": "bullets", "items": [f"{s['title']}: {s['reason']}" for s in skipped]})
    if fragment:
        for b in blocks:
            b.pop("num", None)
    else:
        number_blocks(blocks)
    return {"template": template, "template_name": tpl["name"], "title": title, "org": meta["org"], "date": meta["date"], "blocks": blocks,
            "included": included, "skipped": skipped, "n_charts": n_charts}
