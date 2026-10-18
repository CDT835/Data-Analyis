"""Machine Learning: phân nhóm khách hàng (RFM + K-Means) và dự báo doanh thu theo tháng.

Nguyên tắc: tách tập huấn luyện/kiểm thử theo thời gian (không xáo trộn), đánh giá bằng chỉ số phù hợp,
luôn so sánh với mô hình đơn giản (baseline) và nêu rõ giới hạn; không khẳng định dự đoán chắc chắn đúng.
"""
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from .analytics import _f, prepare
from .loader import LoadError, Table


# ====================================================================== RFM + K-Means
def _label(r_z: float, f_z: float, m_z: float) -> str:
    if m_z > 0.5 and f_z > 0.5 and r_z < 0.3:
        return "Khách hàng giá trị cao (mua nhiều, chi nhiều, mua gần đây)"
    if r_z > 0.5 and m_z < 0.5:
        return "Khách hàng có nguy cơ rời bỏ (lâu chưa mua, giá trị thấp)"
    if r_z > 0.5:
        return "Khách hàng lâu chưa quay lại (từng chi khá)"
    if f_z > 0 and m_z > 0:
        return "Khách hàng trung thành (mua đều, chi trên trung bình)"
    if r_z < 0 and f_z < 0 and m_z < 0:
        return "Khách hàng ít mua nhưng còn hoạt động"
    return "Khách hàng trung bình"


def run_rfm(table: Table, mapping: Dict[str, str], k: Optional[int] = None) -> Dict[str, Any]:
    from sklearn.cluster import KMeans
    from sklearn.metrics import davies_bouldin_score, silhouette_score
    from sklearn.preprocessing import StandardScaler

    for role, label in (("customer_id", "Mã khách hàng"), ("date", "ngày"), ("amount", "số tiền")):
        if role not in mapping:
            raise LoadError(f"Phân nhóm RFM cần ánh xạ cột {label}.")
    typed = prepare(table, mapping)
    d = typed.dropna(subset=["customer_id", "date", "amount"])
    if d.empty:
        raise LoadError("Không có dòng nào đủ mã khách hàng, ngày và số tiền hợp lệ.")
    ref = d["date"].max().normalize() + pd.Timedelta(days=1)
    has_order = "order_id" in d and d["order_id"].notna().any()
    g = d.groupby("customer_id")
    rfm = pd.DataFrame({
        "R": (ref - g["date"].max()).dt.days.astype(float),
        "F": (g["order_id"].nunique() if has_order else g.size()).astype(float),
        "M": g["amount"].sum().astype(float),
    })
    n_nonpos = int((rfm["M"] <= 0).sum())
    rfm = rfm[rfm["M"] > 0]
    n = len(rfm)
    if n < 20:
        raise LoadError(f"Chỉ có {n} khách hàng hợp lệ, cần ít nhất 20 để phân nhóm có ý nghĩa.")

    X = StandardScaler().fit_transform(np.column_stack([rfm["R"], np.log1p(rfm["F"]), np.log1p(rfm["M"])]))
    k_max = min(8, n // 10)
    models, cands = {}, []
    for kk in range(2, k_max + 1):
        km = KMeans(n_clusters=kk, n_init=10, random_state=42).fit(X)
        models[kk] = km
        cands.append({
            "k": kk, "inertia": _f(km.inertia_),
            "silhouette": _f(silhouette_score(X, km.labels_, sample_size=min(n, 5000), random_state=42)),
            "davies_bouldin": _f(davies_bouldin_score(X, km.labels_)),
        })
    best_k = max(cands, key=lambda c: c["silhouette"])["k"]
    chosen = k if (k and k in models) else best_k
    km = models[chosen]
    chosen_row = next(c for c in cands if c["k"] == chosen)

    rfm = rfm.assign(raw=km.labels_)
    order = rfm.groupby("raw")["M"].mean().sort_values(ascending=False).index.tolist()
    remap = {old: i + 1 for i, old in enumerate(order)}
    rfm["cluster"] = rfm["raw"].map(remap)
    total_rev = float(rfm["M"].sum())

    clusters, seen = [], {}
    for old in order:
        sub = rfm[rfm["raw"] == old]
        z = km.cluster_centers_[old]
        name = _label(float(z[0]), float(z[1]), float(z[2]))
        seen[name] = seen.get(name, 0) + 1
        if seen[name] > 1:
            name = f"{name} – nhóm {seen[name]}"
        clusters.append({
            "id": remap[old], "label": name, "size": int(len(sub)), "share_pct": _f(len(sub) / n * 100),
            "mean_recency_days": _f(sub["R"].mean()), "mean_frequency": _f(sub["F"].mean()), "mean_monetary": _f(sub["M"].mean()),
            "median_monetary": _f(sub["M"].median()), "revenue": _f(sub["M"].sum()), "revenue_share_pct": _f(sub["M"].sum() / total_rev * 100) if total_rev else None,
            "z_scores": {"recency": _f(z[0]), "frequency": _f(z[1]), "monetary": _f(z[2])},
        })

    sil = chosen_row["silhouette"]
    level = "rõ ràng" if sil > 0.5 else ("yếu" if sil >= 0.25 else "rất yếu")
    quality = {"level": level, "silhouette": sil, "message":
               f"Hệ số silhouette = {sil:.2f}: cấu trúc nhóm {level} (theo quy ước >0,5 là rõ ràng; 0,25–0,5 là yếu; <0,25 gần như không có cấu trúc nhóm riêng)."}
    limitations = [
        f"Phân nhóm dựa trên {n} khách hàng với 3 đặc trưng R (số ngày kể từ lần mua cuối), F ({'số đơn' if has_order else 'số dòng giao dịch'}) và M (tổng chi tiêu); F và M được lấy log để giảm lệch.",
        f"Số nhóm {chosen} được chọn {'theo yêu cầu của bạn' if (k and k in models) else 'tự động theo hệ số silhouette cao nhất'}; chọn số nhóm khác có thể cho cách chia khác.",
        "Tên nhóm là gợi ý tự động dựa trên so sánh với mức trung bình toàn bộ khách hàng, bạn cần xem lại bảng số liệu trước khi dùng.",
        "K-Means khởi tạo ngẫu nhiên (đã cố định hạt giống để kết quả lặp lại được) và nhạy với giá trị cực đoan.",
    ]
    if n_nonpos:
        limitations.append(f"{n_nonpos} khách hàng có tổng chi tiêu ≤ 0 (ví dụ do trả hàng) bị loại khỏi phân nhóm.")
    small = [c for c in clusters if c["share_pct"] < 5]
    if small:
        limitations.append(f"Có {len(small)} nhóm chiếm dưới 5% khách hàng, kết quả của các nhóm nhỏ kém ổn định.")

    rng = np.random.default_rng(42)
    idx = rng.choice(n, size=min(n, 400), replace=False)
    sample = rfm.iloc[idx]
    top = rfm.sort_values("M", ascending=False).head(30)
    return {
        "reference_date": ref.date().isoformat(), "n_customers": n, "n_excluded_nonpositive": n_nonpos, "n_rows_used": int(len(d)),
        "frequency_basis": "mã đơn hàng" if has_order else "số dòng giao dịch",
        "k_candidates": cands, "k_chosen": chosen, "k_best_silhouette": best_k, "k_selected_by": "người dùng" if (k and k in models) else "silhouette",
        "metrics": {"silhouette": sil, "davies_bouldin": chosen_row["davies_bouldin"], "inertia": chosen_row["inertia"]},
        "quality": quality, "clusters": clusters,
        "scatter": [{"f": _f(r.F), "m": _f(r.M), "r": _f(r.R), "c": int(r.cluster)} for r in sample.itertuples()],
        "top_customers": [{"customer": str(i), "recency_days": _f(r.R), "frequency": _f(r.F), "monetary": _f(r.M), "cluster": int(r.cluster)} for i, r in top.iterrows()],
        "limitations": limitations,
    }


# ====================================================================== Dự báo doanh thu
def _naive(y, h, start):
    return np.repeat(y[-1], h)


def _ma3(y, h, start):
    return np.repeat(y[-3:].mean(), h)


def _linear(y, h, start):
    from sklearn.linear_model import LinearRegression
    t = np.arange(len(y)).reshape(-1, 1)
    return LinearRegression().fit(t, y).predict(np.arange(len(y), len(y) + h).reshape(-1, 1))


def _holt(y, h, start):
    best = None
    for a in (0.2, 0.4, 0.6, 0.8):
        for b in (0.1, 0.3, 0.5):
            level, trend, sse = y[0], y[1] - y[0], 0.0
            for t in range(1, len(y)):
                sse += (y[t] - (level + trend)) ** 2
                new = a * y[t] + (1 - a) * (level + trend)
                trend = b * (new - level) + (1 - b) * trend
                level = new
            if best is None or sse < best[0]:
                best = (sse, level, trend)
    return best[1] + best[2] * np.arange(1, h + 1)


def _snaive(y, h, start):
    return np.array([y[len(y) - 12 + (j % 12)] for j in range(h)])


def _ridge_season(y, h, start):
    from sklearn.linear_model import Ridge

    def feats(lo, hi):
        rows = []
        for t in range(lo, hi):
            month = (start + t).month
            rows.append([t] + [1.0 if month == m else 0.0 for m in range(2, 13)])
        return np.array(rows, dtype=float)

    return Ridge(alpha=1.0).fit(feats(0, len(y)), y).predict(feats(len(y), len(y) + h))


MODELS = [
    ("naive", "Baseline: lấy giá trị tháng gần nhất", _naive, True, 0),
    ("ma3", "Baseline: trung bình 3 tháng gần nhất", _ma3, True, 0),
    ("linear", "Hồi quy tuyến tính theo thời gian (Scikit-learn)", _linear, False, 0),
    ("holt", "Làm mượt mũ Holt (xu hướng tuyến tính)", _holt, False, 0),
    ("snaive", "Baseline mùa vụ: lấy cùng tháng năm trước", _snaive, True, 24),
    ("ridge_season", "Hồi quy Ridge có xu hướng và mùa vụ (Scikit-learn)", _ridge_season, False, 24),
]


def _metrics(actual: np.ndarray, pred: np.ndarray) -> Dict[str, Optional[float]]:
    err = actual - pred
    nz = actual != 0
    return {"mae": _f(np.mean(np.abs(err))), "rmse": _f(np.sqrt(np.mean(err ** 2))),
            "mape": _f(np.mean(np.abs(err[nz] / actual[nz])) * 100) if nz.any() else None}


def run_forecast(table: Table, mapping: Dict[str, str], horizon: int = 3) -> Dict[str, Any]:
    for role, label in (("date", "ngày"), ("amount", "số tiền")):
        if role not in mapping:
            raise LoadError(f"Dự báo doanh thu cần ánh xạ cột {label}.")
    typed = prepare(table, mapping)
    rev = typed.dropna(subset=["date", "amount"])
    if rev.empty:
        raise LoadError("Không có dòng nào có đủ ngày và số tiền hợp lệ.")
    monthly = rev.groupby(rev["date"].dt.to_period("M"))["amount"].sum()

    dropped: List[str] = []
    first, last = monthly.index[0], monthly.index[-1]
    if rev["date"].min().normalize() > first.start_time + pd.Timedelta(days=3):
        dropped.append(str(first))
        monthly = monthly.iloc[1:]
    if len(monthly) and rev["date"].max().normalize() < last.end_time.normalize() - pd.Timedelta(days=2):
        dropped.append(str(last))
        monthly = monthly.iloc[:-1]
    if monthly.empty:
        raise LoadError("Không đủ tháng dữ liệu đầy đủ để dự báo.")
    full = pd.period_range(monthly.index.min(), monthly.index.max(), freq="M")
    gaps = [str(m) for m in full if m not in monthly.index]
    monthly = monthly.reindex(full, fill_value=0.0)
    y = monthly.to_numpy(float)
    n = len(y)
    if n < 12:
        raise LoadError(f"Chỉ có {n} tháng dữ liệu đầy đủ, cần ít nhất 12 tháng để dự báo.")
    horizon = int(max(1, min(horizon, 6, n // 2)))
    start = full[0]

    h_test = min(6, max(3, n // 4))
    train, test = y[:-h_test], y[-h_test:]
    results = []
    for key, label, fn, is_base, min_n in MODELS:
        if n < min_n:
            continue
        try:
            pred = np.maximum(np.asarray(fn(train, h_test, start), dtype=float), 0)
        except Exception:
            continue
        results.append({"key": key, "label": label, "is_baseline": is_base, "pred": pred, **_metrics(test, pred)})
    best = min(results, key=lambda r: r["rmse"])
    baselines = [r for r in results if r["is_baseline"]]
    base = min(baselines, key=lambda r: r["rmse"])
    improvement = _f((base["rmse"] - best["rmse"]) / base["rmse"] * 100) if base["rmse"] else None

    fn = next(m[2] for m in MODELS if m[0] == best["key"])
    fc = np.maximum(np.asarray(fn(y, horizon, start), dtype=float), 0)
    sigma = best["rmse"]
    steps = np.arange(1, horizon + 1)
    lower = np.maximum(fc - 1.96 * sigma * np.sqrt(steps), 0)
    upper = fc + 1.96 * sigma * np.sqrt(steps)
    fut = [str(start + n + j) for j in range(horizon)]

    med = float(np.median(y))
    mad = float(np.median(np.abs(y - med))) * 1.4826
    odd = [str(full[i]) for i in range(n) if mad > 0 and abs(y[i] - med) > 3.5 * mad]

    limitations = [
        f"Dự báo dựa trên {n} tháng doanh thu đầy đủ; chỉ dùng lịch sử doanh thu, không biết khuyến mãi, giá, mùa lễ hay biến động bên ngoài.",
        f"Mô hình được kiểm tra trên {h_test} tháng cuối (huấn luyện bằng {n - h_test} tháng đầu, không xáo trộn thứ tự thời gian). "
        f"Sai số trên tập kiểm thử của mô hình chọn: MAE {best['mae']:,.0f}, RMSE {best['rmse']:,.0f}" + (f", MAPE {best['mape']:.1f}%." if best["mape"] is not None else "."),
        "Khoảng dự báo là khoảng tham khảo xấp xỉ (±1,96 lần RMSE kiểm thử, tăng dần theo số tháng), không phải cam kết thống kê chặt chẽ vì số điểm kiểm thử rất ít.",
    ]
    if n < 24:
        limitations.append(f"Chỉ có {n} tháng nên chưa đủ hai chu kỳ năm để học tính mùa vụ; các mô hình mùa vụ không được sử dụng.")
    if best["is_baseline"]:
        limitations.append("Không có mô hình phức tạp nào tốt hơn baseline đơn giản trên tập kiểm thử, nên dự báo chỉ mang tính tham khảo.")
    elif improvement is not None and improvement < 10:
        limitations.append(f"Mô hình chọn chỉ tốt hơn baseline tốt nhất khoảng {improvement:.1f}% (theo RMSE), cải thiện không đáng kể.")
    if odd:
        limitations.append(f"Các tháng {', '.join(odd)} lệch xa mức thông thường (có thể do mùa vụ hoặc giá trị nhập sai), có thể ảnh hưởng tới dự báo.")
    if gaps:
        limitations.append(f"Có {len(gaps)} tháng không có dữ liệu ({', '.join(gaps[:6])}), được tính là 0.")
    if dropped:
        limitations.append(f"Tháng chưa đủ ngày ({', '.join(dropped)}) bị loại khỏi mô hình để không làm sai lệch.")

    test_months = [str(full[n - h_test + i]) for i in range(h_test)]
    return {
        "granularity": "tháng", "n_months": n,
        "history": {"months": [str(m) for m in full], "values": [_f(v) for v in y]},
        "partial_months_dropped": dropped, "gap_months": gaps,
        "split": {"n_train": n - h_test, "n_test": h_test, "train_end": str(full[n - h_test - 1]), "test_start": test_months[0]},
        "models": [{"key": r["key"], "label": r["label"], "is_baseline": r["is_baseline"], "is_best": r["key"] == best["key"],
                    "mae": r["mae"], "rmse": r["rmse"], "mape": r["mape"]} for r in sorted(results, key=lambda r: r["rmse"])],
        "best": {"key": best["key"], "label": best["label"], "mae": best["mae"], "rmse": best["rmse"], "mape": best["mape"]},
        "baseline": {"key": base["key"], "label": base["label"], "rmse": base["rmse"]},
        "improvement_vs_baseline_pct": improvement,
        "backtest": {"months": test_months, "actual": [_f(v) for v in test], "best": [_f(v) for v in best["pred"]], "baseline": [_f(v) for v in base["pred"]]},
        "forecast": {"months": fut, "values": [_f(v) for v in fc], "lower": [_f(v) for v in lower], "upper": [_f(v) for v in upper], "horizon": horizon},
        "seasonality_used": best["key"] in ("snaive", "ridge_season"),
        "limitations": limitations,
    }
