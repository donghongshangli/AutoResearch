"""
formula_svc.py — 手写公式识别（SimpleTex API）+ LaTeX 编译

用法:
    from server.services.formula_svc import recognize_formula, compile_formula
    latex, error = recognize_formula("/path/to/photo.png")
    result = compile_formula(latex, work_dir)
"""

import json
import os
import subprocess
from pathlib import Path

import requests

# 优先读环境变量 SIMPLETEX_TOKEN，其次读项目根目录 .env 文件
# 获取: https://simpletex.cn/user/center → 用户授权令牌
def _load_token() -> str:
    token = os.environ.get("SIMPLETEX_TOKEN", "")
    if token:
        return token
    # 尝试从 .env 文件加载
    env_file = Path(__file__).resolve().parent.parent.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("SIMPLETEX_TOKEN="):
                return line.split("=", 1)[1].strip()
    return ""

SIMPLETEX_TOKEN = _load_token()

# SimpleTex API 端点
# 轻量模型 (turbo): 每天 2000 次免费，速度快
# 标准模型: 精度更高，免费额度较少
SIMPLEX_API_URL = "https://server.simpletex.cn/api/latex_ocr_turbo"


def recognize_formula(image_path: str) -> tuple[str | None, str | None]:
    """手写公式图片 → LaTeX 字符串。

    Returns:
        (latex, error): 成功时 latex 为非空字符串、error=None；
                        未配置 token 时 latex=None、error 为提示信息。
    """
    if not SIMPLETEX_TOKEN:
        return None, (
            "未配置 SimpleTex API Token。\n\n"
            "1. 打开 https://simpletex.cn/user/center\n"
            "2. 在「用户授权令牌」处创建令牌\n"
            "3. 在项目 .env 文件中设置 SIMPLETEX_TOKEN=你的令牌\n"
            "4. 重启服务器"
        )

    ext = Path(image_path).suffix.lower()
    if ext not in (".png", ".jpg", ".jpeg", ".webp"):
        return None, f"不支持的图片格式: {ext}（支持 png/jpg/webp）"

    try:
        with open(image_path, "rb") as f:
            resp = requests.post(
                SIMPLEX_API_URL,
                files={"file": f},
                headers={"token": SIMPLETEX_TOKEN},
                timeout=30,
            )
        data = resp.json()

        # SimpleTex 返回格式: {"status": true/false, "res": {"latex": "...", "conf": 0.95}, "request_id": "..."}
        if data.get("status") is True:
            latex = data.get("res", {}).get("latex", "")
            if latex:
                return latex.strip(), None
            return None, "SimpleTex 识别结果为空"

        # 失败
        err_info = data.get("err_info", {})
        error_msg = err_info.get("err_msg") or json.dumps(data, ensure_ascii=False)
        return None, f"SimpleTex 识别失败: {error_msg}"

    except requests.exceptions.RequestException as e:
        return None, f"SimpleTex API 请求失败: {e}"

    except Exception as e:
        return None, f"SimpleTex API 调用失败: {e}"


def compile_formula(latex: str, work_dir: Path) -> dict:
    """将 LaTeX 公式字符串编译为 PDF。

    Args:
        latex: LaTeX 公式代码
        work_dir: 项目根目录（编译产物放入 cache/formula/）

    Returns:
        {"status": "ok"|"error", "pdf_path": str|None, "log": str}
    """
    from server.services.compile_svc import _find_xelatex

    xelatex_bin = _find_xelatex()
    if xelatex_bin is None:
        return {
            "status": "error",
            "pdf_path": None,
            "log": "未找到 xelatex。请安装 MiKTeX: https://miktex.org/download",
        }

    sanitized = latex.strip()
    if sanitized.startswith("\\[") and sanitized.endswith("\\]"):
        sanitized = sanitized[2:-2].strip()
    if sanitized.startswith("$$") and sanitized.endswith("$$"):
        sanitized = sanitized[2:-2].strip()

    doc = r"""\documentclass[preview,border=12pt]{standalone}
\usepackage{amsmath}
\usepackage{amssymb}
\usepackage{amsfonts}
\usepackage{bm}
\usepackage{mathtools}
\begin{document}
\[
"""
    doc += sanitized + "\n\\]\n\\end{document}"

    cache_dir = work_dir / "cache" / "formula"
    cache_dir.mkdir(parents=True, exist_ok=True)

    tex_file = cache_dir / "formula.tex"
    tex_file.write_text(doc, encoding="utf-8")

    build_dir = cache_dir / "build"
    build_dir.mkdir(exist_ok=True)

    env = os.environ.copy()
    env.setdefault("MIKTEX_CHECK_UPDATE", "0")

    try:
        result = subprocess.run(
            [
                xelatex_bin,
                "-interaction=nonstopmode",
                "-output-directory", str(build_dir),
                str(tex_file),
            ],
            cwd=cache_dir,
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return {"status": "error", "pdf_path": None, "log": "编译超时（30s）"}

    pdf_file = build_dir / "formula.pdf"
    if pdf_file.exists():
        return {"status": "ok", "pdf_path": str(pdf_file), "log": "编译成功"}

    log_text = result.stderr + result.stdout if result else ""
    error_lines = [l for l in log_text.split("\n") if l.startswith("!")]
    error_msg = "\n".join(error_lines[:10]) if error_lines else log_text[-500:]

    return {"status": "error", "pdf_path": None, "log": error_msg}
