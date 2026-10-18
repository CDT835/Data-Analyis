"""Phân tích thống kê mô tả và doanh thu.

Mọi số liệu được tính trực tiếp từ dữ liệu. Các dòng không dùng được (thiếu ngày/số tiền) được đếm và báo lại,
không bị bỏ qua âm thầm.
"""
import re
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from .loader import LoadError, Table
from .parsing import (collapse_spaces, is_missing, is_placeholder, norm_key,
                      parse_date, parse_number)
from .profiler import NAME_ID_RE, _detect_type, _outlier_bounds

TEXT_ROLES = ("customer_id", "order_id", "category", "product", "region")
NUM_ROLES = ("amount", "quantity", "unit_price", "discount")
DIM_LABEL = {"category": "danh mục", "product": "sản phẩm", "region": "khu vực"}
WEEKDAYS = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ nhật"]


def _date(v):
    d, kind, _ = parse_date(v)
    return d if kind in ("native", "text") else None


def _num(v):
    val, kind = parse_number(v)
    return val if kind else float("nan")


def _txt(v):
    return None if (is_missing(v) or is_placeholder(v)) else collapse_spaces(str(v))


def prepare(table: Table, mapping: Dict[str, str]) -> pd.DataFrame:
    """Đưa các cột đã ánh xạ về đúng kiểu (ngày, số, văn bản). Ô không đọc được thành NaN/NaT/None."""
    df = table.df
    cols: Dict[str, Any] = {}
    for role, col in mapping.items():
        if col not in df.columns:
            continue
        vals = df[col].tolist()
        if role == "date":
            cols[role] = pd.to_datetime(pd.Series([_date(v) for v in vals], dtype=object))
        elif role in NUM_ROLES:
            cols[role] = pd.Series([_num(v) for v in vals], dtype=float)
        elif role in TEXT_ROLES:
            cols[role] = pd.Series([_txt(v) for v in vals], dtype=object)
    return pd.DataFrame(cols, index=range(len(df)))


def _f(x) -> float:
    return float(round(float(x), 4))


# ------------------------------------------------------------------ doanh thu
def revenue_block(typed: pd.DataFrame) -> Optional[Dict[str, Any]]:
    if "date" not in typed or "amount" not in typed:
        return None
    rev = typed.dropna(subset=["date", "amount"]).copy()
    out: Dict[str, Any] = {"rows_used": int(len(rev)), "rows_excluded": int(len(typed) - len(rev)),
                           "excluded_reason": "thiếu hoặc không đọc được ngày/số tiền"}
    if rev.empty:
        raise LoadError("Không có dòng nào có đủ ngày và số tiền hợp lệ để phân tích doanh thu.")

    total = float(rev["amount"].sum())
    neg = rev[rev["amount"] < 0]
    has_order = "order_id" in rev and rev["order_id"].notna().any()
    n_orders = int(rev["order_id"].nunique()) if has_order else int(len(rev))
    kpis = {
        "total_revenue": _f(total), "n_orders": n_orders, "orders_basis": "mã đơn hàng" if has_order else "số dòng",
        "avg_order_value": _f(total / n_orders) if n_orders else None,
        "date_min": rev["date"].min().date().isoformat(), "date_max": rev["date"].max().date().isoformat(),
        "n_negative_rows": int(len(neg)), "negative_total": _f(neg["amount"].sum()) if len(neg) else 0.0,
    }
    if "customer_id" in rev and rev["customer_id"].notna().any():
        kpis["n_customers"] = int(rev["customer_id"].nunique())
        per = rev.groupby("customer_id")["order_id"].nunique() if has_order else rev.groupby("customer_id").size()
        kpis["repeat_customer_rate"] = _f((per >= 2).mean())
    out["kpis"] = kpis

    rev["month"] = rev["date"].dt.to_period("M")
    g = rev.groupby("month")
    monthly = pd.DataFrame({"revenue": g["amount"].sum(), "rows": g.size()})
    if has_order:
        monthly["orders"] = g["order_id"].nunique()
    full = pd.period_range(monthly.index.min(), monthly.index.max(), freq="M")
    missing_months = [str(m) for m in full if m not in monthly.index]
    monthly = monthly.reindex(full, fill_value=0)
    rv = monthly["revenue"].to_numpy(float)
    mom = [None] + [(_f((rv[i] / rv[i - 1] - 1) * 100) if rv[i - 1] else None) for i in range(1, len(rv))]
    yoy = [(_f((rv[i] / rv[i - 12] - 1) * 100) if i >= 12 and rv[i - 12] else None) for i in range(len(rv))]
    out["monthly"] = {
        "months": [str(m) for m in full], "revenue": [_f(x) for x in rv], "rows": monthly["rows"].astype(int).tolist(),
        "orders": monthly["orders"].astype(int).tolist() if has_order else None, "mom_pct": mom, "yoy_pct": yoy,
        "missing_months": missing_months,
    }
    if len(rv) >= 6:
        slope = float(np.polyfit(np.arange(len(rv)), rv, 1)[0])
        out["trend"] = {"slope_per_month": _f(slope), "slope_pct_of_mean": _f(slope / rv.mean() * 100) if rv.mean() else None,
                        "direction": "tăng" if slope > 0 else "giảm",
                        "note": "Độ dốc của đường thẳng khớp với doanh thu theo tháng; chưa phải kết luận về nguyên nhân."}
    best, worst = int(np.argmax(rv)), int(np.argmin(rv))
    out["extremes"] = {"best_month": str(full[best]), "best_value": _f(rv[best]), "worst_month": str(full[worst]), "worst_value": _f(rv[worst])}

    wd = rev.groupby(rev["date"].dt.dayofweek)["amount"].sum().reindex(range(7), fill_value=0)
    out["weekday"] = {"labels": WEEKDAYS, "revenue": [_f(x) for x in wd.to_numpy()]}

    out["breakdowns"] = {}
    for role, label in DIM_LABEL.items():
        if role not in rev or not rev[role].notna().any():
            continue
        grp = rev.dropna(subset=[role]).groupby(role)["amount"].agg(["sum", "size"]).sort_values("sum", ascending=False)
        tot = float(grp["sum"].sum())
        top = grp.head(10)
        out["breakdowns"][role] = {
            "label": label, "n_groups": int(len(grp)), "n_missing": int(rev[role].isna().sum()),
            "items": [{"name": str(k), "revenue": _f(r["sum"]), "rows": int(r["size"]), "share_pct": _f(r["sum"] / tot * 100) if tot else None}
                      for k, r in top.iterrows()],
            "other_revenue": _f(grp["sum"].iloc[10:].sum()) if len(grp) > 10 else 0.0,
        }

    pos = rev.loc[rev["amount"] > 0, "amount"].to_numpy(float)
    if len(pos) >= 30:
        cap = float(np.percentile(pos, 99))
        counts, edges = np.histogram(pos[pos <= cap], bins=20)
        out["histogram"] = {"edges": [_f(e) for e in edges], "counts": counts.tolist(), "n_above_p99": int((pos > cap).sum()), "p99": _f(cap)}
        b = _outlier_bounds(pos)
        if b and b["upper"] is not None:
            big = rev[rev["amount"] > b["upper"]]
            if len(big):
                out["outlier_warning"] = {
                    "count": int(len(big)), "threshold": _f(b["upper"]),
                    "share_of_revenue_pct": _f(big["amount"].sum() / total * 100) if total else None,
                    "message": f"Có {len(big)} dòng có số tiền vượt xa phần còn lại (trên khoảng {b['upper']:,.0f}), chiếm "
                               f"{(big['amount'].sum() / total * 100) if total else 0:.1f}% tổng doanh thu. Hãy kiểm tra có phải nhập sai không, vì các dòng này có thể làm lệch kết quả.",
                }
    if missing_months:
        out["gap_warning"] = f"Có {len(missing_months)} tháng không có dữ liệu ({', '.join(missing_months[:6])}); các tháng này được tính là 0."
    return out


# ------------------------------------------------------------------ mô tả chung
def _is_id_like(name: str, values: List[Any]) -> bool:
    key = norm_key(name)
    nums = [v for v in (parse_number(x)[0] for x in values) if v == v and v is not None]
    return bool(NAME_ID_RE.search(key)) or (len(nums) > 20 and all(float(x).is_integer() for x in nums) and len(set(nums)) / len(nums) > 0.95)


def descriptive_block(table: Table) -> Dict[str, Any]:
    df = table.df
    numeric, categorical, series = [], [], {}
    for name in df.columns:
        values = df[name].tolist()
        t = _detect_type(values)
        if t == "numeric" and not _is_id_like(name, values):
            arr = np.array([_num(v) for v in values], dtype=float)
            valid = arr[~np.isnan(arr)]
            if len(valid) < 3:
                continue
            q1, med, q3 = np.percentile(valid, [25, 50, 75])
            numeric.append({"name": name, "n": int(len(valid)), "n_missing": int(len(arr) - len(valid)), "mean": _f(valid.mean()), "std": _f(valid.std(ddof=1)),
                            "min": _f(valid.min()), "q1": _f(q1), "median": _f(med), "q3": _f(q3), "max": _f(valid.max())})
            series[name] = pd.Series(arr)
        elif t == "text":
            vals = [collapse_spaces(str(v)) for v in values if not (is_missing(v) or is_placeholder(v))]
            uniq = len(set(vals))
            if vals and uniq <= 30 and not NAME_ID_RE.search(norm_key(name)):
                cnt = pd.Series(vals).value_counts()
                categorical.append({"name": name, "n": len(vals), "n_unique": uniq,
                                    "top": [{"value": str(k), "count": int(v), "pct": _f(v / len(vals) * 100)} for k, v in cnt.head(10).items()]})
    out: Dict[str, Any] = {"numeric": numeric[:15], "categorical": categorical[:10]}

    hist = []
    for item in numeric[:6]:
        arr = series[item["name"]].dropna().to_numpy(float)
        lo, hi = np.percentile(arr, [0.5, 99.5])
        if hi <= lo:
            continue
        inside = arr[(arr >= lo) & (arr <= hi)]
        counts, edges = np.histogram(inside, bins=10)
        hist.append({"name": item["name"], "edges": [_f(e) for e in edges], "counts": counts.tolist(), "n_outside": int(len(arr) - len(inside))})
    out["histograms"] = hist

    names = [n["name"] for n in numeric[:10]]
    if len(names) >= 2:
        data = pd.DataFrame({n: series[n] for n in names})
        corr = data.corr(min_periods=30)
        pairs = []
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                r = corr.loc[a, b]
                n_pair = int(data[[a, b]].dropna().shape[0])
                if r == r and abs(r) >= 0.5 and n_pair >= 30:
                    pairs.append({"a": a, "b": b, "r": _f(r), "n": n_pair})
        pairs.sort(key=lambda p: -abs(p["r"]))
        out["correlations"] = {"columns": names, "matrix": [[(None if corr.loc[a, b] != corr.loc[a, b] else _f(corr.loc[a, b])) for b in names] for a in names],
                               "strong_pairs": pairs[:10],
                               "note": "Hệ số tương quan Pearson cho biết hai cột biến thiên cùng nhau, không chứng minh quan hệ nhân quả."}
    return out


def run_stats(table: Table, mapping: Dict[str, str]) -> Dict[str, Any]:
    typed = prepare(table, mapping)
    result: Dict[str, Any] = {"n_rows": int(len(table.df)), "mapping_used": mapping, "mode": "revenue" if ("date" in typed and "amount" in typed) else "general"}
    result["revenue"] = revenue_block(typed)
    result["descriptive"] = descriptive_block(table)
    notes: List[str] = []
    if result["mode"] == "general":
        notes.append("Bộ dữ liệu này chưa ánh xạ đủ cột ngày và số tiền nên chỉ có thống kê mô tả chung; không có phân tích doanh thu.")
    result["notes"] = notes
    return result
