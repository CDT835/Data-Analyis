import base64
import csv
import io
import json
import os
import time
import uuid
from pathlib import Path

SECRET = "x" * 40
os.environ["AIAR_SHARED_SECRET"] = SECRET

from fastapi.testclient import TestClient  # noqa: E402

from app.auth import compute_signature  # noqa: E402
from app.main import app  # noqa: E402
from app.services.parsing import parse_date, parse_number  # noqa: E402

client = TestClient(app)
DATA = Path(__file__).parent / "data"
SALES = DATA / "ban_hang_2025_2026.xlsx"
STUDENTS = DATA / "ket_qua_hoc_tap_sinh_vien.csv"


def call(path, payload, sign=True):
    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if sign:
        ts, nonce = str(int(time.time())), uuid.uuid4().hex
        sig = compute_signature(SECRET, ts, nonce, "POST", path, "", body)
        headers.update({"X-AIAR-Timestamp": ts, "X-AIAR-Nonce": nonce, "X-AIAR-Signature": sig})
    return client.post(path, content=body, headers=headers)


def payload(p: Path, **extra):
    return {"filename": p.name, "file_b64": base64.b64encode(p.read_bytes()).decode(), **extra}


def issue_count(profile, col, code):
    c = next(c for c in profile["columns"] if c["name"] == col)
    return next((i["count"] for i in c["issues"] if i["code"] == code), 0)


def test_requires_signature():
    assert call("/api/v1/datasets/inspect", payload(SALES), sign=False).status_code == 401


def test_inspect_excel_picks_data_sheet():
    r = call("/api/v1/datasets/inspect", payload(SALES))
    assert r.status_code == 200
    d = r.json()
    sheets = {s["name"]: s for s in d["sheets"]}
    assert d["default_sheet"] == "Đơn hàng"
    assert sheets["Ghi chú"]["tabular"] is False
    assert sheets["Đơn hàng"]["n_rows"] == 3886 and sheets["Đơn hàng"]["n_cols"] == 13


def test_preview_first_20_rows():
    r = call("/api/v1/datasets/preview", payload(SALES, sheet="Đơn hàng"))
    d = r.json()
    assert len(d["rows"]) == 20 and d["columns"][0] == "Mã đơn hàng" and d["row_numbers"][0] == 2


def test_profile_sales_matches_injected_defects():
    r = call("/api/v1/datasets/profile", payload(SALES, sheet="Đơn hàng"))
    assert r.status_code == 200
    p = r.json()
    assert p["summary"]["n_rows"] == 3886 and p["duplicates"]["full_rows"] == 30
    assert issue_count(p, "Mã khách hàng", "missing") == 25
    assert issue_count(p, "Thành phố", "missing") == 130
    assert issue_count(p, "Giảm giá (%)", "missing") == 60
    assert issue_count(p, "Đơn giá", "missing") == 35
    assert issue_count(p, "Ngày đặt hàng", "date_as_text") == 60
    assert issue_count(p, "Ngày đặt hàng", "date_invalid") == 3
    assert issue_count(p, "Ngày đặt hàng", "placeholder") == 3
    assert issue_count(p, "Đơn giá", "number_dirty") == 20
    assert issue_count(p, "Số lượng", "number_dirty") == 15
    assert issue_count(p, "Số lượng", "outlier") == 8
    assert issue_count(p, "Số lượng", "negative") == 6
    assert issue_count(p, "Danh mục", "category_variants") + issue_count(p, "Danh mục", "whitespace") == 40
    amount = next(r for r in p["relationships"] if r["code"] == "amount_formula")
    assert amount["count"] == 5
    m = {k: v["column"] for k, v in p["mapping"]["suggested"].items()}
    assert m["date"] == "Ngày đặt hàng" and m["amount"] == "Thành tiền" and m["customer_id"] == "Mã khách hàng"
    assert p["facts"]["date_months"]["Ngày đặt hàng"] == 21


def test_profile_students_is_not_revenue_data():
    p = call("/api/v1/datasets/profile", payload(STUDENTS)).json()
    m = p["mapping"]["suggested"]
    assert "date" not in m and "amount" not in m and "customer_id" not in m  # không giả định là dữ liệu doanh thu
    assert p["duplicates"]["full_rows"] == 8
    assert issue_count(p, "Điểm giữa kỳ", "out_of_range") == 6
    assert issue_count(p, "Điểm cuối kỳ", "not_a_number") == 10
    assert issue_count(p, "Số buổi vắng", "outlier") == 4
    assert issue_count(p, "Ngày sinh", "date_mixed_format") == 40
    lin = next(r for r in p["relationships"] if r["code"] == "linear_total")
    assert "0.10×Điểm chuyên cần + 0.30×Điểm giữa kỳ + 0.60×Điểm cuối kỳ" in lin["message"]
    assert 12 <= lin["count"] <= 20


def clean(p: Path, ids=None, sheet=None, only_default=True):
    prof = call("/api/v1/datasets/profile", payload(p, sheet=sheet)).json()
    chosen = [s for s in prof["suggestions"] if (s["selected"] if ids is None else s["id"] in ids)]
    plan = [{k: s[k] for k in ("id", "action", "column", "params")} for s in chosen]
    r = call("/api/v1/datasets/clean", payload(p, sheet=sheet, plan=plan))
    assert r.status_code == 200, r.text
    out = r.json()
    rows = list(csv.reader(io.StringIO(base64.b64decode(out["csv_b64"]).decode("utf-8-sig"))))
    return out, rows[0], rows[1:]


def test_clean_sales_default_plan():
    out, header, rows = clean(SALES, sheet="Đơn hàng")
    col = {h: i for i, h in enumerate(header)}
    assert out["rows_before"] == 3886 and out["rows_after"] == 3856
    assert len({r[col["Danh mục"]] for r in rows}) == 5
    assert all(r[col["Ngày đặt hàng"]] == "" or len(r[col["Ngày đặt hàng"]]) == 10 and r[col["Ngày đặt hàng"]][4] == "-" for r in rows)
    assert not any("đ" in r[col["Đơn giá"]] or "." in r[col["Đơn giá"]] for r in rows)
    assert not any("cái" in r[col["Số lượng"]] for r in rows)
    assert sum(1 for r in rows if r[col["Ngày đặt hàng"]] == "") == 6  # 3 ký hiệu thiếu + 3 ngày không hợp lệ
    assert sum(1 for r in rows if r[col["Mã khách hàng"]] == "") == 25  # không tự điền mã khách hàng
    assert sum(1 for r in rows if r[col["Đơn giá"]] == "") == 35  # không tự điền đơn giá


def test_clean_only_does_what_was_selected():
    out, header, rows = clean(SALES, ids={"drop_duplicates"}, sheet="Đơn hàng")
    assert out["rows_after"] == 3856 and len(out["applied"]) == 1
    col = {h: i for i, h in enumerate(header)}
    assert any("đ" in r[col["Đơn giá"]] for r in rows)  # chưa chọn nên chưa sửa


def test_clean_outliers_become_empty_not_filled():
    out, header, rows = clean(SALES, ids={"set_missing:Số lượng:outlier"}, sheet="Đơn hàng")
    col = {h: i for i, h in enumerate(header)}
    assert not any(r[col["Số lượng"]] == "500" for r in rows)
    assert sum(1 for r in rows if r[col["Số lượng"]] == "") == 8


def test_clean_students():
    out, header, rows = clean(STUDENTS)
    col = {h: i for i, h in enumerate(header)}
    assert out["rows_after"] == 600
    assert {r[col["Giới tính"]] for r in rows} == {"Nam", "Nữ"}
    assert all(len(r[col["Ngày sinh"]]) == 10 and r[col["Ngày sinh"]][4] == "-" for r in rows)
    assert not any(r[col["Điểm cuối kỳ"]] == "Vắng" for r in rows)


def test_rejects_bad_files():
    b64 = base64.b64encode(b"x,y\n1,2\n").decode()
    assert call("/api/v1/datasets/inspect", {"filename": "a.xls", "file_b64": b64}).status_code == 422
    assert call("/api/v1/datasets/inspect", {"filename": "a.exe", "file_b64": b64}).status_code == 422
    assert call("/api/v1/datasets/inspect", {"filename": "a.xlsx", "file_b64": b64}).status_code == 422
    zipped = base64.b64encode(SALES.read_bytes()).decode()
    assert call("/api/v1/datasets/inspect", {"filename": "fake.csv", "file_b64": zipped}).status_code == 422
    assert call("/api/v1/datasets/inspect", {"filename": "a.csv", "file_b64": "!!!"}).status_code == 422


def test_body_limit(monkeypatch):
    monkeypatch.setenv("AIAR_MAX_FILE_MB", "1")
    big = base64.b64encode(b"a,b\n" + b"1,2\n" * 600_000).decode()
    r = call("/api/v1/datasets/inspect", {"filename": "big.csv", "file_b64": big})
    assert r.status_code == 413


def test_parsing_helpers():
    assert parse_number("1.250.000đ") == (1250000.0, "dirty")
    assert parse_number("1,250,000") == (1250000.0, "text")
    assert parse_number("12,5") == (12.5, "text")
    assert parse_number("7.5") == (7.5, "text")
    assert parse_number("0.125") == (0.125, "text")
    assert parse_number("2 cái") == (2.0, "dirty")
    assert parse_number("KH0001")[1] is None and parse_number("SV2300001")[1] is None
    assert parse_number("15/03/2026")[1] is None and parse_number("Vắng")[1] is None
    assert parse_date("15/03/2026")[0].isoformat() == "2026-03-15"
    assert parse_date("2026-03-15")[2] == "yyyy-mm-dd"
    assert parse_date("31/02/2026")[1] == "invalid" and parse_date("2026-13-05")[1] == "invalid"
    assert parse_date("hello")[1] is None
