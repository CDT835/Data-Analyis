import base64
import csv
import io

import numpy as np
import pytest

from tests.test_datasets import DATA, SALES, STUDENTS, call, payload  # noqa: F401  (cũng đặt biến môi trường khóa)

MAPPING = {"date": "Ngày đặt hàng", "amount": "Thành tiền", "customer_id": "Mã khách hàng", "order_id": "Mã đơn hàng",
           "quantity": "Số lượng", "unit_price": "Đơn giá", "discount": "Giảm giá (%)", "category": "Danh mục",
           "product": "Sản phẩm", "region": "Thành phố"}


@pytest.fixture(scope="module")
def cleaned_csv():
    prof = call("/api/v1/datasets/profile", payload(SALES, sheet="Đơn hàng")).json()
    plan = [{k: s[k] for k in ("id", "action", "column", "params")} for s in prof["suggestions"] if s["selected"]]
    out = call("/api/v1/datasets/clean", payload(SALES, sheet="Đơn hàng", plan=plan)).json()
    return base64.b64decode(out["csv_b64"])


def body(csv_bytes, **extra):
    return {"filename": "clean.csv", "file_b64": base64.b64encode(csv_bytes).decode(), "mapping": MAPPING, **extra}


def test_stats_revenue_matches_independent_sum(cleaned_csv):
    r = call("/api/v1/analysis/stats", body(cleaned_csv))
    assert r.status_code == 200, r.text
    d = r.json()
    rows = list(csv.DictReader(io.StringIO(cleaned_csv.decode("utf-8-sig"))))
    expected = sum(float(x["Thành tiền"]) for x in rows if x["Ngày đặt hàng"] and x["Thành tiền"])
    rev = d["revenue"]
    assert d["mode"] == "revenue"
    assert rev["kpis"]["total_revenue"] == pytest.approx(expected, rel=1e-9)
    assert rev["rows_excluded"] == 6  # 6 ngày trống sau khi làm sạch
    assert sum(rev["monthly"]["revenue"]) == pytest.approx(expected, rel=1e-9)
    assert len(rev["monthly"]["months"]) == 21
    assert rev["kpis"]["n_negative_rows"] == 6
    assert rev["breakdowns"]["category"]["n_groups"] == 5
    assert sum(i["share_pct"] for i in rev["breakdowns"]["category"]["items"]) == pytest.approx(100, abs=0.01)


def test_stats_general_mode_for_non_revenue_data():
    d = call("/api/v1/analysis/stats", {**payload(STUDENTS), "mapping": {}}).json()
    assert d["mode"] == "general" and d["revenue"] is None
    names = {n["name"] for n in d["descriptive"]["numeric"]}
    assert "Điểm tổng kết" in names and "Mã SV" not in names
    assert any("tương quan" in d["descriptive"]["correlations"]["note"] for _ in [0])


def test_rfm_clusters_are_consistent_and_reproducible(cleaned_csv):
    a = call("/api/v1/ml/rfm", body(cleaned_csv)).json()
    b = call("/api/v1/ml/rfm", body(cleaned_csv)).json()
    assert a["clusters"] == b["clusters"]  # cố định random_state
    assert sum(c["size"] for c in a["clusters"]) == a["n_customers"]
    assert [c["id"] for c in a["clusters"]] == list(range(1, a["k_chosen"] + 1))
    assert sum(c["revenue_share_pct"] for c in a["clusters"]) == pytest.approx(100, abs=0.1)
    means = [c["mean_monetary"] for c in a["clusters"]]
    assert means == sorted(means, reverse=True)
    assert a["k_chosen"] == a["k_best_silhouette"] and a["k_selected_by"] == "silhouette"
    assert -1 <= a["metrics"]["silhouette"] <= 1 and a["limitations"]
    forced = call("/api/v1/ml/rfm", body(cleaned_csv, k=3)).json()
    assert forced["k_chosen"] == 3 and forced["k_selected_by"] == "người dùng"


def test_forecast_uses_time_ordered_split_and_reports_limits(cleaned_csv):
    d = call("/api/v1/ml/forecast", body(cleaned_csv, horizon=4)).json()
    hist = d["history"]["months"]
    assert d["split"]["n_train"] + d["split"]["n_test"] == d["n_months"] == len(hist)
    assert d["backtest"]["months"] == hist[-d["split"]["n_test"]:]  # kiểm thử là các tháng cuối, không xáo trộn
    best = min(d["models"], key=lambda m: m["rmse"])
    assert best["is_best"] and d["best"]["key"] == best["key"]
    assert all(m["mae"] >= 0 and m["rmse"] >= m["mae"] for m in d["models"])
    fc = d["forecast"]
    assert fc["horizon"] == 4 and len(fc["values"]) == 4
    assert all(lo <= v <= hi for lo, v, hi in zip(fc["lower"], fc["values"], fc["upper"]))
    assert fc["months"][0] == "2026-10"
    assert d["seasonality_used"] is False  # 21 tháng < 24
    assert any("hai chu kỳ" in s for s in d["limitations"])


def test_forecast_needs_enough_history(cleaned_csv):
    rows = list(csv.reader(io.StringIO(cleaned_csv.decode("utf-8-sig"))))
    head, data = rows[0], rows[1:]
    di = head.index("Ngày đặt hàng")
    short = [r for r in data if r[di] and r[di] < "2025-09-01"]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(head)
    w.writerows(short)
    r = call("/api/v1/ml/forecast", body(buf.getvalue().encode("utf-8")))
    assert r.status_code == 422 and "12 tháng" in r.json()["detail"]


def test_ml_refuses_data_without_required_columns():
    for path in ("/api/v1/ml/rfm", "/api/v1/ml/forecast"):
        r = call(path, {**payload(STUDENTS), "mapping": {}})
        assert r.status_code == 422, path
    assert call("/api/v1/ml/rfm", {**payload(STUDENTS), "mapping": {"hack": "x"}}).status_code == 422


# ---------------------------------------------------------------- Machine Learning tổng quát (không cần cột doanh thu)
SCORES = ["Điểm chuyên cần", "Điểm giữa kỳ", "Điểm cuối kỳ", "Số buổi vắng"]


def stu(**extra):
    return {**payload(STUDENTS), **extra}


def test_general_cluster_on_non_revenue_data():
    a = call("/api/v1/ml/cluster", stu(features=SCORES)).json()
    b = call("/api/v1/ml/cluster", stu(features=SCORES)).json()
    assert a["clusters"] == b["clusters"]  # lặp lại được
    assert sum(c["size"] for c in a["clusters"]) == a["n_rows_used"]
    assert a["n_rows_used"] + a["n_excluded_missing"] == 608  # đủ cả 608 dòng của tệp gốc, dòng thiếu được đếm chứ không bị bỏ âm thầm
    assert [c["id"] for c in a["clusters"]] == list(range(1, a["k_chosen"] + 1))
    assert 0 < sum(a["pca"]["explained"]) <= 1 and len(a["pca"]["points"]) == 400
    assert set(a["clusters"][0]["means"]) == set(SCORES)
    forced = call("/api/v1/ml/cluster", stu(features=SCORES, k=3)).json()
    assert forced["k_chosen"] == 3 and forced["k_selected_by"] == "người dùng"
    assert any("dưới 5%" in s for s in a["limitations"])  # dữ liệu chưa làm sạch có ngoại lệ tạo nhóm rất nhỏ


def test_regression_beats_baseline_and_reports_honestly():
    d = call("/api/v1/ml/regression", stu(target="Điểm cuối kỳ", features=["Điểm chuyên cần", "Điểm giữa kỳ", "Số buổi vắng", "Lớp", "Giới tính"])).json()
    assert d["split"]["n_train"] + d["split"]["n_test"] == d["n_rows_used"]
    best, base = d["best"], d["baseline"]
    assert best["rmse"] <= base["rmse"] and not d["models"][0]["is_baseline"]
    assert all(m["mae"] >= 0 and m["rmse"] >= m["mae"] for m in d["models"])
    assert d["importance"]["items"] and {i["name"] for i in d["importance"]["items"]} <= {f["name"] for f in d["features_used"]}
    assert len(d["predictions"]) <= 300 and d["limitations"] and not d["warnings"]
    again = call("/api/v1/ml/regression", stu(target="Điểm cuối kỳ", features=["Điểm chuyên cần", "Điểm giữa kỳ", "Số buổi vắng", "Lớp", "Giới tính"])).json()
    assert again["models"] == d["models"]


def test_regression_warns_about_leakage():
    d = call("/api/v1/ml/regression", stu(target="Điểm tổng kết", features=SCORES[:3])).json()
    assert d["best"]["r2"] > 0.98 and any("Kết quả rất cao" in w for w in d["warnings"])


def test_classification_with_baseline_confusion_and_leak_warning():
    feats = ["Điểm chuyên cần", "Điểm giữa kỳ", "Số buổi vắng", "Lớp", "Giới tính"]
    d = call("/api/v1/ml/classification", stu(target="Xếp loại", features=feats)).json()
    n_classes = len(d["classes"])
    assert n_classes == 6 and len(d["confusion"]["matrix"]) == n_classes
    assert sum(sum(r) for r in d["confusion"]["matrix"]) == d["split"]["n_test"]
    assert d["baseline"]["accuracy"] == max(m["accuracy"] for m in d["models"] if m["key"] == "majority")
    assert all(0 <= m["accuracy"] <= 1 and 0 <= m["f1_macro"] <= 1 for m in d["models"])
    assert sum(c["support"] for c in d["per_class"]) == d["split"]["n_test"]
    leak = call("/api/v1/ml/classification", stu(target="Xếp loại", features=["Điểm tổng kết"])).json()
    assert any("rò rỉ dữ liệu" in w for w in leak["warnings"])


def test_general_ml_validation():
    f = ["Điểm chuyên cần", "Điểm giữa kỳ"]
    assert call("/api/v1/ml/regression", stu(target="Không có cột này", features=f)).status_code == 422
    assert call("/api/v1/ml/regression", stu(features=f)).status_code == 422  # thiếu cột mục tiêu
    assert call("/api/v1/ml/regression", stu(target="Xếp loại", features=f)).status_code == 422  # mục tiêu không phải số
    assert call("/api/v1/ml/classification", stu(target="Điểm tổng kết", features=f)).status_code == 422  # quá nhiều giá trị
    assert call("/api/v1/ml/regression", stu(target="Điểm cuối kỳ", features=["Điểm cuối kỳ"])).status_code == 422  # mục tiêu nằm trong đầu vào
    assert call("/api/v1/ml/regression", stu(target="Điểm cuối kỳ", features=["Mã SV"])).status_code == 422  # chỉ có cột mã
    assert call("/api/v1/ml/cluster", stu(features=["Điểm giữa kỳ"])).status_code == 422  # cần ≥ 2 cột số
    assert call("/api/v1/ml/cluster", stu(features=["Giới tính", "Lớp"])).status_code == 422  # không phải cột số


def test_leakage_still_flagged_on_cleaned_students():
    prof = call("/api/v1/datasets/profile", payload(STUDENTS)).json()
    plan = [{k: s[k] for k in ("id", "action", "column", "params")} for s in prof["suggestions"] if s["selected"]]
    out = call("/api/v1/datasets/clean", payload(STUDENTS, plan=plan)).json()
    cleaned = base64.b64decode(out["csv_b64"])
    body_ = {"filename": "c.csv", "file_b64": base64.b64encode(cleaned).decode(), "target": "Điểm tổng kết", "features": SCORES[:3]}
    d = call("/api/v1/ml/regression", body_).json()
    assert d["best"]["r2"] >= 0.9 and any("Kết quả rất cao" in w for w in d["warnings"])
    ok = call("/api/v1/ml/regression", {**body_, "target": "Điểm cuối kỳ", "features": ["Điểm chuyên cần", "Điểm giữa kỳ", "Số buổi vắng"]}).json()
    assert ok["best"]["r2"] < 0.9 and not any("Kết quả rất cao" in w for w in ok["warnings"])
