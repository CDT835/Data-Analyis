"""Cấu hình đọc từ biến môi trường (đọc mỗi lần gọi để dễ kiểm thử)."""
import os


class Settings:
    def __init__(self) -> None:
        self.shared_secret: str = os.getenv("AIAR_SHARED_SECRET", "")
        # Khóa cũ, chỉ dùng khi xoay khóa: tạm thời chấp nhận CẢ HAI khóa để đổi khóa không gây gián đoạn
        self.shared_secret_previous: str = os.getenv("AIAR_SHARED_SECRET_PREVIOUS", "")
        self.rate_per_min: int = int(os.getenv("AIAR_RATE_PER_MIN", "120"))      # số yêu cầu hợp lệ tối đa mỗi phút (toàn dịch vụ)
        self.auth_fail_per_min: int = int(os.getenv("AIAR_AUTH_FAIL_PER_MIN", "20"))  # số yêu cầu sai chữ ký tối đa mỗi phút / địa chỉ
        self.max_skew_seconds: int = int(os.getenv("AIAR_MAX_SKEW_SECONDS", "300"))
        self.enable_docs: bool = os.getenv("AIAR_ENABLE_DOCS", "0") == "1"
        # Giới hạn tài nguyên (gói miễn phí chỉ có 512 MB RAM)
        self.max_file_mb: int = int(os.getenv("AIAR_MAX_FILE_MB", "10"))
        self.max_rows: int = int(os.getenv("AIAR_MAX_ROWS", "100000"))
        self.max_cols: int = int(os.getenv("AIAR_MAX_COLS", "200"))

    @property
    def max_body_bytes(self) -> int:
        # base64 làm tăng ~33% kích thước; cộng thêm phần JSON bao quanh
        return int(self.max_file_mb * 1024 * 1024 * 1.4) + 65536


def get_settings() -> Settings:
    return Settings()
