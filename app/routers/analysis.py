"""API phân tích thống kê và Machine Learning. Giống Giai đoạn 3: không lưu tệp, mỗi lần gọi gửi tệp kèm tham số."""
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import verify_signature
from ..services import analytics, loader, ml, ml_general
from .datasets import FilePayload, _decode, _guard

router = APIRouter(prefix="/api/v1", dependencies=[Depends(verify_signature)])

ROLES = {"date", "amount", "customer_id", "order_id", "quantity", "unit_price", "discount", "category", "product", "region"}


class AnalysisPayload(FilePayload):
    mapping: Dict[str, str] = Field(default_factory=dict)
    k: Optional[int] = Field(default=None, ge=2, le=8)
    horizon: int = Field(default=3, ge=1, le=6)
    target: Optional[str] = Field(default=None, max_length=255)
    features: List[str] = Field(default_factory=list, max_length=30)


def _mapping(p: AnalysisPayload) -> Dict[str, str]:
    bad = [r for r in p.mapping if r not in ROLES]
    if bad:
        raise HTTPException(status_code=422, detail=f"Vai trò cột không hợp lệ: {', '.join(bad)}.")
    return {r: c for r, c in p.mapping.items() if c}


def _table(p: AnalysisPayload):
    raw = _decode(p)
    return _guard(lambda: loader.read_table(raw, p.filename, p.sheet))


@router.post("/analysis/stats")
def stats(p: AnalysisPayload):
    table, mapping = _table(p), _mapping(p)
    return _guard(lambda: analytics.run_stats(table, mapping))


@router.post("/ml/rfm")
def rfm(p: AnalysisPayload):
    table, mapping = _table(p), _mapping(p)
    return _guard(lambda: ml.run_rfm(table, mapping, p.k))


@router.post("/ml/forecast")
def forecast(p: AnalysisPayload):
    table, mapping = _table(p), _mapping(p)
    return _guard(lambda: ml.run_forecast(table, mapping, p.horizon))


@router.post("/ml/cluster")
def cluster(p: AnalysisPayload):
    table = _table(p)
    return _guard(lambda: ml_general.run_cluster(table, p.features, p.k))


@router.post("/ml/regression")
def regression(p: AnalysisPayload):
    table = _table(p)
    if not p.target:
        raise HTTPException(status_code=422, detail="Hãy chọn cột mục tiêu cần dự đoán.")
    return _guard(lambda: ml_general.run_regression(table, p.target, p.features))


@router.post("/ml/classification")
def classification(p: AnalysisPayload):
    table = _table(p)
    if not p.target:
        raise HTTPException(status_code=422, detail="Hãy chọn cột mục tiêu cần dự đoán.")
    return _guard(lambda: ml_general.run_classification(table, p.target, p.features))
