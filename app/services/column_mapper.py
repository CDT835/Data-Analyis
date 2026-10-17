"""Gợi ý vai trò của từng cột (ngày, số tiền, mã khách hàng...) dựa vào tên cột và kiểu dữ liệu.

Chỉ là gợi ý có kèm lý do; người dùng luôn là người xác nhận. Không có cột phù hợp thì để trống,
không tự đoán bừa (để không giả định mọi file đều là dữ liệu doanh thu).
"""
import re
from typing import Any, Dict, List

from .parsing import norm_key

ROLES = [
    ("date", "Cột ngày/thời gian", "Dùng cho xu hướng theo thời gian và dự báo"),
    ("amount", "Cột số tiền/doanh thu", "Dùng cho tổng doanh thu, xu hướng, RFM"),
    ("customer_id", "Mã khách hàng", "Dùng cho phân nhóm khách hàng RFM"),
    ("order_id", "Mã đơn hàng", "Dùng để đếm số đơn và phát hiện trùng"),
    ("quantity", "Số lượng", "Dùng để kiểm tra Thành tiền = Số lượng × Đơn giá"),
    ("unit_price", "Đơn giá", "Dùng để kiểm tra Thành tiền"),
    ("discount", "Giảm giá", "Dùng để kiểm tra Thành tiền"),
    ("category", "Nhóm/danh mục", "Dùng để phân tích theo nhóm"),
    ("product", "Sản phẩm", "Dùng để phân tích theo sản phẩm"),
    ("region", "Khu vực/thành phố", "Dùng để phân tích theo khu vực"),
]

# role -> (kiểu cột chấp nhận, danh sách mẫu tên theo thứ tự ưu tiên, mẫu loại trừ)
RULES: Dict[str, Dict[str, Any]] = {
    "date": {"types": {"date"}, "patterns": ["ngay dat", "ngay ban", "ngay giao dich", "ngay hoa don", "order date", "ngay", "date", "thoi gian", "time"],
             "exclude": ["ngay sinh", "sinh nhat", "birth", "dob", "het han", "han su dung"]},
    "amount": {"types": {"numeric"}, "patterns": ["thanh tien", "doanh thu", "tong tien", "tong gia tri", "so tien", "revenue", "amount", "total", "sales", "gia tri"],
               "exclude": ["diem", "score"]},
    "customer_id": {"types": {"id", "text", "category", "numeric"}, "patterns": ["ma khach", "ma kh", "customer id", "customer_id", "cust id", "ma nguoi mua"],
                    "exclude": [], "weak": ["khach hang", "customer"]},
    "order_id": {"types": {"id", "text", "numeric"}, "patterns": ["ma don", "so don", "ma hoa don", "so hoa don", "order id", "order_id", "invoice"], "exclude": []},
    "quantity": {"types": {"numeric"}, "patterns": ["so luong", "quantity", "qty", "sl"], "exclude": []},
    "unit_price": {"types": {"numeric"}, "patterns": ["don gia", "gia ban", "unit price", "price"], "exclude": []},
    "discount": {"types": {"numeric"}, "patterns": ["giam gia", "chiet khau", "discount"], "exclude": []},
    "category": {"types": {"category", "text"}, "patterns": ["danh muc", "nhom hang", "phan loai", "category", "loai"], "exclude": []},
    "product": {"types": {"category", "text", "id"}, "patterns": ["san pham", "ten hang", "mat hang", "product", "item"], "exclude": []},
    "region": {"types": {"category", "text"}, "patterns": ["thanh pho", "tinh", "khu vuc", "vung", "city", "region", "dia chi"], "exclude": ["gioi tinh", "tinh trang"]},
}


def _has(key: str, pattern: str) -> bool:
    return re.search(rf"(^|[^a-z0-9]){re.escape(pattern)}([^a-z0-9]|$)", key) is not None


def suggest_mapping(columns: List[Dict[str, Any]]) -> Dict[str, Any]:
    candidates: List[Dict[str, Any]] = []
    for role, rule in RULES.items():
        for col in columns:
            key = norm_key(col["name"])
            if col["type"] not in rule["types"] or any(_has(key, p) for p in rule["exclude"]):
                continue
            score, why = 0.0, ""
            for rank, p in enumerate(rule["patterns"]):
                if _has(key, p):
                    score = max(0.5, 0.95 - 0.06 * rank)
                    why = f"Tên cột chứa “{p}” và kiểu dữ liệu phù hợp"
                    break
            if not score:
                for p in rule.get("weak", []):
                    if _has(key, p):
                        score, why = 0.35, f"Tên cột chứa “{p}” (độ tin cậy thấp, cần bạn xác nhận)"
                        break
            if score:
                candidates.append({"role": role, "column": col["name"], "confidence": round(score, 2), "reason": why})

    candidates.sort(key=lambda c: -c["confidence"])
    suggested: Dict[str, Any] = {}
    used = set()
    for c in candidates:
        if c["role"] in suggested or c["column"] in used:
            continue
        suggested[c["role"]] = c
        used.add(c["column"])
    alternatives = {r: [c["column"] for c in candidates if c["role"] == r] for r, _, _ in ROLES}
    return {
        "roles": [{"key": k, "label": label, "hint": hint} for k, label, hint in ROLES],
        "suggested": {r: {"column": s["column"], "confidence": s["confidence"], "reason": s["reason"]} for r, s in suggested.items()},
        "alternatives": alternatives,
    }
