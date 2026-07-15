"""
项目管理路由 — 列/增/删
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from pathlib import Path
import subprocess
import shutil

from server import TASKS_DIR, check_project

router = APIRouter()


class ProjectInfo(BaseModel):
    name: str
    path: str
    file_count: int = 0


class ProjectCreate(BaseModel):
    name: str


@router.get("/", response_model=list[ProjectInfo])
async def list_projects():
    TASKS_DIR.mkdir(parents=True, exist_ok=True)
    return [
        ProjectInfo(
            name=d.name,
            path=str(d),
            file_count=sum(1 for _ in d.rglob("*.tex")),
        )
        for d in sorted(TASKS_DIR.iterdir())
        if d.is_dir() and not d.name.startswith(".")
    ]


@router.post("/", response_model=ProjectInfo)
async def create_project(body: ProjectCreate):
    name = body.name.strip()
    # 项目名安全校验
    if not name:
        raise HTTPException(400, "项目名不能为空")
    if set(name) & set('/\\:*?"<>|'):
        raise HTTPException(400, "项目名含非法字符")
    if name.startswith("."):
        raise HTTPException(400, "项目名不能以 . 开头")
    if ".." in name:
        raise HTTPException(400, "项目名不能包含 ..")

    proj_dir = TASKS_DIR / name
    if proj_dir.exists():
        raise HTTPException(400, f"项目 '{name}' 已存在")
    proj_dir.mkdir(parents=True)
    subprocess.run(["git", "init"], cwd=proj_dir, capture_output=True)
    return ProjectInfo(name=name, path=str(proj_dir), file_count=0)


@router.delete("/{name}")
async def delete_project(name: str):
    check_project(name)
    shutil.rmtree(TASKS_DIR / name)
    return {"deleted": name}
