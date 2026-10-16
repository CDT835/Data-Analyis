"""Cấu hình đọc từ biến môi trường (đọc mỗi lần gọi để dễ kiểm thử)."""
import os


class Settings:
    def __init__(self) -> None:
        self.shared_secret: str = os.getenv("AIAR_SHARED_SECRET", "")
        self.max_skew_seconds: int = int(os.getenv("AIAR_MAX_SKEW_SECONDS", "300"))
        self.enable_docs: bool = os.getenv("AIAR_ENABLE_DOCS", "0") == "1"


def get_settings() -> Settings:
    return Settings()
