"""
请求路由 — 写入 request.json（B/C/D/E）

注意：前端不直接调这些路由。
B 走 /api/papers/{name}/generate → 写入 → 调 SSE 流式执行。
C/D 整合在 /api/edit/preview 中。
E 前端直接调 /api/request/E 写入。

保留这些路由作为备用入口（独立提交请求不执行）。模块同学也可用 curl 测试。
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from server import TASKS_DIR, check_project
from server.services.request_svc import write_request

router = APIRouter()


class BRequest(BaseModel):
    project: str
    topic: str
    outline: str = ""
    ref_domains: list[str] = []
    ref_count: int = 10
    constraints: str = ""
    intent: str = ""
    mode: str = "append"


class CRequest(BaseModel):
    project: str
    scope: str
    style: str = "academic"
    intent: str = ""
    text: str = ""
    file: str = ""
    section_title: str = ""
    start_line: int = 0
    end_line: int = 0


class DRequest(BaseModel):
    project: str
    scope: str
    focus: list[str] = []
    intent: str = ""
    text: str = ""
    file: str = ""
    section_title: str = ""
    start_line: int = 0
    end_line: int = 0


class ERequest(BaseModel):
    project: str
    checkpoint: str = ""
    trigger: str = "manual"
    intent: str = ""


def _selection(body) -> dict | None:
    if body.scope != "selection":
        return None
    if not body.text:
        raise HTTPException(400, "段落操作需要选中文本")
    return {
        "text": body.text,
        "file": body.file,
        "section_title": body.section_title,
        "start_line": body.start_line,
        "end_line": body.end_line,
    }


@router.post("/B")
async def submit_b(body: BRequest):
    """B 组：仅写 request.json，不执行。"""
    check_project(body.project)
    write_request(body.project, "B", body.model_dump(exclude={"project"}))
    return {"status": "ok", "message": f"tasks/{body.project}/B/request.json"}


@router.post("/C")
async def submit_c(body: CRequest):
    """C 组：仅写 request.json。"""
    check_project(body.project)
    write_request(
        body.project, "C",
        {"style": body.style, "intent": body.intent},
        scope=body.scope,
        selection=_selection(body),
    )
    return {"status": "ok", "message": f"tasks/{body.project}/C/request.json"}


@router.post("/D")
async def submit_d(body: DRequest):
    """D 组：仅写 request.json。"""
    check_project(body.project)
    write_request(
        body.project, "D",
        {"focus": body.focus, "intent": body.intent},
        scope=body.scope,
        selection=_selection(body),
    )
    return {"status": "ok", "message": f"tasks/{body.project}/D/request.json"}


@router.post("/E")
async def submit_e(body: ERequest):
    """E 组：仅写 request.json（前端直接调用此路由）。"""
    check_project(body.project)
    write_request(
        body.project, "E",
        {"checkpoint": body.checkpoint, "trigger": body.trigger, "intent": body.intent},
    )
    return {"status": "ok", "message": f"tasks/{body.project}/E/request.json"}
