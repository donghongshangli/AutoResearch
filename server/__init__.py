"""
server — AutoResearch 后端

公共常量:
    TASKS_DIR: 论文项目根目录
    check_project(name): 校验项目是否存在，404
"""

from pathlib import Path
from fastapi import HTTPException

TASKS_DIR = Path(__file__).resolve().parent.parent / "tasks"


def check_project(name: str) -> None:
    """验证项目是否存在，不存在则 404。"""
    if not (TASKS_DIR / name).is_dir():
        raise HTTPException(404, f"项目 '{name}' 不存在")
