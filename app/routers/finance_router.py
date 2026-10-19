"""API phân tích báo cáo tài chính."""
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import verify_signature
from ..services import finance, loader
from .datasets import FilePayload, _decode, _guard

router = APIRouter(prefix="/api/v1/finance", dependencies=[Depends(verify_signature)])


class ReanalyzePayload(BaseModel):
    parsed: Dict[str, Any]
    overrides: Dict[str, Any] = Field(default_factory=dict)


@router.post("/parse")
def parse(p: FilePayload):
    raw = _decode(p)
    return _guard(lambda: finance.parse_and_evaluate(raw, p.filename))


@router.post("/analyze")
def analyze(p: ReanalyzePayload):
    """Tính lại với khoản mục do người dùng chọn; không cần gửi lại tệp."""
    try:
        return finance.evaluate(p.parsed, p.overrides)
    except loader.LoadError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except (KeyError, TypeError, ValueError, IndexError, StopIteration):
        raise HTTPException(status_code=422, detail="Dữ liệu báo cáo đã đọc không hợp lệ, hãy đọc lại tệp.")
