"""
E 组 — 工作流引擎

单一入口: run(paper_dir, progress=None) → dict

任务从 E/request.json 读取，结构见 docs/request-schema.md

内部逻辑: E 组自行实现，对外只暴露此函数。
"""

import json
from pathlib import Path


def run(paper_dir: str, progress=None) -> dict:
    """
    管理论文协作工作流。

    参数:
        paper_dir: 论文项目目录（tasks/{paper}/）
        progress:  可选进度回调 progress(stage, message, percent)

    返回:
        {"next": str, "done": list[str], "notes": str}
    """
    proj_dir = Path(paper_dir)
    req_path = proj_dir / "E" / "request.json"

    if req_path.exists():
        try:
            req = json.loads(req_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, Exception):
            req = {}
        checkpoint = req.get("checkpoint", "")
        trigger = req.get("trigger", "manual")
        intent = req.get("intent", "")
    else:
        checkpoint = ""
        trigger = "manual"
        intent = ""

    # TODO: E 组实现工作流逻辑（状态机 / 规则引擎）
    # checkpoint: 当前阶段 draft_done / polish_done / check_done
    # trigger:    manual（手动推进）/ auto（自动检测）
    # intent:     用户补充指令

    return {
        "next": "polish",
        "done": ["generate", "compile"],
        "notes": "[E 组待实现] 工作流推进至润色阶段",
    }
