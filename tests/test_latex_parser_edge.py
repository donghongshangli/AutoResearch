"""
Edge case tests for latex_parser — covers real-world scenarios that could break.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from autolib.latex_parser import LatexParser, Section


def _write_and_parse(tex: str, parser=None) -> tuple:
    """Write temp file -> parse -> return (sections, lookup, warnings)."""
    import tempfile
    tmp = Path(tempfile.gettempdir()) / "_test_edge.tex"
    tmp.write_text(tex, encoding="utf-8")
    if parser is None:
        parser = LatexParser()
    paper = parser.parse_project(tmp)
    tmp.unlink()
    return paper.sections, paper.lookup, paper.warnings


def test_starred_section():
    r"""\section*{Title} — unnumbered section."""
    tex = r"""
\documentclass{article}
\begin{document}
\section*{Acknowledgments}
\label{sec:ack}
Thank you.
\end{document}
"""
    sections, lookup, warns = _write_and_parse(tex)
    assert len(sections) == 1, f"expected 1 section, got {len(sections)}"
    assert sections[0].title == "Acknowledgments"
    assert sections[0].number == ""  # starred = no number
    assert "sec:ack" in lookup
    print("OK starred section")


def test_short_title():
    r"""\section[Short]{Long Title} — short title variant."""
    tex = r"""
\documentclass{article}
\begin{document}
\section[Short TOC]{Methods for Deep Learning Optimization}
\label{sec:method}
Content here.
\end{document}
"""
    sections, lookup, warns = _write_and_parse(tex)
    assert len(sections) == 1
    assert sections[0].title == "Methods for Deep Learning Optimization"
    assert "sec:method" in lookup
    print("OK short title")


def test_chapter_level():
    r"""\chapter{Title} — chapter depth (0)."""
    tex = r"""
\documentclass{report}
\begin{document}
\chapter{Introduction}
\label{sec:intro}
\section{Background}
\label{sec:bg}
Some background.
\section{Method}
\label{sec:method}
More content.
\end{document}
"""
    sections, lookup, warns = _write_and_parse(tex)
    assert len(sections) == 1  # top level is chapter
    assert sections[0].title == "Introduction"
    assert sections[0].depth == 0  # chapter depth
    assert len(sections[0].children) == 2  # Background + Method
    assert sections[0].children[0].depth == 1  # section depth
    print("OK chapter level")


def test_cite_with_optional():
    r"""\cite[page 42]{paper2024} — cite with optional args."""
    tex = r"""
\documentclass{article}
\begin{document}
\section{Test}
\cite[page 42]{paper2024}
\citep[see][chapter 3]{another2023}
\citet{author2022}
\end{document}
"""
    sections, lookup, warns = _write_and_parse(tex)
    all_cites = set()
    for sec in LatexParser._iter_sections(sections):
        all_cites.update(sec.cites)
    assert "paper2024" in all_cites
    assert "another2023" in all_cites
    assert "author2022" in all_cites
    print("OK cite optional args")


def test_cleveref():
    r"""\cref{sec:a,sec:b} — multi-ref command."""
    tex = r"""
\documentclass{article}
\begin{document}
\section{One}\label{sec:a}
\section{Two}\label{sec:b}
Content \cref{sec:a,sec:b} and \Cref{sec:a}.
\end{document}
"""
    sections, lookup, warns = _write_and_parse(tex)
    all_refs = set()
    for sec in LatexParser._iter_sections(sections):
        all_refs.update(sec.refs)
    assert "sec:a" in all_refs
    assert "sec:b" in all_refs
    print("OK cleveref multi-ref")


def test_label_collision():
    """Two files define same label — should not crash."""
    import tempfile, shutil
    d = Path(tempfile.gettempdir()) / "_test_collision"
    d.mkdir(exist_ok=True)
    (d / "main.tex").write_text(r"""
\documentclass{article}
\begin{document}
\section{A}\label{sec:dup}
\input{file1}
\input{file2}
\end{document}
""", encoding="utf-8")
    (d / "file1.tex").write_text(r"\section{B}\label{sec:dup}", encoding="utf-8")
    (d / "file2.tex").write_text(r"\section{C}\label{sec:dup}", encoding="utf-8")

    parser = LatexParser()
    paper = parser.parse_project(d / "main.tex")

    assert len(paper.sections) == 3
    print(f"OK label collision (no crash): lookup points to {paper.lookup['sec:dup'].title}")

    shutil.rmtree(d)


def test_chinese_content():
    """Chinese paper — ensure no crash and correct extraction."""
    tex = r"""
\documentclass{article}
\begin{document}

\section{Introduction}
\label{sec:intro-cn}

Deep learning has achieved great success in NLP \cite{zhang2024}.

\subsection{Research Background}
\label{sec:bg-cn}

In recent years, Transformer architecture \ref{sec:intro-cn} has been widely applied.

\section{Method}
\label{sec:method-cn}

We propose a new method \cite{li2024,wang2024}.
\end{document}
"""
    sections, lookup, warns = _write_and_parse(tex)
    assert len(sections) == 2
    assert sections[0].title == "Introduction"
    assert "sec:intro-cn" in lookup
    assert "sec:bg-cn" in lookup
    assert "sec:method-cn" in lookup

    all_cites = set()
    for sec in LatexParser._iter_sections(sections):
        all_cites.update(sec.cites)
    assert "zhang2024" in all_cites

    intro_cn = lookup["sec:intro-cn"]
    bg_cn = lookup["sec:bg-cn"]
    assert "sec:intro-cn" in bg_cn.refs

    print("OK Chinese paper")


def test_numbered_sections():
    """Number extraction: 1, 1.1, 1.1.1, IV., A.1 etc."""
    tex = r"""
\documentclass{article}
\begin{document}
\section{1. Introduction}
\section{2.3 Method}
\section{IV. Results}
\section{A.1 Appendix}
\section{3.2.1 Deep Dive}
\end{document}
"""
    sections, lookup, warns = _write_and_parse(tex)
    assert sections[0].number == "1"
    assert sections[1].number == "2.3"
    assert sections[2].number == "IV"
    assert sections[3].number == "A.1"
    assert sections[4].number == "3.2.1"
    print("OK numbered sections")


def test_empty_content_boundary():
    """Empty section content — no crash."""
    tex = r"""
\documentclass{article}
\begin{document}
\section{Empty One}
\section{Empty Two}
\end{document}
"""
    sections, lookup, warns = _write_and_parse(tex)
    assert len(sections) == 2
    assert sections[0].content == ""
    assert sections[1].content == ""
    print("OK empty content")


def test_section_path():
    """section_path: from root to current section."""
    tex = r"""
\documentclass{article}
\begin{document}
\section{Introduction}
\section{Method}
\subsection{Algorithm}
\label{sec:algo}
\end{document}
"""
    sections, lookup, warns = _write_and_parse(tex)
    algo = lookup["sec:algo"]
    assert algo.section_path == ["Method", "Algorithm"], f"Expected ['Method', 'Algorithm'], got {algo.section_path}"
    print("OK section_path")


def test_large_paper():
    """Performance: 100 sections, many refs."""
    sections_tex = ""
    for i in range(100):
        sections_tex += f"""
\\section{{Topic {i}}}
\\label{{sec:topic{i}}}

This is the content for topic {i}. We reference \\cite{{paper{i}}} and previous work \\ref{{sec:topic{i-1}}}.
"""
        if i % 3 == 0:
            sections_tex += f"""
\\subsection{{Sub {i}a}}
\\label{{sec:sub{i}a}}
Detailed analysis \\cite{{paper{i}a,paper{i}b}}.
"""
        if i % 5 == 0:
            sections_tex += f"""
\\subsubsection{{Detail {i}}}
Nested content \\ref{{sec:sub{i-3}a}}.
"""

    tex = f"""
\\documentclass{{article}}
\\begin{{document}}
{sections_tex}
\\end{{document}}
"""
    import time
    t0 = time.time()
    sections, lookup, warns = _write_and_parse(tex)
    elapsed = time.time() - t0

    total_secs = len([s for s in LatexParser._iter_sections(sections)])
    print(f"OK large paper: {total_secs} sections, parsed in {elapsed*1000:.0f}ms")


def test_missing_include_file():
    """Missing include file — warn, continue."""
    import tempfile, shutil
    d = Path(tempfile.gettempdir()) / "_test_missing"
    d.mkdir(exist_ok=True)
    (d / "main.tex").write_text(r"""
\documentclass{article}
\begin{document}
\section{Exists}
\label{sec:exists}
\include{missing_file}
\section{Also Exists}
\label{sec:also}
\end{document}
""", encoding="utf-8")

    parser = LatexParser()
    paper = parser.parse_project(d / "main.tex")
    assert len(paper.sections) >= 2
    assert any("missing" in w.lower() for w in paper.warnings), f"Expected missing_file warning, got: {paper.warnings}"
    print(f"OK missing include: warnings={paper.warnings}")

    shutil.rmtree(d)


def test_deep_nesting():
    """Deep nesting: section > subsection > subsubsection."""
    tex = r"""
\documentclass{article}
\begin{document}
\section{Top}
\subsection{Mid}
\subsubsection{Bottom}
\label{sec:bottom}
Deep content.
\end{document}
"""
    sections, lookup, warns = _write_and_parse(tex)
    assert len(sections) == 1
    top = sections[0]
    assert len(top.children) == 1
    mid = top.children[0]
    assert len(mid.children) == 1
    bottom = mid.children[0]
    assert bottom.depth == 3
    assert "sec:bottom" in lookup
    print("OK deep nesting")


def test_paragraph_level():
    r"""\paragraph{Title} — depth 4 (requires pylatexenc patch)."""
    tex = r"""
\documentclass{article}
\begin{document}
\section{Main}
\paragraph{Paragraph Title}
\label{sec:para}
Some paragraph content.
\end{document}
"""
    sections, lookup, warns = _write_and_parse(tex)
    assert len(sections) == 1
    # paragraph should be a child of section
    main = sections[0]
    para = main.children[0]
    assert para.title == "Paragraph Title"
    assert para.depth == 4
    assert "sec:para" in lookup
    print("OK paragraph level")


def test_content_cleaning():
    """Content cleaning: textbf/emph/math/url/href stripped."""
    tex = r"""
\documentclass{article}
\begin{document}
\section{Formatted Content}

\textbf{Bold text} and \emph{emphasized}.

Math: $E=mc^2$ and \url{https://example.com}.

\href{https://arxiv.org}{arXiv link}.
\end{document}
"""
    sections, lookup, warns = _write_and_parse(tex)
    content = sections[0].content
    # LatexNodes2Text aggressively strips \textbf, \emph, \url, \href contents
    # Math ($...$) and plain text between them survive
    assert "Math:" in content
    assert "$E=mc^2$" in content
    assert "and" in content
    print(f"OK content cleaning: {content[:80]}...")


def test_real_paper_structure():
    """Real paper structure verification (multi-file via include)."""
    import tempfile, shutil
    d = Path(tempfile.gettempdir()) / "_test_real"
    d.mkdir(exist_ok=True)

    (d / "main.tex").write_text(r"""
\documentclass{article}
\begin{document}
\input{intro}
\input{method}
\input{conclusion}
\end{document}
""", encoding="utf-8")

    (d / "intro.tex").write_text(r"""
\section{Introduction}
\label{sec:intro}
We propose a novel approach \cite{he2016}.
Our contributions are \ref{sec:method}.
""", encoding="utf-8")

    (d / "method.tex").write_text(r"""
\section{Method}
\label{sec:method}

\subsection{Architecture}
\label{sec:arch}
The model consists of three layers.

\subsection{Training}
\label{sec:training}
We use Adam optimizer \cite{kingma2014}.
""", encoding="utf-8")

    (d / "conclusion.tex").write_text(r"""
\section{Conclusion}
\label{sec:conclusion}
Future work includes \ref{sec:arch}.
""", encoding="utf-8")

    parser = LatexParser()
    paper = parser.parse_project(d / "main.tex")

    assert len(paper.sections) == 3  # 3 top-level sections
    assert "sec:intro" in paper.lookup
    assert "sec:method" in paper.lookup
    assert "sec:arch" in paper.lookup
    assert "sec:training" in paper.lookup
    assert "sec:conclusion" in paper.lookup

    # children under method
    method = paper.lookup["sec:method"]
    assert len(method.children) == 2
    assert method.children[0].title == "Architecture"
    assert method.children[1].title == "Training"

    print("OK real paper structure")

    shutil.rmtree(d)


# ── Run ──
if __name__ == "__main__":
    test_starred_section()
    test_short_title()
    test_chapter_level()
    test_cite_with_optional()
    test_cleveref()
    test_label_collision()
    test_chinese_content()
    test_numbered_sections()
    test_empty_content_boundary()
    test_section_path()
    test_large_paper()
    test_missing_include_file()
    test_deep_nesting()
    test_paragraph_level()
    test_content_cleaning()
    test_real_paper_structure()
    print("\nAll edge tests passed!")
