"""Áp dụng kế hoạch làm sạch do người dùng xác nhận.

Nguyên tắc: chỉ làm đúng các mục được chọn; không tự điền số liệu cho ô thiếu;
mọi thay đổi đều được đếm và báo cáo lại.
"""
import csv
import io
from typing import Any, Dict, List

from .loader import Table
from .parsing import (collapse_spaces, fmt_cell, is_missing, is_placeholder,
                      parse_date, parse_number)

ORDER = {"trim_text": 1, "placeholder_to_missing": 2, "parse_numbers": 3, "parse_dates": 4, "unify_categories": 5,
         "set_missing": 6, "fill_label": 7, "drop_rows_missing": 8, "drop_duplicates": 9}


def apply_plan(table: Table, plan: List[Dict[str, Any]]) -> Dict[str, Any]:
    df = table.df
    names = list(df.columns)
    pos = {c: i for i, c in enumerate(names)}
    rows = [list(r) for r in df.values.tolist()]
    rows_before = len(rows)
    applied: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []

    for item in sorted(plan, key=lambda p: ORDER.get(p.get("action"), 99)):
        action, col, params = item.get("action"), item.get("column") or "", item.get("params") or {}
        rec = {"id": item.get("id"), "action": action, "column": col, "affected": 0, "detail": ""}
        if action not in ORDER:
            skipped.append({**rec, "reason": "Hành động không được hỗ trợ."})
            continue
        if action not in ("trim_text", "drop_duplicates") and col not in pos:
            skipped.append({**rec, "reason": f"Không tìm thấy cột “{col}”."})
            continue

        if action == "trim_text":
            targets = [pos[c] for c in params.get("columns", names) if c in pos]
            n = 0
            for r in rows:
                for j in targets:
                    v = r[j]
                    if isinstance(v, str):
                        t = collapse_spaces(v)
                        if t != v:
                            r[j] = t if t else None
                            n += 1
            rec["affected"] = n

        elif action == "placeholder_to_missing":
            j, n = pos[col], 0
            for r in rows:
                if is_placeholder(r[j]):
                    r[j] = None
                    n += 1
            rec["affected"] = n

        elif action == "parse_numbers":
            j, conv, blank = pos[col], 0, 0
            for r in rows:
                v = r[j]
                if is_missing(v):
                    continue
                val, kind = parse_number(v)
                if kind is None:
                    r[j] = None
                    blank += 1
                elif kind != "native":
                    r[j] = int(val) if float(val).is_integer() else val
                    conv += 1
            rec["affected"] = conv + blank
            rec["detail"] = f"{conv} ô được chuyển thành số; {blank} ô không phải số được để trống."

        elif action == "parse_dates":
            j, conv, blank = pos[col], 0, 0
            for r in rows:
                v = r[j]
                if is_missing(v):
                    continue
                d, kind, _ = parse_date(v)
                if kind in ("native", "text"):
                    iso = d.isoformat()
                    if iso != v:
                        r[j] = iso
                        conv += 1 if kind == "text" else 0
                else:
                    r[j] = None
                    blank += 1
            rec["affected"] = conv + blank
            rec["detail"] = f"{conv} ô được chuẩn hóa về yyyy-mm-dd; {blank} ô không hợp lệ được để trống."

        elif action == "unify_categories":
            mp, j, n = params.get("mapping", {}), pos[col], 0
            for r in rows:
                v = r[j]
                if isinstance(v, str):
                    new = mp.get(collapse_spaces(v))
                    if new is not None and new != v:
                        r[j] = new
                        n += 1
            rec["affected"] = n

        elif action == "set_missing":
            lo, hi, j, n = params.get("lower"), params.get("upper"), pos[col], 0
            for r in rows:
                val, kind = parse_number(r[j])
                if kind is None:
                    continue
                if (lo is not None and val < lo) or (hi is not None and val > hi):
                    r[j] = None
                    n += 1
            rec["affected"] = n
            rec["detail"] = f"{n} giá trị được để trống (không tự điền số thay thế)."

        elif action == "fill_label":
            label, j, n = str(params.get("label") or "Không rõ"), pos[col], 0
            for r in rows:
                if is_missing(r[j]):
                    r[j] = label
                    n += 1
            rec["affected"] = n

        elif action == "drop_rows_missing":
            j = pos[col]
            before = len(rows)
            rows = [r for r in rows if not (is_missing(r[j]) or is_placeholder(r[j]))]
            rec["affected"] = before - len(rows)

        elif action == "drop_duplicates":
            seen, kept = set(), []
            for r in rows:
                key = tuple(r)
                if key in seen:
                    continue
                seen.add(key)
                kept.append(r)
            rec["affected"] = len(rows) - len(kept)
            rows = kept

        applied.append(rec)

    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(names)
    for r in rows:
        w.writerow([fmt_cell(v) for v in r])
    return {"csv": buf.getvalue().encode("utf-8-sig"), "rows_before": rows_before, "rows_after": len(rows),
            "n_cols": len(names), "applied": applied, "skipped": skipped}
