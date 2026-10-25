"""API mẫu báo cáo tài chính: danh mục mẫu, xem trước và xuất Word/PDF/Excel."""
import base64
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import verify_signature
from ..services import report_catalog, report_export
from ..services.loader import LoadError
from ..services.report_blocks import build_report
from ..services.report_custom import normalize_document

router = APIRouter(prefix="/api/v1/reports", dependencies=[Depends(verify_signature)])


class CatalogPayload(BaseModel):
    mapping: Optional[Dict[str, Any]] = None
    statements: Optional[List[Dict[str, Any]]] = None


class ReportPayload(CatalogPayload):
    template: str = Field(max_length=40)
    sections: Optional[List[str]] = Field(default=None, max_length=30)
    title: str = Field(default="", max_length=200)
    org: str = Field(default="", max_length=200)
    date: Optional[str] = Field(default=None, max_length=20)
    analysis: Dict[str, Any]
    checks: Optional[Dict[str, Any]] = None
    std_items: Optional[List[Dict[str, Any]]] = None
    ai: Optional[Dict[str, Any]] = None
    fragment: bool = False  # True: chỉ trả các khối của những phần đã chọn (dùng khi chèn vào bản soạn thủ công)


class RenderPayload(BaseModel):
    title: str = Field(default="", max_length=200)
    org: str = Field(default="", max_length=200)
    date: Optional[str] = Field(default=None, max_length=20)
    blocks: List[Dict[str, Any]] = Field(max_length=500)
    format: str = Field(pattern="^(docx|pdf|xlsx)$")


class ExportPayload(ReportPayload):
    format: str = Field(pattern="^(docx|pdf|xlsx)$")


def _build(p: ReportPayload) -> Dict[str, Any]:
    try:
        return build_report(p.template, p.sections, p.title, p.org, p.analysis, p.checks, p.mapping, p.std_items, p.statements, p.ai, p.date, p.fragment)
    except LoadError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except (KeyError, TypeError, ValueError, IndexError, AttributeError):
        raise HTTPException(status_code=422, detail="Dữ liệu phân tích gửi lên không hợp lệ, hãy chạy lại phân tích tài chính.")


@router.post("/templates")
def templates(p: CatalogPayload):
    have = report_catalog.available_statements(p.mapping, p.statements)
    return {"templates": report_catalog.catalog(have), "available": have}


@router.post("/preview")
def preview(p: ReportPayload):
    return _build(p)


@router.post("/export")
def export(p: ExportPayload):
    return _export(_build(p), p.format)


@router.post("/render")
def render(p: RenderPayload):
    """Xuất tệp từ các khối do người dùng tự soạn (đã được kiểm tra và chuẩn hóa)."""
    try:
        rep = normalize_document(p.title, p.org, p.date, p.blocks)
    except LoadError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return _export(rep, p.format)


def _export(rep: Dict[str, Any], fmt: str) -> Dict[str, Any]:
    try:
        data = report_export.EXPORTERS[fmt](rep)
    except Exception:
        raise HTTPException(status_code=500, detail="Không tạo được tệp báo cáo. Hãy thử lại hoặc chọn định dạng khác.")
    return {"format": fmt, "filename": report_export.safe_filename(rep["title"], fmt), "mime": report_export.MIME[fmt], "size": len(data),
            "skipped": rep["skipped"], "included": rep["included"], "content_b64": base64.b64encode(data).decode("ascii")}
