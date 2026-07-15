"""doc_graph 压力测试（精简版 API）"""
import sys, os, tempfile, shutil, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from autolib.latex_parser import LatexParser
from autolib.doc_graph import DocGraph, BibEntry


def build_large_paper():
    s = [r"\documentclass{article}", r"\begin{document}"]
    s.append(r"\section{Introduction}\label{sec:intro}")
    s.append(r"Overview \cite{survey2023,classic2010,fundamental2015}.")
    s.append(r"Refs: \ref{sec:background}, \ref{sec:method:intro}.")

    s.append(r"\section{Background}\label{sec:background}")
    for i in range(1, 6):
        s.append(rf"\subsection{{Topic {i}}}\label{{sec:bg:{i}}}")
        s.append(rf"Work on topic {i} \cite{{paper{i}a,paper{i}b,paper{i}c}}.")
        s.append(rf"As in \ref{{sec:intro}}.")

    s.append(r"\section{Method}\label{sec:method:intro}")
    for i in range(1, 4):
        s.append(rf"\subsection{{Approach {i}}}\label{{sec:method:{i}}}")
        s.append(rf"Component {i}. \cite{{paper{i}a,our2025}}.")
        if i > 1:
            s.append(rf"Builds on \ref{{sec:method:{i-1}}}.")
        for j in range(1, 3):
            s.append(rf"\subsubsection{{Detail {i}.{j}}}\label{{sec:method:{i}:{j}}}")
            s.append(rf"Impl {i}.{j}. See \ref{{sec:method:{i}}}.")

    s.append(r"\section{Experiments}\label{sec:eval:setup}")
    for i in range(1, 5):
        s.append(rf"\subsection{{Exp {i}}}\label{{sec:eval:{i}}}")
        s.append(rf"\subsubsection{{Setup}}\label{{sec:eval:{i}:setup}}")
        s.append(rf"Config.")
        s.append(rf"\subsubsection{{Results}}\label{{sec:eval:{i}:result}}")
        s.append(rf"Metrics. \ref{{sec:eval:{i-1}:result}}." if i > 1 else rf"Metrics.")
        s.append(rf"Per \ref{{sec:method:1}}.")

    s.append(r"\section{Conclusion}\label{sec:conc}")
    s.append(r"Summary. Extends \ref{{sec:method:1}}, \ref{{sec:method:3}}.")
    s.append(r"\end{document}")
    return "\n".join(s)


def build_bib():
    return r"""
@string{emnlp = "Proceedings of EMNLP"}
@string{cvpr  = "IEEE CVPR"}
@comment{junk, ignored content}

@article{survey2023,
  title = {A Comprehensive Survey of Long-Context LMs},
  author = {Smith, John and Zhang, Wei and Kumar, A. B. and O'Brien, Sean},
  year = {2023},
  journal = {Journal of AI Research},
  abstract = {We survey recent advances in long-context LMs.}
}
@article{classic2010,
  title = {Foundations of Deep Learning: From {RBMs} to {DBNs}},
  author = {Hinton, Geoffrey E.},
  year = {2010},
  journal = {Neural Computation}
}
@article{fundamental2015,
  title = {On the Fundamental Limits of Neural Network Training},
  author = {Goodfellow, Ian and Bengio, Yoshua},
  year = {2015},
  booktitle = {ICLR}
}
@article{paper1a,title={Method A},author={Alpha, A.},year={2024},journal=emnlp}
@article{paper1b,title={Method B},author={Beta, B.},year={2024},journal={NeurIPS}}
@article{paper1c,title={Method C},author={Gamma, G.},year={2024},journal={ICML}}
@article{paper2a,title={Advancing SOTA},author={Epsilon, E.},year={2023},journal=cvpr}
@article{paper2b,title={Efficient Training},author={Theta, T.},year={2023},journal={arXiv}}
@article{paper2c,title={Scaling Laws},author={Iota, I.},year={2022},journal={TMLR}}
@article{paper3a,title={Beyond {Transformers}},author={Kappa, K.},year={2024},journal={Science}}
@article{paper3b,title={Training Dynamics},author={Lambda, L.},year={2024},journal={}}
@article{paper3c,title={Emergent Abilities},author={Mu, M.},year={2025}}
@article{paper4a,title={{LLM} Deployment},author={Nu, N.},year={2025},journal={ACL}}
@article{paper4b,title={Quantization},author={Omicron, O.},year={2025},journal={ICLR}}
@article{paper4c,title={Memory-Efficient},author={Pi, P.},year={2025},journal={NeurIPS}}
@article{paper5a,title={{RAG} Survey},author={Rho, R.},year={2024},journal={ACM CSUR}}
@article{paper5b,title={Dense Retrieval},author={Sigma, S.},year={2020},journal={EMNLP}}
@article{paper5c,title={{BERT}: Pre-training},author={Devlin, Jacob},year={2019},journal={NAACL}}
@article{our2025,title={Document Graphs for AI Writing},author={Our, Team},year={2025}}
"""


def main():
    tmpdir = tempfile.mkdtemp()
    with open(os.path.join(tmpdir, "main.tex"), "w", encoding="utf-8") as f:
        f.write(build_large_paper())
    with open(os.path.join(tmpdir, "refs.bib"), "w", encoding="utf-8") as f:
        f.write(build_bib())

    parser = LatexParser()
    t0 = time.time()
    paper = parser.parse_project(os.path.join(tmpdir, "main.tex"))
    graph = DocGraph(paper, [os.path.join(tmpdir, "refs.bib")])
    t1 = time.time()

    # basic counts
    n_sections = len(paper.all_sections)
    n_cites = len(paper.all_cites)
    n_bib = len(graph._bib)
    print(f"  Sections: {n_sections}, Cites: {n_cites}, Bib: {n_bib}, Time: {(t1-t0)*1000:.0f}ms")

    # bib loading
    assert n_bib >= 19, f"Expected >=19 bib entries, got {n_bib}"
    assert graph.uncached_cites() == []
    print("  [OK] all cites have bib data")

    # special chars in authors
    e = graph.cite_info("survey2023")
    assert e and "O'Brien" in str(e.authors)
    assert "Kumar, A. B." in str(e.authors)
    print("  [OK] special author names")

    # titles with preserved braces
    assert "RBMs" in graph.cite_info("classic2010").title
    assert "BERT" in graph.cite_info("paper5c").title
    print("  [OK] brace-protected titles")

    # string macros (bare values)
    assert graph.cite_info("paper1a").journal == "emnlp"
    assert graph.cite_info("paper2a").journal == "cvpr"
    print("  [OK] bare value fields (string macros)")

    # empty journal
    assert graph.cite_info("paper3b").journal == ""
    assert graph.cite_info("paper3b").booktitle == ""
    print("  [OK] empty journal field")

    # booktitle vs journal
    assert graph.cite_info("fundamental2015").booktitle == "ICLR"
    assert graph.cite_info("fundamental2015").journal == ""
    print("  [OK] booktitle for inproceedings")

    # ref backlinks
    bl = graph.ref_backlinks("sec:method:1")
    assert len(bl) > 5, f"sec:method:1 heavily referenced, got {len(bl)}"
    print(f"  [OK] sec:method:1 backlinks: {len(bl)}")

    # broken refs
    broken = graph.broken_refs()
    assert len(broken) == 0, f"Expected 0 broken refs, got {broken}"
    print("  [OK] no broken refs")

    # section neighbors (deep nesting)
    leaf = paper.lookup.get("sec:method:1:1")
    if leaf:
        n = graph.section_neighbors(leaf.id)
        assert n["parent"] is not None
        assert n["next"] is not None  # Detail 1.2
        assert len(n["siblings"]) == 1
        assert len(n["path"]) == 3
        print("  [OK] deep nesting neighbors")

    # performance
    assert t1 - t0 < 1.0
    print(f"  [OK] performance: {(t1-t0)*1000:.1f}ms")

    shutil.rmtree(tmpdir)
    print(f"\nALL STRESS TESTS PASSED ({n_sections} sections, {n_bib} bib, {n_cites} cites)")


if __name__ == "__main__":
    main()
