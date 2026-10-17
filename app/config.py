"""Cấu hình đọc từ biến môi trường (đọc mỗi lần gọi để dễ kiểm thử)."""
import os


class Settings:
    def __init__(self) -> None:
        self.shared_secret: str = os.getenv("AIAR_SHARED_SECRET", "")
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
