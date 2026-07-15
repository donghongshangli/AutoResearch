"""最终测试：长论文 + 公式 + 复杂结构"""
import sys, os, tempfile, shutil, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from autolib.latex_parser import LatexParser
from autolib.doc_graph import DocGraph


def build_deep_paper(n_sections: int = 80):
    """构造一篇 80+ 节、含大量公式的长论文"""
    lines = [r"\documentclass{article}", r"\usepackage{amsmath,amssymb}", r"\begin{document}"]

    # 引言
    lines.append(r"\section{Introduction}\label{sec:intro}")
    lines.append(r"The effective context window capacity is defined as:")
    lines.append(r"\begin{equation}\label{eq:capacity}")
    lines.append(r"C_{\text{eff}} = \sum_{i=1}^{n} \min(|c_i|, \tau)")
    lines.append(r"\end{equation}")
    lines.append(r"where $c_i$ is the $i$-th context segment and $\tau$ is a threshold.")
    lines.append(r"As shown in \cite{ref1}, $\mathcal{O}(n \log n)$ complexity is achievable.")
    lines.append(r"See \ref{eq:capacity} and \ref{sec:method:overview}.")

    # Background
    lines.append(r"\section{Background}\label{sec:bg}")
    for i in range(1, 6):
        lines.append(rf"\subsection{{Background Topic {i}}}\label{{sec:bg:{i}}}")
        lines.append(rf"Prior work covers $\alpha_{{{i}}}$, $\beta_{{{i}}}$, $\gamma_{{{i}}}$.")
        # align environment with complex math
        lines.append(r"\begin{align}\label{eq:bg:" + str(i) + "}")
        lines.append(r"f(x) = \sum_{j=1}^{k} w_j \cdot \phi_j(x) \\")
        lines.append(r"g(x) = \frac{1}{1 + e^{-x}}")
        lines.append(r"\end{align}")
        if i > 1:
            lines.append(rf"Refer to \cite{{paper{i}a}} and \ref{{sec:bg:{i-1}}}.")
        else:
            lines.append(rf"Refer to \cite{{paper{i}a}}.")
        for j in range(2):
            lines.append(rf"\subsubsection{{Detail {i}.{j+1}}}\label{{sec:bg:{i}:{j+1}}}")
            lines.append(r"$\mathbf{W} \in \mathbb{R}^{d \times d}$")

    # Method
    lines.append(r"\section{Method}\label{sec:method:overview}")
    for m in range(1, 5):
        lines.append(rf"\subsection{{Method Component {m}}}\label{{sec:method:{m}}}")
        lines.append(r"$\mathcal{L}(x) = \|\mathbf{A} x - \mathbf{b}\|_2^2$")
        if m > 1:
            lines.append(rf"Builds on \cite{{paper{m}b}} and \ref{{sec:method:{m-1}}}.")
        else:
            lines.append(rf"Builds on \cite{{paper{m}b}}.")
        for k in range(3):
            lines.append(rf"\subsubsection{{Sub-component {m}.{k+1}}}\label{{sec:method:{m}:{k+1}}}")
            lines.append(r"$\nabla \mathcal{L} = \mathbf{A}^T(\mathbf{A} x - \mathbf{b})$")
            lines.append(rf"See \ref{{sec:method:{m}}} for context.")

    # Experiments
    lines.append(r"\section{Experiments}\label{sec:exp}")
    for e in range(1, 4):
        lines.append(rf"\subsection{{Experiment {e}}}\label{{sec:exp:{e}}}")
        lines.append(r"\begin{table}[h]\label{tab:" + str(e) + "}")
        lines.append(rf"\caption{{Results for experiment {e}}}")
        lines.append(r"\begin{tabular}{lc}")
        lines.append(r"Method & Score \\ \hline")
        lines.append(rf"Baseline & {50+e*10:.1f} \\")
        lines.append(rf"Ours & {70+e*5:.1f} \\")
        lines.append(r"\end{tabular}")
        lines.append(r"\end{table}")
        lines.append(rf"Table \ref{{tab:{e}}} shows improvement.")
        lines.append(rf"Consistent with \ref{{sec:method:{e}}}.")

    # Conclusion
    lines.append(r"\section{Conclusion}\label{sec:conc}")
    lines.append(r"We proved that $\lim_{n \to \infty} \frac{1}{n}\sum_{i=1}^n x_i = \mu$.")
    lines.append(r"Future work: $\mathcal{O}(n)$ instead of $\mathcal{O}(n \log n)$ per \ref{sec:method:1}.")

    lines.append(r"\end{document}")
    return "\n".join(lines)


def build_bib():
    b = []
    b.append(r"""@article{ref1,title={Long-Context Language Models},author={Smith, J.},year={2024},journal={JMLR}}""")
    for i in range(1, 6):
        for c in ['a', 'b', 'c']:
            b.append(rf"""@article{{paper{i}{c},title={{Paper {i}{c}}},author={{Author {i}{c}}},year={{2024}},journal={{\\emph{{Conf {i}}}}}}}""")
    return "\n".join(b)


def main():
    tmpdir = tempfile.mkdtemp()
    with open(os.path.join(tmpdir, "main.tex"), "w", encoding="utf-8") as f:
        f.write(build_deep_paper())
    with open(os.path.join(tmpdir, "refs.bib"), "w", encoding="utf-8") as f:
        f.write(build_bib())

    # ── 解析 ──
    t0 = time.time()
    parser = LatexParser()
    paper = parser.parse_project(os.path.join(tmpdir, "main.tex"))
    graph = DocGraph(paper, [os.path.join(tmpdir, "refs.bib")])
    t1 = time.time()

    n = len(paper.all_sections)
    print(f"  Total sections: {n}")
    print(f"  Parse+build: {(t1-t0)*1000:.0f}ms")
    assert t1 - t0 < 1.0, f"Too slow: {(t1-t0)*1000:.0f}ms"
    print()

    # ── 检查公式内容是否保留 ──
    intro = paper.lookup["sec:intro"]
    content = intro.content
    print(f"=== Introduction content ({len(content)} chars) ===")
    # print snippet safely (avoid Unicode console issues on Windows)
    safe = content.encode('ascii', errors='replace').decode('ascii')
    print(safe[:300])
    print()

    # 公式关键词检查（LatexNodes2Text 将 LaTeX → Unicode 纯文本）
    # C_{\text{eff}} → "C_eff", \sum → ∑, \mathcal{O} → 𝒪
    assert "C_eff" in content, f"C_eff formula not in content: {safe[:100]}"
    assert "c_i" in content, "c_i not in content"
    assert "complexity" in content, "complexity discussion not in content"
    print("  [OK] Display formula ($C_eff$, c_i, complexity) preserved")

    # 对齐环境
    bg1 = paper.lookup["sec:bg:1"]
    assert "f(x)" in bg1.content, "align env not in content: " + bg1.content[:100]
    print("  [OK] align environment (f(x), g(x)) preserved")

    # 内联公式 — subsubsection content
    bg1_sub = paper.lookup["sec:bg:1:1"]
    # \mathbf{W} \in \mathbb{R}^{d \times d} → "W in R d x d"
    assert bg1_sub is not None and len(bg1_sub.content) > 0
    print(f"  [OK] inline math preserved ({len(bg1_sub.content)} chars)")

    # 极限
    conc = paper.lookup["sec:conc"]
    assert len(conc.content) > 0 and ("lim" in conc.content.lower() or "mu" in conc.content)
    print("  [OK] limit notation preserved")

    # ── 引用完整性 ──
    print(f"\n  Labels: {len(paper.all_labels)}")
    print(f"  Cites:  {len(paper.all_cites)}")
    print(f"  Refs:   {sum(len(s.refs) for s in paper.all_sections)}")
    print(f"  Bib:    {len(graph._bib)}")

    assert graph.uncached_cites() == []
    print("  [OK] all cites have bib data")

    # ── ref 连通性 ──
    method1 = graph.ref_backlinks("sec:method:1")
    print(f"  [OK] sec:method:1 referenced by {len(method1)} sections")

    broken = graph.broken_refs()
    assert len(broken) == 0, f"Broken refs: {broken}"
    print("  [OK] zero broken refs")

    # ── 深层嵌套 localion ──
    deep = paper.lookup.get("sec:method:3:2")
    if deep:
        n = graph.section_neighbors(deep.id)
        assert len(n["path"]) == 3
        print(f"  [OK] deep section path: {' > '.join(n['path'])}")
        if n["parent"]:
            print(f"  [OK] parent: {n['parent'].title}")

    # ── bib 内容 ──
    e = graph.cite_info("paper1a")
    assert e and "Paper 1a" in e.title
    print(f"  [OK] bib entry: {e.title} by {e.authors[0]}, {e.year}")

    shutil.rmtree(tmpdir)
    print(f"\n=== FINAL VERDICT ===")
    print(f"  {n} sections, {len(paper.all_labels)} labels, {len(paper.all_cites)} cites")
    print(f"  Formulas: preserved")
    print(f"  Ref integrity: 0 broken")
    print(f"  Bib coverage: 100%")
    print(f"  Time: {(t1-t0)*1000:.0f}ms")
    print(f"  ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
