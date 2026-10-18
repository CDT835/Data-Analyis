"""Machine Learning tổng quát cho mọi bảng dữ liệu (không cần cột doanh thu).

- Phân nhóm các dòng bằng K-Means trên các cột số do người dùng chọn.
- Dự đoán một cột số (hồi quy) và một cột phân loại (khi có nhãn).

Nguyên tắc: tách tập huấn luyện/kiểm thử, luôn so sánh với baseline, báo cáo đầy đủ chỉ số, cảnh báo nguy cơ rò rỉ dữ liệu,
không điền giá trị cho ô thiếu (dòng thiếu bị loại và được đếm), nêu rõ giới hạn.
"""
import time
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .analytics import _f, _num, _txt
from .loader import LoadError, Table
from .parsing import norm_key
from .profiler import NAME_ID_RE, _detect_type

MAX_ROWS = 5000
SEED = 42
TIME_BUDGET = 25.0  # giây; vượt thì bỏ bước tính độ quan trọng của cột (gói miễn phí CPU rất yếu)


def _canon(series: pd.Series) -> pd.Series:
    """Gộp các cách viết khác nhau của cùng một nhóm (hoa/thường, có/không dấu, khoảng trắng)."""
    groups: Dict[str, Counter] = {}
    for v in series.dropna():
        groups.setdefault(norm_key(v), Counter())[v] += 1
    best = {k: c.most_common(1)[0][0] for k, c in groups.items()}
    return series.map(lambda v: best[norm_key(v)] if isinstance(v, str) else None)


def _numeric_matrix(table: Table, features: List[str], min_cols: int, label: str) -> Tuple[pd.DataFrame, List[Dict[str, str]]]:
    df = table.df
    cols, skipped = {}, []
    for c in features:
        if c not in df.columns:
            raise LoadError(f"Không tìm thấy cột “{c}” trong dữ liệu.")
        vals = df[c].tolist()
        if NAME_ID_RE.search(norm_key(c)):
            skipped.append({"name": c, "reason": "cột mã định danh, không dùng để phân nhóm"})
        elif _detect_type(vals) != "numeric":
            skipped.append({"name": c, "reason": "không phải cột số"})
        else:
            cols[c] = pd.Series([_num(v) for v in vals], dtype=float)
    if len(cols) < min_cols:
        raise LoadError(f"{label} cần ít nhất {min_cols} cột số hợp lệ (đã loại: " + (", ".join(s["name"] for s in skipped) or "không có") + ").")
    return pd.DataFrame(cols), skipped


def _quality(sil: float) -> Dict[str, Any]:
    level = "rõ ràng" if sil > 0.5 else ("yếu" if sil >= 0.25 else "rất yếu")
    return {"level": level, "silhouette": sil, "message":
            f"Hệ số silhouette = {sil:.2f}: cấu trúc nhóm {level} (theo quy ước >0,5 là rõ ràng; 0,25–0,5 là yếu; <0,25 gần như không có cấu trúc nhóm riêng)."}


# ====================================================================== Phân nhóm các dòng
def run_cluster(table: Table, features: List[str], k: Optional[int] = None) -> Dict[str, Any]:
    from sklearn.cluster import KMeans
    from sklearn.metrics import davies_bouldin_score, silhouette_score
    from sklearn.preprocessing import StandardScaler

    X, skipped = _numeric_matrix(table, features, 2, "Phân nhóm")
    ok = X.notna().all(axis=1)
    n_excl = int((~ok).sum())
    X = X[ok].reset_index(drop=True)
    if len(X) < 30:
        raise LoadError(f"Chỉ có {len(X)} dòng đầy đủ dữ liệu ở các cột đã chọn (đã loại {n_excl} dòng thiếu), cần ít nhất 30.")
    sampled = len(X) > MAX_ROWS
    if sampled:
        X = X.iloc[np.sort(np.random.default_rng(SEED).choice(len(X), MAX_ROWS, replace=False))].reset_index(drop=True)
    names, n = list(X.columns), len(X)
    scaler = StandardScaler().fit(X)
    Z = scaler.transform(X)

    models, cands = {}, []
    for kk in range(2, min(8, n // 10) + 1):
        km = KMeans(n_clusters=kk, n_init=10, random_state=SEED).fit(Z)
        models[kk] = km
        cands.append({"k": kk, "inertia": _f(km.inertia_), "silhouette": _f(silhouette_score(Z, km.labels_, sample_size=min(n, 3000), random_state=SEED)),
                      "davies_bouldin": _f(davies_bouldin_score(Z, km.labels_))})
    best_k = max(cands, key=lambda c: c["silhouette"])["k"]
    chosen = k if (k and k in models) else best_k
    km = models[chosen]
    row = next(c for c in cands if c["k"] == chosen)

    sizes = pd.Series(km.labels_).value_counts()
    order = sizes.index.tolist()  # nhóm lớn nhất lên trước
    remap = {old: i + 1 for i, old in enumerate(order)}
    clusters = []
    for old in order:
        mask = km.labels_ == old
        z = km.cluster_centers_[old]
        hi_names = [f"“{names[j]}”" for j in np.argsort(-z)[:2] if z[j] > 0.5]
        lo_names = [f"“{names[j]}”" for j in np.argsort(z)[:2] if z[j] < -0.5]
        parts = ([("cao hơn trung bình ở " + ", ".join(hi_names))] if hi_names else []) + ([("thấp hơn trung bình ở " + ", ".join(lo_names))] if lo_names else [])
        desc = "; ".join(parts) or "gần mức trung bình ở hầu hết các cột"
        clusters.append({"id": remap[old], "size": int(mask.sum()), "share_pct": _f(mask.mean() * 100), "description": desc[0].upper() + desc[1:],
                         "means": {nm: _f(X.loc[mask, nm].mean()) for nm in names}, "z": {nm: _f(z[j]) for j, nm in enumerate(names)}})

    # Chiếu xuống 2 chiều (PCA bằng SVD) chỉ để vẽ biểu đồ
    U, S, Vt = np.linalg.svd(Z - Z.mean(axis=0), full_matrices=False)
    proj = (Z - Z.mean(axis=0)) @ Vt[:2].T
    explained = (S ** 2 / np.sum(S ** 2))[:2]
    idx = np.random.default_rng(SEED).choice(n, size=min(n, 400), replace=False)
    limitations = [
        f"Phân nhóm dựa trên {n} dòng và {len(names)} cột số ({', '.join(names)}), đã chuẩn hóa để các cột có thang đo khác nhau được so sánh công bằng.",
        f"Số nhóm {chosen} được chọn {'theo yêu cầu của bạn' if (k and k in models) else 'tự động theo hệ số silhouette cao nhất'}; chọn số nhóm khác cho cách chia khác.",
        "Nhóm là cách chia theo khoảng cách giữa các giá trị, không có nghĩa là các dòng thực sự thuộc các loại khác nhau. Phần mô tả nhóm chỉ nêu cột nào cao/thấp hơn trung bình.",
        "Biểu đồ phân tán là hình chiếu xuống 2 chiều (PCA) nên chỉ giữ lại một phần thông tin.",
    ]
    if n_excl:
        limitations.append(f"{n_excl} dòng thiếu dữ liệu ở các cột đã chọn bị loại (không điền giá trị thay thế).")
    if sampled:
        limitations.append(f"Dữ liệu lớn nên dùng mẫu ngẫu nhiên {MAX_ROWS:,} dòng để chạy trong giới hạn của dịch vụ miễn phí.")
    if skipped:
        limitations.append("Các cột bị bỏ qua: " + "; ".join(f"{s['name']} ({s['reason']})" for s in skipped) + ".")
    small = [c for c in clusters if c["share_pct"] < 5]
    if small:
        limitations.append(f"Có {len(small)} nhóm chiếm dưới 5% số dòng, kết quả của các nhóm nhỏ kém ổn định.")
    return {
        "task": "cluster", "features": names, "features_skipped": skipped, "n_rows_used": n, "n_excluded_missing": n_excl, "sampled": sampled,
        "k_candidates": cands, "k_chosen": chosen, "k_best_silhouette": best_k, "k_selected_by": "người dùng" if (k and k in models) else "silhouette",
        "metrics": {"silhouette": row["silhouette"], "davies_bouldin": row["davies_bouldin"], "inertia": row["inertia"]},
        "quality": _quality(row["silhouette"]), "clusters": clusters,
        "pca": {"explained": [_f(e) for e in explained], "points": [{"x": _f(proj[i, 0]), "y": _f(proj[i, 1]), "c": remap[int(km.labels_[i])]} for i in idx]},
        "limitations": limitations,
    }


# ====================================================================== Dự đoán có giám sát
def _prepare_xy(table: Table, target: str, features: List[str], task: str):
    df = table.df
    for c in [target] + features:
        if c not in df.columns:
            raise LoadError(f"Không tìm thấy cột “{c}” trong dữ liệu.")
    if target in features:
        raise LoadError("Cột mục tiêu không được nằm trong danh sách cột đầu vào.")
    if not features:
        raise LoadError("Hãy chọn ít nhất một cột đầu vào.")
    tvals = df[target].tolist()
    ttype = _detect_type(tvals)
    if task == "regression":
        if ttype != "numeric":
            raise LoadError(f"Cột mục tiêu “{target}” không phải cột số. Hãy dùng chức năng dự đoán phân loại.")
        y = pd.Series([_num(v) for v in tvals], dtype=float)
    else:
        if ttype == "numeric":
            nums = [_num(v) for v in tvals]
            valid = [v for v in nums if v == v]
            if len(set(valid)) > 10 or not all(float(v).is_integer() for v in valid):
                raise LoadError(f"Cột “{target}” là cột số có nhiều giá trị, không phải cột phân loại. Hãy dùng chức năng dự đoán cột số.")
            y = pd.Series([(str(int(v)) if v == v else None) for v in nums], dtype=object)
        elif ttype == "text":
            y = _canon(pd.Series([_txt(v) for v in tvals], dtype=object))
        else:
            raise LoadError(f"Cột mục tiêu “{target}” không phù hợp để phân loại (kiểu ngày hoặc trống).")
    cols, num_cols, cat_cols, skipped = {}, [], [], []
    for c in features:
        vals = df[c].tolist()
        t = _detect_type(vals)
        if NAME_ID_RE.search(norm_key(c)):
            skipped.append({"name": c, "reason": "cột mã định danh, không có giá trị dự đoán"})
        elif t == "numeric":
            cols[c] = pd.Series([_num(v) for v in vals], dtype=float)
            num_cols.append(c)
        elif t == "text":
            s = _canon(pd.Series([_txt(v) for v in vals], dtype=object))
            if s.nunique() > 20:
                skipped.append({"name": c, "reason": "quá nhiều giá trị khác nhau (trên 20)"})
            else:
                cols[c] = s
                cat_cols.append(c)
        else:
            skipped.append({"name": c, "reason": "kiểu ngày hoặc trống, chưa hỗ trợ làm cột đầu vào"})
    if not cols:
        raise LoadError("Không còn cột đầu vào hợp lệ sau khi loại các cột không phù hợp.")
    X = pd.DataFrame(cols)
    ok = y.notna() & X.notna().all(axis=1)
    n_excl = int((~ok).sum())
    X, y = X[ok].reset_index(drop=True), y[ok].reset_index(drop=True)
    if len(X) < 50:
        raise LoadError(f"Chỉ có {len(X)} dòng đầy đủ dữ liệu ở các cột đã chọn (đã loại {n_excl} dòng thiếu hoặc không đọc được), cần ít nhất 50 dòng.")
    sampled = len(X) > MAX_ROWS
    if sampled:
        keep = np.sort(np.random.default_rng(SEED).choice(len(X), MAX_ROWS, replace=False))
        X, y = X.iloc[keep].reset_index(drop=True), y.iloc[keep].reset_index(drop=True)
    return X, y, num_cols, cat_cols, skipped, n_excl, sampled


def _pipeline(estimator, num_cols, cat_cols, scale):
    from sklearn.compose import ColumnTransformer
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler
    parts = []
    if num_cols:
        parts.append(("num", StandardScaler() if scale else "passthrough", num_cols))
    if cat_cols:
        parts.append(("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), cat_cols))
    return Pipeline([("pre", ColumnTransformer(parts)), ("model", estimator)])


def _importance(pipe, X_test, y_test, scoring, label, t0) -> Dict[str, Any]:
    from sklearn.inspection import permutation_importance
    if time.time() - t0 > TIME_BUDGET:
        return {"method": "Bỏ qua tính độ quan trọng của cột vì sắp hết thời gian xử lý của dịch vụ miễn phí.", "items": []}
    if len(X_test) > 500:
        sel = np.random.default_rng(SEED).choice(len(X_test), 500, replace=False)
        X_test, y_test = X_test.iloc[sel], y_test.iloc[sel]
    r = permutation_importance(pipe, X_test, y_test, n_repeats=3, random_state=SEED, scoring=scoring, n_jobs=1)
    items = sorted(({"name": c, "importance": _f(m), "std": _f(s)} for c, m, s in zip(X_test.columns, r.importances_mean, r.importances_std)), key=lambda i: -i["importance"])
    return {"method": label, "items": items[:15]}


def _feature_info(X, num_cols, cat_cols):
    return [{"name": c, "kind": "số" if c in num_cols else "phân loại"} for c in X.columns]


def run_regression(table: Table, target: str, features: List[str]) -> Dict[str, Any]:
    from sklearn.dummy import DummyRegressor
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.linear_model import LinearRegression
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
    from sklearn.model_selection import train_test_split

    t0 = time.time()
    X, y, num_cols, cat_cols, skipped, n_excl, sampled = _prepare_xy(table, target, features, "regression")
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, random_state=SEED)
    specs = [("mean", "Baseline: luôn dự đoán giá trị trung bình", DummyRegressor(strategy="mean"), True, False),
             ("linear", "Hồi quy tuyến tính (Scikit-learn)", LinearRegression(), False, True),
             ("forest", "Rừng ngẫu nhiên – Random Forest (Scikit-learn)", RandomForestRegressor(n_estimators=100, random_state=SEED, n_jobs=1), False, False)]
    fitted, results = {}, []
    for key, label, est, base, scale in specs:
        pipe = _pipeline(est, num_cols, cat_cols, scale).fit(Xtr, ytr)
        pred, pred_tr = pipe.predict(Xte), pipe.predict(Xtr)
        fitted[key] = (pipe, pred)
        results.append({"key": key, "label": label, "is_baseline": base, "mae": _f(mean_absolute_error(yte, pred)),
                        "rmse": _f(np.sqrt(mean_squared_error(yte, pred))), "r2": _f(r2_score(yte, pred)), "train_r2": _f(r2_score(ytr, pred_tr))})
    best = min(results, key=lambda r: r["rmse"])
    base = next(r for r in results if r["is_baseline"])
    for r in results:
        r["is_best"] = r["key"] == best["key"]
    improvement = _f((base["rmse"] - best["rmse"]) / base["rmse"] * 100) if base["rmse"] else None

    warnings: List[str] = []
    for c in num_cols:
        r = np.corrcoef(X[c], y)[0, 1] if X[c].std() > 0 and y.std() > 0 else 0
        if abs(r) > 0.98:
            warnings.append(f"Cột “{c}” gần như trùng khớp tuyến tính với cột mục tiêu (|r| = {abs(r):.3f}); có thể nó được tính từ cột mục tiêu hoặc ngược lại, khi đó mô hình không có giá trị dự đoán thực tế.")
    if best["r2"] >= 0.9 and not best["is_baseline"]:
        warnings.append(f"Kết quả rất cao (R² = {best['r2']:.3f}). Điều này thường xảy ra khi cột mục tiêu được tính trực tiếp từ các cột đầu vào; khi đó mô hình chỉ học lại công thức chứ chưa chắc dự đoán được điều gì mới. Hãy kiểm tra trước khi tin kết quả.")
    if best["train_r2"] - best["r2"] > 0.3 and not best["is_baseline"]:
        warnings.append(f"R² trên tập huấn luyện ({best['train_r2']:.2f}) cao hơn nhiều so với tập kiểm thử ({best['r2']:.2f}): dấu hiệu mô hình học thuộc dữ liệu (quá khớp).")

    imp = {"method": "Mô hình tốt nhất là baseline nên không có cột nào giúp dự đoán tốt hơn trung bình.", "items": []}
    if not best["is_baseline"]:
        imp = _importance(fitted[best["key"]][0], Xte, yte, "r2", "Mức giảm R² trên tập kiểm thử khi xáo trộn từng cột (càng lớn càng quan trọng)", t0)
    pred = fitted[best["key"]][1]
    idx = np.random.default_rng(SEED).choice(len(yte), size=min(len(yte), 300), replace=False)
    limitations = [
        f"Mô hình học từ {len(Xtr)} dòng và được kiểm tra trên {len(Xte)} dòng chưa từng thấy (chia ngẫu nhiên 80/20, cố định hạt giống). Dữ liệu có thứ tự thời gian nên dùng chức năng dự báo thay vì chia ngẫu nhiên.",
        f"Sai số kiểm thử của mô hình chọn: MAE {best['mae']:,.2f}, RMSE {best['rmse']:,.2f}, R² {best['r2']:.2f}.",
        "Mô hình chỉ chỉ ra mối liên hệ trong dữ liệu, không chứng minh nguyên nhân – kết quả.",
        "Chỉ đúng với dữ liệu cùng kiểu với dữ liệu đã học; không nên dùng cho đối tượng khác hẳn.",
    ]
    if best["is_baseline"]:
        limitations.append("Không có mô hình nào tốt hơn baseline trên tập kiểm thử, nên các cột đầu vào đã chọn chưa giúp dự đoán cột này.")
    elif improvement is not None and improvement < 10:
        limitations.append(f"Mô hình chọn chỉ cải thiện RMSE khoảng {improvement:.1f}% so với baseline, mức cải thiện nhỏ.")
    if n_excl:
        limitations.append(f"{n_excl} dòng thiếu hoặc không đọc được ở cột mục tiêu/đầu vào bị loại (không điền giá trị thay thế).")
    if sampled:
        limitations.append(f"Dữ liệu lớn nên dùng mẫu ngẫu nhiên {MAX_ROWS:,} dòng để chạy trong giới hạn của dịch vụ miễn phí.")
    if skipped:
        limitations.append("Các cột đầu vào bị bỏ qua: " + "; ".join(f"{s['name']} ({s['reason']})" for s in skipped) + ".")
    return {
        "task": "regression", "target": target, "features_used": _feature_info(X, num_cols, cat_cols), "features_skipped": skipped,
        "n_rows_used": int(len(X)), "n_excluded_missing": n_excl, "sampled": sampled,
        "split": {"n_train": int(len(Xtr)), "n_test": int(len(Xte)), "method": "ngẫu nhiên 80/20, random_state=42"},
        "models": sorted(results, key=lambda r: r["rmse"]), "best": {k: best[k] for k in ("key", "label", "mae", "rmse", "r2")},
        "baseline": {"key": base["key"], "rmse": base["rmse"], "r2": base["r2"]}, "improvement_vs_baseline_pct": improvement,
        "target_summary": {"mean": _f(y.mean()), "std": _f(y.std()), "min": _f(y.min()), "max": _f(y.max())},
        "predictions": [{"actual": _f(yte.iloc[i]), "pred": _f(pred[i])} for i in idx],
        "importance": imp, "warnings": warnings, "limitations": limitations,
    }


def run_classification(table: Table, target: str, features: List[str]) -> Dict[str, Any]:
    from sklearn.dummy import DummyClassifier
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import (accuracy_score, balanced_accuracy_score, confusion_matrix, f1_score,
                                 precision_recall_fscore_support)
    from sklearn.model_selection import train_test_split
    from sklearn.tree import DecisionTreeClassifier

    t0 = time.time()
    X, y, num_cols, cat_cols, skipped, n_excl, sampled = _prepare_xy(table, target, features, "classification")
    counts = y.value_counts()
    rare = counts[counts < 5]
    notes: List[str] = []
    if len(rare):
        keep = y.isin(counts[counts >= 5].index)
        notes.append(f"Bỏ {int(rare.sum())} dòng thuộc {len(rare)} nhóm quá ít dòng (dưới 5): " + ", ".join(f"{k} ({v})" for k, v in rare.items()) + ".")
        X, y = X[keep].reset_index(drop=True), y[keep].reset_index(drop=True)
        counts = y.value_counts()
    classes = counts.index.tolist()
    if not 2 <= len(classes) <= 10:
        raise LoadError(f"Cột “{target}” có {len(classes)} nhóm hợp lệ; chức năng này cần từ 2 đến 10 nhóm (mỗi nhóm ít nhất 5 dòng).")
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, random_state=SEED, stratify=y)
    specs = [("majority", "Baseline: luôn dự đoán nhóm phổ biến nhất", DummyClassifier(strategy="most_frequent"), True, False),
             ("logistic", "Hồi quy logistic (Scikit-learn)", LogisticRegression(max_iter=1000), False, True),
             ("forest", "Rừng ngẫu nhiên – Random Forest (Scikit-learn)", RandomForestClassifier(n_estimators=100, random_state=SEED, n_jobs=1, class_weight="balanced_subsample"), False, False)]
    fitted, results = {}, []
    for key, label, est, base, scale in specs:
        pipe = _pipeline(est, num_cols, cat_cols, scale).fit(Xtr, ytr)
        pred = pipe.predict(Xte)
        fitted[key] = (pipe, pred)
        p, r, f1, _ = precision_recall_fscore_support(yte, pred, labels=classes, average="macro", zero_division=0)
        results.append({"key": key, "label": label, "is_baseline": base, "accuracy": _f(accuracy_score(yte, pred)),
                        "balanced_accuracy": _f(balanced_accuracy_score(yte, pred)), "precision_macro": _f(p), "recall_macro": _f(r), "f1_macro": _f(f1),
                        "f1_weighted": _f(f1_score(yte, pred, average="weighted", zero_division=0))})
    best = max(results, key=lambda r: (r["f1_macro"], r["accuracy"]))
    base = next(r for r in results if r["is_baseline"])
    for r in results:
        r["is_best"] = r["key"] == best["key"]
    pred = fitted[best["key"]][1]
    p, r, f1, sup = precision_recall_fscore_support(yte, pred, labels=classes, zero_division=0)
    per_class = [{"label": str(c), "precision": _f(p[i]), "recall": _f(r[i]), "f1": _f(f1[i]), "support": int(sup[i])} for i, c in enumerate(classes)]

    warnings: List[str] = list(notes)
    for c in num_cols:
        stump = DecisionTreeClassifier(max_depth=3, random_state=SEED).fit(Xtr[[c]], ytr)
        acc = accuracy_score(yte, stump.predict(Xte[[c]]))
        if acc >= 0.97 and base["accuracy"] < 0.9:
            warnings.append(f"Chỉ riêng cột “{c}” đã dự đoán đúng {acc:.0%} trên tập kiểm thử. Có thể cột mục tiêu được tạo ra từ cột này (rò rỉ dữ liệu), khi đó mô hình không có giá trị dự đoán thực tế.")
    if best["accuracy"] >= 0.95 and not best["is_baseline"]:
        warnings.append(f"Độ chính xác rất cao ({best['accuracy']:.1%}). Hãy kiểm tra xem cột mục tiêu có được tính trực tiếp từ các cột đầu vào không (rò rỉ dữ liệu).")
    if base["accuracy"] >= 0.8:
        warnings.append(f"Dữ liệu mất cân bằng: nhóm phổ biến nhất chiếm {base['accuracy']:.0%} tập kiểm thử, nên độ chính xác đơn thuần dễ gây hiểu lầm; hãy xem thêm F1 và recall theo từng nhóm.")

    imp = {"method": "Mô hình tốt nhất là baseline nên không có cột nào giúp dự đoán tốt hơn việc chọn nhóm phổ biến nhất.", "items": []}
    if not best["is_baseline"]:
        imp = _importance(fitted[best["key"]][0], Xte, yte, "accuracy", "Mức giảm độ chính xác trên tập kiểm thử khi xáo trộn từng cột (càng lớn càng quan trọng)", t0)
    cm = confusion_matrix(yte, pred, labels=classes)
    limitations = [
        f"Mô hình học từ {len(Xtr)} dòng và được kiểm tra trên {len(Xte)} dòng chưa từng thấy (chia ngẫu nhiên có phân tầng theo nhóm, 80/20, cố định hạt giống).",
        f"Mô hình chọn theo F1 trung bình các nhóm: độ chính xác {best['accuracy']:.1%}, F1 macro {best['f1_macro']:.2f}, so với baseline {base['accuracy']:.1%}.",
        "Số dòng trong tập kiểm thử không lớn nên các chỉ số có thể dao động nếu chia lại dữ liệu; nhóm ít dòng càng kém ổn định.",
        "Mô hình chỉ chỉ ra mối liên hệ trong dữ liệu, không chứng minh nguyên nhân – kết quả.",
    ]
    if best["is_baseline"]:
        limitations.append("Không có mô hình nào tốt hơn baseline, nên các cột đầu vào đã chọn chưa giúp dự đoán cột này.")
    if n_excl:
        limitations.append(f"{n_excl} dòng thiếu hoặc không đọc được bị loại (không điền giá trị thay thế).")
    if sampled:
        limitations.append(f"Dữ liệu lớn nên dùng mẫu ngẫu nhiên {MAX_ROWS:,} dòng để chạy trong giới hạn của dịch vụ miễn phí.")
    if skipped:
        limitations.append("Các cột đầu vào bị bỏ qua: " + "; ".join(f"{s['name']} ({s['reason']})" for s in skipped) + ".")
    return {
        "task": "classification", "target": target, "features_used": _feature_info(X, num_cols, cat_cols), "features_skipped": skipped,
        "n_rows_used": int(len(X)), "n_excluded_missing": n_excl, "sampled": sampled,
        "split": {"n_train": int(len(Xtr)), "n_test": int(len(Xte)), "method": "ngẫu nhiên phân tầng 80/20, random_state=42"},
        "classes": [{"label": str(c), "count": int(counts[c])} for c in classes],
        "models": sorted(results, key=lambda r: -r["f1_macro"]), "best": {k: best[k] for k in ("key", "label", "accuracy", "balanced_accuracy", "f1_macro")},
        "baseline": {"key": base["key"], "accuracy": base["accuracy"]},
        "per_class": per_class, "confusion": {"labels": [str(c) for c in classes], "matrix": cm.tolist()},
        "importance": imp, "warnings": warnings, "limitations": limitations,
    }
