"""
论文编辑路由 — 文件树、读写、B 组请求、统一文档视图
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from pathlib import Path
import asyncio

from server import TASKS_DIR, check_project
from server.services.request_svc import write_request
from server.services.git_svc import git_commit

router = APIRouter()


# ═══════════════════════════════════════════════════════════
# Pydantic 模型
# ═══════════════════════════════════════════════════════════

class FileNode(BaseModel):
    name: str
    path: str
    type: str  # "file" | "dir"
    children: list["FileNode"] = []


class FileContent(BaseModel):
    content: str


class WriteFile(BaseModel):
    content: str


class GenerateRequest(BaseModel):
    topic: str
    outline: str = ""
    ref_domains: list[str] = []
    ref_count: int = 10
    constraints: str = ""
    intent: str = ""
    mode: str = "append"


class GenerateResult(BaseModel):
    status: str
    files: list[str] = []
    message: str = ""


class MergedDoc(BaseModel):
    merged_text: str
    segments: list[dict]
    main_file: str = ""


class MergedSave(BaseModel):
    merged_text: str
    segments: list[dict] = []


class MergedSaveResponse(BaseModel):
    status: str
    strategy: str = ""
    updated: list[str] = []


# ═══════════════════════════════════════════════════════════
# 文件树
# ═══════════════════════════════════════════════════════════

def _build_tree(dir_path: Path, root: Path) -> list[FileNode]:
    nodes = []
    for p in sorted(dir_path.iterdir(), key=lambda x: (x.is_file(), x.name)):
        if p.name in (".git", "build", "__pycache__"):
            continue
        rel = str(p.relative_to(root))
        if p.is_dir():
            nodes.append(FileNode(
                name=p.name, path=rel, type="dir",
                children=_build_tree(p, root),
            ))
        else:
            nodes.append(FileNode(name=p.name, path=rel, type="file"))
    return nodes


@router.get("/{paper_name}/tree", response_model=list[FileNode])
async def get_file_tree(paper_name: str):
    check_project(paper_name)
    return _build_tree(TASKS_DIR / paper_name, TASKS_DIR / paper_name)


def _safe_path(paper_name: str, path: str) -> Path:
    """校验路径安全，防止 ../ 越界攻击。"""
    base = (TASKS_DIR / paper_name).resolve()
    target = (base / path).resolve()
    if not str(target).startswith(str(base)):
        raise HTTPException(403, "路径越界")
    return target


@router.get("/{paper_name}/file", response_model=FileContent)
async def read_file(paper_name: str, path: str = ""):
    check_project(paper_name)
    fp = _safe_path(paper_name, path)
    if not fp.exists():
        raise HTTPException(404, f"文件 '{path}' 不存在")
    return FileContent(content=fp.read_text(encoding="utf-8"))


@router.put("/{paper_name}/file")
async def write_file(paper_name: str, path: str, body: WriteFile):
    check_project(paper_name)
    fp = _safe_path(paper_name, path)
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(body.content, encoding="utf-8")
    git_commit(TASKS_DIR / paper_name, f"edit: {path}")
    return {"written": str(fp)}


# ═══════════════════════════════════════════════════════════
# B 组生成
# ═══════════════════════════════════════════════════════════

@router.post("/{paper_name}/generate", response_model=GenerateResult)
async def generate_draft(paper_name: str, body: GenerateRequest):
    """写入 request.json，立即返回。进度通过 GET /api/tasks/{name}/B/stream。"""
    check_project(paper_name)
    write_request(
        project=paper_name,
        group="B",
        user_fields={
            "topic": body.topic,
            "outline": body.outline,
            "ref_domains": body.ref_domains,
            "ref_count": body.ref_count,
            "constraints": body.constraints,
            "intent": body.intent,
            "mode": body.mode,
        },
    )
    return GenerateResult(status="queued", message="通过 SSE 端点获取进度")


# ═══════════════════════════════════════════════════════════
# 统一文档视图
# ═══════════════════════════════════════════════════════════

@router.get("/{paper_name}/merged", response_model=MergedDoc)
async def get_merged(paper_name: str):
    check_project(paper_name)
    from server.services.merge_svc import merge_project
    result = await asyncio.to_thread(merge_project, TASKS_DIR / paper_name)
    return MergedDoc(**result)


@router.put("/{paper_name}/merged", response_model=MergedSaveResponse)
async def save_merged(paper_name: str, body: MergedSave):
    check_project(paper_name)
    from server.services.merge_svc import save_merged
    from server.services.git_svc import git_commit

    proj_dir = TASKS_DIR / paper_name
    result = await asyncio.to_thread(save_merged, proj_dir, body.merged_text, body.segments)

    if result.get("status") == "ok":
        updated_count = len(result.get("updated", []))
        git_commit(
            proj_dir,
            f"edit: merged save ({result.get('strategy', '')}) — {updated_count} files"
        )

    return MergedSaveResponse(**result)
