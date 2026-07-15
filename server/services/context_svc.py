"""
context_svc.py — 上下文格式化服务

不是引擎，是工具。基于 doc_graph 的数据，按需拼装 AI 上下文包。

职责：
  - build_context(): 按分层策略拼装上下文
  - read_argument(): 加载论文论证结构（argument.md）
  - sample_peers(): 风格锚点采样

不依赖 AI 模型，纯数据格式化。
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Optional

from autolib.doc_graph import (
    DocGraph,
    CiteSummary,
    RefSummary,
    ExpandedContext,
    OutlineNode,
)
from autolib.latex_parser import Section


# ── 常量 ──────────────────────────────────────────────────

# L1-L5 各层的 token 估算系数（中文 ≈1.5 字/token，英文 ≈0.75 字/token）
TOKEN_RATIO = 1.0  # 保守估计: 1 字符 ≈ 1 token

# argument.md 相对路径（从论文项目根目录）
ARGUMENT_FILE = "argument.md"


# ── 公开接口 ──────────────────────────────────────────────

def build_context(
    section: Section,
    graph: DocGraph,
    layers: list[str] | None = None,
    max_tokens: int = 6000,
    project_dir: Optional[Path] = None,
) -> str:
    """按分层策略组装 AI 上下文包。

    Args:
        section: 光标所在的 Section
        graph: 文档知识图谱实例
        layers: 需要哪些层，默认 ["L1", "L2", "L3"]
                L1 = 当前段原文，L2 = 结构上下文，
                L3 = 引用摘要，L4 = 风格采样，L5 = 论文骨架
        max_tokens: token 预算上限
        project_dir: 论文项目根目录（用于读 argument.md）

    Returns:
        格式化的上下文字符串，可直接拼接进 AI prompt
    """
    if layers is None:
        layers = ["L1", "L2", "L3"]

    parts: list[str] = []
    used = 0

    # ── L1: 当前段落 ──
    if "L1" in layers:
        l1 = _layer_l1(section)
        if l1:
            parts.append(l1)
            used += len(l1)

    # ── L2: 结构上下文 ──
    if "L2" in layers:
        l2 = _layer_l2(section, graph)
        if l2:
            parts.append(l2)
            used += len(l2)

    # ── L3: 引用摘要 ──
    if "L3" in layers:
        budget = max_tokens - used
        l3 = _layer_l3(section, graph, budget)
        if l3:
            parts.append(l3)
            used += len(l3)

    # ── L4: 风格采样 ──
    if "L4" in layers:
        budget = max_tokens - used
        l4 = _layer_l4(section, graph, budget)
        if l4:
            parts.append(l4)
            used += len(l4)

    # ── L5: 论文骨架 ──
    if "L5" in layers:
        budget = max_tokens - used
        l5 = _layer_l5(graph, budget)
        if l5:
            parts.append(l5)
            used += len(l5)

    # ── 论证结构（如果存在） ──
    if project_dir:
        arg_md = project_dir / ARGUMENT_FILE
        if arg_md.exists():
            budget = max_tokens - used
            arg_text = _read_argument(arg_md, budget)
            if arg_text:
                parts.append(arg_text)
                used += len(arg_text)

    return "\n\n".join(parts)


def read_argument(project_dir: Path) -> Optional[str]:
    """读取论文的论证结构文件。

    Args:
        project_dir: 论文项目根目录

    Returns:
        argument.md 的内容，不存在返回 None
    """
    arg_path = project_dir / ARGUMENT_FILE
    if not arg_path.exists():
        return None
    return _read_argument(arg_path, max_chars=-1)


def sample_peers(
    section: Section,
    graph: DocGraph,
    k: int = 3,
    max_chars_per: int = 500,
) -> list[str]:
    """从同论文其他 Section 随机采样段落，用于风格一致性。

    优先级：同父节兄弟 > 顶层兄弟 > 任意 Section。
    采样时只取 content 前 max_chars_per 字符。

    Args:
        section: 当前 Section
        graph: 文档知识图谱
        k: 采样段落数量
        max_chars_per: 每段最多取多少字符

    Returns:
        段落文本列表（已截断）
    """
    # 候选池
    peer_contents: list[str] = []

    # 优先：同父节兄弟
    siblings = graph._siblings.get(section.id, [])
    for sib in siblings:
        if sib.content:
            peer_contents.append(sib.content[:max_chars_per])

    # 其次：父节的其他子节（递归）
    parent = graph._parent.get(section.id)
    if parent is not None:
        for child in parent.children:
            if child.id != section.id and child.content:
                existing = {c[:50] for c in peer_contents}
                if child.content[:50] not in existing:
                    peer_contents.append(child.content[:max_chars_per])

    # 兜底：任意 Section
    all_sections = graph.paper.all_sections
    if len(peer_contents) < k:
        existing = {c[:50] for c in peer_contents}
        for sec in all_sections:
            if sec.id != section.id and sec.content:
                if sec.content[:50] not in existing:
                    peer_contents.append(sec.content[:max_chars_per])
                    existing.add(sec.content[:50])
            if len(peer_contents) >= k * 3:
                break

    # 随机选 k 个
    if len(peer_contents) > k:
        peer_contents = random.sample(peer_contents, k)

    return peer_contents


# ── 内部：分层组装 ────────────────────────────────────────

def _layer_l1(section: Section) -> str:
    """L1: 当前段原文。"""
    if not section.content.strip():
        return ""
    return f"# 当前段落 ({section.title})\n\n{section.content}"


def _layer_l2(section: Section, graph: DocGraph) -> str:
    """L2: 结构上下文——父节、兄弟节、路径。"""
    neighbors = graph.section_neighbors(section.id)
    path = neighbors.get("path", [])
    parent = neighbors.get("parent")
    siblings = neighbors.get("siblings", [])

    lines = ["# 结构上下文"]
    lines.append(f"位置: {' > '.join(path)}")

    if parent:
        lines.append(f"所属节: {parent.title}")
        # 父节的引用信息
        if parent.cites or parent.refs:
            lines.append(f"父节引用: {len(parent.cites)} 篇文献, {len(parent.refs)} 个交叉引用")

    if siblings:
        sib_titles = [s.title for s in siblings]
        lines.append(f"兄弟节: {', '.join(sib_titles)}")

    return "\n".join(lines)


def _layer_l3(
    section: Section, graph: DocGraph, budget: int
) -> str:
    """L3: 引用上下文——cite 摘要 + ref 目标信息。

    超预算时优先截断 cite 摘要（保留标题+作者），
    仍不够时删掉无摘要的 cite，再不够删完整条 ref。
    """
    ctx = graph.expand_context(section)

    lines = ["# 引用上下文"]

    # 优先填充全部内容
    cite_lines: list[str] = []
    ref_lines: list[str] = []

    for c in ctx.cite_summaries:
        parts = [f"- [{c.key}] {c.title}"]
        if c.authors_text:
            parts.append(f"  {c.authors_text} ({c.year})" if c.year else f"  {c.authors_text}")
        if c.first_sentence:
            parts.append(f"  {c.first_sentence}")
        cite_lines.append("\n".join(parts))

    for r in ctx.ref_summaries:
        if r.section_title:
            ref_lines.append(
                f"- \\ref{{{r.label}}} → {r.section_title}"
                + (f": {r.first_sentence}" if r.first_sentence else "")
            )
        else:
            ref_lines.append(f"- \\ref{{{r.label}}} → [未找到目标节]")

    full_cites = "\n".join(cite_lines) if cite_lines else "(无引用文献)"
    full_refs = "\n".join(ref_lines) if ref_lines else "(无交叉引用)"

    full_text = lines[0] + "\n\n引用文献:\n" + full_cites + "\n\n交叉引用:\n" + full_refs

    if budget <= 0 or len(full_text) <= budget:
        return full_text

    # 超预算：逐步缩
    # 策略 1: cite 摘要只保留首句的前 100 字符
    trimmed_cites = []
    for c in ctx.cite_summaries:
        parts = [f"- [{c.key}] {c.title}"]
        if c.authors_text:
            parts.append(f"  {c.authors_text} ({c.year})" if c.year else f"  {c.authors_text}")
        if c.first_sentence:
            parts.append(f"  {c.first_sentence[:100]}...")
        trimmed_cites.append("\n".join(parts))

    trimmed_text = lines[0] + "\n\n引用文献:\n" + "\n".join(trimmed_cites)
    if ref_lines:
        trimmed_text += "\n\n交叉引用:\n" + "\n".join(ref_lines)

    if len(trimmed_text) <= budget:
        return trimmed_text

    # 策略 2: 再去掉 ref 详情，只列 label 名
    short_refs = [f"- \\ref{{{r.label}}}" for r in ctx.ref_summaries]
    minimal = (
        lines[0]
        + "\n\n引用文献:\n"
        + "\n".join(trimmed_cites)
        + "\n\n交叉引用:\n"
        + "\n".join(short_refs)
    )

    return minimal[:budget]


def _layer_l4(
    section: Section, graph: DocGraph, budget: int
) -> str:
    """L4: 风格锚点——同论文其他段落采样。"""
    peers = sample_peers(section, graph, k=2, max_chars_per=300)
    if not peers:
        return ""

    lines = ["# 风格参考（同论文其他段落）"]
    for i, p in enumerate(peers, 1):
        lines.append(f"\n样本 {i}:\n{p}")

    full = "\n".join(lines)
    if budget <= 0 or len(full) <= budget:
        return full
    return full[:budget]


def _layer_l5(graph: DocGraph, budget: int) -> str:
    """L5: 论文骨架——Section 树轮廓。"""

    def _render(nodes: list[OutlineNode], indent: int = 0) -> list[str]:
        lines = []
        prefix = "  " * indent
        for node in nodes:
            num_str = f" {node.number}" if node.number else ""
            lines.append(
                f"{prefix}- {node.title}{num_str} ({node.char_count:,} 字符) [id={node.id}]"
            )
            lines.extend(_render(node.children, indent + 1))
        return lines

    outline_nodes = graph.outline()
    lines = ["# 论文结构"]
    lines.extend(_render(outline_nodes))

    full = "\n".join(lines)
    if budget <= 0 or len(full) <= budget:
        return full
    return full[:budget]


def _read_argument(arg_path: Path, max_chars: int = -1) -> str:
    """读取 argument.md，可选截断。"""
    try:
        text = arg_path.read_text(encoding="utf-8", errors="replace").strip()
    except Exception:
        return ""

    if not text:
        return ""

    if max_chars > 0 and len(text) > max_chars:
        text = text[:max_chars] + "\n\n... (截断)"

    return "# 论文论证结构 (argument.md)\n\n" + text
