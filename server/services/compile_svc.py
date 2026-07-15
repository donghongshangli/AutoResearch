"""
compile_svc.py — LaTeX 编译服务

用法:
    from server.services.compile_svc import compile_latex
    result = compile_latex(proj_dir)
"""

import subprocess
import shutil
import os
from pathlib import Path

from autolib.utils import find_main_tex


def _find_xelatex() -> str | None:
    """在常见位置查找 xelatex，处理 PATH 未刷新的情况。"""
    home = Path.home()
    candidates = [
        "xelatex",  # PATH 中已有（新开终端可用）
        str(home / r"AppData\Local\Programs\MiKTeX\miktex\bin\x64\xelatex.exe"),
        r"C:\Program Files\MiKTeX\miktex\bin\x64\xelatex.exe",
    ]
    for c in candidates:
        if shutil.which(c):
            return c
    return None


def compile_latex(proj_dir: Path) -> dict:
    """编译论文 PDF。

    查找 main.tex，用 xelatex 编译，产物输出到 build/。
    """
    xelatex_bin = _find_xelatex()
    if xelatex_bin is None:
        return {
            "status": "error",
            "pdf_path": None,
            "log": "未找到 xelatex。请安装 MiKTeX: https://miktex.org/download",
        }

    # 查找入口 .tex 文件
    main_tex = find_main_tex(proj_dir)
    if main_tex is None:
        return {
            "status": "error",
            "pdf_path": None,
            "log": "未找到 main.tex 或包含 \\documentclass 的 .tex 文件",
        }

    build_dir = proj_dir / "build"
    build_dir.mkdir(exist_ok=True)

    # 清理旧辅助文件，确保每次编译都是干净的（避免 .aux/.toc 等缓存导致引用错位）
    for pattern in ["*.aux", "*.toc", "*.out", "*.log", "*.lof", "*.lot", "*.bbl", "*.blg", "*.synctex.gz"]:
        for f in build_dir.glob(pattern):
            f.unlink()

    # 编译（xelatex 两次以解决交叉引用）
    env = os.environ.copy()
    env.setdefault("MIKTEX_CHECK_UPDATE", "0")
    result = None
    for _ in range(2):
        result = subprocess.run(
            [
                xelatex_bin,
                "-interaction=nonstopmode",
                "-output-directory", str(build_dir),
                str(main_tex),
            ],
            cwd=proj_dir,
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )

    pdf_file = build_dir / main_tex.with_suffix(".pdf").name
    if not pdf_file.exists():
        # 提取关键错误
        error_lines = _extract_errors(result.stdout + result.stderr if result else "")
        return {"status": "error", "pdf_path": None, "log": error_lines}

    return {
        "status": "ok",
        "pdf_path": str(pdf_file.relative_to(proj_dir)),
        "log": "编译成功",
    }


def _extract_errors(log: str) -> str:
    """从编译日志提取以 ! 开头的错误行。"""
    lines = log.split("\n")
    errors = [line for line in lines if line.startswith("!")]
    if errors:
        return "\n".join(errors)
    # 没找到典型错误行，返回最后 30 行
    return "\n".join(lines[-30:])
