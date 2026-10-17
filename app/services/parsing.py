"""Hàm đọc và chuẩn hóa từng ô dữ liệu (số, ngày, giá trị thiếu, bỏ dấu tiếng Việt)."""
import datetime as dt
import re
import unicodedata
from typing import Any, Optional, Tuple

# Các chuỗi thường dùng để thay cho "không có dữ liệu"
PLACEHOLDERS = {
    "n/a", "na", "#n/a", "null", "none", "nan", "--", "-", "?", "missing",
    "không rõ", "khong ro", "chưa rõ", "chua ro", "(trống)", "trống", "trong",
}


def strip_accents(text: str) -> str:
    text = text.replace("đ", "d").replace("Đ", "D")
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


def norm_key(text: Any) -> str:
    """Khóa so sánh: bỏ dấu, hạ chữ thường, gộp khoảng trắng."""
    return re.sub(r"\s+", " ", strip_accents(str(text)).strip().casefold())


def collapse_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def is_missing(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, float) and v != v:
        return True
    if isinstance(v, str) and v.strip() == "":
        return True
    return False


def is_placeholder(v: Any) -> bool:
    return isinstance(v, str) and v.strip().lower() in PLACEHOLDERS


# ---------------------------------------------------------------- số
_NUM_RE = re.compile(r"[-+]?\d[\d.,]*")
_PREFIX_OK = re.compile(r"^[\$₫€£]?$")
_SPACE_THOUSANDS = re.compile(r"^\d{1,3}(?:[ \u00a0]\d{3})+$")


def parse_number(v: Any) -> Tuple[Optional[float], Optional[str]]:
    """Trả về (giá trị, loại). loại: 'native' | 'text' (chuỗi chỉ gồm số) | 'dirty' (có đơn vị/ký hiệu) | None."""
    if isinstance(v, bool):
        return None, None
    if isinstance(v, (int, float)):
        if isinstance(v, float) and (v != v or v in (float("inf"), float("-inf"))):
            return None, None
        return float(v), "native"
    if not isinstance(v, str):
        return None, None
    s = v.strip()
    if not s:
        return None, None
    if _SPACE_THOUSANDS.match(s):
        s = re.sub(r"[ \u00a0]", "", s)
    m = _NUM_RE.search(s)
    if not m:
        return None, None
    prefix, suffix = s[: m.start()].strip(), s[m.end():].strip()
    # Tiền tố chữ (KH0001, SV23...) là mã, không phải số; hậu tố chứa chữ số là ngày/phân số
    if not _PREFIX_OK.match(prefix) or len(suffix) > 10 or re.search(r"\d", suffix):
        return None, None
    raw = m.group(0)
    sign = -1.0 if raw.startswith("-") else 1.0
    digits = raw.lstrip("+-").rstrip(".,")
    try:
        if re.fullmatch(r"\d{1,3}(\.\d{3})+", digits) and not digits.startswith("0."):
            val = float(digits.replace(".", ""))
        elif re.fullmatch(r"\d{1,3}(,\d{3})+", digits) and not digits.startswith("0,"):
            val = float(digits.replace(",", ""))
        elif re.fullmatch(r"\d{1,3}(,\d{3})+\.\d+", digits):
            val = float(digits.replace(",", ""))
        elif re.fullmatch(r"\d{1,3}(\.\d{3})+,\d+", digits):
            val = float(digits.replace(".", "").replace(",", "."))
        elif re.fullmatch(r"\d+,\d+", digits):
            val = float(digits.replace(",", "."))
        elif re.fullmatch(r"\d+(\.\d+)?", digits):
            val = float(digits)
        else:
            return None, None
    except ValueError:
        return None, None
    clean = prefix == "" and suffix == ""
    return sign * val, ("text" if clean else "dirty")


# ---------------------------------------------------------------- ngày
_DATE_RE = re.compile(
    r"^\s*(\d{1,4})([/\-.])(\d{1,2})\2(\d{1,4})(?:[ T]\d{1,2}:\d{2}(?::\d{2})?(?:\.\d+)?)?\s*$"
)


def parse_date(v: Any) -> Tuple[Optional[dt.date], Optional[str], Optional[str]]:
    """Trả về (ngày, loại, định dạng). loại: 'native' | 'text' | 'invalid' | None (không phải ngày)."""
    if isinstance(v, dt.datetime):
        return v.date(), "native", "native"
    if isinstance(v, dt.date):
        return v, "native", "native"
    if not isinstance(v, str):
        return None, None, None
    m = _DATE_RE.match(v)
    if not m:
        return None, None, None
    a, sep, b, c = m.group(1), m.group(2), m.group(3), m.group(4)
    if len(a) == 4 and len(c) <= 2:
        y, mo, d, fmt = int(a), int(b), int(c), f"yyyy{sep}mm{sep}dd"
    elif len(c) == 4 and len(a) <= 2:
        d, mo, y, fmt = int(a), int(b), int(c), f"dd{sep}mm{sep}yyyy"  # quy ước Việt Nam: ngày trước tháng
    else:
        return None, None, None
    if not 1900 <= y <= 2100:
        return None, "invalid", fmt
    try:
        return dt.date(y, mo, d), "text", fmt
    except ValueError:
        return None, "invalid", fmt


# ---------------------------------------------------------------- xuất
def fmt_cell(v: Any) -> str:
    """Định dạng một ô khi ghi ra CSV đã làm sạch."""
    if v is None:
        return ""
    if isinstance(v, float):
        if v != v:
            return ""
        return str(int(v)) if v.is_integer() else repr(v)
    if isinstance(v, dt.datetime):
        return v.date().isoformat() if v.time() == dt.time(0) else v.isoformat(sep=" ")
    if isinstance(v, dt.date):
        return v.isoformat()
    return str(v)


def preview_cell(v: Any) -> Optional[str]:
    if is_missing(v):
        return None
    s = fmt_cell(v)
    return s if len(s) <= 80 else s[:77] + "..."
