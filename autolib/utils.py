"""
autolib/utils.py — 公共工具函数
"""

from pathlib import Path
from typing import Optional


def find_main_tex(proj_dir: Path) -> Optional[Path]:
    """在项目目录中寻找编译入口 .tex 文件。

    优先级：
        1. main.tex
        2. 包含 \\documentclass 的 .tex
        3. 任意 .tex

    Args:
        proj_dir: 论文项目根目录

    Returns:
        找到的 .tex 文件路径，找不到返回 None
    """
    candidate = proj_dir / "main.tex"
    if candidate.exists():
        return candidate
    for tex in proj_dir.rglob("*.tex"):
        try:
            if "\\documentclass" in tex.read_text(encoding="utf-8", errors="ignore"):
                return tex
        except Exception:
            pass
    tex_files = list(proj_dir.rglob("*.tex"))
    return tex_files[0] if tex_files else None
