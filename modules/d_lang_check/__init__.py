"""
D 组 — 语言检查器

单一入口: run(paper_dir, progress=None) → list[dict]

任务从 D/request.json 读取，结构见 docs/request-schema.md

内部逻辑: D 组自行实现，对外只暴露此函数。
"""

import json
from pathlib import Path
from typing import Callable, Optional


def run(paper_dir: str, progress: Optional[Callable] = None) -> list[dict]:
    """
    检查文本中的语言问题。

    参数:
        paper_dir: 论文项目目录（tasks/{paper}/）

    返回:
        [{"type": "grammar"|"spelling"|"style",
          "line": int,
          "message": str,
          "fix": str}, ...]
    """
    proj_dir = Path(paper_dir)
    req_path = proj_dir / "D" / "request.json"

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
        focus = req.get("focus", [])
        intent = req.get("intent", "")
    else:
        text = ""
        context = ""
        focus = []
        intent = ""

    # TODO: D 组实现检查逻辑（调 GPT / 规则引擎）
    # text:    待检查的 LaTeX 原文
    # context: 框架组装的上下文包
    # focus:   ["grammar", "spelling", "tense", "logic", "style"] 之一或多个
    # intent:  用户补充指令

    return [
        {
            "type": "grammar",
            "line": 1,
            "message": "[D 组待实现] 示例: 主谓不一致",
            "fix": "[D 组待实现] 修正后的文本",
        }
    ]
