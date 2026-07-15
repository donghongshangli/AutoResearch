"""
latex_parser.py — LaTeX 结构化解析器

从 .tex 源码中提取论文结构：Section 树、label 定位、引用关系。
支持多文件项目（\\input / \\include 递归解析）。

对外接口:
    parser = LatexParser()

    # 接口 1：解析单个 .tex 文件
    result = parser.parse_file("sections/intro.tex")
    # → FileParseResult(sections, labels, includes)

    # 接口 2：解析整个项目（自动遍历 \\input/\\include）
    paper = parser.parse_project("main.tex")
    # → PaperAST(sections, lookup, files)

    # 按 label 查 Section（O(1)）
    sec = paper.lookup["sec:intro"]

    # 按编号查 Section（O(1)）
    sec = paper.lookup["§2.3"]

设计原则:
    - Section 包含标题 + 正文内容，Label 只是寻址锚点
    - content 字段 = 本节直接文本（不含子节内容），子节走 children 递归
    - 容错：不规范 LaTeX 记录 warning 不崩溃
    - 不依赖 autolib 其他模块，零耦合
"""

from __future__ import annotations

import re
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from pylatexenc.latexwalker import (
    LatexWalker,
    LatexMacroNode,
    LatexEnvironmentNode,
    LatexCharsNode,
    LatexGroupNode,
    LatexCommentNode,
    LatexSpecialsNode,
)
from pylatexenc.latex2text import LatexNodes2Text


# ── 修复 pylatexenc 默认上下文缺失 ──────────────────────────
# pylatexenc 默认不识别 \paragraph（但识别 \subparagraph），
# 注册一下避免 \paragraph{Title} 的标题提取为空。

def _patch_pylatexenc_context():
    r"""向 pylatexenc 全局默认上下文注册 \paragraph 宏。"""
    try:
        import pylatexenc.latexwalker as _lw
        db = _lw.get_default_latex_context_db()
        ms = _lw.macrospec
        if db.get_macro_spec("paragraph") is None:
            db.add_macro_spec(
                ms.MacroSpec("paragraph", ms.MacroStandardArgsParser("*[{"))
            )
    except Exception:
        pass  # 静默失败——最多 paragraph 标题提取不到


_patch_pylatexenc_context()


# ── 数据结构 ──────────────────────────────────────────────

@dataclass
class Section:
    """论文的一个章节节点。

    嵌套结构：顶层 Section.children 含子 Section，递归向下。
    content 不含子节内容——要完整文本，沿 children 树拼接。
    """

    title: str
    """标题文本，如 "2.3 Optimization Method" """

    content: str
    """本节直接正文（LaTeX 命令已清洗为纯文本），不含子节内容"""

    depth: int
    """层级: 1=section, 2=subsection, 3=subsubsection"""

    number: str = ""
    """编号，如 "2.3"，从标题自动提取"""

    id: str = ""
    """唯一标识。优先用第一个 label，没有则用编号+标题生成"""

    labels: list[str] = field(default_factory=list)
    """本节内定义的 label 列表（去掉了标签本身如 'sec:' 前缀不处理）"""

    cites: list[str] = field(default_factory=list)
    """本节内 \\cite{...} 引用的文献 key"""

    refs: list[str] = field(default_factory=list)
    """本节内 \\ref{...} 引用的其他 label"""

    children: list["Section"] = field(default_factory=list)
    """子节列表，保持源文件顺序"""

    file: str = ""
    """所在 .tex 文件路径（相对或绝对，取决于调用时传入的路径）"""

    line_start: int = 0
    """标题在源文件中的起始行号（1-based）"""

    line_end: int = 0
    """本节内容在源文件中的结束行号（1-based）"""

    # ── 只读属性 ──

    @property
    def full_content(self) -> str:
        """递归拼接：本节 content + 所有子节的 title+content。

        用于一次性获取某个 Section 下的完整文本（发给 AI 做上下文）。
        """
        parts = [self.content] if self.content else []
        for child in self.children:
            parts.append(f"\n{child.title}\n{child.full_content}")
        return "\n".join(parts).strip()

    @property
    def section_path(self) -> list[str]:
        """从根 Section 到当前 Section 的标题路径，如 ['Method', 'Optimization']"""
        # 由 PaperAST._build_lookup 填充
        return getattr(self, "_section_path", [self.title])

    def __repr__(self) -> str:
        return (
            f"Section(id={self.id!r}, title={self.title!r}, "
            f"depth={self.depth}, labels={self.labels}, "
            f"cites={len(self.cites)}, refs={len(self.refs)}, "
            f"children={len(self.children)})"
        )


@dataclass
class FileParseResult:
    """单文件解析结果。"""

    file: str
    sections: list[Section]
    labels: dict[str, str]  # label → section id
    includes: list[str]  # 本文件中 \\input/\\include 引用的文件路径
    warnings: list[str] = field(default_factory=list)


@dataclass
class PaperAST:
    """整篇论文的解析结果。"""

    main_file: str
    sections: list[Section]
    """顶层 Section 树"""

    lookup: dict[str, Section] = field(default_factory=dict)
    """label 或 section id → Section（O(1) 查找）"""

    files: list[str] = field(default_factory=list)
    """所有涉及的文件路径"""

    warnings: list[str] = field(default_factory=list)
    """解析过程中产生的非致命警告"""

    # ── 内部 ──

    _label_names: set[str] = field(default_factory=set)
    """纯粹 \\label{...} 的名字集合，不含 section id"""

    # ── 便捷属性 ──

    @property
    def all_sections(self) -> list[Section]:
        """扁平化所有 Section（先序遍历）。"""

        def _flatten(secs: list[Section]) -> list[Section]:
            result = []
            for s in secs:
                result.append(s)
                result.extend(_flatten(s.children))
            return result

        return _flatten(self.sections)

    @property
    def all_labels(self) -> list[str]:
        """所有 \\label{...} 定义的名字列表（不含 section id）。"""
        return sorted(self._label_names)

    @property
    def all_cites(self) -> list[str]:
        """去重后的所有引用文献 key。"""
        seen = set()
        result = []
        for sec in self.all_sections:
            for cite in sec.cites:
                if cite not in seen:
                    seen.add(cite)
                    result.append(cite)
        return result


# ── 解析器 ─────────────────────────────────────────────────

# 匹配编号前缀: "1.", "2.3", "IV.", "A.1", "3.2.1" 等
_NUMBER_RE = re.compile(
    r"^"
    r"(?:[A-Z]\.\s*)?"  # optional "A." / "B." (appendix prefix)
    r"(?:"
    r"[IVXLCDM]+"  # Roman: IV, VIII, etc.
    r"|"
    r"\d+(?:\.\d+)*"  # Decimal: 1, 2.3, 3.2.1
    r")?"
    r"(?:\.?\s+)"  # trailing dot + whitespace
)


class LatexParser:
    """LaTeX 结构化解析器。

    使用方式:
        parser = LatexParser()

        # 单文件解析
        result = parser.parse_file("intro.tex")

        # 整篇论文解析
        paper = parser.parse_project("main.tex")
        sec = paper.lookup["sec:method"]
    """

    # 视为标题层级的 LaTeX 命令
    SECTION_COMMANDS: dict[str, int] = {
        "chapter": 0,
        "section": 1,
        "subsection": 2,
        "subsubsection": 3,
        "paragraph": 4,
    }

    # 跨文件引用命令
    INCLUDE_COMMANDS: set[str] = {"input", "include", "subfile"}

    # cite 类命令（可能带多个 key）
    CITE_COMMANDS: set[str] = {
        "cite", "citep", "citet", "citealt", "citealp",
        "citeauthor", "citeyear", "nocite",
    }

    def __init__(self, project_root: Optional[str | Path] = None):
        """初始化解析器。

        Args:
            project_root: 项目根目录。解析 \\input/\\include 的相对路径时
                          以此为基准。默认 = 主 .tex 文件所在目录。
        """
        self._project_root: Optional[Path] = (
            Path(project_root) if project_root else None
        )
        self._visited: set[str] = set()  # include 循环依赖检测
        self._warnings: list[str] = []
        self._to_text = LatexNodes2Text()  # 复用实例

    # ── 公开接口 ──────────────────────────────────────────

    def parse_file(self, file_path: str | Path) -> FileParseResult:
        """解析单个 .tex 文件。

        Args:
            file_path: .tex 文件路径

        Returns:
            FileParseResult: 包含 sections、labels 映射、include 文件列表
        """
        path = Path(file_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {path}")

        tex = path.read_text(encoding="utf-8", errors="replace")
        warnings: list[str] = []

        try:
            walker = LatexWalker(tex)
            nodelist, pos_start, pos_end = walker.get_latex_nodes()
        except Exception as e:
            # 严重损坏的文件：返回空结果
            return FileParseResult(
                file=str(path),
                sections=[],
                labels={},
                includes=[],
                warnings=[f"LatexWalker 解析失败 ({path.name}): {e}"],
            )

        # 展平节点树（深度优先）
        flat_nodes = list(self._flatten_nodes(nodelist))

        # 提取结构化信息
        sections, includes = self._extract_structure(
            flat_nodes, tex, str(path), warnings
        )

        # 建 label → section id 映射
        label_map: dict[str, str] = {}
        for sec in self._iter_sections(sections):
            for lbl in sec.labels:
                label_map[lbl] = sec.id

        return FileParseResult(
            file=str(path),
            sections=sections,
            labels=label_map,
            includes=includes,
            warnings=warnings,
        )

    def parse_project(self, main_tex: str | Path) -> PaperAST:
        """解析整篇论文（自动遍历 \\input / \\include）。

        Args:
            main_tex: 主 .tex 文件路径

        Returns:
            PaperAST: 完整 Section 树 + lookup 表
        """
        main_path = Path(main_tex).resolve()
        if not main_path.exists():
            raise FileNotFoundError(f"主文件不存在: {main_path}")

        if self._project_root is None:
            self._project_root = main_path.parent

        self._visited.clear()
        self._warnings.clear()

        # 递归解析主文件 + 所有 include
        all_results: list[FileParseResult] = []
        all_files: list[str] = []
        self._resolve_and_parse(
            main_path, all_results, all_files, depth=0
        )

        # 合并所有文件的 Section 树（按 include 顺序拼接）
        merged_sections: list[Section] = []
        for r in all_results:
            merged_sections.extend(r.sections)

        # 建 lookup 表（label + section id → Section）
        lookup, label_names = self._build_lookup(merged_sections)

        return PaperAST(
            main_file=str(main_path),
            sections=merged_sections,
            lookup=lookup,
            files=all_files,
            warnings=self._warnings,
            _label_names=label_names,
        )

    # ── 内部：节点遍历 ─────────────────────────────────────

    @staticmethod
    def _flatten_nodes(nodes):
        """递归展平节点树为深度优先序列。"""
        for node in nodes:
            yield node
            if hasattr(node, "nodelist") and node.nodelist:
                yield from LatexParser._flatten_nodes(node.nodelist)

    @staticmethod
    def _iter_sections(sections: list[Section]):
        """递归遍历 Section 树。"""
        for sec in sections:
            yield sec
            yield from LatexParser._iter_sections(sec.children)

    # ── 内部：结构提取 ─────────────────────────────────────

    def _extract_structure(
        self,
        flat_nodes: list,
        tex: str,
        file_path: str,
        warnings: list[str],
    ) -> tuple[list[Section], list[str]]:
        """从展平的节点列表中提取 sections、includes。

        Returns:
            (sections, includes)
        """
        root_sections: list[Section] = []
        stack: list[dict] = []  # [{section, heading_end_pos}]

        includes: list[str] = []

        n = len(flat_nodes)
        i = 0
        while i < n:
            node = flat_nodes[i]

            if isinstance(node, LatexCommentNode):
                i += 1
                continue  # 跳过注释

            if not isinstance(node, LatexMacroNode):
                i += 1
                continue

            cmd = node.macroname

            # ── Section 命令 ──
            if cmd in self.SECTION_COMMANDS:
                depth = self.SECTION_COMMANDS[cmd]
                heading_end = node.pos + node.len

                # 关闭栈中所有 depth >= 当前 depth 的 section
                while stack and stack[-1]["section"].depth >= depth:
                    finished = stack.pop()
                    sec = finished["section"]
                    sec.content = self._clean_content(
                        tex, finished["heading_end"], node.pos
                    )
                    sec.line_end = tex[: node.pos].count("\n") + 1
                    if stack:
                        stack[-1]["section"].children.append(sec)
                    else:
                        root_sections.append(sec)

                # 创建新 section
                title = self._extract_argument_text(node)
                # \paragraph 等命令 pylatexenc 可能不解析参数，
                # title 在紧随的 LatexGroupNode 里
                if not title and i + 1 < n:
                    next_node = flat_nodes[i + 1]
                    if isinstance(next_node, LatexGroupNode) and next_node.nodelist:
                        title = (
                            self._to_text.nodelist_to_text(next_node.nodelist)
                            .strip()
                        )
                        heading_end = (
                            next_node.pos + next_node.len
                        )  # 标题结束位置在 group 之后

                number = self._extract_number(title)
                sec = Section(
                    title=title,
                    content="",
                    depth=depth,
                    number=number,
                    id=self._make_section_id(title, number, []),
                    file=file_path,
                    line_start=tex[: node.pos].count("\n") + 1,
                )
                stack.append({"section": sec, "heading_end": heading_end})

            # ── Label ──
            elif cmd == "label":
                lbl = self._extract_argument_text(node)
                if lbl and stack:
                    stack[-1]["section"].labels.append(lbl)

            # ── Cite ──
            elif cmd in self.CITE_COMMANDS:
                keys = self._extract_comma_keys(node)
                if keys and stack:
                    stack[-1]["section"].cites.extend(keys)

            # ── Ref ──
            elif cmd in ("ref", "eqref", "pageref", "autoref", "cref", "Cref"):
                key = self._extract_argument_text(node)
                if key and stack:
                    # cref 可能包含多个逗号分隔的 key: \cref{sec:a,sec:b}
                    for k in key.split(","):
                        k = k.strip()
                        if k:
                            stack[-1]["section"].refs.append(k)

            # ── Input / Include ──
            elif cmd in self.INCLUDE_COMMANDS:
                arg = self._extract_argument_text(node)
                if arg:
                    includes.append(arg)

            i += 1

        # 关闭栈中所有剩余 section
        end_pos = len(tex)
        while stack:
            finished = stack.pop()
            sec = finished["section"]
            sec.content = self._clean_content(tex, finished["heading_end"], end_pos)
            sec.line_end = tex[:end_pos].count("\n") + 1
            if stack:
                stack[-1]["section"].children.append(sec)
            else:
                root_sections.append(sec)

        # 修复 section id（现在 labels 已知）
        for sec in self._iter_sections(root_sections):
            sec.id = self._make_section_id(sec.title, sec.number, sec.labels)

        return root_sections, includes

    # ── 内部：多文件解析 ────────────────────────────────────

    def _resolve_and_parse(
        self,
        file_path: Path,
        results: list[FileParseResult],
        all_files: list[str],
        depth: int = 0,
    ) -> None:
        """递归解析文件及其 include。

        Args:
            file_path: 当前 .tex 文件绝对路径
            results: 累积的解析结果列表
            all_files: 累积的文件路径列表
            depth: 递归深度（检测循环依赖）
        """
        file_key = str(file_path.resolve())

        if file_key in self._visited:
            return  # 已解析，跳过
        self._visited.add(file_key)

        if depth > 20:
            self._warnings.append(f"include 深度超过 20，可能存在循环依赖: {file_key}")
            return

        result = self.parse_file(file_path)
        results.append(result)
        all_files.append(file_key)
        self._warnings.extend(result.warnings)

        # 递归解析 include 文件
        parent_dir = file_path.parent
        for include_path in result.includes:
            resolved = self._resolve_include_path(include_path, parent_dir)
            if resolved:
                self._resolve_and_parse(resolved, results, all_files, depth + 1)
            else:
                self._warnings.append(
                    f"找不到 include 文件: '{include_path}' "
                    f"(from {file_path.name})"
                )

    def _resolve_include_path(
        self, raw: str, parent_dir: Path
    ) -> Optional[Path]:
        """解析 \\input/\\include 的路径。

        LaTeX 自动补 .tex 后缀（若未提供），路径相对于父文件目录。
        """
        raw = raw.strip()

        # 去掉可能的引号和花括号残留
        raw = raw.strip('"').strip("'")

        # 先去尾部的 }（极少数情况 node 参数提取残留）
        raw = raw.rstrip("}")

        # 尝试多种路径变体
        candidates = [raw]
        if not raw.endswith(".tex"):
            candidates.append(raw + ".tex")

        for cand in candidates:
            # 相对路径
            rel = parent_dir / cand
            if rel.exists():
                return rel.resolve()

            # 绝对路径（很少见但可能有）
            abs_p = Path(cand)
            if abs_p.is_absolute() and abs_p.exists():
                return abs_p.resolve()

            # 相对于 project_root
            if self._project_root:
                proj_rel = self._project_root / cand
                if proj_rel.exists():
                    return proj_rel.resolve()

        return None

    # ── 内部：Lookup 表 ─────────────────────────────────────

    def _build_lookup(self, sections: list[Section]) -> tuple[dict[str, Section], set[str]]:
        """建 label + section id → Section 的 O(1) 查找表。

        同时为每个 Section 填充 section_path。

        Returns:
            (lookup_dict, label_names_set)
        """
        lookup: dict[str, Section] = {}
        label_names: set[str] = set()

        def _walk(secs: list[Section], path_prefix: list[str]):
            for sec in secs:
                path = path_prefix + [sec.title]
                sec._section_path = path  # type: ignore[attr-defined]

                # 按 id 索引
                if sec.id:
                    lookup[sec.id] = sec

                # 按编号索引（如 "§2.3"）
                if sec.number:
                    lookup[f"§{sec.number}"] = sec

                # 按 label 索引
                for lbl in sec.labels:
                    lookup[lbl] = sec
                    label_names.add(lbl)

                # 递归
                _walk(sec.children, path)

        _walk(sections, [])
        return lookup, label_names

    # ── 内部：文本处理 ──────────────────────────────────────

    def _clean_content(self, tex: str, start: int, end: int) -> str:
        """提取并清洗指定范围的 LaTeX 文本为纯文本。

        使用 LatexNodes2Text 剥离 LaTeX 命令，保留可读文字。
        """
        if start >= end:
            return ""

        chunk = tex[start:end]

        # 去掉前导空白行
        chunk = chunk.lstrip("\n")

        if not chunk.strip():
            return ""

        try:
            walker = LatexWalker(chunk)
            nodes, _, _ = walker.get_latex_nodes()
            text = self._to_text.nodelist_to_text(nodes)
        except Exception:
            # 降级：返回原始文本（简单清理）
            text = self._fallback_clean(chunk)

        # 压缩连续空行，去首尾空白
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    @staticmethod
    def _fallback_clean(text: str) -> str:
        """简单的 LaTeX 文本清洗（LatexNodes2Text 失败时的降级方案）。"""
        # 去掉注释
        text = re.sub(r"(?<!\\)%.*$", "", text, flags=re.MULTILINE)
        # 去掉 \begin{...} / \end{...}
        text = re.sub(r"\\begin\{[^}]*\}", "", text)
        text = re.sub(r"\\end\{[^}]*\}", "", text)
        # 去掉简单命令（保留参数文本）
        text = re.sub(r"\\[a-zA-Z]+\*?(?:\{[^}]*\})*", "", text)
        return text

    def _extract_argument_text(self, node: LatexMacroNode) -> str:
        """从宏节点提取最后一个必选参数的纯文本。

        因为 \\section 有可选参数（*、[toc title]），标题始终在最后一个位置。
        \\label 只有单个必选参数，取最后一个同样正确。
        """
        if not node.nodeargd or not node.nodeargd.argnlist:
            return ""
        argnlist = node.nodeargd.argnlist
        # 从后往前找第一个非 None 的 group node
        for arg in reversed(argnlist):
            if arg is None:
                continue
            if hasattr(arg, "nodelist") and arg.nodelist:
                return self._to_text.nodelist_to_text(arg.nodelist).strip()
            if isinstance(arg, list) and arg:
                return self._to_text.nodelist_to_text(arg).strip()
        return ""

    def _extract_comma_keys(self, node: LatexMacroNode) -> list[str]:
        """从 \\cite{a,b,c} 类命令提取逗号分隔的 key 列表。"""
        raw = self._extract_argument_text(node)
        if not raw:
            return []
        return [k.strip() for k in raw.split(",") if k.strip()]

    @staticmethod
    def _extract_number(title: str) -> str:
        """从标题文本中提取编号，如 '2.3 Optimization' → '2.3'。"""
        m = _NUMBER_RE.match(title)
        if m:
            num = m.group().rstrip(". ")
            return num
        return ""

    @staticmethod
    def _make_section_id(
        title: str, number: str, labels: list[str]
    ) -> str:
        """生成 section 唯一标识。

        优先级: 第一个 label > 编号 > 标题 slug。
        """
        if labels:
            return labels[0]
        if number:
            return f"§{number}"
        # 标题 slug：小写、空格变连字符、只保留字母数字和连字符
        slug = re.sub(r"[^a-z0-9-]", "", title.lower().replace(" ", "-"))
        return slug[:50] if slug else "untitled"
