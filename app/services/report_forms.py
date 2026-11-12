"""Biểu mẫu báo cáo tài chính theo Thông tư 200/2014/TT-BTC và Thông tư 133/2016/TT-BTC.

Mỗi dòng: mã số | cấp thụt lề | tên chỉ tiêu | công thức cộng/trừ các mã con (nếu có).
Số liệu lấy đúng dòng theo mã số trong báo cáo người dùng tải lên. Nếu dòng không có trong dữ liệu nhưng
các dòng con có, hệ thống tính lại theo công thức của biểu mẫu và đánh dấu "(tính lại)". Không có gì thì để "—".
Tên và mã số đối chiếu từ biểu mẫu công bố; cần đối chiếu lại với văn bản gốc trước khi nộp chính thức.
"""
from typing import Any, Dict, List, Optional, Tuple

# --------------------------------------------------------------- B01-DN (TT200)
_B01_DN = """
100|0|A - TÀI SẢN NGẮN HẠN|110+120+130+140+150
110|1|I. Tiền và các khoản tương đương tiền|111+112
111|2|1. Tiền
112|2|2. Các khoản tương đương tiền
120|1|II. Đầu tư tài chính ngắn hạn|121+122+123
121|2|1. Chứng khoán kinh doanh
122|2|2. Dự phòng giảm giá chứng khoán kinh doanh (*)
123|2|3. Đầu tư nắm giữ đến ngày đáo hạn
130|1|III. Các khoản phải thu ngắn hạn|131+132+133+134+135+136+137+139
131|2|1. Phải thu ngắn hạn của khách hàng
132|2|2. Trả trước cho người bán ngắn hạn
133|2|3. Phải thu nội bộ ngắn hạn
134|2|4. Phải thu theo tiến độ kế hoạch hợp đồng xây dựng
135|2|5. Phải thu về cho vay ngắn hạn
136|2|6. Phải thu ngắn hạn khác
137|2|7. Dự phòng phải thu ngắn hạn khó đòi (*)
139|2|8. Tài sản thiếu chờ xử lý
140|1|IV. Hàng tồn kho|141+149
141|2|1. Hàng tồn kho
149|2|2. Dự phòng giảm giá hàng tồn kho (*)
150|1|V. Tài sản ngắn hạn khác|151+152+153+154+155
151|2|1. Chi phí trả trước ngắn hạn
152|2|2. Thuế GTGT được khấu trừ
153|2|3. Thuế và các khoản khác phải thu Nhà nước
154|2|4. Giao dịch mua bán lại trái phiếu Chính phủ
155|2|5. Tài sản ngắn hạn khác
200|0|B - TÀI SẢN DÀI HẠN|210+220+230+240+250+260
210|1|I. Các khoản phải thu dài hạn|211+212+213+214+215+216+219
211|2|1. Phải thu dài hạn của khách hàng
212|2|2. Trả trước cho người bán dài hạn
213|2|3. Vốn kinh doanh ở đơn vị trực thuộc
214|2|4. Phải thu nội bộ dài hạn
215|2|5. Phải thu về cho vay dài hạn
216|2|6. Phải thu dài hạn khác
219|2|7. Dự phòng phải thu dài hạn khó đòi (*)
220|1|II. Tài sản cố định|221+224+227
221|2|1. Tài sản cố định hữu hình|222+223
222|3|- Nguyên giá
223|3|- Giá trị hao mòn luỹ kế (*)
224|2|2. Tài sản cố định thuê tài chính|225+226
225|3|- Nguyên giá
226|3|- Giá trị hao mòn luỹ kế (*)
227|2|3. Tài sản cố định vô hình|228+229
228|3|- Nguyên giá
229|3|- Giá trị hao mòn luỹ kế (*)
230|1|III. Bất động sản đầu tư|231+232
231|2|- Nguyên giá
232|2|- Giá trị hao mòn luỹ kế (*)
240|1|IV. Tài sản dở dang dài hạn|241+242
241|2|1. Chi phí sản xuất, kinh doanh dở dang dài hạn
242|2|2. Chi phí xây dựng cơ bản dở dang
250|1|V. Đầu tư tài chính dài hạn|251+252+253+254+255
251|2|1. Đầu tư vào công ty con
252|2|2. Đầu tư vào công ty liên doanh, liên kết
253|2|3. Đầu tư góp vốn vào đơn vị khác
254|2|4. Dự phòng đầu tư tài chính dài hạn (*)
255|2|5. Đầu tư nắm giữ đến ngày đáo hạn
260|1|VI. Tài sản dài hạn khác|261+262+263+268
261|2|1. Chi phí trả trước dài hạn
262|2|2. Tài sản thuế thu nhập hoãn lại
263|2|3. Thiết bị, vật tư, phụ tùng thay thế dài hạn
268|2|4. Tài sản dài hạn khác
270|0|TỔNG CỘNG TÀI SẢN (270 = 100 + 200)|100+200
300|0|C - NỢ PHẢI TRẢ|310+330
310|1|I. Nợ ngắn hạn|311+312+313+314+315+316+317+318+319+320+321+322+323+324
311|2|1. Phải trả người bán ngắn hạn
312|2|2. Người mua trả tiền trước ngắn hạn
313|2|3. Thuế và các khoản phải nộp Nhà nước
314|2|4. Phải trả người lao động
315|2|5. Chi phí phải trả ngắn hạn
316|2|6. Phải trả nội bộ ngắn hạn
317|2|7. Phải trả theo tiến độ kế hoạch hợp đồng xây dựng
318|2|8. Doanh thu chưa thực hiện ngắn hạn
319|2|9. Phải trả ngắn hạn khác
320|2|10. Vay và nợ thuê tài chính ngắn hạn
321|2|11. Dự phòng phải trả ngắn hạn
322|2|12. Quỹ khen thưởng, phúc lợi
323|2|13. Quỹ bình ổn giá
324|2|14. Giao dịch mua bán lại trái phiếu Chính phủ
330|1|II. Nợ dài hạn|331+332+333+334+335+336+337+338+339+340+341+342+343
331|2|1. Phải trả người bán dài hạn
332|2|2. Người mua trả tiền trước dài hạn
333|2|3. Chi phí phải trả dài hạn
334|2|4. Phải trả nội bộ về vốn kinh doanh
335|2|5. Phải trả nội bộ dài hạn
336|2|6. Doanh thu chưa thực hiện dài hạn
337|2|7. Phải trả dài hạn khác
338|2|8. Vay và nợ thuê tài chính dài hạn
339|2|9. Trái phiếu chuyển đổi
340|2|10. Cổ phiếu ưu đãi
341|2|11. Thuế thu nhập hoãn lại phải trả
342|2|12. Dự phòng phải trả dài hạn
343|2|13. Quỹ phát triển khoa học và công nghệ
400|0|D - VỐN CHỦ SỞ HỮU|410+430
410|1|I. Vốn chủ sở hữu|411+412+413+414+415+416+417+418+419+420+421+422
411|2|1. Vốn góp của chủ sở hữu|411a+411b
411a|3|- Cổ phiếu phổ thông có quyền biểu quyết
411b|3|- Cổ phiếu ưu đãi
412|2|2. Thặng dư vốn cổ phần
413|2|3. Quyền chọn chuyển đổi trái phiếu
414|2|4. Vốn khác của chủ sở hữu
415|2|5. Cổ phiếu quỹ (*)
416|2|6. Chênh lệch đánh giá lại tài sản
417|2|7. Chênh lệch tỷ giá hối đoái
418|2|8. Quỹ đầu tư phát triển
419|2|9. Quỹ hỗ trợ sắp xếp doanh nghiệp
420|2|10. Quỹ khác thuộc vốn chủ sở hữu
421|2|11. Lợi nhuận sau thuế chưa phân phối|421a+421b
421a|3|- LNST chưa phân phối lũy kế đến cuối kỳ trước
421b|3|- LNST chưa phân phối kỳ này
422|2|12. Nguồn vốn đầu tư XDCB
430|1|II. Nguồn kinh phí và quỹ khác|431+432
431|2|1. Nguồn kinh phí
432|2|2. Nguồn kinh phí đã hình thành TSCĐ
440|0|TỔNG CỘNG NGUỒN VỐN (440 = 300 + 400)|300+400
"""

# --------------------------------------------------------------- B02-DN (TT200)
_B02_DN = """
01|0|1. Doanh thu bán hàng và cung cấp dịch vụ
02|0|2. Các khoản giảm trừ doanh thu
10|0|3. Doanh thu thuần về bán hàng và cung cấp dịch vụ (10 = 01 - 02)|01-02
11|0|4. Giá vốn hàng bán
20|0|5. Lợi nhuận gộp về bán hàng và cung cấp dịch vụ (20 = 10 - 11)|10-11
21|0|6. Doanh thu hoạt động tài chính
22|0|7. Chi phí tài chính
23|1|- Trong đó: Chi phí lãi vay
25|0|8. Chi phí bán hàng
26|0|9. Chi phí quản lý doanh nghiệp
30|0|10. Lợi nhuận thuần từ hoạt động kinh doanh {30 = 20 + (21 - 22) - (25 + 26)}|20+21-22-25-26
31|0|11. Thu nhập khác
32|0|12. Chi phí khác
40|0|13. Lợi nhuận khác (40 = 31 - 32)|31-32
50|0|14. Tổng lợi nhuận kế toán trước thuế (50 = 30 + 40)|30+40
51|0|15. Chi phí thuế TNDN hiện hành
52|0|16. Chi phí thuế TNDN hoãn lại
60|0|17. Lợi nhuận sau thuế thu nhập doanh nghiệp (60 = 50 - 51 - 52)|50-51-52
70|0|18. Lãi cơ bản trên cổ phiếu (*)
71|0|19. Lãi suy giảm trên cổ phiếu (*)
"""

# --------------------------------------------------------------- B02-DNN (TT133)
_B02_DNN = """
01|0|1. Doanh thu bán hàng và cung cấp dịch vụ
02|0|2. Các khoản giảm trừ doanh thu
10|0|3. Doanh thu thuần về bán hàng và cung cấp dịch vụ (10 = 01 - 02)|01-02
11|0|4. Giá vốn hàng bán
20|0|5. Lợi nhuận gộp về bán hàng và cung cấp dịch vụ (20 = 10 - 11)|10-11
21|0|6. Doanh thu hoạt động tài chính
22|0|7. Chi phí tài chính
23|1|- Trong đó: Chi phí lãi vay
24|0|8. Chi phí quản lý kinh doanh
30|0|9. Lợi nhuận thuần từ hoạt động kinh doanh (30 = 20 + 21 - 22 - 24)|20+21-22-24
31|0|10. Thu nhập khác
32|0|11. Chi phí khác
40|0|12. Lợi nhuận khác (40 = 31 - 32)|31-32
50|0|13. Tổng lợi nhuận kế toán trước thuế (50 = 30 + 40)|30+40
51|0|14. Chi phí thuế TNDN
60|0|15. Lợi nhuận sau thuế thu nhập doanh nghiệp (60 = 50 - 51)|50-51
"""
# Mã 23 là "trong đó" của 22 nên không tham gia công thức cộng.


def _parse(text: str) -> List[Dict[str, Any]]:
    out = []
    for ln in text.strip().splitlines():
        p = ln.split("|")
        formula = []
        if len(p) > 3 and p[3]:
            import re
            for sign, code in re.findall(r"([+-]?)(\d+[a-z]?)", p[3]):
                formula.append((-1 if sign == "-" else 1, code))
        out.append({"code": p[0], "level": int(p[1]), "label": p[2], "formula": formula})
    return out


FORMS: Dict[str, Dict[str, Any]] = {
    "bs_tt200": {"code": "B01-DN", "title": "Bảng cân đối kế toán (Mẫu B01-DN, Thông tư 200/2014/TT-BTC)", "type": "bs", "lines": _parse(_B01_DN)},
    "is_tt200": {"code": "B02-DN", "title": "Báo cáo kết quả hoạt động kinh doanh (Mẫu B02-DN, Thông tư 200/2014/TT-BTC)", "type": "is", "lines": _parse(_B02_DN)},
    "is_tt133": {"code": "B02-DNN", "title": "Báo cáo kết quả hoạt động kinh doanh (Mẫu B02-DNN, Thông tư 133/2016/TT-BTC)", "type": "is", "lines": _parse(_B02_DNN)},
}


def _norm_code(c: Any) -> str:
    return str(c or "").strip().lower().rstrip(".").replace(" ", "")


def fill_form(form_key: str, statements: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Điền biểu mẫu từ các báo cáo đã đọc. Trả về {periods, rows:[{code,level,label,values,calc}], found, total}."""
    f = FORMS[form_key]
    sts = [s for s in statements or [] if isinstance(s, dict) and s.get("type") == f["type"]]
    if not sts:
        return {"periods": [], "rows": [], "found": 0, "total": len(f["lines"]), "calc": 0}
    periods: List[Dict[str, Any]] = []
    by_code: Dict[str, Dict[str, Optional[float]]] = {}
    for st in sts:
        for j, p in enumerate(st.get("periods") or []):
            if not any(q["pid"] == p["pid"] for q in periods):
                periods.append(p)
        for r in st.get("rows") or []:
            code = _norm_code(r.get("code"))
            if not code or not r.get("has_values") or code in by_code:
                continue
            by_code[code] = {st["periods"][j]["pid"]: v for j, v in enumerate(r.get("values") or []) if j < len(st["periods"])}
    periods.sort(key=lambda p: tuple(p.get("sort") or ()))
    pids = [p["pid"] for p in periods]
    lines = {ln["code"]: ln for ln in f["lines"]}
    memo: Dict[str, Tuple[Dict[str, Optional[float]], bool]] = {}

    def val(code: str, stack=()) -> Tuple[Dict[str, Optional[float]], bool]:
        if code in memo:
            return memo[code]
        res: Dict[str, Optional[float]] = {pid: None for pid in pids}
        calc = False
        if code in by_code:
            res = {pid: by_code[code].get(pid) for pid in pids}
        elif code in lines and lines[code]["formula"] and code not in stack:
            parts = [(sg, val(c, stack + (code,))[0]) for sg, c in lines[code]["formula"]]
            for pid in pids:
                got = [(sg, d[pid]) for sg, d in parts if d.get(pid) is not None]
                if got:
                    res[pid] = sum(sg * v for sg, v in got)
                    calc = True
        memo[code] = (res, calc)
        return memo[code]

    rows, found, ncalc = [], 0, 0
    for ln in f["lines"]:
        v, calc = val(ln["code"])
        has = any(x is not None for x in v.values())
        if has and not calc:
            found += 1
        if has and calc:
            ncalc += 1
        rows.append({"code": ln["code"], "level": ln["level"], "label": ln["label"], "values": [v[pid] for pid in pids], "calc": calc and has})
    return {"periods": periods, "rows": rows, "found": found, "calc": ncalc, "total": len(f["lines"])}
