import platform
import time
from importlib import metadata

from fastapi import APIRouter, Depends

from ..auth import verify_signature

router = APIRouter()
_started_at = time.time()

_LIBS = ["fastapi", "pandas", "numpy", "openpyxl", "scikit-learn"]


def _version(name: str) -> str:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return "chưa cài"


@router.get("/healthz", include_in_schema=False)
def healthz():
    """Không cần xác thực, không lộ thông tin. Dùng để Render kiểm tra và để đánh thức dịch vụ."""
    return {"status": "ok"}


@router.get("/api/v1/health", dependencies=[Depends(verify_signature)])
def health():
    return {
        "status": "ok",
        "service": "ai-report-service",
        "version": "0.4.0",
        "python": platform.python_version(),
        "libraries": {lib: _version(lib) for lib in _LIBS},
        "uptime_seconds": int(time.time() - _started_at),
        "server_time": int(time.time()),
    }
