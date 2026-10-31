"""Che dữ liệu nhận diện trước khi gửi nội dung sang dịch vụ AI bên ngoài (Groq).

Dữ kiện gửi đi vốn đã chỉ gồm số liệu đã tính, nhãn kỳ và tên chỉ tiêu; không có tên tệp hay tên người dùng.
Lớp này là chốt chặn thêm: nếu nhãn dòng hay ghi chú trong tệp lỡ chứa email, số điện thoại, mã số thuế/số tài khoản
hoặc tên công ty, chúng được thay bằng "[đã ẩn]" trước khi gửi đi. Chỉ ảnh hưởng phần gửi đi, không đổi dữ kiện lưu trong hệ thống.
"""
import os
import re
from typing import Tuple

MASK = "[đã ẩn]"

_PATTERNS = [
    re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"),                                   # email
    re.compile(r"https?://\S+|www\.\S+"),                                           # liên kết
    re.compile(r"(?<!\d)(?<!\d[.,])(?:\+84|0)[\s-]?\d{2,3}[\s-]?\d{3}[\s-]?\d{3,4}(?!\d)(?![.,]\d)"),  # số điện thoại VN
    re.compile(r"(?<!\d)(?<!\d[.,])\d{10,}(?!\d)(?![.,]\d)"),                                    # dãy ≥10 chữ số liền (MST, số tài khoản, CCCD)
    # tên công ty: sau từ khóa lấy tối đa 6 từ tiếp theo, dừng ở dấu câu hoặc từ nối (và, của, là, có, tại, trong, với, cho)
    re.compile(r"\b(?:Công ty|Cty|CTCP|CTY|Tập đoàn|Ngân hàng|Doanh nghiệp tư nhân|DNTN)\b(?:\s+(?!(?:và|của|là|có|tại|trong|với|cho)\b)[\wÀ-ỹ&-]+){1,6}"),
]


def enabled() -> bool:
    return os.getenv("AIAR_AI_MASK", "1").strip().lower() not in ("0", "false", "no", "off")


def mask(text: str) -> Tuple[str, int]:
    """Trả về (văn bản đã che, số vị trí đã che)."""
    total = 0
    for pat in _PATTERNS:
        text, n = pat.subn(MASK, text)
        total += n
    return text, total
