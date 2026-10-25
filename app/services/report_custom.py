"""Báo cáo do người dùng tự soạn: kiểm tra, làm sạch và chuẩn hóa danh sách khối trước khi xuất Word/PDF/Excel.

Trình soạn trên trình duyệt gửi lên danh sách khối (cùng định dạng với báo cáo dựng tự động). Dịch vụ KHÔNG tin dữ liệu này:
mọi chuỗi bị cắt độ dài và bỏ ký tự điều khiển, mọi kiểu khối lạ bị từ chối, số lượng khối, hàng, cột, biểu đồ đều có giới hạn.
Số liệu trong bảng và biểu đồ do người dùng chèn từ kết quả phân tích hoặc tự nhập; hệ thống không tự sinh thêm con số nào.
"""
import math
import re
from typing import Any, Dict, List, Optional

from .loader import LoadError
from .report_blocks import MAX_CHARTS, _clean, number_blocks, today_vn

MAX_BLOCKS = 400
MAX_TEXT = 8000
MAX_ITEMS = 80
MAX_ROWS = 100
MAX_COLS = 12
MAX_LABELS = 40
MAX_SERIES = 8
MAX_TOTAL_CHARS = 400_000
KINDS = ("line", "bar", "stacked")
CALLOUTS = ("info", "warn", "ok")


def _num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _text(v: Any, limit: int = MAX_TEXT) -> str:
    return _clean(v, limit)


_NUMLIKE = re.compile(r"^[+\-−–]?\(?\d[\d.,]*\)?\s*(%|lần|vòng|ngày|đồng|triệu đồng|nghìn đồng|tỷ đồng|VND|đ)?$")


def _numeric_cols(rows: List[List[str]], n: int) -> List[int]:
    """Cột nào toàn số (bỏ qua ô trống và dấu gạch) thì căn phải; cột chữ căn trái."""
    out = []
    for j in range(n):
        cells = [r[j].strip() for r in rows if j < len(r) and r[j].strip() not in ("", "—", "-")]
        if cells and all(_NUMLIKE.match(c) for c in cells):
            out.append(j)
    return out


def _table(b: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    headers = b.get("headers")
    rows = b.get("rows")
    if not isinstance(headers, list) or not headers or not isinstance(rows, list):
        return None
    if len(headers) > MAX_COLS or len(rows) > MAX_ROWS:
        raise LoadError(f"Bảng quá lớn (tối đa {MAX_ROWS} hàng và {MAX_COLS} cột).")
    n = len(headers)
    out_rows = []
    for r in rows:
        r = r if isinstance(r, list) else []
        out_rows.append([_text(r[j], 400) if j < len(r) else "" for j in range(n)])
    out: Dict[str, Any] = {"t": "table", "headers": [_text(h, 200) for h in headers], "rows": out_rows, "caption": _text(b.get("caption"), 300)}
    raw, nf = b.get("raw"), b.get("nf")
    if isinstance(raw, list) and len(raw) == len(rows) and all(isinstance(r, list) and len(r) == n for r in raw) \
            and all(v is None or _num(v) for r in raw for v in r):
        out["raw"] = raw
        if isinstance(nf, list) and len(nf) == len(rows) and all(isinstance(x, str) and len(x) < 40 for x in nf):
            out["nf"] = nf
    nc = b.get("num_cols")
    if isinstance(nc, list) and all(isinstance(i, int) and not isinstance(i, bool) and 0 <= i < n for i in nc):
        out["num_cols"] = nc
    else:
        out["num_cols"] = _numeric_cols(out_rows, n)
    return out


def _chart(b: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    labels, series = b.get("labels"), b.get("series")
    if b.get("kind") not in KINDS or not isinstance(labels, list) or not labels or not isinstance(series, list) or not series:
        return None
    if len(labels) > MAX_LABELS or len(series) > MAX_SERIES:
        raise LoadError("Biểu đồ có quá nhiều điểm hoặc quá nhiều chuỗi số liệu.")
    n = len(labels)
    out_series = []
    for s in series:
        if not isinstance(s, dict) or not isinstance(s.get("values"), list):
            return None
        vals = [v if _num(v) else None for v in s["values"][:n]]
        vals += [None] * (n - len(vals))
        out_series.append({"name": _text(s.get("name"), 100), "values": vals})
    return {"t": "chart", "kind": b["kind"], "title": _text(b.get("title"), 200) or "Biểu đồ", "labels": [_text(x, 40) for x in labels],
            "series": out_series, "unit": _text(b.get("unit"), 40)}


def normalize_document(title: str, org: str, date: Optional[str], blocks: List[Any]) -> Dict[str, Any]:
    if not isinstance(blocks, list) or len(blocks) > MAX_BLOCKS:
        raise LoadError(f"Báo cáo có quá nhiều mục (tối đa {MAX_BLOCKS}).")
    out: List[Dict[str, Any]] = []
    total = 0
    for b in blocks:
        if not isinstance(b, dict):
            continue
        t = b.get("t")
        if t == "title":
            continue  # tên báo cáo lấy từ ô nhập, không lấy từ khối
        if t == "heading":
            txt = _text(b.get("text"), 300).replace("\n", " ")
            if txt:
                out.append({"t": "heading", "level": 2 if b.get("level") == 2 else 1, "text": txt})
        elif t == "para":
            for line in _text(b.get("text")).split("\n"):
                if line.strip():
                    out.append({"t": "para", "text": line.strip()})
        elif t == "bullets":
            items = b.get("items")
            if isinstance(items, list):
                clean = [_text(i, 600).replace("\n", " ") for i in items[:MAX_ITEMS]]
                clean = [i for i in clean if i.strip()]
                if clean:
                    out.append({"t": "bullets", "items": clean})
        elif t == "callout":
            txt = _text(b.get("text"), 2000).replace("\n", " ")
            if txt:
                out.append({"t": "callout", "kind": b.get("kind") if b.get("kind") in CALLOUTS else "info", "text": txt})
        elif t == "kpis" and isinstance(b.get("items"), list):
            rows = [[_text(k.get("label"), 200), _text(k.get("value"), 100), _text(k.get("delta"), 200)] for k in b["items"][:MAX_ROWS] if isinstance(k, dict)]
            out.append({"t": "table", "headers": ["Chỉ tiêu", "Giá trị", "So sánh"], "rows": rows, "caption": "", "num_cols": [1]})
        elif t == "table":
            tb = _table(b)
            if tb:
                out.append(tb)
        elif t == "chart":
            ch = _chart(b)
            if ch:
                out.append(ch)
        else:
            raise LoadError("Báo cáo có loại nội dung không được hỗ trợ.")
    if not out:
        raise LoadError("Báo cáo chưa có nội dung. Hãy thêm ít nhất một mục.")
    if sum(1 for b in out if b["t"] == "chart") > MAX_CHARTS:
        raise LoadError(f"Báo cáo có quá nhiều biểu đồ (tối đa {MAX_CHARTS}).")
    for b in out:
        total += len(str(b))
    if total > MAX_TOTAL_CHARS:
        raise LoadError("Nội dung báo cáo quá dài so với giới hạn của dịch vụ.")
    number_blocks(out)
    title = _clean(title, 200) or "Báo cáo"
    org = _clean(org, 200)
    blocks_all = [{"t": "title", "text": title, "subtitle": org}] + out
    return {"template": "manual", "template_name": "Báo cáo soạn thủ công", "title": title, "org": org, "date": _clean(date, 20) or today_vn(),
            "blocks": blocks_all, "included": [], "skipped": [], "n_charts": sum(1 for b in out if b["t"] == "chart")}
