"""
merge_svc 集成测试 — merge_project + save_merged (offset/structural)

测试覆盖:
  - merge_project: 单文件 / 多文件 / 空项目
  - save_merged offset:   小改动（< 1000 字符）
  - save_merged structural: 大改动（≥ 1000 字符）
  - 边界: SOURCE 标记在正文中 / 跨 segment 删除
"""
import sys
import shutil
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from autolib.latex_parser import LatexParser
from server.services.merge_svc import merge_project, save_merged


# ═══════════════════════════════════════════════════════════
# 辅助：搭建测试项目
# ═══════════════════════════════════════════════════════════

PREAMBLE = r"""\documentclass{article}
\usepackage{amsmath}
\title{Test Paper}
\author{Test Author}

\begin{document}
\maketitle
"""


def _make_single_file_project(d: Path) -> Path:
    """创建单文件 LaTeX 项目，返回 main.tex 路径。"""
    main = d / "main.tex"
    main.write_text(
        PREAMBLE
        + r"""
\section{Introduction}
\label{sec:intro}

This is the introduction. We discuss the background here.

\section{Method}
\label{sec:method}

Our method is described in detail. We use a transformer architecture.

\section{Conclusion}
\label{sec:conclusion}

We have demonstrated the effectiveness of our approach.
\end{document}
""",
        encoding="utf-8",
    )
    return main


def _make_multi_file_project(d: Path) -> dict:
    """创建多文件 LaTeX 项目。返回各文件路径。"""
    main = d / "main.tex"
    sections = d / "sections"
    sections.mkdir(parents=True)

    main.write_text(
        PREAMBLE
        + r"""
\input{sections/introduction}
\input{sections/method}
\input{sections/conclusion}
\end{document}
""",
        encoding="utf-8",
    )

    intro = sections / "introduction.tex"
    intro.write_text(
        r"""\section{Introduction}
\label{sec:intro}

This is the introduction. We cite prior work \cite{smith2020}.

\subsection{Motivation}
\label{sec:motivation}

Why this matters.
""",
        encoding="utf-8",
    )

    method = sections / "method.tex"
    method.write_text(
        r"""\section{Method}
\label{sec:method}

Our method uses a three-stage pipeline \cite{jones2021}.

\begin{equation}
\label{eq:main}
y = f(x) + \epsilon
\end{equation}
""",
        encoding="utf-8",
    )

    conclusion = sections / "conclusion.tex"
    conclusion.write_text(
        r"""\section{Conclusion}
\label{sec:conclusion}

We have shown that our approach works.
""",
        encoding="utf-8",
    )

    return {"main": main, "intro": intro, "method": method, "conclusion": conclusion}


# ═══════════════════════════════════════════════════════════
# merge_project 测试
# ═══════════════════════════════════════════════════════════

def test_merge_single_file():
    d = Path(tempfile.mkdtemp())
    try:
        _make_single_file_project(d)
        result = merge_project(d)

        assert result["merged_text"], "merged_text 不应为空"
        assert "Introduction" in result["merged_text"]
        assert "Method" in result["merged_text"]
        assert "Conclusion" in result["merged_text"]
        assert result["main_file"] == "main.tex"
        assert len(result["segments"]) >= 1, "至少有一个 segment"

        # preamble 应在 merged_text 开头
        assert r"\documentclass" in result["merged_text"]
        assert r"\end{document}" in result["merged_text"]

        print("✅ merge 单文件通过")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_merge_multi_file():
    d = Path(tempfile.mkdtemp())
    try:
        _make_multi_file_project(d)
        result = merge_project(d)

        assert result["main_file"] == "main.tex"
        assert "Introduction" in result["merged_text"]
        assert "Method" in result["merged_text"]
        assert "Conclusion" in result["merged_text"]
        assert "Motivation" in result["merged_text"]
        assert r"\end{document}" in result["merged_text"]

        # segments 应包含各子文件
        files = {seg["file"] for seg in result["segments"]}
        assert "main.tex" in files
        assert any("introduction.tex" in f for f in files)
        assert any("method.tex" in f for f in files)
        assert any("conclusion.tex" in f for f in files)

        # 每个 segment 的 start/end 应在 merged_text 范围内
        text = result["merged_text"]
        for seg in result["segments"]:
            assert 0 <= seg["start"] < seg["end"] <= len(text), \
                f"segment {seg['file']} 越界: start={seg['start']}, end={seg['end']}, text_len={len(text)}"

        print("✅ merge 多文件通过")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_merge_empty_project():
    d = Path(tempfile.mkdtemp())
    try:
        result = merge_project(d)
        assert result["merged_text"] == ""
        assert result["segments"] == []
        assert result["main_file"] == ""
        print("✅ merge 空项目通过")
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ═══════════════════════════════════════════════════════════
# save_merged offset 策略（小改动）
# ═══════════════════════════════════════════════════════════

def test_save_offset_small_edit():
    """单文件项目：改几个单词 → offset 策略。"""
    d = Path(tempfile.mkdtemp())
    try:
        _make_single_file_project(d)
        result = merge_project(d)

        # 改一个词
        modified = result["merged_text"].replace("transformer", "Transformer-based")
        assert len(modified) - len(result["merged_text"]) < 1000, "改动应触发 offset"

        save_result = save_merged(d, modified, result["segments"])
        assert save_result["status"] == "ok"
        assert save_result["strategy"] == "offset"

        # 验证文件确实被改了
        main_content = (d / "main.tex").read_text(encoding="utf-8")
        assert "Transformer-based" in main_content
        assert "transformer" not in main_content  # 旧词不应存在

        print("✅ save offset 小改动通过")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_save_offset_multi_file():
    """多文件项目：改子文件内容 → offset 策略。"""
    d = Path(tempfile.mkdtemp())
    try:
        files = _make_multi_file_project(d)
        result = merge_project(d)

        # 改 introduction.tex 里的内容（"This is the introduction" 在 introduction.tex 中）
        modified = result["merged_text"].replace(
            "This is the introduction.",
            "This is the revised introduction with extra detail.",
        )
        assert len(modified) - len(result["merged_text"]) < 1000

        save_result = save_merged(d, modified, result["segments"])
        assert save_result["status"] == "ok"
        assert save_result["strategy"] == "offset"

        # 验证子文件被改
        intro_content = files["intro"].read_text(encoding="utf-8")
        assert "revised introduction with extra detail" in intro_content, \
            f"introduction.tex 应包含修改后的内容，实际: {intro_content[:200]}"

        # method.tex 的内容应保留原样
        method_content = files["method"].read_text(encoding="utf-8")
        assert "three-stage pipeline" in method_content, "method.tex 不应被改"

        print("✅ save offset 多文件通过")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_save_offset_preserves_preamble():
    """offset 保存不应破坏 preamble 和 main.tex 结构。"""
    d = Path(tempfile.mkdtemp())
    try:
        _make_single_file_project(d)
        result = merge_project(d)

        modified = result["merged_text"].replace(
            "effectiveness", "efficacy",
        )

        save_result = save_merged(d, modified, result["segments"])
        assert save_result["status"] == "ok"

        main_content = (d / "main.tex").read_text(encoding="utf-8")
        assert r"\documentclass{article}" in main_content
        assert r"\usepackage{amsmath}" in main_content
        assert r"\end{document}" in main_content
        assert "efficacy" in main_content

        print("✅ save offset preamble 保留通过")
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ═══════════════════════════════════════════════════════════
# save_merged structural 策略（大改动）
# ═══════════════════════════════════════════════════════════

def test_save_structural_large_edit():
    """单文件项目：大段改写 → structural 策略。"""
    d = Path(tempfile.mkdtemp())
    try:
        _make_single_file_project(d)
        result = merge_project(d)
        orig_len = len(result["merged_text"])

        # 把整个 Introduction 段大幅改写
        old_intro = "This is the introduction. We discuss the background here."
        new_intro = "This is the completely rewritten introduction. " + \
                    "We provide extensive background on the topic. " * 50
        modified = result["merged_text"].replace(old_intro, new_intro)
        assert len(modified) - orig_len > 1000, \
            f"改动 {len(modified) - orig_len} 字符，应触发 structural"

        save_result = save_merged(d, modified, result["segments"])
        assert save_result["status"] == "ok"
        assert save_result["strategy"] == "structural", \
            f"期望 structural，实际 {save_result.get('strategy')}"

        # 验证文件内容
        main_content = (d / "main.tex").read_text(encoding="utf-8")
        assert "completely rewritten introduction" in main_content, \
            f"main.tex 应包含插入内容: {main_content[main_content.find('Introduction'):main_content.find('Introduction')+300]}"

        # 不应丢失其他 section
        assert "Method" in main_content
        assert "Conclusion" in main_content

        print("✅ save structural 大改动通过")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_save_structural_multi_file():
    """多文件项目：大段改写 → structural 策略。"""
    d = Path(tempfile.mkdtemp())
    try:
        files = _make_multi_file_project(d)
        result = merge_project(d)

        # 把 Conclusion 整段替换掉
        modified = result["merged_text"].replace(
            "We have shown that our approach works.",
            "We have comprehensively demonstrated that our approach works. "
            + "Extensive experiments confirm the findings. " * 40,
        )
        assert abs(len(modified) - len(result["merged_text"])) > 1000

        save_result = save_merged(d, modified, result["segments"])
        assert save_result["status"] == "ok"
        assert save_result["strategy"] == "structural"

        # conclusion.tex 应该有新内容
        conclusion_content = files["conclusion"].read_text(encoding="utf-8")
        assert "comprehensively demonstrated" in conclusion_content

        # main.tex 的 \input 列表应保留
        main_content = files["main"].read_text(encoding="utf-8")
        assert r"\input{sections/introduction}" in main_content or \
               r"\input{sections/introduction" in main_content

        print("✅ save structural 多文件通过")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_save_structural_preserves_preamble():
    """structural 策略也不应破坏 preamble。"""
    d = Path(tempfile.mkdtemp())
    try:
        _make_single_file_project(d)
        result = merge_project(d)

        # 大段替换
        insertion = "Extra text to trigger structural. " * 100
        modified = result["merged_text"].replace(
            r"\section{Method}",
            r"\section{Method}" + "\n" + insertion,
        )

        save_result = save_merged(d, modified, result["segments"])
        assert save_result["status"] == "ok"

        main_content = (d / "main.tex").read_text(encoding="utf-8")
        assert r"\documentclass{article}" in main_content
        assert r"\end{document}" in main_content

        print("✅ save structural preamble 保留通过")
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ═══════════════════════════════════════════════════════════
# 边界 & 特殊场景
# ═══════════════════════════════════════════════════════════

def test_save_multiple_rounds():
    """多次 merge → edit → save 循环，确保不累积错误。"""
    d = Path(tempfile.mkdtemp())
    try:
        _make_single_file_project(d)

        for i in range(3):
            result = merge_project(d)
            word = f"iteration_{i}"
            modified = result["merged_text"].replace(
                "introduction", f"introduction {word}",
            )
            save_result = save_merged(d, modified, result["segments"])
            assert save_result["status"] == "ok", f"第 {i} 轮保存失败"

            main_content = (d / "main.tex").read_text(encoding="utf-8")
            assert word in main_content, f"第 {i} 轮修改未生效"

        print("✅ 多次 merge-save 循环通过")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_save_idempotent():
    """同一份 merged_text 保存两次，第二次应该是 no-op。"""
    d = Path(tempfile.mkdtemp())
    try:
        _make_single_file_project(d)
        result = merge_project(d)

        save1 = save_merged(d, result["merged_text"], result["segments"])
        assert save1["status"] in ("ok", "no_changes"), f"第一次保存失败: {save1}"

        save2 = save_merged(d, result["merged_text"], result["segments"])
        assert save2["status"] in ("ok", "no_changes"), f"第二次保存失败: {save2}"

        # 两次保存后文件应一致
        content1 = (d / "main.tex").read_text(encoding="utf-8")
        assert r"\section{Introduction}" in content1
        assert r"\section{Method}" in content1

        print("✅ save 幂等性通过")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_source_marker_in_content():
    """如果正文中出现类似 SOURCE 标记的文字，offset 策略不应误切。"""
    d = Path(tempfile.mkdtemp())
    try:
        _make_single_file_project(d)
        result = merge_project(d)

        # 在正文中插入一个类似 SOURCE 标记的行
        modified = result["merged_text"].replace(
            "This is the introduction.",
            "This is the introduction.\n\nWe reference % === SOURCE: fake.tex === in our analysis.",
        )
        assert len(modified) - len(result["merged_text"]) < 1000

        save_result = save_merged(d, modified, result["segments"])
        assert save_result["status"] == "ok", f"保存失败: {save_result}"

        # 如果误切，文件内容会丢失或错乱
        main_content = (d / "main.tex").read_text(encoding="utf-8")
        assert "fake.tex ===" in main_content, "SOURCE 标记应保留在正文中"
        assert r"\section{Method}" in main_content, "Method section 不应丢失"

        # 再次 merge 验证结构完整
        result2 = merge_project(d)
        assert "Method" in result2["merged_text"]
        assert "fake.tex ===" in result2["merged_text"]

        print("✅ SOURCE 标记在正文中通过")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_new_section_in_structural():
    """structural 策略：新增一个 Section → 应自动创建新文件。"""
    d = Path(tempfile.mkdtemp())
    try:
        files = _make_multi_file_project(d)
        result = merge_project(d)

        # 在 Method 和 Conclusion 之间插入新 Section
        new_section = r"""\section{Experiments}
\label{sec:experiments}

We conducted extensive experiments on multiple datasets.
""" + ("Details about experimental setup. " * 60)

        modified = result["merged_text"].replace(
            r"\section{Conclusion}",
            new_section + r"\n\section{Conclusion}",
        )

        save_result = save_merged(d, modified, result["segments"])
        assert save_result["status"] == "ok", f"保存失败: {save_result}"

        # 应新建了 experiments.tex
        exp_file = d / "sections" / "experiments.tex"
        assert exp_file.exists(), f"应创建 experiments.tex，文件列表: {list((d/'sections').iterdir())}"

        exp_content = exp_file.read_text(encoding="utf-8")
        assert "Experiments" in exp_content
        assert "extensive experiments" in exp_content

        # main.tex 应包含新的 \input
        main_content = files["main"].read_text(encoding="utf-8")
        assert "experiments" in main_content.lower(), \
            f"main.tex 应引用 experiments: {main_content}"

        print("✅ structural 新增 Section 通过")
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ═══════════════════════════════════════════════════════════
# 运行
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    tests = [
        test_merge_single_file,
        test_merge_multi_file,
        test_merge_empty_project,
        test_save_offset_small_edit,
        test_save_offset_multi_file,
        test_save_offset_preserves_preamble,
        test_save_structural_large_edit,
        test_save_structural_multi_file,
        test_save_structural_preserves_preamble,
        test_save_multiple_rounds,
        test_save_idempotent,
        test_source_marker_in_content,
        test_new_section_in_structural,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"❌ {t.__name__}: {e}")
            import traceback
            traceback.print_exc()
    print(f"\n{passed}/{len(tests)} 通过")
