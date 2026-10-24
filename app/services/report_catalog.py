"""Danh mục mẫu báo cáo tài chính (một nguồn duy nhất; plugin WordPress giữ bản sao cùng nội dung).

4 mẫu và 18 phần. Mỗi mẫu có điều kiện dữ liệu: "bs" (Bảng cân đối kế toán), "is" (Báo cáo kết quả kinh doanh)
hoặc None (không đòi hỏi). Phần nào thiếu dữ liệu sẽ tự bỏ qua kèm lý do, không bịa số.
"""
from typing import Any, Dict, List, Optional

# slug -> (tiêu đề, cần báo cáo nào: None | "bs" | "is")
SECTIONS: Dict[str, Dict[str, Any]] = {
    "info": {"title": "Thông tin báo cáo", "needs": None},
    "scope": {"title": "Phạm vi và nguồn dữ liệu", "needs": None},
    "data_checks": {"title": "Kiểm tra số liệu", "needs": None},
    "kpis": {"title": "Chỉ tiêu chính kỳ gần nhất", "needs": None},
    "revenue_profit_chart": {"title": "Biểu đồ doanh thu và lợi nhuận", "needs": "is"},
    "liquidity": {"title": "Khả năng thanh toán", "needs": "bs"},
    "leverage": {"title": "Cơ cấu vốn và đòn bẩy tài chính", "needs": "bs"},
    "profitability": {"title": "Khả năng sinh lời", "needs": "is"},
    "efficiency": {"title": "Hiệu quả hoạt động", "needs": "bs"},
    "dupont": {"title": "Phân tích DuPont", "needs": "bs"},
    "growth": {"title": "Tăng trưởng các chỉ tiêu chính", "needs": None},
    "vertical": {"title": "Phân tích cơ cấu (theo chiều dọc)", "needs": None},
    "alerts": {"title": "Cảnh báo", "needs": None},
    "mapping": {"title": "Đối chiếu khoản mục", "needs": None},
    "ai_summary": {"title": "Tóm tắt của AI", "needs": None},
    "ai_detail": {"title": "Nhận xét chi tiết của AI", "needs": None},
    "ai_reco": {"title": "Khuyến nghị và phân tích nên làm tiếp", "needs": None},
    "notes": {"title": "Ghi chú và giới hạn của phân tích", "needs": None},
}
ORDER: List[str] = list(SECTIONS)

TEMPLATES: Dict[str, Dict[str, Any]] = {
    "fin_overview": {
        "name": "Báo cáo phân tích tài chính tổng hợp",
        "description": "Toàn cảnh tình hình tài chính: thanh toán, cơ cấu vốn, sinh lời, hiệu quả, DuPont, tăng trưởng và nhận xét AI.",
        "needs": None,
        "sections": ORDER[:],
        "default_off": ["mapping"],
    },
    "fin_liquidity": {
        "name": "Báo cáo khả năng thanh toán và cơ cấu vốn",
        "description": "Tập trung vào thanh toán ngắn hạn, đòn bẩy và cơ cấu tài sản, nguồn vốn. Cần Bảng cân đối kế toán.",
        "needs": "bs",
        "sections": ["info", "scope", "data_checks", "kpis", "liquidity", "leverage", "vertical", "alerts", "mapping", "ai_summary", "ai_detail", "ai_reco", "notes"],
        "default_off": ["mapping", "ai_detail"],
    },
    "fin_profitability": {
        "name": "Báo cáo khả năng sinh lời và hiệu quả hoạt động",
        "description": "Doanh thu, lợi nhuận, biên lợi nhuận, ROA/ROE, DuPont và vòng quay. Cần Báo cáo kết quả kinh doanh.",
        "needs": "is",
        "sections": ["info", "scope", "data_checks", "kpis", "revenue_profit_chart", "profitability", "efficiency", "dupont", "growth", "alerts", "mapping", "ai_summary", "ai_detail", "ai_reco", "notes"],
        "default_off": ["mapping"],
    },
    "fin_quality": {
        "name": "Báo cáo chất lượng số liệu tài chính",
        "description": "Kết quả kiểm tra các phép cộng và cân đối, lỗi gốc và hệ quả, đối chiếu khoản mục và giới hạn của phân tích.",
        "needs": None,
        "sections": ["info", "scope", "data_checks", "mapping", "alerts", "notes"],
        "default_off": [],
    },
}

NEEDS_LABEL = {"bs": "Bảng cân đối kế toán", "is": "Báo cáo kết quả kinh doanh"}


def available_statements(mapping: Optional[Dict[str, Any]], statements: Optional[List[Dict[str, Any]]]) -> Dict[str, bool]:
    """Báo cáo nào có trong dữ liệu: dựa vào các báo cáo đã đọc và các khoản mục đã ánh xạ."""
    have = {"bs": False, "is": False}
    for st in statements or []:
        if isinstance(st, dict) and st.get("type") in have:
            have[st["type"]] = True
    for v in (mapping or {}).values():
        if isinstance(v, dict) and isinstance(v.get("statement"), str):
            kind = v["statement"].split(":", 1)[0]
            if kind in have:
                have[kind] = True
    return have


def template_status(slug: str, have: Dict[str, bool]) -> Dict[str, Any]:
    t = TEMPLATES[slug]
    need = t["needs"]
    ok = need is None or have.get(need, False)
    return {"slug": slug, "name": t["name"], "description": t["description"], "needs": need,
            "usable": ok, "reason": "" if ok else f"Mẫu này cần {NEEDS_LABEL[need]}, nhưng dữ liệu chưa có báo cáo đó.",
            "sections": [{"slug": s, "title": SECTIONS[s]["title"], "needs": SECTIONS[s]["needs"], "default": s not in t["default_off"],
                          "usable": SECTIONS[s]["needs"] is None or have.get(SECTIONS[s]["needs"], False)} for s in t["sections"]]}


def catalog(have: Optional[Dict[str, bool]] = None) -> List[Dict[str, Any]]:
    have = have if have is not None else {"bs": True, "is": True}
    return [template_status(s, have) for s in TEMPLATES]
