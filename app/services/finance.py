"""Phân tích báo cáo tài chính (Bảng cân đối kế toán, Báo cáo kết quả kinh doanh) theo bố cục mẫu báo cáo Việt Nam.

Quy trình: đọc tệp → nhận diện loại báo cáo, kỳ báo cáo, đơn vị → gắn các dòng với khoản mục chuẩn (ưu tiên "Mã số",
sau đó tên chỉ tiêu) → kiểm tra các phép cộng/cân đối → tính chỉ số. Mọi con số được tính trực tiếp từ dữ liệu;
khoản mục không tìm thấy thì chỉ số liên quan để trống và nêu lý do, không tự ước lượng.
"""
import datetime as dt
import re
from typing import Any, Dict, List, Optional, Tuple

from .analytics import _f
from .loader import LoadError, _open_workbook, _read_csv_rows, detect_type
from .parsing import is_missing, norm_key, parse_number

# ====================================================================== khoản mục chuẩn
# (khóa, báo cáo, tên hiển thị, [mã số], [(kiểu so khớp, mẫu tên đã bỏ dấu)])
STD = [
    ("current_assets", "bs", "Tài sản ngắn hạn", ["100"], [("eq", "tai san ngan han")]),
    ("cash", "bs", "Tiền và các khoản tương đương tiền", ["110"], [("eq", "tien va cac khoan tuong duong tien")]),
    ("st_investments", "bs", "Đầu tư tài chính ngắn hạn", ["120"], [("eq", "dau tu tai chinh ngan han")]),
    ("receivables", "bs", "Các khoản phải thu ngắn hạn", ["130"], [("eq", "cac khoan phai thu ngan han")]),
    ("inventory", "bs", "Hàng tồn kho", ["140"], [("eq", "hang ton kho")]),
    ("other_ca", "bs", "Tài sản ngắn hạn khác", ["150"], [("eq", "tai san ngan han khac")]),
    ("non_current_assets", "bs", "Tài sản dài hạn", ["200"], [("eq", "tai san dai han")]),
    ("lt_receivables", "bs", "Các khoản phải thu dài hạn", ["210"], [("eq", "cac khoan phai thu dai han")]),
    ("fixed_assets", "bs", "Tài sản cố định", ["220"], [("eq", "tai san co dinh")]),
    ("investment_property", "bs", "Bất động sản đầu tư", ["230"], [("eq", "bat dong san dau tu")]),
    ("lt_wip", "bs", "Tài sản dở dang dài hạn", ["240"], [("eq", "tai san do dang dai han")]),
    ("lt_investments", "bs", "Đầu tư tài chính dài hạn", ["250"], [("eq", "dau tu tai chinh dai han")]),
    ("other_nca", "bs", "Tài sản dài hạn khác", ["260"], [("eq", "tai san dai han khac")]),
    ("total_assets", "bs", "Tổng cộng tài sản", ["270"], [("sw", "tong cong tai san"), ("eq", "tong tai san")]),
    ("total_liabilities", "bs", "Nợ phải trả", ["300"], [("eq", "no phai tra")]),
    ("current_liabilities", "bs", "Nợ ngắn hạn", ["310"], [("eq", "no ngan han")]),
    ("payables", "bs", "Phải trả người bán ngắn hạn", ["311"], [("sw", "phai tra nguoi ban")]),
    ("st_debt", "bs", "Vay và nợ thuê tài chính ngắn hạn", ["320"], [("eq", "vay va no thue tai chinh ngan han")]),
    ("long_term_liabilities", "bs", "Nợ dài hạn", ["330"], [("eq", "no dai han")]),
    ("lt_debt", "bs", "Vay và nợ thuê tài chính dài hạn", ["338"], [("eq", "vay va no thue tai chinh dai han")]),
    ("equity", "bs", "Vốn chủ sở hữu", ["400"], [("eq", "von chu so huu")]),
    ("owner_equity", "bs", "Vốn chủ sở hữu (chi tiết)", ["410"], []),
    ("funds", "bs", "Nguồn kinh phí và quỹ khác", ["430"], [("eq", "nguon kinh phi va quy khac")]),
    ("retained", "bs", "Lợi nhuận sau thuế chưa phân phối", ["421"], [("sw", "loi nhuan sau thue chua phan phoi")]),
    ("total_capital", "bs", "Tổng cộng nguồn vốn", ["440"], [("sw", "tong cong nguon von"), ("eq", "tong nguon von")]),
    ("gross_revenue", "is", "Doanh thu bán hàng và cung cấp dịch vụ", ["01"], [("eq", "doanh thu ban hang va cung cap dich vu"), ("eq", "tong doanh thu")]),
    ("deductions", "is", "Các khoản giảm trừ doanh thu", ["02"], [("eq", "cac khoan giam tru doanh thu")]),
    ("net_revenue", "is", "Doanh thu thuần", ["10"], [("sw", "doanh thu thuan")]),
    ("cogs", "is", "Giá vốn hàng bán", ["11"], [("eq", "gia von hang ban")]),
    ("gross_profit", "is", "Lợi nhuận gộp", ["20"], [("sw", "loi nhuan gop")]),
    ("fin_income", "is", "Doanh thu hoạt động tài chính", ["21"], [("eq", "doanh thu hoat dong tai chinh")]),
    ("fin_expense", "is", "Chi phí tài chính", ["22"], [("eq", "chi phi tai chinh")]),
    ("interest_expense", "is", "Chi phí lãi vay", ["23"], [("has", "chi phi lai vay")]),
    ("selling_exp", "is", "Chi phí bán hàng", ["25"], [("eq", "chi phi ban hang")]),
    ("admin_exp", "is", "Chi phí quản lý doanh nghiệp", ["26"], [("eq", "chi phi quan ly doanh nghiep")]),
    ("operating_profit", "is", "Lợi nhuận thuần từ hoạt động kinh doanh", ["30"], [("sw", "loi nhuan thuan tu hoat dong kinh doanh")]),
    ("other_income", "is", "Thu nhập khác", ["31"], [("eq", "thu nhap khac")]),
    ("other_expense", "is", "Chi phí khác", ["32"], [("eq", "chi phi khac")]),
    ("other_profit", "is", "Lợi nhuận khác", ["40"], [("eq", "loi nhuan khac")]),
    ("profit_before_tax", "is", "Tổng lợi nhuận kế toán trước thuế", ["50"], [("sw", "tong loi nhuan ke toan truoc thue")]),
    ("tax_current", "is", "Chi phí thuế TNDN hiện hành", ["51"], [("has", "thue tndn hien hanh")]),
    ("tax_deferred", "is", "Chi phí thuế TNDN hoãn lại", ["52"], [("has", "thue tndn hoan lai")]),
    ("net_profit", "is", "Lợi nhuận sau thuế", ["60"], [("sw", "loi nhuan sau thue")]),
]
STD_BY_KEY = {s[0]: s for s in STD}
COST_KEYS = ["deductions", "cogs", "fin_expense", "interest_expense", "selling_exp", "admin_exp", "other_expense", "tax_current", "tax_deferred"]
TYPE_LABEL = {"bs": "Bảng cân đối kế toán", "is": "Báo cáo kết quả kinh doanh", "cf": "Báo cáo lưu chuyển tiền tệ"}

# Các đẳng thức kế toán: (khóa tổng, [thành phần bắt buộc], [thành phần tùy chọn]); khóa bắt đầu bằng '-' là khoản trừ.
IDENTITIES = [
    ("total_assets", ["current_assets", "non_current_assets"], []),
    ("total_capital", ["total_liabilities", "equity"], []),
    ("total_liabilities", ["current_liabilities"], ["long_term_liabilities"]),
    ("equity", ["owner_equity"], ["funds"]),
    ("current_assets", [], ["cash", "st_investments", "receivables", "inventory", "other_ca"]),
    ("non_current_assets", [], ["lt_receivables", "fixed_assets", "investment_property", "lt_wip", "lt_investments", "other_nca"]),
    ("net_revenue", ["gross_revenue"], ["-deductions"]),
    ("gross_profit", ["net_revenue", "-cogs"], []),
    ("operating_profit", ["gross_profit", "-selling_exp", "-admin_exp"], ["fin_income", "-fin_expense"]),
    ("other_profit", ["other_income", "-other_expense"], []),
    ("profit_before_tax", ["operating_profit"], ["other_profit"]),
    ("net_profit", ["profit_before_tax"], ["-tax_current", "-tax_deferred"]),
]


# ====================================================================== đọc số, kỳ, tên
def fin_number(v: Any) -> Tuple[Optional[float], Optional[str]]:
    """Đọc ô số của báo cáo tài chính: hỗ trợ số trong ngoặc đơn là số âm, dấu '-' là 0, dấu ngăn cách hàng nghìn."""
    if v is None or (isinstance(v, str) and v.strip() == ""):
        return None, None
    if isinstance(v, bool):
        return None, "invalid"
    if isinstance(v, (int, float)):
        return (float(v), "native") if v == v else (None, None)
    s = str(v).strip()
    if s in ("-", "–", "—"):
        return 0.0, "dash"
    neg = False
    m = re.fullmatch(r"\(\s*(.+?)\s*\)", s)
    if m:
        neg, s = True, m.group(1)
    val, kind = parse_number(s)
    if val is None:
        return None, "invalid"
    return (-abs(val) if neg else val), "text"


def name_key(name: Any) -> str:
    s = re.sub(r"\(\*+\)", "", norm_key(name or ""))
    for _ in range(4):
        s2 = re.sub(r"^(?:[-–•]\s*)+", "", s)
        s2 = re.sub(r"^trong do\s*:?\s*", "", s2)
        s2 = re.sub(r"^(?:[a-z]{1,4}|\d+)\s*[\.\)\-:]\s+", "", s2)
        if s2 == s:
            break
        s = s2
    return s.strip()


def period_info(v: Any) -> Optional[Dict[str, Any]]:
    """Nhận diện tiêu đề cột kỳ: 2025, 'Năm 2025', '31/12/2025', 'Quý 1/2025', 'Tháng 3/2025', 'Số cuối năm', 'Số đầu năm'."""
    if isinstance(v, dt.datetime):
        v = v.date()
    if isinstance(v, dt.date):
        pid = str(v.year) if (v.month, v.day) == (12, 31) else v.strftime("%d/%m/%Y")
        return {"pid": pid, "label": pid, "sort": (v.year, v.month, v.day), "kind": "year" if (v.month, v.day) == (12, 31) else "date"}
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        if float(v).is_integer() and 1990 <= v <= 2100:
            return {"pid": str(int(v)), "label": str(int(v)), "sort": (int(v), 12, 31), "kind": "year"}
        return None
    if not isinstance(v, str) or not v.strip() or len(v.strip()) > 26:
        return None
    ns = norm_key(v)
    if re.search(r"\bcuoi (nam|ky)\b", ns):
        return {"pid": "Cuối kỳ", "label": "Cuối kỳ", "sort": (9999, 12, 31), "kind": "end"}
    if re.search(r"\bdau (nam|ky)\b", ns):
        return {"pid": "Đầu kỳ", "label": "Đầu kỳ", "sort": (9998, 1, 1), "kind": "start"}
    m = re.search(r"(?:quy\s*([1-4])|\bq\s*([1-4]))\D{0,6}((?:19|20)\d{2})", ns) or re.search(r"((?:19|20)\d{2})\D{0,3}q\s*([1-4])", ns)
    if m:
        g = m.groups()
        q, y = (int(g[0] or g[1]), int(g[2])) if len(g) == 3 else (int(g[1]), int(g[0]))
        return {"pid": f"{y}-Q{q}", "label": f"Quý {q}/{y}", "sort": (y, q * 3, 28), "kind": "quarter"}
    m = re.search(r"(?:thang\s*|\bt)(\d{1,2})\D{1,3}((?:19|20)\d{2})", ns) or re.fullmatch(r"(\d{1,2})[/\-.]((?:19|20)\d{2})", ns)
    if m and 1 <= int(m.group(1)) <= 12:
        mo, y = int(m.group(1)), int(m.group(2))
        return {"pid": f"{y}-{mo:02d}", "label": f"Tháng {mo}/{y}", "sort": (y, mo, 28), "kind": "month"}
    m = re.search(r"(\d{1,2})[/\-.](\d{1,2})[/\-.]((?:19|20)\d{2})", ns)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= mo <= 12 and 1 <= d <= 31:
            pid = str(y) if (mo, d) == (12, 31) else f"{d:02d}/{mo:02d}/{y}"
            return {"pid": pid, "label": pid, "sort": (y, mo, d), "kind": "year" if (mo, d) == (12, 31) else "date"}
    m = re.search(r"(?<!\d)((?:19|20)\d{2})(?!\d)", ns)
    if m:
        y = int(m.group(1))
        return {"pid": str(y), "label": str(y), "sort": (y, 12, 31), "kind": "year"}
    return None


def _detect_unit(text: str) -> Optional[str]:
    m = re.search(r"don vi tinh\s*:?\s*([a-z ]{2,24})", text)
    if not m:
        return None
    u = m.group(1)
    for key, label in (("trieu", "triệu đồng"), ("nghin", "nghìn đồng"), ("ngan", "nghìn đồng"), ("ty", "tỷ đồng")):
        if re.search(rf"\b{key}\b", u):
            return label
    return "đồng" if re.search(r"\b(dong|vnd)\b", u) else None


# ====================================================================== đọc một bảng (sheet)
def _classify(text: str, rows: List[Dict[str, Any]]) -> Optional[str]:
    codes = {r["code"] for r in rows if r["code"]}
    names = [name_key(r["name"]) for r in rows]
    score = {"bs": 0, "is": 0, "cf": 0}
    if re.search(r"can doi ke toan|balance sheet", text):
        score["bs"] += 3
    if re.search(r"ket qua hoat dong kinh doanh|ket qua kinh doanh|income statement|profit and loss", text):
        score["is"] += 3
    if re.search(r"luu chuyen tien te|cash flow", text):
        score["cf"] += 3
    if "270" in codes or any(n.startswith("tong cong tai san") for n in names):
        score["bs"] += 2
    if "440" in codes or any(n.startswith("tong cong nguon von") for n in names):
        score["bs"] += 2
    if any(n.startswith("doanh thu thuan") for n in names):
        score["is"] += 2
    if any(n.startswith("loi nhuan sau thue") and "chua phan phoi" not in n for n in names):
        score["is"] += 2
    if any(n.startswith("luu chuyen tien thuan") for n in names):
        score["cf"] += 2
    best = max(score, key=score.get)
    return best if score[best] >= 2 else None


def parse_sheet(title: str, grid: List[List[Any]], is_excel: bool = True) -> Optional[Dict[str, Any]]:
    grid = [list(r) for r in grid]
    head_i, head_periods = None, []
    for i, row in enumerate(grid[:40]):
        ps = [(j, period_info(c)) for j, c in enumerate(row) if period_info(c)]
        has_label = any(isinstance(c, str) and re.search(r"chi tieu|ma so|tai san|nguon von|khoan muc", norm_key(c)) for c in row)
        kinds = {p["kind"] for _, p in ps}
        if len(ps) >= 2 or (len(ps) == 1 and has_label and "end" not in kinds and "start" not in kinds):
            head_i, head_periods = i, ps
            break
    if head_i is None:
        return None
    header = grid[head_i]
    pcols = [j for j, _ in head_periods]
    name_col = next((j for j, c in enumerate(header) if isinstance(c, str) and c.strip() and j not in pcols
                     and norm_key(c) not in ("ma so", "ma", "thuyet minh", "code", "ms")), 0)
    code_col = next((j for j, c in enumerate(header) if isinstance(c, str) and norm_key(c) in ("ma so", "ma", "code", "ms")), None)
    if code_col is None:
        for j in range(0, min(pcols)):
            vals = [r[j] for r in grid[head_i + 1:] if j < len(r) and not is_missing(r[j])]
            ok = sum(1 for v in vals if re.fullmatch(r"\d{2,3}", str(int(v)) if isinstance(v, float) and v.is_integer() else str(v).strip()))
            if vals and ok / len(vals) >= 0.6 and j != name_col:
                code_col = j
                break

    rows: List[Dict[str, Any]] = []
    n_text = n_invalid = n_missing = 0
    for k, r in enumerate(grid[head_i + 1:], start=head_i + 2):
        r = r + [None] * (max(pcols + [name_col, code_col or 0]) + 1 - len(r))
        name = r[name_col]
        name = str(name).strip() if not is_missing(name) else ""
        code = None
        if code_col is not None and not is_missing(r[code_col]):
            c = r[code_col]
            code = str(int(c)) if isinstance(c, (int, float)) and float(c).is_integer() else str(c).strip()
            code = code if re.fullmatch(r"\d{1,3}", code) else None
        vals, text_cells, invalid_cells = [], 0, 0
        for j in pcols:
            v, flag = fin_number(r[j])
            vals.append(v)
            text_cells += (flag == "text") and is_excel
            invalid_cells += flag == "invalid"
        has_values = any(v is not None for v in vals) or invalid_cells > 0
        if not name and not has_values:
            continue
        if has_values or code:
            n_text += text_cells
            n_invalid += invalid_cells
            n_missing += sum(1 for v in vals if v is None) if code or has_values else 0
        rows.append({"idx": k, "code": code, "name": name, "values": vals, "has_values": has_values, "text_cells": text_cells, "invalid_cells": invalid_cells})
    if not [r for r in rows if r["has_values"]]:
        return None
    top = " ".join(norm_key(c) for r in grid[:head_i + 1] for c in r if isinstance(c, str))
    stype = _classify(norm_key(title) + " " + top, rows)
    return {"sheet": title, "type": stype, "type_label": TYPE_LABEL.get(stype, "Không rõ"), "unit": _detect_unit(top),
            "periods": [p for _, p in head_periods], "rows": rows,
            "n_text_cells": n_text, "n_invalid_cells": n_invalid, "n_missing_cells": n_missing}


def parse_file(raw: bytes, filename: str) -> Dict[str, Any]:
    ftype = detect_type(filename, raw)
    sheets: List[Tuple[str, List[List[Any]]]] = []
    if ftype == "csv":
        grid, _ = _read_csv_rows(raw)
        sheets.append(("CSV", grid))
    else:
        wb = _open_workbook(raw)
        try:
            for ws in wb.worksheets:
                if hasattr(ws, "iter_rows"):
                    rows = []
                    for r in ws.iter_rows(values_only=True):
                        rows.append(list(r))
                        if len(rows) >= 3000:
                            break
                    sheets.append((ws.title, rows))
        finally:
            wb.close()
    statements, skipped = [], []
    for title, grid in sheets:
        st = parse_sheet(title, grid, ftype == "excel")
        if st is None:
            skipped.append({"sheet": title, "reason": "không tìm thấy bảng số liệu theo kỳ (không phải báo cáo tài chính)"})
        elif st["type"] is None:
            skipped.append({"sheet": title, "reason": "có bảng số liệu nhưng không nhận diện được là Bảng cân đối kế toán hay Báo cáo kết quả kinh doanh"})
        elif st["type"] == "cf":
            skipped.append({"sheet": title, "reason": "Báo cáo lưu chuyển tiền tệ chưa được phân tích ở phiên bản này"})
        else:
            st["id"] = f"{st['type']}:{title}"
            statements.append(st)
    if not statements:
        raise LoadError("Không nhận diện được Bảng cân đối kế toán hoặc Báo cáo kết quả kinh doanh trong tệp. "
                        "Hãy kiểm tra tệp có dòng tiêu đề kỳ (ví dụ 31/12/2025, Năm 2025) và cột Mã số/Chỉ tiêu.")
    seen = {}
    for st in statements:
        if st["type"] in seen:
            skipped.append({"sheet": st["sheet"], "reason": f"đã có một {st['type_label']} khác ({seen[st['type']]}), bảng này không được dùng"})
        else:
            seen[st["type"]] = st["sheet"]
    statements = [s for s in statements if seen[s["type"]] == s["sheet"]]
    return {"file_type": ftype, "statements": statements, "skipped": skipped}


# ====================================================================== ánh xạ khoản mục
def _match(rows: List[Dict[str, Any]], key: str) -> Optional[Dict[str, Any]]:
    _, _, label, codes, patterns = STD_BY_KEY[key]
    for c in codes:
        for i, r in enumerate(rows):
            if r["code"] == c and r["has_values"]:
                return {"row": i, "code": r["code"], "name": r["name"], "source": f"mã số {c}"}
    for mode, pat in patterns:
        for i, r in enumerate(rows):
            if not r["has_values"]:
                continue
            nk = name_key(r["name"])
            if (mode == "eq" and nk == pat) or (mode == "sw" and nk.startswith(pat)) or (mode == "has" and pat in nk):
                return {"row": i, "code": r["code"], "name": r["name"], "source": "tên chỉ tiêu"}
    return None


def auto_mapping(parsed: Dict[str, Any]) -> Dict[str, Any]:
    out = {}
    for key, stmt, *_ in STD:
        st = next((s for s in parsed["statements"] if s["type"] == stmt), None)
        if st:
            m = _match(st["rows"], key)
            if m:
                out[key] = {"statement": st["id"], **m}
    return out


def apply_overrides(parsed: Dict[str, Any], mapping: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
    mapping = dict(mapping)
    for key, o in (overrides or {}).items():
        if key not in STD_BY_KEY:
            continue
        if not o:
            mapping.pop(key, None)
            continue
        st = next((s for s in parsed["statements"] if s["id"] == o.get("statement")), None)
        i = o.get("row")
        if st and isinstance(i, int) and 0 <= i < len(st["rows"]) and st["type"] == STD_BY_KEY[key][1] and st["rows"][i]["has_values"]:
            r = st["rows"][i]
            mapping[key] = {"statement": st["id"], "row": i, "code": r["code"], "name": r["name"], "source": "bạn chọn"}
    return mapping


def build_matrix(parsed: Dict[str, Any], mapping: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, Optional[float]]], List[str]]:
    periods: Dict[str, Dict[str, Any]] = {}
    for st in parsed["statements"]:
        for p in st["periods"]:
            periods.setdefault(p["pid"], p)
    ordered = sorted(periods.values(), key=lambda p: tuple(p["sort"]))
    M: Dict[str, Dict[str, Optional[float]]] = {}
    for key, m in mapping.items():
        st = next(s for s in parsed["statements"] if s["id"] == m["statement"])
        row = st["rows"][m["row"]]
        M[key] = {p["pid"]: row["values"][j] for j, p in enumerate(st["periods"])}
    notes: List[str] = []
    cogs = [v for v in M.get("cogs", {}).values() if v is not None]
    if cogs and sum(1 for v in cogs if v < 0) > len(cogs) / 2:
        for k in COST_KEYS:
            if k in M:
                M[k] = {p: (-v if v is not None else None) for p, v in M[k].items()}
        notes.append("Các khoản chi phí trong báo cáo được ghi bằng số âm; hệ thống đã đổi dấu để tính toán.")
    return ordered, M, notes


# ====================================================================== kiểm tra
def run_checks(parsed: Dict[str, Any], mapping: Dict[str, Any], periods, M) -> Dict[str, Any]:
    checks: List[Dict[str, Any]] = []
    not_checked: List[str] = []

    def v(key, pid):
        return M.get(key, {}).get(pid)

    def tol(x):
        return max(1.0, 0.0005 * abs(x))

    for total, req, opt in IDENTITIES:
        if total not in M:
            continue
        if any(k.lstrip("-") not in M for k in req) or (not req and sum(1 for k in opt if k.lstrip("-") in M) < 2):
            not_checked.append(f"{STD_BY_KEY[total][2]}: thiếu khoản mục thành phần để kiểm tra phép cộng")
            continue
        used = [k for k in req + opt if k.lstrip("-") in M]
        formula = f"{STD_BY_KEY[total][2]} = " + " ".join(("− " if k.startswith("-") else "+ ") + STD_BY_KEY[k.lstrip('-')][2] for k in used).lstrip("+ ").strip()
        for p in periods:
            pid = p["pid"]
            actual = v(total, pid)
            parts = [v(k.lstrip("-"), pid) for k in used]
            if actual is None or any(x is None for x in parts):
                continue
            expected = sum((-x if k.startswith("-") else x) for k, x in zip(used, parts))
            diff = actual - expected
            checks.append({"kind": "sum", "total": total, "title": STD_BY_KEY[total][2], "formula": formula, "period": p["label"], "expected": _f(expected), "actual": _f(actual),
                           "diff": _f(diff), "ok": abs(diff) <= tol(expected), "components": [k.lstrip("-") for k in used], "pid": pid})
    if "total_assets" in M and "total_capital" in M:
        for p in periods:
            a, c = v("total_assets", p["pid"]), v("total_capital", p["pid"])
            if a is not None and c is not None:
                checks.append({"kind": "balance", "total": "balance", "title": "Cân đối: Tổng tài sản = Tổng nguồn vốn", "formula": "Tổng cộng tài sản = Tổng cộng nguồn vốn",
                               "period": p["label"], "expected": _f(c), "actual": _f(a), "diff": _f(a - c), "ok": abs(a - c) <= tol(c),
                               "components": ["total_assets", "total_capital"], "pid": p["pid"]})
    data_issues = []
    for st in parsed["statements"]:
        used_rows = {m["row"] for m in mapping.values() if m["statement"] == st["id"]}
        blanks = [(i, r, j) for i, r in enumerate(st["rows"]) if r["has_values"] for j, x in enumerate(r["values"]) if x is None and (r["code"] or i in used_rows)]
        if blanks:
            imp = sum(1 for i, _, _ in blanks if i in used_rows)
            data_issues.append({"statement": st["type_label"], "count": len(blanks), "message": f"Có {len(blanks)} ô trống ở các dòng có số liệu ở kỳ khác"
                                + (f" (trong đó {imp} ô thuộc khoản mục dùng để tính chỉ số)" if imp else "") + ": "
                                + "; ".join(f"{r['name'].strip()} ({st['periods'][j]['label']})" for _, r, j in blanks[:6]) + ("…" if len(blanks) > 6 else "")})
        if st["n_text_cells"]:
            data_issues.append({"statement": st["type_label"], "message": f"{st['n_text_cells']} ô số đang lưu dạng chữ (có dấu chấm ngăn cách hoặc số âm trong ngoặc đơn); hệ thống đã đọc được thành số.", "count": st["n_text_cells"]})
        if st["n_invalid_cells"]:
            data_issues.append({"statement": st["type_label"], "message": f"{st['n_invalid_cells']} ô không đọc được thành số; các ô này được bỏ qua.", "count": st["n_invalid_cells"]})
    bad_keys = {(c["total"], c["pid"]) for c in checks if not c["ok"]}
    for c in checks:
        c["cascade"] = (not c["ok"]) and any((k, c["pid"]) in bad_keys for k in c["components"])
    failed = sorted((c for c in checks if not c["ok"]), key=lambda c: c["cascade"])
    return {"n_checked": len(checks), "n_failed": len(failed), "n_root_failed": sum(1 for c in failed if not c["cascade"]), "failed": failed, "passed_titles": sorted({c["title"] for c in checks if c["ok"]}),
            "not_checked": not_checked, "data_issues": data_issues, "all": checks[:200]}


# ====================================================================== chỉ số
PERIOD_DAYS = {"year": 365.0, "date": 365.0, "end": 365.0, "start": 365.0, "quarter": 91.25, "month": 30.4}


def analyze(periods, M, notes: List[str], unit: Optional[str]) -> Dict[str, Any]:
    pids = [p["pid"] for p in periods]
    labels = [p["label"] for p in periods]
    n = len(pids)

    def val(k, i):
        return M.get(k, {}).get(pids[i]) if 0 <= i < n else None

    def avg(k, i):
        cur, prev = val(k, i), val(k, i - 1)
        if cur is None:
            return None, None
        if prev is None:
            return cur, "cuối kỳ"
        return (cur + prev) / 2, "bình quân"

    def div(a, b):
        return None if a is None or b is None or b == 0 else a / b

    def sub(a, b):
        return None if a is None or b is None else a - b

    days = [PERIOD_DAYS.get(p["kind"], 365.0) for p in periods]
    groups: List[Dict[str, Any]] = []

    def group(name, defs):
        items = []
        for key, label, formula, kind, fn, need in defs:
            if any(k not in M for k in need):
                items.append({"key": key, "label": label, "formula": formula, "unit": kind, "values": [None] * n, "basis": [None] * n,
                              "available": False, "reason": "Thiếu khoản mục: " + ", ".join(STD_BY_KEY[k][2] for k in need if k not in M)})
                continue
            vals, basis = [], []
            for i in range(n):
                res = fn(i)
                v, b = res if isinstance(res, tuple) else (res, None)
                vals.append(None if v is None else _f(v))
                basis.append(b)
            items.append({"key": key, "label": label, "formula": formula, "unit": kind, "values": vals, "basis": basis, "available": any(x is not None for x in vals), "reason": ""})
        groups.append({"name": name, "items": items})

    def cur_ratio(a, b):
        return lambda i: div(val(a, i), val(b, i))

    def over_avg(num, den, mult=1.0):
        def fn(i):
            d, b = avg(den, i)
            r = div(val(num, i), d)
            return (None if r is None else r * mult), b
        return fn

    group("Khả năng thanh toán", [
        ("current_ratio", "Tỷ số thanh toán hiện hành", "Tài sản ngắn hạn ÷ Nợ ngắn hạn", "lần", cur_ratio("current_assets", "current_liabilities"), ["current_assets", "current_liabilities"]),
        ("quick_ratio", "Tỷ số thanh toán nhanh", "(Tài sản ngắn hạn − Hàng tồn kho) ÷ Nợ ngắn hạn", "lần",
         lambda i: div(sub(val("current_assets", i), val("inventory", i)), val("current_liabilities", i)), ["current_assets", "inventory", "current_liabilities"]),
        ("cash_ratio", "Tỷ số thanh toán tiền mặt", "Tiền và tương đương tiền ÷ Nợ ngắn hạn", "lần", cur_ratio("cash", "current_liabilities"), ["cash", "current_liabilities"]),
    ])
    group("Cơ cấu vốn và đòn bẩy", [
        ("debt_to_assets", "Nợ phải trả / Tổng tài sản", "Nợ phải trả ÷ Tổng tài sản", "lần", cur_ratio("total_liabilities", "total_assets"), ["total_liabilities", "total_assets"]),
        ("debt_to_equity", "Nợ phải trả / Vốn chủ sở hữu", "Nợ phải trả ÷ Vốn chủ sở hữu", "lần", cur_ratio("total_liabilities", "equity"), ["total_liabilities", "equity"]),
        ("equity_multiplier", "Hệ số nhân vốn", "Tổng tài sản ÷ Vốn chủ sở hữu", "lần", cur_ratio("total_assets", "equity"), ["total_assets", "equity"]),
        ("interest_coverage", "Khả năng trả lãi vay", "(LN trước thuế + Chi phí lãi vay) ÷ Chi phí lãi vay", "lần",
         lambda i: div(None if val("profit_before_tax", i) is None or val("interest_expense", i) is None else val("profit_before_tax", i) + val("interest_expense", i), val("interest_expense", i)),
         ["profit_before_tax", "interest_expense"]),
    ])
    group("Khả năng sinh lời", [
        ("gross_margin", "Biên lợi nhuận gộp", "Lợi nhuận gộp ÷ Doanh thu thuần", "%", lambda i: _pct(div(val("gross_profit", i), val("net_revenue", i))), ["gross_profit", "net_revenue"]),
        ("operating_margin", "Biên lợi nhuận hoạt động", "LN thuần từ HĐKD ÷ Doanh thu thuần", "%", lambda i: _pct(div(val("operating_profit", i), val("net_revenue", i))), ["operating_profit", "net_revenue"]),
        ("net_margin", "Biên lợi nhuận ròng", "Lợi nhuận sau thuế ÷ Doanh thu thuần", "%", lambda i: _pct(div(val("net_profit", i), val("net_revenue", i))), ["net_profit", "net_revenue"]),
        ("roa", "ROA – Tỷ suất sinh lời trên tài sản", "Lợi nhuận sau thuế ÷ Tổng tài sản bình quân", "%", over_avg("net_profit", "total_assets", 100.0), ["net_profit", "total_assets"]),
        ("roe", "ROE – Tỷ suất sinh lời trên vốn chủ sở hữu", "Lợi nhuận sau thuế ÷ Vốn chủ sở hữu bình quân", "%", over_avg("net_profit", "equity", 100.0), ["net_profit", "equity"]),
    ])

    def turn(num, den):
        return over_avg(num, den)

    def days_of(num, den):
        def fn(i):
            t, b = turn(num, den)(i)
            return (None if not t else days[i] / t), b
        return fn

    def ccc(i):
        a, b, c = days_of("cogs", "inventory")(i)[0], days_of("net_revenue", "receivables")(i)[0], days_of("cogs", "payables")(i)[0]
        return (None if None in (a, b, c) else a + b - c), None

    group("Hiệu quả hoạt động", [
        ("inventory_turnover", "Vòng quay hàng tồn kho", "Giá vốn hàng bán ÷ Hàng tồn kho bình quân", "vòng", turn("cogs", "inventory"), ["cogs", "inventory"]),
        ("dio", "Số ngày tồn kho", "Số ngày trong kỳ ÷ Vòng quay hàng tồn kho", "ngày", days_of("cogs", "inventory"), ["cogs", "inventory"]),
        ("receivable_turnover", "Vòng quay các khoản phải thu", "Doanh thu thuần ÷ Phải thu ngắn hạn bình quân", "vòng", turn("net_revenue", "receivables"), ["net_revenue", "receivables"]),
        ("dso", "Số ngày thu tiền bình quân", "Số ngày trong kỳ ÷ Vòng quay các khoản phải thu", "ngày", days_of("net_revenue", "receivables"), ["net_revenue", "receivables"]),
        ("dpo", "Số ngày trả tiền người bán", "Số ngày trong kỳ ÷ (Giá vốn ÷ Phải trả người bán bình quân)", "ngày", days_of("cogs", "payables"), ["cogs", "payables"]),
        ("ccc", "Chu kỳ chuyển đổi tiền", "Số ngày tồn kho + Số ngày thu tiền − Số ngày trả tiền", "ngày", ccc, ["cogs", "inventory", "net_revenue", "receivables", "payables"]),
        ("asset_turnover", "Vòng quay tổng tài sản", "Doanh thu thuần ÷ Tổng tài sản bình quân", "vòng", turn("net_revenue", "total_assets"), ["net_revenue", "total_assets"]),
    ])
    R = {it["key"]: it for g in groups for it in g["items"]}

    def rv(key, i):
        it = R.get(key)
        return it["values"][i] if it and it["available"] else None

    growth = []
    for key in ("net_revenue", "gross_profit", "operating_profit", "net_profit", "total_assets", "total_liabilities", "equity"):
        if key not in M:
            continue
        vals = [val(key, i) for i in range(n)]
        yoy = [None] + [(_f((vals[i] / vals[i - 1] - 1) * 100) if vals[i] is not None and vals[i - 1] not in (None, 0) and vals[i - 1] > 0 else None) for i in range(1, n)]
        cagr = None
        if n >= 3 and vals[0] and vals[-1] and vals[0] > 0 and vals[-1] > 0 and all(p["kind"] in ("year", "date") for p in periods):
            cagr = _f(((vals[-1] / vals[0]) ** (1 / (n - 1)) - 1) * 100)
        growth.append({"key": key, "label": STD_BY_KEY[key][2], "values": [None if x is None else _f(x) for x in vals], "yoy_pct": yoy, "cagr_pct": cagr})

    def share(keys, base):
        out = []
        for k in keys:
            if k in M and base in M:
                out.append({"key": k, "label": STD_BY_KEY[k][2], "pct": [None if div(val(k, i), val(base, i)) is None else _f(div(val(k, i), val(base, i)) * 100) for i in range(n)]})
        return out

    vertical = {
        "assets": {"base": "Tổng tài sản", "items": share(["cash", "st_investments", "receivables", "inventory", "other_ca", "current_assets", "fixed_assets", "non_current_assets"], "total_assets")},
        "capital": {"base": "Tổng nguồn vốn", "items": share(["current_liabilities", "long_term_liabilities", "total_liabilities", "equity"], "total_capital" if "total_capital" in M else "total_assets")},
        "income": {"base": "Doanh thu thuần", "items": share(["cogs", "gross_profit", "selling_exp", "admin_exp", "fin_expense", "operating_profit", "profit_before_tax", "net_profit"], "net_revenue")},
    }

    dupont = None
    if all(k in M for k in ("net_profit", "net_revenue", "total_assets", "equity")):
        rows = []
        for i in range(n):
            ta, _ = avg("total_assets", i)
            eq, _ = avg("equity", i)
            nm, at, em = div(val("net_profit", i), val("net_revenue", i)), div(val("net_revenue", i), ta), div(ta, eq)
            prod = None if None in (nm, at, em) else nm * at * em * 100
            rows.append({"period": labels[i], "net_margin_pct": None if nm is None else _f(nm * 100), "asset_turnover": None if at is None else _f(at),
                         "equity_multiplier": None if em is None else _f(em), "roe_pct": None if prod is None else _f(prod)})
        dupont = {"rows": rows, "note": "ROE = Biên lợi nhuận ròng × Vòng quay tổng tài sản × Hệ số nhân vốn (dùng tài sản và vốn chủ sở hữu bình quân)."}

    alerts: List[Dict[str, Any]] = []

    def alert(sev, i, title, msg):
        alerts.append({"severity": sev, "period": labels[i], "title": title, "message": msg})

    for i in range(n):
        cr, qr, de, ic = rv("current_ratio", i), rv("quick_ratio", i), rv("debt_to_equity", i), rv("interest_coverage", i)
        if cr is not None and cr < 1:
            alert("warn", i, "Thanh toán ngắn hạn thấp", f"Tỷ số thanh toán hiện hành là {_vn(cr)}, nhỏ hơn 1: tài sản ngắn hạn không đủ bao phủ nợ ngắn hạn (ngưỡng tham khảo, mức phù hợp phụ thuộc ngành).")
        if qr is not None and qr < 0.5:
            alert("warn", i, "Thanh toán nhanh thấp", f"Tỷ số thanh toán nhanh là {_vn(qr)}, nhỏ hơn 0,5 (ngưỡng tham khảo).")
        if de is not None and de > 2:
            alert("warn", i, "Đòn bẩy cao", f"Nợ phải trả gấp {_vn(de)} lần vốn chủ sở hữu (ngưỡng tham khảo là 2 lần).")
        if val("equity", i) is not None and val("equity", i) <= 0:
            alert("high", i, "Vốn chủ sở hữu âm hoặc bằng 0", f"Vốn chủ sở hữu là {_vnum(val('equity', i))}.")
        if val("net_profit", i) is not None and val("net_profit", i) < 0:
            alert("high", i, "Lỗ ròng", f"Lợi nhuận sau thuế là {_vnum(val('net_profit', i))} (âm).")
        if ic is not None and ic < 1.5:
            alert("warn", i, "Khả năng trả lãi vay thấp", f"Khả năng trả lãi vay là {_vn(ic)} lần, nhỏ hơn 1,5 (ngưỡng tham khảo).")
        if i > 0:
            gm, gm0 = rv("gross_margin", i), rv("gross_margin", i - 1)
            if gm is not None and gm0 is not None and gm0 - gm >= 2:
                alert("warn", i, "Biên lợi nhuận gộp giảm", f"Biên lợi nhuận gộp giảm từ {_vn(gm0, 1)}% xuống {_vn(gm, 1)}% (giảm {_vn(gm0 - gm, 1)} điểm phần trăm).")
            for key, name, thr in (("dso", "Số ngày thu tiền bình quân", 15), ("dio", "Số ngày tồn kho", 15)):
                a, b = rv(key, i), rv(key, i - 1)
                if a is not None and b and b > 0 and (a / b - 1) * 100 >= thr:
                    alert("warn", i, f"{name} tăng", f"{name} tăng từ {b:.0f} lên {a:.0f} ngày (+{(a / b - 1) * 100:.0f}%), tiền bị giữ lâu hơn trong phải thu/hàng tồn kho.")
            rev0, rev1 = val("net_revenue", i - 1), val("net_revenue", i)
            if rev0 and rev1 is not None and rev0 > 0 and rev1 < rev0:
                alert("warn", i, "Doanh thu giảm", f"Doanh thu thuần giảm {_vn(abs(rev1 / rev0 - 1) * 100, 1)}% so với kỳ trước.")
            np0, np1 = val("net_profit", i - 1), val("net_profit", i)
            if np0 and np1 is not None and np0 > 0 and np1 < np0 * 0.8:
                alert("warn", i, "Lợi nhuận sau thuế giảm mạnh", f"Lợi nhuận sau thuế giảm {_vn(abs(np1 / np0 - 1) * 100, 1)}% so với kỳ trước.")
    sev_order = {"high": 0, "warn": 1}
    alerts.sort(key=lambda a: (sev_order.get(a["severity"], 2)))

    out_notes = list(notes)
    if unit:
        out_notes.append(f"Đơn vị tính của báo cáo: {unit}. Các tỷ số không phụ thuộc đơn vị.")
    if any(p["kind"] in ("quarter", "month") for p in periods):
        out_notes.append("Dữ liệu theo quý/tháng: các số ngày được tính theo độ dài kỳ; ROA, ROE và vòng quay là theo kỳ, chưa quy năm.")
    if any(p["kind"] in ("start", "end") for p in periods):
        out_notes.append("Báo cáo chỉ có cột đầu kỳ và cuối kỳ nên chưa rõ độ dài kỳ; giả định kỳ là 1 năm.")
    if n == 1:
        out_notes.append("Chỉ có 1 kỳ nên các chỉ số dùng giá trị bình quân được tính theo số cuối kỳ và không có phân tích tăng trưởng.")
    if any(b == "cuối kỳ" for it in R.values() for b in it["basis"] if b):
        out_notes.append("Với kỳ đầu tiên (hoặc kỳ thiếu số liệu kỳ trước), các chỉ số cần số bình quân được tính theo số cuối kỳ; xem cột cơ sở tính.")
    out_notes.append(f"Có {n} kỳ báo cáo nên hệ thống không dự báo bằng mô hình thống kê (cần chuỗi dài hơn nhiều); chỉ phân tích xu hướng quá khứ.")
    latest = {}
    for key in ("net_revenue", "net_profit", "total_assets", "equity"):
        if key in M and val(key, n - 1) is not None:
            latest[key] = {"label": STD_BY_KEY[key][2], "value": _f(val(key, n - 1)), "yoy_pct": next((g["yoy_pct"][-1] for g in growth if g["key"] == key), None)}
    for key in ("current_ratio", "debt_to_equity", "gross_margin", "net_margin", "roe", "roa"):
        if rv(key, n - 1) is not None:
            latest[key] = {"label": R[key]["label"], "value": rv(key, n - 1), "unit": R[key]["unit"], "prev": rv(key, n - 2) if n > 1 else None}
    return {"periods": [{"pid": p["pid"], "label": p["label"], "kind": p["kind"]} for p in periods], "unit": unit, "ratio_groups": groups,
            "growth": growth, "vertical": vertical, "dupont": dupont, "alerts": alerts, "latest": latest, "notes": out_notes}


def _vn(x: float, d: int = 2) -> str:
    """Số thập phân theo cách viết Việt Nam (dấu phẩy)."""
    return f"{x:.{d}f}".replace(".", ",")


def _vnum(x: float) -> str:
    """Số nguyên có dấu chấm ngăn cách hàng nghìn."""
    return f"{x:,.0f}".replace(",", ".")


def _pct(x: Optional[float]) -> Optional[float]:
    return None if x is None else x * 100


# ====================================================================== điểm vào
def evaluate(parsed: Dict[str, Any], overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    mapping = apply_overrides(parsed, auto_mapping(parsed), overrides or {})
    periods, M, notes = build_matrix(parsed, mapping)
    units = {s["unit"] for s in parsed["statements"] if s["unit"]}
    unit = units.pop() if len(units) == 1 else None
    if len(units) > 1:
        notes.append("Các báo cáo dùng đơn vị tính khác nhau; hãy kiểm tra trước khi so sánh số tuyệt đối.")
    checks = run_checks(parsed, mapping, periods, M)
    analysis = analyze(periods, M, notes, unit)
    expected = {k: STD_BY_KEY[k][2] for k in ("total_assets", "current_assets", "current_liabilities", "equity", "net_revenue", "cogs", "net_profit") if k not in mapping}
    return {"mapping": mapping, "unmapped_important": expected, "checks": checks, "analysis": analysis}


def parse_and_evaluate(raw: bytes, filename: str) -> Dict[str, Any]:
    parsed = parse_file(raw, filename)
    return {"parsed": parsed, "std_items": [{"key": k, "statement": s, "label": lbl, "codes": codes} for k, s, lbl, codes, _ in STD], **evaluate(parsed)}
