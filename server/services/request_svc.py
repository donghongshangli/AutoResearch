"""
request_svc.py — B/C/D/E 请求文件写入服务

职责：
  1. 将用户请求写入 tasks/{project}/{Group}/request.json
  2. 对 C/D 组的段落选择做边界安全校验，防止切在 LaTeX 命令中间
  3. 自动填充 _meta 和 context（C/D 组）

原则：
  - 每个 group 文件夹下只有一个 request.json，新覆旧
  - _meta 字段全自动填入，模块不用管
  - 边界安全校验静默扩展，不在前端提示
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from autolib.latex_parser import LatexParser
from autolib.doc_graph import DocGraph
from autolib.utils import find_main_tex
from server.services.context_svc import build_context


# ── 项目根 ──────────────────────────────────────────────────

def _tasks_dir() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "tasks"


# ── 公开接口：写入请求文件 ──────────────────────────────────

def write_request(
    project: str,
    group: str,
    user_fields: dict,
    scope: str = "full",
    selection: Optional[dict] = None,
) -> Path:
    """写入 request.json 到指定项目的 group 文件夹。

    Args:
        project:    论文项目名（tasks/ 下的文件夹名）
        group:      组名（"B"/"C"/"D"/"E"）
        user_fields: 用户填的字段，不含 _meta
        scope:      仅 C/D 组，"selection" 或 "full"
        selection:  仅 C/D 组 scope=selection 时，含 {text, file, start_line, end_line}

    Returns:
        写入的 request.json 路径
    """
    proj_dir = _tasks_dir() / project
    group_dir = proj_dir / group
    group_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # ── 构建 _meta ──
    meta: dict = {
        "task": _task_name(group),
        "project": project,
        "paper_dir": str(proj_dir.resolve()),
        "created_at": now,
    }
    if group in ("C", "D"):
        meta["scope"] = scope

    # ── C/D 组：组装 context 和边界安全 ──
    if group in ("C", "D") and scope == "selection" and selection:
        selection = _safe_boundary(selection, proj_dir)
        context = _build_context_for_selection(selection, proj_dir)
    elif group in ("C", "D") and scope == "full":
        context = _build_context_full(proj_dir)
        selection = None
    else:
        context = None

    # ── 组装最终 JSON ──
    request = {"_meta": meta}

    if group == "B":
        request.update({
            "topic": user_fields.get("topic", ""),
            "outline": user_fields.get("outline", ""),
            "ref_domains": user_fields.get("ref_domains", []),
            "ref_count": user_fields.get("ref_count", 10),
            "constraints": user_fields.get("constraints", ""),
            "intent": user_fields.get("intent", ""),
            "mode": user_fields.get("mode", "append"),
        })
    elif group == "C":
        request.update({
            "selection": selection,
            "context": context or "",
            "style": user_fields.get("style", "academic"),
            "intent": user_fields.get("intent", ""),
        })
    elif group == "D":
        request.update({
            "selection": selection,
            "context": context or "",
            "focus": user_fields.get("focus", []),
            "intent": user_fields.get("intent", ""),
        })
    elif group == "E":
        request.update({
            "checkpoint": user_fields.get("checkpoint", ""),
            "trigger": user_fields.get("trigger", "manual"),
            "intent": user_fields.get("intent", ""),
        })

    # ── 写入 ──
    req_path = group_dir / "request.json"
    req_path.write_text(
        json.dumps(request, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return req_path


# ── 边界安全：防止切在 LaTeX 命令中间 ──────────────────────

# 需要保护的 LaTeX 命令模式
_CMD_PATTERNS = [
    # \section{...} \subsection{...} 等段命令
    re.compile(r'\\(?:sub)*section\s*\{'),
    re.compile(r'\\(?:chapter|part|paragraph|subparagraph)\s*\{'),
    # \cite{...} \ref{...} \label{...}
    re.compile(r'\\(?:cite|ref|label|eqref|pageref)\s*\{'),
    # \begin{...} ... \end{...}
    re.compile(r'\\begin\{'),
    re.compile(r'\\end\{'),
    # \textbf{...} \textit{...} 等格式命令
    re.compile(r'\\(?:textbf|textit|texttt|textsc|emph|underline)\s*\{'),
    # \url{...} \href{...}
    re.compile(r'\\(?:url|href)\s*\{'),
    # \footnote{...}
    re.compile(r'\\footnote\s*\{'),
]


def _safe_boundary(selection: dict, proj_dir: Path) -> dict:
    """检查并修正选中范围，确保不切在 LaTeX 命令中间。

    自动扩展 start_line 和 end_line 到安全边界，
    同时更新 selection.text。
    """
    file_path = proj_dir / selection["file"]
    if not file_path.exists():
        return selection

    lines = file_path.read_text(encoding="utf-8").splitlines()
    start = selection["start_line"] - 1  # 0-based
    end = selection["end_line"] - 1

    # ── 向前扩展：如果 start 行切在命令中 ──
    while start > 0:
        if _line_starts_in_command(lines[start], lines[start - 1]):
            start -= 1
        else:
            break

    # ── 向后扩展：如果选中范围内有未闭合的 { ──
    # 累加选中范围内的花括号净深度，> 0 则继续向后扩展直到闭合
    depth = _brace_net(lines[start : end + 1])
    while end < len(lines) - 1 and depth > 0:
        end += 1
        depth += _brace_net([lines[end]])

    # ── 更新 selection ──
    expanded = "\n".join(lines[start : end + 1])
    return {
        "text": expanded,
        "file": selection.get("file", ""),
        "section_title": selection.get("section_title", ""),
        "start_line": start + 1,  # 1-based
        "end_line": end + 1,
    }


def _line_starts_in_command(line: str, prev_line: str) -> bool:
    """检查此行开头是否处于上一行未闭合的 LaTeX 命令参数中。

    策略：如果上一行末尾有未闭合的 {（即命令参数跨行了），
    且本行开头不是 } 或 %，则说明本行开头切在了命令参数中间。
    """
    stripped = line.lstrip()
    if not stripped:
        return False
    # 如果行开头是 } 或 %，说明前面的命令已闭合或这是注释
    if stripped[0] in "}%":
        return False
    # 上一行末尾有未闭合的 { → 本行在命令参数中间
    return _line_ends_in_command(prev_line)


def _line_ends_in_command(line: str) -> bool:
    """检查此行末尾是否有未闭合的 {，说明命令跨到了下一行。"""
    # 统计花括号
    depth = 0
    i = 0
    while i < len(line):
        if line[i] == '{' and not _is_escaped(line, i):
            depth += 1
        elif line[i] == '}' and not _is_escaped(line, i):
            depth -= 1
        i += 1
    return depth > 0


def _is_escaped(text: str, pos: int) -> bool:
    """检查位置 pos 的字符是否被反斜杠转义。"""
    if pos == 0:
        return False
    # 计算前面连续的反斜杠数量
    count = 0
    p = pos - 1
    while p >= 0 and text[p] == '\\':
        count += 1
        p -= 1
    return count % 2 == 1


def _brace_net(lines: list[str]) -> int:
    """计算多行的花括号净深度（{ = +1, } = -1）。"""
    depth = 0
    for line in lines:
        i = 0
        while i < len(line):
            if line[i] == '{' and not _is_escaped(line, i):
                depth += 1
            elif line[i] == '}' and not _is_escaped(line, i):
                depth -= 1
            i += 1
    return depth


# ── 上下文组装 ──────────────────────────────────────────────

def _build_context_for_selection(selection: dict, proj_dir: Path) -> str:
    """为段落选择组装上下文包（L1+L2+L3+L4）。"""
    try:
        main_tex = find_main_tex(proj_dir)
        if main_tex is None:
            return ""

        parser = LatexParser(str(proj_dir))
        paper = parser.parse_project(main_tex)
        graph = DocGraph(paper)

        section = graph.locate(
            selection["file"],
            selection["start_line"],
        )
        if section is None:
            # 找不到所在 Section，退化为全 L5 模式
            return build_context(
                paper.sections[0], graph,
                layers=["L5"],
                max_tokens=2000,
                project_dir=proj_dir,
            )

        return build_context(
            section, graph,
            layers=["L1", "L2", "L3", "L4"],
            max_tokens=6000,
            project_dir=proj_dir,
        )
    except Exception:
        return ""


def _build_context_full(proj_dir: Path) -> str:
    """全文模式的上下文（L5 论文骨架）。"""
    try:
        main_tex = find_main_tex(proj_dir)
        if main_tex is None:
            return ""

        parser = LatexParser(str(proj_dir))
        paper = parser.parse_project(main_tex)
        graph = DocGraph(paper)

        # 全文润色/检查：给骨架 + argument.md
        layers = ["L5"]
        if paper.sections:
            return build_context(
                paper.sections[0], graph,
                layers=layers,
                max_tokens=6000,
                project_dir=proj_dir,
            )
        return ""
    except Exception:
        return ""


# ── 工具 ────────────────────────────────────────────────────

def _task_name(group: str) -> str:
    return {
        "B": "generate",
        "C": "polish",
        "D": "lang_check",
        "E": "workflow",
    }.get(group, "unknown")


