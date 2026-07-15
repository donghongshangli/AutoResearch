"""
latex_parser 验证测试 — 使用 test-latex-v2.py 的 SAMPLE_TEX
"""
import sys
from pathlib import Path

# 加项目根到 path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from autolib.latex_parser import LatexParser, Section, PaperAST, FileParseResult

# ── 测试用的 SAMPLE_TEX ──
SAMPLE_TEX = r"""
\documentclass[11pt]{article}

\title{A Comprehensive Test}
\author{Test Author}

\begin{document}
\maketitle

\begin{abstract}
This paper evaluates Python LaTeX parsing libraries.
We test pylatexenc and TexSoup.
\end{abstract}

\section{Introduction}
\label{sec:intro}

Understanding LaTeX structure is crucial for AI-assisted writing.
As shown in prior work \cite{prism2025,jayalath2024}, existing tools
like Prism \ref{fig:prism-arch} rely on server-side parsing.

\subsection{Problem Statement}
\label{sec:problem}

The core challenge is parsing \verb|\section|, \verb|\label|,
\verb|\cite|, and \verb|\ref| commands from multi-file projects.

\subsection{Motivation}
\label{sec:motivation}

As described in Section \ref{sec:problem} and Equation \ref{eq:context_window}.

\begin{equation}
\label{eq:context_window}
C_{\text{effective}} = \sum_{i=1}^{n} \min(|c_i|, \tau)
\end{equation}

\section{Method}
\label{sec:method}

\begin{figure}[t]
\centering
\caption{System architecture.}
\label{fig:prism-arch}
\end{figure}

\subsection{Document Graph Construction}
\label{sec:docgraph}

We build a three-level index \cite{chang2024bookscore,liu2024repoqa}.

\begin{table}[h]
\centering
\caption{Comparison of parsing libraries}
\label{tab:comparison}
\begin{tabular}{lcc}
\hline
Library & Sections & Labels \\
\hline
pylatexenc & yes & yes \\
TexSoup   & yes & partial \\
\hline
\end{tabular}
\end{table}

\subsection{Context Assembly Engine}
\label{sec:context_engine}

\begin{enumerate}
\item Locate current paragraph via cursor position
\item Traverse refs and cites
\item Assemble context packet
\end{enumerate}

\subsubsection{Token Budget Management}

Following \cite{hwang2024structured}, we use a hierarchical schema.

\section{Results}
\label{sec:results}

Our parser handles nested environments and complex citations
like \cite{prism2025,jayalath2024,chang2024bookscore}.

\section{Conclusion}
\label{sec:conclusion}

We have shown that Python-based LaTeX parsing is viable
\cite{gunel2024prism}.

\bibliographystyle{plain}
\bibliography{refs}

\end{document}
"""


def test_parse_via_file():
    """通过临时文件测试 parse_file。"""
    import tempfile, os

    tmp = Path(tempfile.gettempdir()) / "_test_latex_parser.tex"
    tmp.write_text(SAMPLE_TEX, encoding="utf-8")

    parser = LatexParser()
    result = parser.parse_file(tmp)

    # 基本检查
    assert len(result.sections) == 4, f"期望 4 个顶层 section，实际 {len(result.sections)}"
    assert result.file == str(tmp.resolve())

    # Section 名称
    titles = [s.title for s in result.sections]
    assert "Introduction" in titles[0]
    assert "Method" in titles[1]
    assert "Results" in titles[2]
    assert "Conclusion" in titles[3]

    # Introduction 的 sub sections
    intro = result.sections[0]
    assert len(intro.children) == 2
    assert intro.children[0].title == "Problem Statement"
    assert intro.children[1].title == "Motivation"

    # Labels
    assert "sec:intro" in intro.labels
    assert "sec:problem" in intro.children[0].labels
    assert "sec:motivation" in intro.children[1].labels

    # Method 的子节 + 孙节
    method = result.sections[1]
    assert len(method.children) == 2
    assert method.children[0].title == "Document Graph Construction"
    assert method.children[1].title == "Context Assembly Engine"
    assert len(method.children[1].children) == 1
    assert method.children[1].children[0].title == "Token Budget Management"

    # 全局 label 数
    all_labels = []
    for sec in parser._iter_sections(result.sections):
        all_labels.extend(sec.labels)
    # sec:intro, sec:problem, sec:motivation, eq:context_window,
    # sec:method, fig:prism-arch, sec:docgraph, tab:comparison,
    # sec:context_engine, sec:results, sec:conclusion
    assert len(all_labels) == 11, f"期望 11 个 label，实际 {len(all_labels)}: {all_labels}"

    # 引用
    all_cites = set()
    for sec in parser._iter_sections(result.sections):
        all_cites.update(sec.cites)
    assert "prism2025" in all_cites
    assert "chang2024bookscore" in all_cites

    # 交叉引用
    all_refs = set()
    for sec in parser._iter_sections(result.sections):
        all_refs.update(sec.refs)
    assert "fig:prism-arch" in all_refs
    assert "sec:problem" in all_refs
    assert "eq:context_window" in all_refs

    # content 不为空
    for sec in parser._iter_sections(result.sections):
        if sec.depth <= 2:
            assert sec.content.strip(), f"{sec.title} 的 content 为空"

    # includes 列表
    assert isinstance(result.includes, list)

    # line 信息
    for sec in parser._iter_sections(result.sections):
        assert sec.line_start > 0
        assert sec.line_end >= sec.line_start

    tmp.unlink()
    print("✅ parse_file 测试通过")


def test_parse_project():
    """测试 parse_project（单文件相当于直接解析）。"""
    import tempfile

    tmp = Path(tempfile.gettempdir()) / "_test_project_main.tex"
    tmp.write_text(SAMPLE_TEX, encoding="utf-8")

    parser = LatexParser()
    paper = parser.parse_project(tmp)

    assert paper.main_file == str(tmp.resolve())
    assert len(paper.sections) == 4
    assert len(paper.files) == 1
    assert len(paper.warnings) == 0

    # lookup by label
    assert paper.lookup["sec:intro"].title == "Introduction"
    assert paper.lookup["sec:method"].title == "Method"
    assert paper.lookup["sec:problem"].title == "Problem Statement"
    assert paper.lookup["eq:context_window"].depth == 2  # in Motivation subsection

    # lookup by section id (numbered sections aren't numbered here, so fall back to label)
    # the id is the first label
    assert paper.lookup["sec:intro"].id == "sec:intro"

    # all_sections
    all_secs = paper.all_sections
    assert len(all_secs) == 9  # 4 top + 2 intro subs + 2 method subs + 1 subsub

    # all_labels
    assert len(paper.all_labels) == 11

    # all_cites (prism2025, jayalath2024, chang2024bookscore, liu2024repoqa,
    #            hwang2024structured, gunel2024prism)
    assert len(paper.all_cites) == 6

    # full_content
    intro = paper.lookup["sec:intro"]
    full = intro.full_content
    assert "Understanding LaTeX structure" in full
    assert "Problem Statement" in full  # child title should be included
    assert "Motivation" in full

    tmp.unlink()
    print("✅ parse_project 测试通过")


def test_robustness():
    """测试不规范 LaTeX 容错。"""
    import tempfile

    dirty = r"""
\section{Missing closing brace
\label{test-label}
\textbf{unclosed bold
\begin{itemize}
\item First
% No \end{itemize}
"""
    tmp = Path(tempfile.gettempdir()) / "_test_dirty.tex"
    tmp.write_text(dirty, encoding="utf-8")

    parser = LatexParser()
    result = parser.parse_file(tmp)

    # 不崩溃就算过
    assert result.file
    assert isinstance(result.sections, list)
    assert isinstance(result.warnings, list)

    tmp.unlink()
    print("✅ 容错测试通过")


def test_multi_file():
    """测试多文件项目。"""
    import tempfile, os

    d = Path(tempfile.gettempdir()) / "_test_multifile"
    d.mkdir(exist_ok=True)

    main = d / "main.tex"
    intro = d / "sections" / "intro.tex"
    method = d / "sections" / "method.tex"
    intro.parent.mkdir(exist_ok=True)

    main.write_text(r"""
\documentclass{article}
\begin{document}

\section{Main Section}
\label{sec:main}

\input{sections/intro}

\input{sections/method}

\end{document}
""", encoding="utf-8")

    intro.write_text(r"""
\section{Introduction}
\label{sec:intro}

Intro text here \cite{paper1}.

\subsection{Motivation}
\label{sec:motivation}

Motivation text \ref{sec:main}.
""", encoding="utf-8")

    method.write_text(r"""
\section{Method}
\label{sec:method}

Method text here \cite{paper2,paper3}.

\subsection{Implementation}
\label{sec:implementation}

Implementation details.
""", encoding="utf-8")

    parser = LatexParser()
    paper = parser.parse_project(main)

    # 3 个文件
    assert len(paper.files) == 3, f"期望 3 个文件，实际 {len(paper.files)}"

    # 顶层 sections（按 include 顺序合并）
    assert len(paper.sections) == 3  # Main + Introduction + Method

    # lookup
    assert paper.lookup["sec:main"].title == "Main Section"
    assert paper.lookup["sec:intro"].title == "Introduction"
    assert paper.lookup["sec:method"].title == "Method"
    assert paper.lookup["sec:motivation"].title == "Motivation"
    assert paper.lookup["sec:implementation"].title == "Implementation"

    # 跨文件交叉引用
    assert "sec:main" in paper.lookup["sec:motivation"].refs

    # 去重引用
    assert "paper1" in paper.all_cites
    assert "paper2" in paper.all_cites
    assert "paper3" in paper.all_cites
    assert len(paper.all_cites) == 3

    # 无警告
    assert paper.warnings == [], f"意外警告: {paper.warnings}"

    # 清理
    import shutil
    shutil.rmtree(d)
    print("✅ 多文件测试通过")


def test_empty_file():
    """测试空文件。"""
    import tempfile

    tmp = Path(tempfile.gettempdir()) / "_test_empty.tex"
    tmp.write_text("", encoding="utf-8")

    parser = LatexParser()
    result = parser.parse_file(tmp)
    assert result.sections == []
    assert result.labels == {}
    assert result.includes == []

    tmp.unlink()
    print("✅ 空文件测试通过")


def test_lookup():
    """测试 PaperAST.lookup 按 label 和 section id 查找。"""
    import tempfile

    tmp = Path(tempfile.gettempdir()) / "_test_lookup.tex"
    tmp.write_text(SAMPLE_TEX, encoding="utf-8")

    parser = LatexParser()
    paper = parser.parse_project(tmp)

    # 按 label
    sec = paper.lookup.get("sec:method")
    assert sec is not None
    assert sec.title == "Method"

    # 不存在的 label
    sec = paper.lookup.get("sec:nonexistent")
    assert sec is None

    # 按 section id（编号查找）
    sec = paper.lookup.get("sec:intro")
    assert sec is not None
    assert sec.title == "Introduction"

    tmp.unlink()
    print("✅ lookup 测试通过")


# ── 运行 ──
if __name__ == "__main__":
    test_parse_via_file()
    test_parse_project()
    test_robustness()
    test_multi_file()
    test_empty_file()
    test_lookup()
    print("\n🎉 全部测试通过！")
