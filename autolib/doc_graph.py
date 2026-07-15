"""
doc_graph.py — 论文文档知识图谱：在 PaperAST 之上建立逻辑关系网络

latex_parser 拆开结构，doc_graph 连起关系：
  - cite key → bib 元数据
  - label → 反向引用索引（谁引用了这个 label）
  - 兄弟节索引（前后节、父节、路径）
  - 光标定位（行号 → Section）
  - 论文骨架（Section 树轮廓）
  - 引用上下文包（Section 的所有依赖摘要）

一次构建，O(1) 查询。不依赖 AI 模型。

用法:
    from autolib.doc_graph import DocGraph
    paper = parser.parse_project("main.tex")
    graph = DocGraph(paper, ["refs.bib"])
    graph.cite_info("prism2025")           # → BibEntry | None
    graph.ref_backlinks("sec:method")      # → [Section, ...]
    graph.section_neighbors("sec:method")  # → {prev, next, parent, siblings, path}
    graph.locate("sections/method.tex", 45)  # → Section | None
    graph.outline()                        # → [OutlineNode, ...]
    graph.expand_context(section)          # → ExpandedContext
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .latex_parser import PaperAST, Section


# ── 数据结构 ──────────────────────────────────────────────

@dataclass
class BibEntry:
    """一条 bib 条目。纯数据，不做格式化。"""

    key: str
    title: str = ""
    authors: list[str] = field(default_factory=list)
    year: str = ""
    journal: str = ""
    booktitle: str = ""
    abstract: str = ""


@dataclass
class OutlineNode:
    """论文骨架中的一个节点。"""

    title: str
    depth: int
    id: str
    number: str = ""
    char_count: int = 0
    children: list["OutlineNode"] = field(default_factory=list)


@dataclass
class CiteSummary:
    """一条引用文献的摘要信息（AI 决策用，不是完整 BibEntry）。"""

    key: str
    title: str
    authors_text: str
    year: str
    first_sentence: str


@dataclass
class RefSummary:
    """一个 \\ref 目标节的摘要信息。"""

    label: str
    section_title: str
    section_id: str
    first_sentence: str


@dataclass
class ExpandedContext:
    """一个 Section 的完整依赖摘要。

    cite_summaries: 本节引用的每篇文献的关键信息
    ref_summaries: 本节 \\ref 指向的每个目标节的关键信息
    """

    section_id: str
    cite_summaries: list[CiteSummary] = field(default_factory=list)
    ref_summaries: list[RefSummary] = field(default_factory=list)


# ── 文档知识图谱 ──────────────────────────────────────────

class DocGraph:
    """论文文档知识图谱。

    在 PaperAST 之上构建多层索引：引用关系、兄弟节关系、
    行号定位、论文骨架。bib_paths 可选——无 .bib 文件时 cite_info() 返回 None。
    """

    def __init__(
        self,
        paper: PaperAST,
        bib_paths: list[str] | None = None,
    ):
        self.paper = paper

        # ── cite key → BibEntry ──
        self._bib: dict[str, BibEntry] = {}
        if bib_paths:
            for bp in bib_paths:
                self._load_bib(bp)

        # ── label → 引用它的 Section 列表（反向索引）──
        self._backlinks: dict[str, list[Section]] = {}
        self._build_ref_index()

        # ── 兄弟节索引 ──
        self._prev: dict[str, str | None] = {}
        self._next: dict[str, str | None] = {}
        self._parent: dict[str, Section | None] = {}
        self._siblings: dict[str, list[Section]] = {}
        self._build_sibling_index()

        # ── 行号索引（文件路径 → [(line_start, line_end, section), ...]）──
        self._line_index: dict[str, list[tuple[int, int, Section]]] = {}
        self._build_line_index()

    # ════════════════════════════════════════════════════════
    # 公开查询 — 引用
    # ════════════════════════════════════════════════════════

    def cite_info(self, key: str) -> BibEntry | None:
        """cite key → bib 元数据。无数据返回 None。"""
        return self._bib.get(key)

    def ref_target(self, label: str) -> Section | None:
        """\\ref{label} 指向的 Section。不存在返回 None。"""
        return self.paper.lookup.get(label)

    def ref_backlinks(self, label: str) -> list[Section]:
        """引用了这个 label 的所有 Section。"""
        return self._backlinks.get(label, [])

    # ════════════════════════════════════════════════════════
    # 公开查询 — 结构导航
    # ════════════════════════════════════════════════════════

    def section_neighbors(self, section_id: str) -> dict:
        """获取某个 Section 的邻居信息。

        Returns:
            {prev: Section|None, next: Section|None,
             parent: Section|None, siblings: [Section, ...],
             path: [str, ...]}
        """
        sec = self._resolve(section_id)
        if sec is None:
            return dict(prev=None, next=None, parent=None, siblings=[], path=[])

        prev_id = self._prev.get(sec.id)
        next_id = self._next.get(sec.id)

        return dict(
            prev=self._resolve(prev_id) if prev_id else None,
            next=self._resolve(next_id) if next_id else None,
            parent=self._parent.get(sec.id),
            siblings=self._siblings.get(sec.id, []),
            path=sec.section_path,
        )

    def outline(self) -> list[OutlineNode]:
        """论文 Section 树轮廓——每节标题、层级、字数，不含正文。

        给 AI 当导航地图用。几百 tokens 换一个全景。
        """
        def _build(sections: list[Section]) -> list[OutlineNode]:
            nodes = []
            for sec in sections:
                nodes.append(OutlineNode(
                    title=sec.title,
                    depth=sec.depth,
                    id=sec.id,
                    number=sec.number,
                    char_count=len(sec.content),
                    children=_build(sec.children),
                ))
            return nodes

        return _build(self.paper.sections)

    def locate(self, file_path: str, line_number: int) -> Section | None:
        """光标定位：文件路径 + 行号 → 光标所在的 Section。

        Args:
            file_path: .tex 文件路径（匹配 Section.file 尾部即可）
            line_number: 1-based 行号

        Returns:
            所在 Section，若行号落在所有 Section 之外则返回 None
        """
        # 标准化文件路径（只比尾部，因为 Section.file 可能是绝对/相对路径）
        file_key = Path(file_path).name

        # 先从 _line_index 中匹配文件名
        for stored_file, entries in self._line_index.items():
            if Path(stored_file).name == file_key:
                return self._binary_locate(entries, line_number)

        # 精确匹配失败，尝试在 PaperAST 中遍历所有 Section 行号范围
        for sec in self.paper.all_sections:
            if Path(sec.file).name == file_key:
                if sec.line_start <= line_number <= sec.line_end:
                    return sec

        return None

    # ════════════════════════════════════════════════════════
    # 公开查询 — 引用上下文
    # ════════════════════════════════════════════════════════

    def expand_context(self, section: Section) -> ExpandedContext:
        """给定一个 Section，拉出它的所有引用依赖摘要。

        不递归——每个 cite 返回标题+作者+摘要首句，
        每个 ref 返回目标节标题+首句。AI 拿着这个做推理，
        不用自己遍历 cite/ref。

        Args:
            section: 要展开的 Section 对象

        Returns:
            ExpandedContext: cites 和 refs 的摘要列表
        """
        ctx = ExpandedContext(section_id=section.id)

        # cites → 摘要信息
        for key in section.cites:
            bib = self._bib.get(key)
            if bib:
                ctx.cite_summaries.append(CiteSummary(
                    key=key,
                    title=bib.title,
                    authors_text=", ".join(bib.authors[:3]) if bib.authors else "",
                    year=bib.year,
                    first_sentence=self._extract_first_sentence(bib.abstract),
                ))
            else:
                # 没有 bib 数据，也给出占位——AI 知道有这篇引用
                ctx.cite_summaries.append(CiteSummary(
                    key=key,
                    title="",
                    authors_text="",
                    year="",
                    first_sentence="",
                ))

        # refs → 目标节摘要
        for label in section.refs:
            target = self.ref_target(label)
            if target:
                ctx.ref_summaries.append(RefSummary(
                    label=label,
                    section_title=target.title,
                    section_id=target.id,
                    first_sentence=self._extract_first_sentence(target.content),
                ))
            else:
                ctx.ref_summaries.append(RefSummary(
                    label=label,
                    section_title="",
                    section_id="",
                    first_sentence="",
                ))

        return ctx

    # ════════════════════════════════════════════════════════
    # 健康检查
    # ════════════════════════════════════════════════════════

    def broken_refs(self) -> list[str]:
        """所有指向不存在 label 的 \\ref 列表（去重）。"""
        seen: set[str] = set()
        broken: list[str] = []
        for sec in self.paper.all_sections:
            for lbl in sec.refs:
                if lbl not in seen and lbl not in self.paper.lookup:
                    seen.add(lbl)
                    broken.append(lbl)
        return broken

    def uncached_cites(self) -> list[str]:
        """论文中引用了但 bib 数据缺失的 cite key 列表。"""
        return [k for k in self.paper.all_cites if k not in self._bib]

    # ════════════════════════════════════════════════════════
    # 内部构建
    # ════════════════════════════════════════════════════════

    def _resolve(self, section_id: str | None) -> Section | None:
        if not section_id:
            return None
        return self.paper.lookup.get(section_id)

    def _build_ref_index(self) -> None:
        """构建 label → [引用方] 反向索引。"""
        for sec in self.paper.all_sections:
            for lbl in sec.refs:
                if lbl not in self._backlinks:
                    self._backlinks[lbl] = []
                self._backlinks[lbl].append(sec)

    def _build_sibling_index(self) -> None:
        """构建兄弟节前后关系索引。"""

        def _walk(sections: list[Section], parent: Section | None) -> None:
            for i, sec in enumerate(sections):
                self._parent[sec.id] = parent
                self._siblings[sec.id] = [s for j, s in enumerate(sections) if j != i]
                if i > 0:
                    self._prev[sec.id] = sections[i - 1].id
                if i < len(sections) - 1:
                    self._next[sec.id] = sections[i + 1].id
                _walk(sec.children, sec)

        _walk(self.paper.sections, None)

    def _build_line_index(self) -> None:
        """构建行号 → Section 索引。

        按文件分组，每个文件内按 line_start 排序。
        同一文件内 Section 行号范围不重叠（latex_parser 保证）。
        """
        for sec in self.paper.all_sections:
            if sec.file not in self._line_index:
                self._line_index[sec.file] = []
            self._line_index[sec.file].append(
                (sec.line_start, sec.line_end, sec)
            )

        # 排序保证二分查找可用
        for entries in self._line_index.values():
            entries.sort(key=lambda x: x[0])

    @staticmethod
    def _binary_locate(
        entries: list[tuple[int, int, Section]], line: int
    ) -> Section | None:
        """二分查找行号所在的 Section。"""
        lo, hi = 0, len(entries) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            start, end, sec = entries[mid]
            if start <= line <= end:
                return sec
            if line < start:
                hi = mid - 1
            else:
                lo = mid + 1
        return None

    # ── 工具 ──────────────────────────────────────────────

    @staticmethod
    def _extract_first_sentence(text: str) -> str:
        """提取一段文本的第一句话（按 .!? 断句）。最多 200 字符。"""
        if not text:
            return ""
        # 找第一个句子结束位置
        m = re.search(r"[.!?]\s+[A-Z\u4e00-\u9fff]", text)
        if m:
            first = text[: m.start() + 1].strip()
        else:
            first = text[:200].rsplit(" ", 1)[0].strip()
        return first[:200]

    # ── BibTeX 解析 ──────────────────────────────────────

    def _load_bib(self, bib_path: str) -> None:
        """加载 .bib 文件。"""
        path = Path(bib_path)
        if not path.exists():
            return
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return
        for entry in self._parse_bibtex(raw):
            if entry.key and entry.key not in self._bib:
                self._bib[entry.key] = entry

    @staticmethod
    def _parse_bibtex(raw: str) -> list[BibEntry]:
        """解析 BibTeX 文本。跳过 @string/@comment/@preamble。"""
        entries: list[BibEntry] = []
        pattern = re.compile(r'@(\w+)\s*\{\s*([^,]+)\s*,', re.IGNORECASE)
        skip_types = {"string", "comment", "preamble"}
        pos = 0

        while True:
            m = pattern.search(raw, pos)
            if not m:
                break

            entry_type = m.group(1).lower()
            key = m.group(2).strip()

            if entry_type in skip_types:
                open_brace = raw.find('{', m.start())
                if open_brace != -1:
                    close_brace = DocGraph._match_brace(raw, open_brace)
                    pos = (close_brace + 1) if close_brace != -1 else m.end()
                else:
                    pos = m.end()
                continue

            open_brace = raw.find('{', m.start())
            if open_brace == -1:
                pos = m.end()
                continue

            body_start = m.end()
            body_end = DocGraph._match_brace(raw, open_brace)
            if body_end == -1:
                pos = m.end()
                continue

            body = raw[body_start:body_end]
            fields = DocGraph._parse_fields(body)

            entries.append(BibEntry(
                key=key,
                title=fields.pop("title", ""),
                authors=DocGraph._parse_authors(fields.pop("author", "")),
                year=fields.pop("year", ""),
                journal=fields.pop("journal", ""),
                booktitle=fields.pop("booktitle", ""),
                abstract=fields.pop("abstract", ""),
            ))

            pos = body_end + 1

        return entries

    @staticmethod
    def _match_brace(text: str, open_pos: int) -> int:
        """从 open_pos（'{'）找匹配的 '}'。处理嵌套。返回位置或 -1。"""
        if open_pos >= len(text) or text[open_pos] != '{':
            return -1
        depth = 0
        for i in range(open_pos, len(text)):
            if text[i] == '{':
                depth += 1
            elif text[i] == '}':
                depth -= 1
                if depth == 0:
                    return i
        return -1

    @staticmethod
    def _parse_fields(body: str) -> dict[str, str]:
        """解析 key = {val} / \"val\" / bare_val。"""
        fields: dict[str, str] = {}
        pattern = re.compile(
            r'(\w+)\s*=\s*'
            r'(?:\{((?:[^{}]|\{[^{}]*\})*)\}'  # {...}
            r'|"((?:[^"\\]|\\.)*")'            # "..."
            r'|([^,}]+))',                      # bare
            re.IGNORECASE | re.DOTALL,
        )
        for m in pattern.finditer(body):
            name = m.group(1).lower()
            val = m.group(2) or m.group(3) or m.group(4) or ""
            val = re.sub(r'\s+', ' ', val.strip())
            val = re.sub(r'\{([^{}]+)\}', r'\1', val)  # 去保护花括号
            fields[name] = val
        return fields

    @staticmethod
    def _parse_authors(raw: str) -> list[str]:
        """\"Zhang, Wei and Li, Ming\" → [\"Zhang, Wei\", \"Li, Ming\"]"""
        if not raw.strip():
            return []
        return [p.strip() for p in re.split(r'\s+and\s+', raw, flags=re.IGNORECASE) if p.strip()]
