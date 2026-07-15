"""
C 组 — 润色引擎

单一入口: run(paper_dir, progress=None) → str

任务从 C/request.json 读取，结构见 docs/request-schema.md

内部逻辑: C 组自行实现，对外只暴露此函数。
"""

import json
from pathlib import Path


from typing import Callable, Optional


def run(paper_dir: str, progress: Optional[Callable] = None) -> str:
    """
    润色指定文本。

    参数:
        paper_dir: 论文项目目录（tasks/{paper}/）

    返回:
        润色后的文本
    """
    proj_dir = Path(paper_dir)
    req_path = proj_dir / "C" / "request.json"

    if req_path.exists():
        try:
            req = json.loads(req_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, Exception):
            req = {}
        scope = req.get("_meta", {}).get("scope", "selection")
        text = ""
        if scope == "selection" and req.get("selection"):
            text = req["selection"].get("text", "")
        context = req.get("context", "")
        style = req.get("style", "academic")
        intent = req.get("intent", "")
    else:
        text = ""
        context = ""
        style = "academic"
        intent = ""

    # TODO: C 组实现润色逻辑（调 GPT / 规则引擎）
    # text:   待润色的 LaTeX 原文
    # context: 框架组装的上下文包（含当前段落、结构、引用链）
    # style:  academic / concise / fluent
    # intent: 用户补充指令

    return text + "\n% [C 组润色标记: 待实现]"
