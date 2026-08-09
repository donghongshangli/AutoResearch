"""
latex_protect.py — LaTeX 命令保护层

职责：
  - 识别文本中的 LaTeX 保护区（命令、数学公式、注释、环境块）
  - 过滤掉与保护区重叠的检查结果，确保不误报 LaTeX 语法
  - 可选：将 LaTeX 命令替换为占位符后做纯净文本检查（strip-restore）

设计理念（来自 D 同学任务拆解中的"拆装法"）：
  Strip（拆）→ 识别所有 LaTeX 命令 → 标记保护区
  Check（检）→ 在非保护区内执行语言检查
  Restore（装）→ 无需装回——我们只在非保护区内报告问题

  当前实现采用"保护区过滤"策略（更简单、更安全、适用早期阶段）。
  未来当需要 LLM 做全文润色时，再扩展为完整的 strip-restore 方案。

用法:
    from modules.d_lang_check.latex_protect import LatexProtector

    protector = LatexProtector()
    safe_results = protector.filter(results, text)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


# ═══════════════════════════════════════════════════════════════
# 受保护区域类型
# ═══════════════════════════════════════════════════════════════

@dataclass
class ProtectedRegion:
    """文本中的一段 LaTeX 保护区。"""
    start: int
    """起始字符偏移 (0-based, inclusive)"""
    end: int
    """结束字符偏移 (0-based, exclusive)"""
    kind: str
    """区域类型: cite | ref | label | math_inline | math_display | env | command | comment | macro"""


# ── 要保护的 LaTeX 模式 ──────────────────────────────────────

# cite 类命令: \cite{...} \citep{...} \citet{...} \citeauthor{...} \citeyear{...} \nocite{...}
_CITE_RE = re.compile(
    r'\\(?:cite|citet|citep|citealt|citealp|citeauthor|citeyear|nocite)'
    r'\s*(?:\[[^\]]*\])?\s*\{[^}]*\}',
)

# ref 类命令: \ref{...} \eqref{...} \pageref{...} \autoref{...} \cref{...} \Cref{...}
_REF_RE = re.compile(
    r'\\(?:eqref|pageref|autoref|[Cc]ref|ref)\s*\{[^}]*\}',
)

# label 命令: \label{...}
_LABEL_RE = re.compile(r'\\label\s*\{[^}]*\}')

# 行内数学公式: $...$ 或 \(...\)
_MATH_INLINE_RE = re.compile(r'\$[^$]+\$|\\\(.+?\\\)')

# 独立行数学公式: $$...$$ 或 \[...\]
_MATH_DISPLAY_RE = re.compile(
    r'\$\$[\s\S]*?\$\$|\\\[[\s\S]*?\\\]',
    re.DOTALL,
)

# 环境块: \begin{...} ... \end{...}
_ENV_RE = re.compile(
    r'\\begin\{[^}]+\}[\s\S]*?\\end\{[^}]+\}',
    re.DOTALL,
)

# 格式/字体命令: \textbf{...} \textit{...} \texttt{...} \textsc{...} \emph{...} \underline{...}
_FORMAT_RE = re.compile(
    r'\\(?:textbf|textit|texttt|textsc|emph|underline|mathbf|mathit|mathrm|mathsf|mathtt)\s*\{',
)

# url/href 命令: \url{...} \href{...}
_URL_RE = re.compile(r'\\(?:url|href)\s*\{[^}]*\}')

# footnote: \footnote{...}
_FOOTNOTE_RE = re.compile(r'\\footnote\s*\{')

# Section 命令: \section{...} \subsection{...} 等
_SECTION_RE = re.compile(
    r'\\(?:chapter|(?:sub)*section|paragraph|subparagraph)\s*\*?\s*\{[^}]*\}',
)

# 注释: %... 到行尾
_COMMENT_RE = re.compile(r'(?<!\\)%.*$', re.MULTILINE)

# 行内 LaTeX 命令（通用模式）: \cmd{...} \cmd[...]{...} \cmd*
_GENERIC_CMD_RE = re.compile(
    r'\\(?:[a-zA-Z@]+)\*?\s*(?:\[[^\]]*\])?\s*\{',
)

# \verb|...| 或 \verb...  (原样输出，不应被检查)
_VERB_RE = re.compile(r'\\verb\|[^|]*\||\\verb[^a-zA-Z].')


def _find_matching_brace(text: str, open_pos: int) -> int:
    """从 open_pos 的 '{' 找到匹配的 '}'。返回位置索引或 -1。"""
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


# ═══════════════════════════════════════════════════════════════
# LatexProtector
# ═══════════════════════════════════════════════════════════════

class LatexProtector:
    """LaTeX 命令保护器。

    识别文本中的 LaTeX 受保护区域，过滤掉落在其中的检查结果。
    采用"保护区过滤"策略——不修改文本，只过滤结果。

    用法:
        protector = LatexProtector()
        regions = protector.scan(text)          # 扫描保护区
        safe = protector.filter(results, text)   # 过滤检查结果
    """

    def __init__(self):
        self._regions: list[ProtectedRegion] = []
        self._text: str = ""

    # ── 扫描 ─────────────────────────────────────────────────

    def scan(self, text: str) -> list[ProtectedRegion]:
        """扫描文本中的所有 LaTeX 受保护区域。

        Args:
            text: LaTeX 原文

        Returns:
            按 start 排序的 ProtectedRegion 列表
        """
        regions: list[ProtectedRegion] = []

        # 1. 注释 (优先级最高——注释中的内容不需要检查)
        for m in _COMMENT_RE.finditer(text):
            regions.append(ProtectedRegion(m.start(), m.end(), "comment"))

        # 2. \verb (原样输出内容)
        for m in _VERB_RE.finditer(text):
            regions.append(ProtectedRegion(m.start(), m.end(), "verb"))

        # 3. 数学公式
        for m in _MATH_DISPLAY_RE.finditer(text):
            regions.append(ProtectedRegion(m.start(), m.end(), "math_display"))
        for m in _MATH_INLINE_RE.finditer(text):
            regions.append(ProtectedRegion(m.start(), m.end(), "math_inline"))

        # 4. 环境块
        for m in _ENV_RE.finditer(text):
            regions.append(ProtectedRegion(m.start(), m.end(), "env"))

        # 5. cite / ref / label / url / footnote (简单命令——单层花括号)
        for pat, kind in [
            (_CITE_RE, "cite"),
            (_REF_RE, "ref"),
            (_LABEL_RE, "label"),
            (_URL_RE, "url"),
            (_FOOTNOTE_RE, "footnote"),
            (_SECTION_RE, "section"),
        ]:
            for m in pat.finditer(text):
                regions.append(ProtectedRegion(m.start(), m.end(), kind))

        # 6. 格式命令：\textbf{...} 等（需要找匹配花括号）
        for m in _FORMAT_RE.finditer(text):
            brace_start = m.end() - 1  # '{' 的位置
            brace_end = _find_matching_brace(text, brace_start)
            if brace_end >= 0:
                regions.append(ProtectedRegion(m.start(), brace_end + 1, "format"))

        # 7. 通用命令：\cmd[...]{...}（兜底，避免重复覆盖）
        for m in _GENERIC_CMD_RE.finditer(text):
            brace_start = m.end() - 1  # '{' 的位置
            # 此命令可能已经被前面的 pattern 覆盖，检查一下
            if any(r.start <= m.start() < r.end for r in regions):
                continue
            brace_end = _find_matching_brace(text, brace_start)
            if brace_end >= 0:
                regions.append(ProtectedRegion(m.start(), brace_end + 1, "macro"))

        # 排序 + 合并重叠
        regions.sort(key=lambda r: (r.start, r.end))
        self._regions = regions
        self._text = text
        return regions

    # ── 过滤 ─────────────────────────────────────────────────

    def filter(
        self,
        results: list,
        text: Optional[str] = None,
    ) -> list:
        """过滤掉与 LaTeX 保护区重叠的检查结果。

        Args:
            results: CheckResult 列表（来自 rules.py）
            text:    可选，如果传了则重新扫描

        Returns:
            过滤后的安全 CheckResult 列表
        """
        if text is not None:
            self.scan(text)

        if not self._regions:
            return results

        return [r for r in results if not self._is_protected(r)]

    def _is_protected(self, result) -> bool:
        """Check if result falls within a protected region (line-based matching)."""
        r_line = getattr(result, "line", 0)
        if r_line <= 0 or not self._text:
            return False

        text = self._text
        for region in self._regions:
            start_line = text[:region.start].count(chr(10)) + 1
            end_line = text[:region.end].count(chr(10)) + 1
            if start_line <= r_line <= end_line:
                return True
        return False

    @property
    def regions(self) -> list[ProtectedRegion]:
        """最近一次 scan() 的结果。"""
        return self._regions

    def protected_count(self) -> int:
        """受保护区域的数量。"""
        return len(self._regions)

    def region_kinds(self) -> dict[str, int]:
        """各类保护区的数量统计。"""
        counts: dict[str, int] = {}
        for r in self._regions:
            counts[r.kind] = counts.get(r.kind, 0) + 1
        return counts

    # ── 易用接口 ─────────────────────────────────────────────

    def safe_check(
        self,
        text: str,
        results: list,
    ) -> list:
        """一站式：扫描 + 过滤。"""
        self.scan(text)
        return self.filter(results)
