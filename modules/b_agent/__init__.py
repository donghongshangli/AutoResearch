"""
B 组 — Agent 流水线 + 文献检索

单一入口: run(paper_dir, progress=None) → dict

任务从 B/request.json 读取，结构见 docs/request-schema.md

mode 字段（可选，默认 "append"）:
  - "append":   累加模式 — 保留已有文件，只追加新内容
  - "overwrite": 覆盖模式 — 清空 sections/ 后完整重建

progress 回调签名: progress(stage: str, message: str, percent: int) -> None
"""

import json
import re
import time
from pathlib import Path
from typing import Callable, Optional

from autolib.project_sync import sync_main_tex


def run(paper_dir: str, progress: Optional[Callable] = None) -> dict:
    """
    生成论文 .tex 文件组。

    参数:
        paper_dir: 论文项目目录（tasks/{paper}/）
        progress:  可选进度回调

    返回:
        {"status": "ok", "files": ["sections/intro.tex", ...]}
    """
    proj_dir = Path(paper_dir)
    req_path = proj_dir / "B" / "request.json"

    if req_path.exists():
        try:
            req = json.loads(req_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, Exception):
            req = {}
        topic = req.get("topic", "")
        outline = req.get("outline", "")
        ref_domains = req.get("ref_domains", [])
        ref_count = req.get("ref_count", 10)
        constraints = req.get("constraints", "")
        intent = req.get("intent", "")
        mode = req.get("mode", "append")
    else:
        topic, outline, ref_domains, ref_count, constraints, intent = "", "", [], 10, "", ""
        mode = "append"

    if mode not in ("append", "overwrite"):
        return {"status": "error", "message": f"未知 mode: {mode}，可选值为 append / overwrite"}

    def _p(stage, msg, pct):
        if progress:
            progress(stage, msg, pct)

    # ── 初始化 ──
    _p("init", "初始化项目结构", 5)
    proj_dir.mkdir(parents=True, exist_ok=True)
    sections_dir = proj_dir / "sections"
    sections_dir.mkdir(exist_ok=True)

    # ── 文献检索（stub）──
    _p("searching", f"检索文献（目标 {ref_count} 篇）…", 10)
    time.sleep(0.3)  # TODO: 替换为真实文献检索

    # ── 解析大纲 ──
    if outline:
        raw = [s.strip() for s in outline.replace("\n", ",").split(",") if s.strip()]
        titles = [s.lstrip("0123456789. ") for s in raw]
    else:
        titles = ["Introduction", "Related Work", "Methodology", "Experiments", "Conclusion"]

    new_slugs = [_slug(t) for t in titles]

    # ── overwrite 模式：清空 sections 下的 .tex 文件 ──
    if mode == "overwrite":
        _p("writing", "清除旧文件", 20)
        for f in sections_dir.glob("*.tex"):
            f.unlink()

    # ── append 模式：删除与新章节 slug 冲突的旧文件 ──
    if mode == "append":
        for slug in new_slugs:
            old_path = sections_dir / f"{slug}.tex"
            if old_path.exists():
                _p("writing", f"替换旧文件 {old_path.name}", 20)
                old_path.unlink()

    # ── 逐节生成 ──
    files: list[str] = []
    for i, title in enumerate(titles):
        slug = new_slugs[i]
        pct = 30 + int(60 * (i + 1) / len(titles))
        section_path = sections_dir / f"{slug}.tex"

        if mode == "append" and section_path.exists():
            _p("generating", f"跳过 {title}（已存在）", pct)
            files.append(f"sections/{slug}.tex")
            continue

        _p("generating", f"生成 {title}", pct)
        section_path.write_text(
            f"\\section{{{title}}}\n% 由 B 组 Agent 流水线生成\n\n", encoding="utf-8"
        )
        files.append(f"sections/{slug}.tex")
        time.sleep(0.15)  # TODO: 替换为真实 LLM 生成

    # ── 统一重建 main.tex（从 sections/ 实际文件生成 \\input 列表）+ 清理孤儿 ──
    _p("writing", "同步 main.tex + 清理孤儿文件", 95)
    _ensure_main_tex(proj_dir, topic)
    sync_main_tex(proj_dir, keep_stems=set(new_slugs))

    _p("done", f"生成完成 — {len(files)} 个文件", 100)
    return {"status": "ok", "files": files}


def _slug(title: str) -> str:
    s = title.lower().replace(" ", "-")
    s = re.sub(r"[^a-z0-9-]", "", s)
    return s[:40] or "untitled"


def _ensure_main_tex(proj_dir: Path, topic: str = "") -> None:
    """确保项目存在 main.tex，不存在时创建默认模板。"""
    main_tex = proj_dir / "main.tex"
    if main_tex.exists():
        return
    main_tex.write_text(rf"""\documentclass{{article}}
\usepackage[UTF8]{{ctex}}
\usepackage{{amsmath,amssymb}}
\usepackage{{graphicx}}
\usepackage{{hyperref}}

\title{{{topic or "论文标题"}}}

\author{{}}

\begin{{document}}
\maketitle
\end{{document}}
""", encoding="utf-8")
