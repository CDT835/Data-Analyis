"""API phân tích báo cáo tài chính."""
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import verify_signature
from ..services import finance, finance_ext, loader
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


class ForecastPayload(BaseModel):
    analysis: Dict[str, Any]
    horizon: int = Field(default=3, ge=1, le=4)


class AnalysisOnly(BaseModel):
    analysis: Dict[str, Any]


class ScenarioPayload(ReanalyzePayload):
    adjustments: Dict[str, Any] = Field(default_factory=dict)


def _ext(fn):
    try:
        return fn()
    except loader.LoadError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except (KeyError, TypeError, ValueError, IndexError, StopIteration, ZeroDivisionError):
        raise HTTPException(status_code=422, detail="Dữ liệu phân tích không hợp lệ, hãy chạy lại phân tích tài chính.")


@router.post("/forecast")
def forecast(p: ForecastPayload):
    return _ext(lambda: finance_ext.forecast(p.analysis, p.horizon))


@router.post("/health-score")
def health_score(p: AnalysisOnly):
    return _ext(lambda: finance_ext.health_score(p.analysis))


@router.post("/scenario")
def scenario(p: ScenarioPayload):
    return _ext(lambda: finance_ext.scenario(p.parsed, p.overrides, p.adjustments))
