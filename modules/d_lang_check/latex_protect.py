"""
latex_protect.py — Shared LaTeX command protection utilities.

Two strategies:
  1. strip/restore: Replace LaTeX with placeholders → clean text → restore.
     Used by: academize, generator, paraphraser, cite_checker.
  2. line-based filter: Identify LaTeX regions, exclude results on those lines.
     Used by: lang_check.

Usage:
    from modules.d_lang_check.latex_protect import strip_latex, restore_latex, filter_results
"""

from __future__ import annotations

import re
from typing import Optional

# ═══════════════════════════════════════════════════════════════
# LaTeX command patterns
# ═══════════════════════════════════════════════════════════════

_CITE_RE = re.compile(
    r'\\(?:cite|citet|citep|citealt|citealp|citeauthor|citeyear|nocite)'
    r'\s*(?:\[[^\]]*\])?\s*\{[^}]*\}',
)
_REF_RE = re.compile(
    r'\\(?:eqref|pageref|autoref|[Cc]ref|ref|label)\s*\{[^}]*\}',
)
_MATH_INLINE_RE = re.compile(r'\$[^$]+\$|\\\(.+?\\\)')
_MATH_DISPLAY_RE = re.compile(r'\$\$[\s\S]*?\$\$|\\\[[\s\S]*?\\\]', re.DOTALL)
_ENV_RE = re.compile(r'\\begin\{[^}]+\}[\s\S]*?\\end\{[^}]+\}', re.DOTALL)
_COMMENT_RE = re.compile(r'(?<!\\)%.*$', re.MULTILINE)

# Combined pattern for all LaTeX regions (used by line-based filter)
_PROTECTED_PATTERNS = [
    ("comment", _COMMENT_RE),
    ("math_display", _MATH_DISPLAY_RE),
    ("math_inline", _MATH_INLINE_RE),
    ("env", _ENV_RE),
    ("cite", _CITE_RE),
    ("ref", _REF_RE),
]

# ═══════════════════════════════════════════════════════════════
# Strategy 1: strip / restore (placeholder substitution)
# ═══════════════════════════════════════════════════════════════

_PLACEHOLDER_RE = re.compile(r'<<LATEX_(\d+)>>')


def strip_latex(text: str) -> tuple[str, dict[int, str]]:
    """Replace LaTeX commands with placeholders <<LATEX_N>>.

    Protects: \\cite, \\ref, $math$, $$math$$, \\begin...\\end environments.

    Returns:
        (cleaned_text, latex_map) where latex_map is {index: original_latex}
    """
    latex_map: dict[int, str] = {}
    counter = [0]

    def _replace(m):
        idx = counter[0]
        latex_map[idx] = m.group(0)
        counter[0] += 1
        return f"<<LATEX_{idx}>>"

    # Protection order: cite → ref → inline math → display math → environments
    cleaned = _CITE_RE.sub(_replace, text)
    cleaned = _REF_RE.sub(_replace, cleaned)
    cleaned = _MATH_INLINE_RE.sub(_replace, cleaned)
    cleaned = _MATH_DISPLAY_RE.sub(_replace, cleaned)
    cleaned = _ENV_RE.sub(_replace, cleaned)

    return cleaned, latex_map


def restore_latex(text: str, latex_map: dict[int, str]) -> str:
    """Restore <<LATEX_N>> placeholders to original LaTeX commands.

    Args:
        text:      Text with <<LATEX_N>> placeholders
        latex_map: Map from strip_latex() — {index: original_latex}

    Returns:
        Text with original LaTeX commands restored
    """
    def _restore(m):
        idx = int(m.group(1))
        return latex_map.get(idx, m.group(0))

    restored = _PLACEHOLDER_RE.sub(_restore, text)
    # Clean up any unresolvable placeholders
    restored = re.sub(r'<<LATEX_\d+>>', '', restored)
    return restored


# ═══════════════════════════════════════════════════════════════
# Strategy 2: line-based filter (for lang_check results)
# ═══════════════════════════════════════════════════════════════

def _find_protected_lines(text: str) -> set[int]:
    """Find all line numbers that fall within LaTeX protected regions."""
    protected: set[int] = set()
    for _kind, pattern in _PROTECTED_PATTERNS:
        for m in pattern.finditer(text):
            start_line = text[:m.start()].count('\n') + 1
            end_line = text[:m.end()].count('\n') + 1
            for line in range(start_line, end_line + 1):
                protected.add(line)
    return protected


def filter_results(results: list, text: Optional[str] = None) -> list:
    """Filter out CheckResult items that fall on LaTeX-protected lines.

    Args:
        results: List of CheckResult objects (each has a .line attribute)
        text:    The original LaTeX text. If None, no filtering.

    Returns:
        Filtered list of CheckResult objects
    """
    if not text or not results:
        return results

    protected = _find_protected_lines(text)
    if not protected:
        return results

    return [r for r in results if getattr(r, "line", 0) not in protected]
