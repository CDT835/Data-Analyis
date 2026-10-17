"""Kiểm tra chất lượng dữ liệu và tạo gợi ý làm sạch.

Mọi con số đều được tính trực tiếp từ dữ liệu; không ước lượng hay bịa số liệu.
Các gợi ý chỉ là đề xuất, người dùng xác nhận mới áp dụng (xem cleaner.py).
"""
import re
from collections import Counter
from typing import Any, Dict, List, Optional

import numpy as np

from .column_mapper import suggest_mapping
from .loader import Table
from .parsing import (collapse_spaces, is_missing, is_placeholder, norm_key,
                      parse_date, parse_number, preview_cell)

NAME_ID_RE = re.compile(r"(^|[^a-z0-9])(ma|id|so hieu)([^a-z0-9]|$)|_id$")
SCORE_RE = re.compile(r"(^|[^a-z])(diem|score)([^a-z]|$)")
TYPE_LABEL = {"numeric": "Số", "date": "Ngày", "text": "Văn bản", "category": "Phân loại", "id": "Mã định danh", "empty": "Trống"}


# ------------------------------------------------------------------ tiện ích
def _issue(code: str, severity: str, message: str, count: int, examples: Optional[list] = None) -> Dict[str, Any]:
    return {"code": code, "severity": severity, "message": message, "count": int(count), "examples": examples or []}


def _ratio_sev(count: int, total: int) -> str:
    r = count / total if total else 1
    return "info" if r <= 0.01 else ("warn" if r <= 0.05 else "high")


def _examples(idx: List[int], values: List[Any], rn: List[int], k: int = 3) -> List[Dict[str, Any]]:
    return [{"row": rn[i], "value": preview_cell(values[i]) or ""} for i in idx[:k]]


def _sample(values: List[Any], k: int = 300) -> List[Any]:
    vals = [v for v in values if not is_missing(v) and not is_placeholder(v)]
    if len(vals) <= k:
        return vals
    step = len(vals) / k
    return [vals[int(i * step)] for i in range(k)]


def _detect_type(values: List[Any]) -> str:
    sample = _sample(values)
    if not sample:
        return "empty"
    n = len(sample)
    if sum(1 for v in sample if parse_date(v)[1] is not None) / n >= 0.7:
        return "date"
    if sum(1 for v in sample if parse_number(v)[1] is not None) / n >= 0.7:
        return "numeric"
    return "text"


def _fmt_num(x: float) -> str:
    return f"{x:,.0f}" if abs(x) >= 1000 or float(x).is_integer() else f"{x:,.2f}"


# ------------------------------------------------------------------ từng loại cột
def _outlier_bounds(arr: np.ndarray) -> Optional[Dict[str, Any]]:
    if len(arr) < 30:
        return None
    pos = arr[arr > 0]
    if len(pos) / len(arr) >= 0.9 and np.median(pos) > 0 and pos.max() / np.median(pos) > 20:
        lg = np.log10(pos)
        q1, q3 = np.percentile(lg, [25, 75])
        if q3 - q1 == 0:
            return None
        return {"lower": None, "upper": float(10 ** (q3 + 1.5 * (q3 - q1))), "method": "log"}
    q1, q3 = np.percentile(arr, [25, 75])
    iqr = q3 - q1
    if iqr == 0:
        if not np.all(np.mod(arr, 1) == 0):
            return None
        iqr = 1.0
    return {"lower": float(q1 - 3 * iqr), "upper": float(q3 + 3 * iqr), "method": "iqr"}


def _analyze_numeric(name, key, values, rn, file_type, issues, sugg, side, n_valid):
    idx, vals, dirty, bad, kinds = [], [], [], [], Counter()
    for i, v in enumerate(values):
        if is_missing(v) or is_placeholder(v):
            continue
        val, kind = parse_number(v)
        if kind is None:
            bad.append(i)
            continue
        idx.append(i)
        vals.append(val)
        kinds[kind] += 1
        if kind == "dirty":
            dirty.append(i)
    arr = np.array(vals, dtype=float)
    side["numeric"] = dict(zip(idx, vals))
    stats: Dict[str, Any] = {}
    if len(arr):
        stats = {"n": len(arr), "min": float(arr.min()), "max": float(arr.max()), "mean": float(arr.mean()),
                 "median": float(np.median(arr)), "std": float(arr.std()), "integer": bool(np.all(np.mod(arr, 1) == 0))}

    if dirty:
        issues.append(_issue("number_dirty", _ratio_sev(len(dirty), n_valid),
                             f"{len(dirty)} ô có đơn vị/ký hiệu đi kèm số (ví dụ “1.250.000đ”, “2 cái”)", len(dirty), _examples(dirty, values, rn)))
    text_nums = [i for i in idx if kinds and parse_number(values[i])[1] == "text" and isinstance(values[i], str)]
    if file_type == "excel" and text_nums and kinds["native"] >= len(text_nums):
        issues.append(_issue("number_as_text", "warn", f"{len(text_nums)} ô số đang lưu dạng chữ trong Excel", len(text_nums), _examples(text_nums, values, rn)))
        dirty = dirty + text_nums
    if bad:
        issues.append(_issue("not_a_number", _ratio_sev(len(bad), n_valid),
                             f"{len(bad)} ô không phải số trong cột số (ví dụ “{preview_cell(values[bad[0]])}”)", len(bad), _examples(bad, values, rn)))
    if dirty or bad:
        sugg.append({"id": f"parse_numbers:{name}", "action": "parse_numbers", "column": name, "severity": "warn", "selected": True,
                     "title": f"Chuyển cột “{name}” về dạng số",
                     "description": "Bỏ đơn vị/ký hiệu đi kèm (đ, cái...) và đọc dấu chấm/phẩy ngăn cách. Ô không đọc được thành số sẽ để trống (không tự điền số).",
                     "affected": len(dirty) + len(bad), "params": {}})

    if len(arr) < 30:
        return stats
    flagged_range = None
    pct = "%" in name or "phan tram" in key
    if SCORE_RE.search(key) or pct:
        lo_hi = (0.0, 100.0) if pct else ((0.0, 10.0) if np.mean((arr >= 0) & (arr <= 10)) >= 0.9 else
                                          ((0.0, 100.0) if np.mean((arr >= 0) & (arr <= 100)) >= 0.9 else None))
        if lo_hi:
            flagged_range = lo_hi
            bad_idx = [i for i, v in zip(idx, vals) if v < lo_hi[0] or v > lo_hi[1]]
            if bad_idx:
                issues.append(_issue("out_of_range", "high", f"{len(bad_idx)} giá trị ngoài khoảng hợp lệ {lo_hi[0]:g}–{lo_hi[1]:g}", len(bad_idx), _examples(bad_idx, values, rn)))
                sugg.append({"id": f"set_missing:{name}:range", "action": "set_missing", "column": name, "severity": "high", "selected": False,
                             "title": f"Để trống giá trị ngoài khoảng {lo_hi[0]:g}–{lo_hi[1]:g} ở cột “{name}”",
                             "description": "Các giá trị này gần như chắc chắn là nhập sai. Bạn nên đối chiếu nguồn gốc trước khi để trống.",
                             "affected": len(bad_idx), "params": {"lower": lo_hi[0], "upper": lo_hi[1]}})
    if flagged_range is None:
        neg = [i for i, v in zip(idx, vals) if v < 0]
        if neg and len(neg) / len(arr) <= 0.05:
            issues.append(_issue("negative", "warn", f"{len(neg)} giá trị âm bất thường (có thể là đơn trả hàng hoặc nhập sai)", len(neg), _examples(neg, values, rn)))
            sugg.append({"id": f"set_missing:{name}:negative", "action": "set_missing", "column": name, "severity": "warn", "selected": False,
                         "title": f"Để trống giá trị âm ở cột “{name}”",
                         "description": "Chỉ nên chọn nếu các giá trị âm là lỗi. Nếu là đơn trả hàng thì hãy giữ nguyên.",
                         "affected": len(neg), "params": {"lower": 0.0, "upper": None}})
        id_like = NAME_ID_RE.search(key) or (stats.get("integer") and len(set(vals)) / len(vals) > 0.95)
        b = None if id_like else _outlier_bounds(arr)
        if b:
            out = [i for i, v in zip(idx, vals) if (b["upper"] is not None and v > b["upper"]) or (b["lower"] is not None and v < b["lower"] and v >= 0)]
            if out:
                shown = _fmt_num(b["upper"])
                issues.append(_issue("outlier", "warn", f"{len(out)} giá trị bất thường (vượt xa phần còn lại, ngưỡng khoảng {shown})", len(out), _examples(out, values, rn)))
                sugg.append({"id": f"set_missing:{name}:outlier", "action": "set_missing", "column": name, "severity": "warn", "selected": False,
                             "title": f"Để trống giá trị bất thường ở cột “{name}”",
                             "description": f"Các giá trị vượt ngưỡng khoảng {shown} (tính bằng khoảng tứ phân vị). Có thể là nhập sai hoặc ngoại lệ thật; hãy xem lại trước khi chọn.",
                             "affected": len(out), "params": {"lower": b["lower"] if b["method"] == "iqr" else None, "upper": b["upper"]}})
    return stats


def _analyze_date(name, values, rn, file_type, issues, sugg, side, n_valid):
    valid, invalid, bad = [], [], []
    fmts: Counter = Counter()
    dates = {}
    for i, v in enumerate(values):
        if is_missing(v) or is_placeholder(v):
            continue
        d, kind, fmt = parse_date(v)
        if kind is None:
            bad.append(i)
        elif kind == "invalid":
            invalid.append(i)
        else:
            valid.append(i)
            dates[i] = d
            fmts[fmt] += 1
    side["dates"] = dates
    stats: Dict[str, Any] = {"formats": dict(fmts)}
    if dates:
        ds = sorted(dates.values())
        stats.update(min=ds[0].isoformat(), max=ds[-1].isoformat(), n_months=len({(d.year, d.month) for d in ds}))
    text_fmts = {f: c for f, c in fmts.items() if f != "native"}
    need_fix = False
    if file_type == "excel" and "native" in fmts and text_fmts:
        n = sum(text_fmts.values())
        issues.append(_issue("date_as_text", _ratio_sev(n, n_valid), f"{n} ô ngày đang lưu dạng chữ trong khi các ô còn lại là ngày thật của Excel", n,
                             _examples([i for i in valid if parse_date(values[i])[1] == "text"], values, rn)))
        need_fix = True
    if len(fmts) > 1 and not ("native" in fmts and len(text_fmts) == 1):
        listing = ", ".join(f"{f} ({c})" for f, c in fmts.most_common())
        issues.append(_issue("date_mixed_format", "warn", f"Cột ngày có {len(fmts)} định dạng khác nhau: {listing}", sum(fmts.values()) - fmts.most_common(1)[0][1]))
        need_fix = True
    if invalid:
        issues.append(_issue("date_invalid", _ratio_sev(len(invalid), n_valid),
                             f"{len(invalid)} ngày không hợp lệ (ví dụ “{preview_cell(values[invalid[0]])}”)", len(invalid), _examples(invalid, values, rn)))
        need_fix = True
    if bad:
        issues.append(_issue("not_a_date", _ratio_sev(len(bad), n_valid), f"{len(bad)} ô không phải ngày trong cột ngày (ví dụ “{preview_cell(values[bad[0]])}”)", len(bad), _examples(bad, values, rn)))
        need_fix = True
    if need_fix:
        sugg.append({"id": f"parse_dates:{name}", "action": "parse_dates", "column": name, "severity": "warn", "selected": True,
                     "title": f"Chuẩn hóa cột “{name}” về dạng ngày yyyy-mm-dd",
                     "description": "Ngày dạng chữ được đọc theo thứ tự ngày/tháng/năm (dd/mm/yyyy). Ngày không hợp lệ hoặc không đọc được sẽ để trống, không tự đoán.",
                     "affected": len(invalid) + len(bad) + (sum(text_fmts.values()) if "native" in fmts else sum(fmts.values()) - fmts.most_common(1)[0][1]), "params": {}})
    return stats


def _variant_groups(values: List[Any]) -> List[Dict[str, Any]]:
    groups: Dict[str, Counter] = {}
    for v in values:
        if not isinstance(v, str) or is_missing(v) or is_placeholder(v):
            continue
        t = collapse_spaces(v)
        groups.setdefault(norm_key(t), Counter())[t] += 1
    return [{"canonical": c.most_common(1)[0][0], "variants": dict(c)} for c in groups.values() if len(c) > 1]


# ------------------------------------------------------------------ chính
def build_profile(table: Table) -> Dict[str, Any]:
    df = table.df
    names = list(df.columns)
    n = len(df)
    rn = table.row_numbers
    cols_vals = {c: df[c].tolist() for c in names}
    suggestions: List[Dict[str, Any]] = []
    columns: List[Dict[str, Any]] = []
    side: Dict[str, Dict[str, Any]] = {}
    ws_cols: List[Dict[str, Any]] = []
    total_missing = 0

    for pos, name in enumerate(names):
        values = cols_vals[name]
        key = norm_key(name)
        issues: List[Dict[str, Any]] = []
        sugg: List[Dict[str, Any]] = []
        s: Dict[str, Any] = {}
        side[name] = s

        miss = [i for i, v in enumerate(values) if is_missing(v)]
        ph = [i for i, v in enumerate(values) if is_placeholder(v)]
        n_valid = n - len(miss)
        total_missing += len(miss)
        ctype = _detect_type(values)
        uniq = {v for i, v in enumerate(values) if not is_missing(v)}
        n_unique = len(uniq)

        if ctype == "text":
            if NAME_ID_RE.search(key) and n_unique > 30:
                ctype = "id"
            elif n_unique <= max(30, 0.05 * max(n_valid, 1)):
                ctype = "category"

        stats: Dict[str, Any] = {}
        if ctype == "numeric":
            stats = _analyze_numeric(name, key, values, rn, table.file_type, issues, sugg, s, n_valid)
        elif ctype == "date":
            stats = _analyze_date(name, values, rn, table.file_type, issues, sugg, s, n_valid)

        if ph:
            tokens = sorted({str(values[i]).strip() for i in ph})
            issues.append(_issue("placeholder", "warn", f"{len(ph)} ô dùng ký hiệu thay cho dữ liệu thiếu ({', '.join('“' + t + '”' for t in tokens[:5])})", len(ph), _examples(ph, values, rn)))
            sugg.append({"id": f"placeholder_to_missing:{name}", "action": "placeholder_to_missing", "column": name, "severity": "warn", "selected": True,
                         "title": f"Coi ký hiệu thay cho dữ liệu thiếu ở cột “{name}” là ô trống",
                         "description": f"Các ký hiệu: {', '.join(tokens[:8])}.", "affected": len(ph), "params": {}})
        if miss:
            sev = "info" if len(miss) / n <= 0.05 else ("warn" if len(miss) / n <= 0.2 else "high")
            issues.append(_issue("missing", sev, f"Thiếu {len(miss)} ô ({len(miss) / n:.1%})", len(miss), _examples(miss, values, [r for r in rn])))

        if ctype in ("text", "category", "id"):
            ws = [i for i, v in enumerate(values) if isinstance(v, str) and v.strip() and v != collapse_spaces(v)]
            if ws:
                issues.append(_issue("whitespace", "info", f"{len(ws)} ô có khoảng trắng thừa ở đầu/cuối hoặc giữa chữ", len(ws), _examples(ws, values, rn)))
                ws_cols.append({"column": name, "count": len(ws)})
            if ctype in ("text", "category") and n_unique <= 500:
                groups = _variant_groups(values)
                if groups:
                    mapping, affected = {}, 0
                    for g in groups:
                        for var, cnt in g["variants"].items():
                            if var != g["canonical"]:
                                mapping[var] = g["canonical"]
                                affected += cnt
                    ex = [{"row": None, "value": f"{', '.join(g['variants'])} → {g['canonical']}"} for g in groups[:3]]
                    issues.append(_issue("category_variants", "warn", f"Cùng một nhóm nhưng viết khác nhau ({len(groups)} nhóm, {affected} ô cần thống nhất)", affected, ex))
                    sugg.append({"id": f"unify_categories:{name}", "action": "unify_categories", "column": name, "severity": "warn", "selected": True,
                                 "title": f"Thống nhất cách viết các nhóm ở cột “{name}”",
                                 "description": "Gộp các biến thể (hoa/thường, có/không dấu, khoảng trắng) về cách viết phổ biến nhất: " +
                                                "; ".join(f"{', '.join(v for v in g['variants'] if v != g['canonical'])} → {g['canonical']}" for g in groups[:4]),
                                 "affected": affected, "params": {"mapping": mapping}})
            stats = {"top_values": Counter(collapse_spaces(v) for v in values if isinstance(v, str) and not is_missing(v)).most_common(6)} if n_unique <= 500 else {}

        columns.append({
            "name": name, "position": pos + 1, "type": ctype, "type_label": TYPE_LABEL[ctype], "n_valid": n_valid,
            "n_missing": len(miss), "pct_missing": round(len(miss) / n, 4) if n else 0, "n_placeholder": len(ph), "n_unique": n_unique,
            "samples": [preview_cell(v) for v in list(dict.fromkeys(v for v in values if not is_missing(v)))[:3]],
            "stats": stats, "issues": issues,
        })
        suggestions.extend(sugg)

    # ---- trùng lặp
    dup_mask = df.duplicated(keep="first").tolist()
    dup_idx = [i for i, d in enumerate(dup_mask) if d]
    key_cols = []
    for c in columns:
        if c["type"] == "id" and c["n_valid"] and c["n_unique"] / c["n_valid"] >= 0.9:
            seen, repeats = set(), []
            for i, v in enumerate(cols_vals[c["name"]]):
                if is_missing(v):
                    continue
                if v in seen:
                    repeats.append(i)
                seen.add(v)
            if repeats:
                key_cols.append({"column": c["name"], "count": len(repeats), "also_full_duplicate": sum(1 for i in repeats if dup_mask[i])})
    duplicates = {"full_rows": len(dup_idx), "example_rows": [rn[i] for i in dup_idx[:5]], "key_columns": key_cols}

    # ---- gợi ý ánh xạ cột + kiểm tra quan hệ
    mapping = suggest_mapping(columns)
    relationships = _relationships(columns, side, mapping, rn)

    # ---- gợi ý theo vai trò cột
    col_by_name = {c["name"]: c for c in columns}
    for role in ("date", "amount", "customer_id"):
        m = mapping["suggested"].get(role)
        if m and col_by_name[m["column"]]["n_missing"] > 0:
            c = col_by_name[m["column"]]
            suggestions.append({"id": f"drop_rows_missing:{c['name']}", "action": "drop_rows_missing", "column": c["name"], "severity": "info", "selected": False,
                                "title": f"Xóa các dòng thiếu “{c['name']}”",
                                "description": "Cột này cần thiết cho phân tích. Các dòng thiếu sẽ bị loại bỏ (không điền giá trị giả).",
                                "affected": c["n_missing"], "params": {}})
    for c in columns:
        if c["type"] == "category" and c["n_missing"] > 0:
            suggestions.append({"id": f"fill_label:{c['name']}", "action": "fill_label", "column": c["name"], "severity": "info", "selected": False,
                                "title": f"Gán nhãn “Không rõ” cho ô thiếu ở cột “{c['name']}”",
                                "description": "Chỉ gắn nhãn văn bản để giữ lại dòng khi thống kê theo nhóm; không tạo số liệu.",
                                "affected": c["n_missing"], "params": {"label": "Không rõ"}})

    if ws_cols:
        suggestions.insert(0, {"id": "trim_text", "action": "trim_text", "column": "", "severity": "info", "selected": True,
                               "title": "Cắt khoảng trắng thừa trong các ô văn bản",
                               "description": "Áp dụng cho các cột: " + ", ".join(w["column"] for w in ws_cols),
                               "affected": sum(w["count"] for w in ws_cols), "params": {"columns": [w["column"] for w in ws_cols]}})
    if dup_idx:
        suggestions.append({"id": "drop_duplicates", "action": "drop_duplicates", "column": "", "severity": "warn", "selected": True,
                            "title": "Xóa các dòng trùng lặp hoàn toàn (giữ lại dòng đầu tiên)",
                            "description": "Chỉ xóa những dòng giống hệt dòng trước đó ở mọi cột. Sau khi chuẩn hóa định dạng có thể phát hiện thêm dòng trùng.",
                            "affected": len(dup_idx), "params": {}})

    notes = []
    if any("dd/mm/yyyy" in str(c["stats"].get("formats", {})) or "dd-mm-yyyy" in str(c["stats"].get("formats", {})) for c in columns if c["type"] == "date"):
        notes.append("Ngày dạng chữ được đọc theo thứ tự ngày/tháng/năm (dd/mm/yyyy), quy ước phổ biến ở Việt Nam.")
    if table.info.get("dropped_empty_rows"):
        notes.append(f"Đã bỏ qua {table.info['dropped_empty_rows']} dòng trống hoàn toàn khi đọc tệp.")
    if table.info.get("dropped_empty_cols"):
        notes.append(f"Đã bỏ qua {table.info['dropped_empty_cols']} cột trống không có tiêu đề.")

    facts = {
        "date_months": {c["name"]: c["stats"].get("n_months", 0) for c in columns if c["type"] == "date"},
        "date_range": {c["name"]: [c["stats"].get("min"), c["stats"].get("max")] for c in columns if c["type"] == "date"},
        "distinct": {c["name"]: c["n_unique"] for c in columns if c["type"] in ("id", "text", "category")},
        "types": {c["name"]: c["type"] for c in columns},
    }
    summary = {
        "n_rows": n, "n_cols": len(names), "n_duplicates": len(dup_idx), "n_missing_cells": total_missing,
        "pct_missing_cells": round(total_missing / (n * len(names)), 4) if n and names else 0,
        "n_columns_with_issues": sum(1 for c in columns if any(i["severity"] != "info" for i in c["issues"])),
        "file_type": table.file_type, "sheet": table.sheet, "header_row": table.info.get("header_row"),
        "encoding": table.info.get("encoding"), "delimiter": table.info.get("delimiter"),
    }
    preview = {
        "columns": names,
        "rows": [[preview_cell(v) for v in df.iloc[i].tolist()] for i in range(min(20, n))],
        "row_numbers": rn[:20],
    }
    return {"summary": summary, "columns": columns, "duplicates": duplicates, "relationships": relationships, "mapping": mapping,
            "suggestions": suggestions, "facts": facts, "notes": notes, "preview": preview}


def _robust_fit(X: np.ndarray, y: np.ndarray, tol: float = 0.1, iters: int = 300):
    """Hồi quy bền vững (RANSAC đơn giản) để vài dòng nhập sai không làm lệch công thức ước lượng."""
    n, k = X.shape
    rng = np.random.default_rng(0)
    best = None
    for _ in range(iters):
        sel = rng.choice(n, k, replace=False)
        try:
            w = np.linalg.solve(X[sel], y[sel])
        except np.linalg.LinAlgError:
            continue
        inl = np.abs(y - X @ w) <= tol
        if best is None or inl.sum() > best.sum():
            best = inl
    if best is None or best.sum() < max(k + 1, 0.7 * n):
        return None
    w, *_ = np.linalg.lstsq(X[best], y[best], rcond=None)
    best = np.abs(y - X @ w) <= tol
    w, *_ = np.linalg.lstsq(X[best], y[best], rcond=None)
    res = np.abs(y - X @ w)
    ss_res = float(np.sum((y[best] - X[best] @ w) ** 2))
    ss_tot = float(np.sum((y[best] - y[best].mean()) ** 2))
    r2 = 1 - ss_res / ss_tot if ss_tot else 0.0
    return w, res, r2, float(best.mean())


# ------------------------------------------------------------------ quan hệ giữa các cột
def _relationships(columns, side, mapping, rn) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    sg = mapping["suggested"]

    if all(r in sg for r in ("amount", "quantity", "unit_price")):
        amt, qty, prc = (side[sg[r]["column"]].get("numeric", {}) for r in ("amount", "quantity", "unit_price"))
        disc = side[sg["discount"]["column"]].get("numeric", {}) if "discount" in sg else None
        idx = [i for i in amt if i in qty and i in prc and (disc is None or i in disc)]
        bad = []
        for i in idx:
            expected = qty[i] * prc[i] * (1 - (disc[i] if disc else 0) / 100)
            if abs(amt[i] - expected) > max(1000, 0.01 * abs(expected)):
                bad.append((i, amt[i], expected))
        label = f"{sg['amount']['column']} = {sg['quantity']['column']} × {sg['unit_price']['column']}" + (f" × (1 − {sg['discount']['column']}/100)" if disc else "")
        out.append({"code": "amount_formula", "ok": not bad, "checked": len(idx), "count": len(bad),
                    "message": (f"Đã kiểm tra {len(idx)} dòng đủ dữ liệu: " + (f"{len(bad)} dòng không khớp công thức {label}" if bad else f"tất cả khớp công thức {label}")),
                    "examples": [{"row": rn[i], "value": f"{a:,.0f} ≠ {e:,.0f}"} for i, a, e in bad[:3]]})

    nums = [c for c in columns if c["type"] == "numeric"]
    for t in [c for c in nums if re.search(r"(tong ket|tong diem|diem tong|^total)", norm_key(c["name"]))]:
        srcs = [c for c in nums if c["name"] != t["name"] and SCORE_RE.search(norm_key(c["name"]))]
        if len(srcs) < 2:
            continue
        y_map = side[t["name"]].get("numeric", {})
        maps = [side[c["name"]].get("numeric", {}) for c in srcs]
        idx = [i for i in y_map if all(i in m for m in maps)]
        if len(idx) < 30:
            continue
        X = np.array([[m[i] for m in maps] for i in idx])
        y = np.array([y_map[i] for i in idx])
        fit = _robust_fit(X, y)
        if fit is None:
            continue
        w, res, r2, share = fit
        if r2 < 0.995 or not 0.9 <= float(w.sum()) <= 1.1:
            continue
        bad = [idx[j] for j in np.flatnonzero(res > 0.15)]
        formula = " + ".join(f"{wi:.2f}×{c['name']}" for wi, c in zip(w, srcs))
        out.append({"code": "linear_total", "ok": not bad, "checked": len(idx), "count": len(bad),
                    "message": f"Ước lượng từ dữ liệu: {t['name']} ≈ {formula} (khớp với {share:.0%} số dòng). Có {len(bad)}/{len(idx)} dòng lệch hơn 0,15 so với công thức này; cần bạn xác nhận công thức thật.",
                    "examples": [{"row": rn[i], "value": f"{y_map[i]:g}"} for i in bad[:3]]})
    return out
