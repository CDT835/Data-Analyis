"""API AI nhận xét. Khóa API chỉ nằm trong thân yêu cầu đã ký, không được ghi log hay trả lại."""
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import verify_signature
from ..services import ai
from ..services.loader import LoadError

router = APIRouter(prefix="/api/v1/ai", dependencies=[Depends(verify_signature)])


class FactsPayload(BaseModel):
    analysis: Dict[str, Any]
    checks: Optional[Dict[str, Any]] = None


class CommentaryPayload(FactsPayload):
    model: str = Field(default="openai/gpt-oss-120b", max_length=64)
    api_key: Optional[str] = Field(default=None, max_length=300, repr=False)
    detail: str = Field(default="full", pattern="^(full|short)$")


class TestPayload(BaseModel):
    model: str = Field(default="openai/gpt-oss-120b", max_length=64)
    api_key: Optional[str] = Field(default=None, max_length=300, repr=False)


def _run(fn):
    try:
        return fn()
    except LoadError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except (KeyError, TypeError, ValueError, IndexError, AttributeError):
        raise HTTPException(status_code=422, detail="Dữ liệu phân tích gửi lên không hợp lệ, hãy chạy lại phân tích tài chính.")


@router.post("/facts")
def facts(p: FactsPayload):
    def go():
        f = ai.build_facts(p.analysis, p.checks)
        return {"facts": f, "facts_hash": ai.facts_hash(f)}
    return _run(go)


@router.post("/finance-commentary")
def commentary(p: CommentaryPayload):
    return _run(lambda: ai.generate_finance_commentary(p.analysis, p.checks, p.model, p.api_key, p.detail))


@router.post("/test")
def test(p: TestPayload):
    return _run(lambda: ai.test_connection(p.model, p.api_key))
