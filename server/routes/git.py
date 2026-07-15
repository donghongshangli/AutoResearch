"""
Git 历史路由 — 查看 diff / 回退
"""

from fastapi import APIRouter, HTTPException

from server import TASKS_DIR, check_project
from server.services.git_svc import git_log, git_diff, git_revert

router = APIRouter()


@router.get("/{paper}/log")
async def get_log(paper: str, max_count: int = 20):
    check_project(paper)
    return git_log(TASKS_DIR / paper, max_count=max_count)


@router.get("/{paper}/diff/{hash}")
async def get_diff(paper: str, hash: str):
    check_project(paper)
    diff_text = git_diff(TASKS_DIR / paper, hash)
    if not diff_text:
        raise HTTPException(404, "无法获取 diff")
    return {"hash": hash, "diff": diff_text}


@router.post("/{paper}/revert/{hash}")
async def do_revert(paper: str, hash: str):
    check_project(paper)
    result = git_revert(TASKS_DIR / paper, hash)
    if result.get("status") == "error":
        raise HTTPException(400, result.get("message", "回退失败"))
    return result
