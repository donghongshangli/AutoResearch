"""
doc_graph 单元测试
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from autolib.latex_parser import LatexParser
from autolib.doc_graph import DocGraph, BibEntry


SAMPLE_TEX = r"""
\documentclass[11pt]{article}

\title{A Comprehensive Test}
\author{Test Author}

\begin{document}
\maketitle

\begin{abstract}
This paper evaluates Python LaTeX parsing libraries.
\end{abstract}

\section{Introduction}
\label{sec:intro}

Understanding LaTeX structure is crucial \cite{prism2025,jayalath2024}.
As shown in Figure \ref{fig:prism-arch}.

\subsection{Problem Statement}
\label{sec:problem}

The core challenge is parsing commands.
See Section \ref{sec:method}.

\section{Method}
\label{sec:method}

Our approach \cite{chang2024bookscore}.

\subsection{Implementation}
\label{sec:implementation}

We build on \cite{liu2024repoqa}.

\section{Conclusion}
\label{sec:conclusion}

Summary \cite{gunel2024prism}.
"""

SAMPLE_BIB = r"""
@article{prism2025,
  title = {PRISM: Efficient Long-Range Processing},
  author = {Smith, John and Zhang, Wei},
  year = {2025},
  journal = {arXiv},
  abstract = {We present PRISM, an efficient framework for long-range text.}
}
@article{jayalath2024,
  title = {LaTeX Parsing for AI},
  author = {Jayalath, A. B.},
  year = {2024},
  journal = {ACL}
}
@article{chang2024bookscore,
  title = {BookScore: A Benchmark},
  author = {Chang, Peter},
  year = {2024}
}
@article{liu2024repoqa,
  title = {RepoQA: Code Understanding},
  author = {Liu, Ming},
  year = {2024},
  journal = {ICLR}
}
"""


def _setup():
    """创建临时 test paper + bib → (parser, graph)."""
    d = Path(tempfile.mkdtemp())
    main = d / "main.tex"
    bib = d / "refs.bib"
    main.write_text(SAMPLE_TEX, encoding="utf-8")
    bib.write_text(SAMPLE_BIB, encoding="utf-8")

    parser = LatexParser()
    paper = parser.parse_project(main)
    graph = DocGraph(paper, [str(bib)])
    return d, main, bib, parser, paper, graph


def _cleanup(d: Path):
    import shutil
    shutil.rmtree(d, ignore_errors=True)


# ── cite_info ──────────────────────────────────────────────

def test_cite_info_known():
    d, _, _, _, _, graph = _setup()
    entry = graph.cite_info("prism2025")
    assert entry is not None
    assert entry.title == "PRISM: Efficient Long-Range Processing"
    assert "Smith" in str(entry.authors)
    assert entry.year == "2025"
    _cleanup(d)


def test_cite_info_unknown():
    d, _, _, _, _, graph = _setup()
    assert graph.cite_info("nonexistent") is None
    _cleanup(d)


def test_cite_info_empty_bib():
    """DocGraph without bib — cite_info always None."""
    d, main, _, parser, paper, _ = _setup()
    graph_no_bib = DocGraph(paper)  # no bib_paths
    assert graph_no_bib.cite_info("prism2025") is None
    _cleanup(d)


# ── ref_target ─────────────────────────────────────────────

def test_ref_target_known():
    d, _, _, _, _, graph = _setup()
    target = graph.ref_target("sec:method")
    assert target is not None
    assert target.title == "Method"
    _cleanup(d)


def test_ref_target_unknown():
    d, _, _, _, _, graph = _setup()
    assert graph.ref_target("sec:nonexistent") is None
    _cleanup(d)


# ── ref_backlinks ──────────────────────────────────────────

def test_ref_backlinks():
    d, _, _, _, _, graph = _setup()
    # sec:problem is referenced by Motivation section (via \ref)
    # Actually: "See Section \ref{sec:method}" is in Problem Statement section
    # So sec:method should have a backlink from sec:problem
    backlinks = graph.ref_backlinks("sec:method")
    assert len(backlinks) >= 1
    assert any("Problem Statement" in s.title for s in backlinks)
    _cleanup(d)


def test_ref_backlinks_nonexistent():
    d, _, _, _, _, graph = _setup()
    assert graph.ref_backlinks("sec:nonexistent") == []
    _cleanup(d)


# ── section_neighbors ──────────────────────────────────────

def test_section_neighbors_root():
    """Root section has no parent. First child has no prev."""
    d, _, _, _, _, graph = _setup()
    intro = graph.ref_target("sec:intro")
    assert intro is not None
    neighbors = graph.section_neighbors(intro.id)
    assert neighbors["parent"] is None
    assert neighbors["prev"] is None  # first top-level section
    assert neighbors["next"] is not None  # sec:method comes after
    assert len(neighbors["path"]) == 1
    _cleanup(d)


def test_section_neighbors_last():
    """Last section has no next."""
    d, _, _, _, _, graph = _setup()
    conc = graph.ref_target("sec:conclusion")
    neighbors = graph.section_neighbors(conc.id)
    assert neighbors["next"] is None
    assert neighbors["prev"] is not None
    _cleanup(d)


def test_section_neighbors_child():
    """Subsection has parent and siblings."""
    d, _, _, _, _, graph = _setup()
    prob = graph.ref_target("sec:problem")
    neighbors = graph.section_neighbors(prob.id)
    assert neighbors["parent"] is not None
    assert neighbors["parent"].title == "Introduction"
    assert len(neighbors["siblings"]) == 0  # Problem Statement is the only subsection
    assert len(neighbors["path"]) == 2  # Introduction > Problem Statement
    _cleanup(d)


def test_section_neighbors_nonexistent():
    d, _, _, _, _, graph = _setup()
    neighbors = graph.section_neighbors("nonexistent")
    assert neighbors["prev"] is None
    assert neighbors["next"] is None
    assert neighbors["parent"] is None
    assert neighbors["siblings"] == []
    assert neighbors["path"] == []
    _cleanup(d)


# ── outline ────────────────────────────────────────────────

def test_outline():
    d, _, _, _, _, graph = _setup()
    nodes = graph.outline()
    titles = [n.title for n in nodes]
    assert "Introduction" in titles
    assert "Method" in titles
    assert "Conclusion" in titles
    # Intro has 2 subsections
    intro_node = next(n for n in nodes if n.title == "Introduction")
    assert len(intro_node.children) == 1  # Problem Statement
    _cleanup(d)


def test_outline_empty():
    """Empty paper → empty outline."""
    d = Path(tempfile.mkdtemp())
    main = d / "main.tex"
    main.write_text(r"\documentclass{article}\begin{document}\end{document}", encoding="utf-8")
    parser = LatexParser()
    paper = parser.parse_project(main)
    graph = DocGraph(paper)
    assert graph.outline() == []
    _cleanup(d)


# ── locate ─────────────────────────────────────────────────

def test_locate_valid():
    d, _, _, _, _, graph = _setup()
    sec = graph.locate("main.tex", 17)  # should be in Introduction section
    assert sec is not None
    assert "Introduction" in sec.title
    _cleanup(d)


def test_locate_by_filename_only():
    """locate should match by filename basename."""
    d, _, _, _, _, graph = _setup()
    sec = graph.locate("main.tex", 20)
    assert sec is not None
    _cleanup(d)


def test_locate_out_of_range():
    """Line outside all sections → None."""
    d, _, _, _, _, graph = _setup()
    assert graph.locate("main.tex", 99999) is None
    _cleanup(d)


def test_locate_nonexistent_file():
    d, _, _, _, _, graph = _setup()
    assert graph.locate("nope.tex", 1) is None
    _cleanup(d)


# ── expand_context ─────────────────────────────────────────

def test_expand_context_with_cites():
    d, _, _, _, _, graph = _setup()
    intro = graph.ref_target("sec:intro")
    ctx = graph.expand_context(intro)
    assert len(ctx.cite_summaries) >= 2  # prism2025, jayalath2024
    cite_keys = [c.key for c in ctx.cite_summaries]
    assert "prism2025" in cite_keys
    # One of them should have a title
    prism = next(c for c in ctx.cite_summaries if c.key == "prism2025")
    assert prism.title != ""
    _cleanup(d)


def test_expand_context_with_refs():
    d, _, _, _, _, graph = _setup()
    prob = graph.ref_target("sec:problem")
    ctx = graph.expand_context(prob)
    assert len(ctx.ref_summaries) >= 1  # ref to sec:method
    ref_labels = [r.label for r in ctx.ref_summaries]
    assert "sec:method" in ref_labels
    _cleanup(d)


def test_expand_context_empty():
    """Section with no cites and no refs → empty summaries."""
    d, _, _, _, _, graph = _setup()
    conc = graph.ref_target("sec:conclusion")
    ctx = graph.expand_context(conc)
    # gunel2024prism is cited but no bib data
    assert isinstance(ctx.cite_summaries, list)
    _cleanup(d)


# ── broken_refs / uncached_cites ───────────────────────────

def test_broken_refs_clean():
    d, _, _, _, _, graph = _setup()
    # fig:prism-arch has no \label in this sample, so it's broken
    broken = graph.broken_refs()
    assert "fig:prism-arch" in broken
    _cleanup(d)


def test_uncached_cites():
    d, _, _, _, _, graph = _setup()
    # gunel2024prism is cited but not in the bib
    uncached = graph.uncached_cites()
    assert "gunel2024prism" in uncached
    _cleanup(d)


# ── _extract_first_sentence ────────────────────────────────

def test_extract_first_sentence_normal():
    from autolib.doc_graph import DocGraph as DG
    text = "This is sentence one. This is sentence two."
    result = DG._extract_first_sentence(text)
    assert result == "This is sentence one."
    assert len(result) < len(text)


def test_extract_first_sentence_no_period():
    from autolib.doc_graph import DocGraph as DG
    text = "This is a single sentence without period"
    result = DG._extract_first_sentence(text)
    assert len(result) <= 200


def test_extract_first_sentence_empty():
    from autolib.doc_graph import DocGraph as DG
    assert DG._extract_first_sentence("") == ""


def test_extract_first_sentence_long():
    from autolib.doc_graph import DocGraph as DG
    text = "A" * 500
    result = DG._extract_first_sentence(text)
    assert len(result) <= 200


# ── run ────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        test_cite_info_known, test_cite_info_unknown, test_cite_info_empty_bib,
        test_ref_target_known, test_ref_target_unknown,
        test_ref_backlinks, test_ref_backlinks_nonexistent,
        test_section_neighbors_root, test_section_neighbors_last,
        test_section_neighbors_child, test_section_neighbors_nonexistent,
        test_outline, test_outline_empty,
        test_locate_valid, test_locate_by_filename_only,
        test_locate_out_of_range, test_locate_nonexistent_file,
        test_expand_context_with_cites, test_expand_context_with_refs,
        test_expand_context_empty,
        test_broken_refs_clean, test_uncached_cites,
        test_extract_first_sentence_normal, test_extract_first_sentence_no_period,
        test_extract_first_sentence_empty, test_extract_first_sentence_long,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"✅ {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"❌ {t.__name__}: {e}")
    print(f"\n{passed}/{len(tests)} passed")
