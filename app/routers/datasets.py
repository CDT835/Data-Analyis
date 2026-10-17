"""API xử lý tệp dữ liệu. Python không lưu tệp: mỗi lần gọi, WordPress gửi tệp (base64) kèm tham số."""
import base64
import binascii
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import verify_signature
from ..config import get_settings
from ..services import cleaner, loader, profiler
from ..services.parsing import preview_cell

router = APIRouter(prefix="/api/v1/datasets", dependencies=[Depends(verify_signature)])


class FilePayload(BaseModel):
    filename: str = Field(max_length=255)
    file_b64: str
    sheet: Optional[str] = Field(default=None, max_length=255)


class PlanItem(BaseModel):
    id: Optional[str] = None
    action: str
    column: Optional[str] = ""
    params: Dict[str, Any] = {}


class CleanPayload(FilePayload):
    plan: List[PlanItem] = []


def _decode(payload: FilePayload) -> bytes:
    try:
        raw = base64.b64decode(payload.file_b64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=422, detail="Dữ liệu tệp gửi lên không hợp lệ.")
    limit = get_settings().max_file_mb * 1024 * 1024
    if len(raw) > limit:
        raise HTTPException(status_code=413, detail=f"Tệp lớn hơn {get_settings().max_file_mb} MB, vượt giới hạn của dịch vụ.")
    if not raw:
        raise HTTPException(status_code=422, detail="Tệp rỗng.")
    return raw


def _guard(fn):
    try:
        return fn()
    except loader.LoadError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/inspect")
def inspect(payload: FilePayload):
    raw = _decode(payload)
    return _guard(lambda: loader.inspect_file(raw, payload.filename))


@router.post("/preview")
def preview(payload: FilePayload):
    raw = _decode(payload)
    table = _guard(lambda: loader.read_table(raw, payload.filename, payload.sheet, limit=20))
    return {
        "sheet": table.sheet,
        "columns": list(table.df.columns),
        "rows": [[preview_cell(v) for v in row] for row in table.df.values.tolist()],
        "row_numbers": table.row_numbers,
        "info": table.info,
    }


@router.post("/profile")
def profile(payload: FilePayload):
    raw = _decode(payload)
    table = _guard(lambda: loader.read_table(raw, payload.filename, payload.sheet))
    return profiler.build_profile(table)


@router.post("/clean")
def clean(payload: CleanPayload):
    raw = _decode(payload)
    table = _guard(lambda: loader.read_table(raw, payload.filename, payload.sheet))
    result = cleaner.apply_plan(table, [p.model_dump() for p in payload.plan])
    result["csv_b64"] = base64.b64encode(result.pop("csv")).decode("ascii")
    return result
