"""
编辑路由 — 选中段落 → 写 request.json → SSE 流式执行 → 前端收结果

统一数据流：
    1. POST /api/edit/preview → 写入 request.json → 返回 queued
    2. 前端连接 GET /api/tasks/{project}/C/stream（或 D/stream）
    3. SSE 推送进度 → done 事件携带结果
    4. 前端自行 diff / 格式化展示
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from pathlib import Path
import asyncio

from server import TASKS_DIR, check_project
from server.services.request_svc import write_request
from server.services.git_svc import git_commit

router = APIRouter()


class EditRequest(BaseModel):
    paper_name: str
    file_path: str
    start_line: int
    end_line: int
    action: str             # "polish" | "lang_check"
    scope: str = "selection"
    style: str = "academic"
    focus: list[str] = []
    intent: str = ""
    text: str = ""


class PreviewQueued(BaseModel):
    status: str             # "queued"
    group: str              # "C" | "D"
    project: str            # 论文项目名


class ApplyRequest(BaseModel):
    paper_name: str
    file_path: str
    action: str
    accepted: bool
    modified: str = ""
    start_line: int = 0        # >0 时手术替换 [start_line, end_line]
    end_line: int = 0           # =0 时整体覆盖文件


@router.post("/preview", response_model=PreviewQueued)
async def preview_edit(body: EditRequest):
    """选中段落 → 写入 request.json → 返回 queued。

    SSE 流: GET /api/tasks/{project}/C/stream（或 D/stream）
    done 事件的 result 字段：
        C (polish):    string — 润色后的文本
        D (lang_check): list[dict] — 检查结果 [{type, line, message, fix}, ...]
    """
    check_project(body.paper_name)
    proj_dir = (TASKS_DIR / body.paper_name).resolve()

    # 读取选中文本
    if body.text.strip():
        selected = body.text
    else:
        fp = (proj_dir / body.file_path).resolve()
        if not fp.exists():
            raise HTTPException(404, f"文件 '{body.file_path}' 不存在")
        lines = fp.read_text(encoding="utf-8").splitlines()
        selected = "\n".join(lines[body.start_line - 1 : body.end_line])

    # 写 request.json（含边界安全 + context 自动填充）
    group = "C" if body.action == "polish" else "D"
    selection_info = {
        "text": selected,
        "file": body.file_path,
        "section_title": "",
        "start_line": body.start_line,
        "end_line": body.end_line,
    }
    write_request(
        project=body.paper_name,
        group=group,
        user_fields={
            "intent": body.intent,
            **({"style": body.style} if body.action == "polish" else {"focus": body.focus}),
        },
        scope=body.scope,
        selection=selection_info,
    )

    return PreviewQueued(
        status="queued",
        group=group,
        project=body.paper_name,
    )


@router.post("/apply")
async def apply_edit(body: ApplyRequest):
    if not body.accepted:
        return {"status": "discarded"}

    if not body.file_path:
        raise HTTPException(400, "file_path 不能为空")

    proj_dir = TASKS_DIR / body.paper_name
    if not proj_dir.is_dir():
        raise HTTPException(404, f"项目 '{body.paper_name}' 不存在")

    fp = (proj_dir / body.file_path).resolve()

    if body.start_line > 0 and body.end_line > 0:
        # ── 选区替换：手术级替换 [start_line, end_line] ──
        if not fp.exists():
            raise HTTPException(404, f"文件 '{body.file_path}' 不存在")
        lines = fp.read_text(encoding="utf-8").splitlines()
        before = "\n".join(lines[: body.start_line - 1])
        after = "\n".join(lines[body.end_line :])
        parts = [before, body.modified]
        if after:
            parts.append(after)
        fp.write_text("\n".join(parts) if before or after else body.modified, encoding="utf-8")
        git_commit(proj_dir, f"edit: {body.action} applied to {body.file_path}")
        return {"status": "applied", "file": body.file_path}

    elif _is_main_file(proj_dir, body.file_path):
        # ── 全文润色/检查：走 save_merged 拆回多文件 + 重建 main.tex ──
        from server.services.merge_svc import save_merged
        result = await asyncio.to_thread(save_merged, proj_dir, body.modified, [])
        if result.get("status") == "ok":
            git_commit(proj_dir, f"edit: {body.action} applied (full, strategy={result.get('strategy', '')})")
        return result

    else:
        # ── 直接写文件（兜底）──
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(body.modified, encoding="utf-8")
        git_commit(proj_dir, f"edit: {body.action} applied to {body.file_path}")
        return {"status": "applied", "file": body.file_path}


def _is_main_file(proj_dir: Path, file_path: str) -> bool:
    """判断是否为论文主文件（main.tex 或含 \\documentclass 的文件）。"""
    name = Path(file_path).name
    if name in ("main.tex", "paper.tex"):
        return True
    f = proj_dir / file_path
    if f.exists():
        try:
            return "\\documentclass" in f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            pass
    return False
