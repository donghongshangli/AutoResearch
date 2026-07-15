"""
project_sync.py — 项目文件一致性同步

保证 main.tex 的 \\input 列表 ≡ sections/ 中的实际 .tex 文件。
不依赖 parser、不依赖 doc_graph，纯文件系统级别操作。

用法:
    from autolib.project_sync import sync_main_tex
    sync_main_tex(proj_dir, keep_stems={"intro", "method", "conclusion"})
"""

import re
from pathlib import Path

from autolib.utils import find_main_tex


def sync_main_tex(proj_dir: Path, keep_stems: set[str] | None = None) -> dict:
    """重建 main.tex 的 \\input 列表，确保与 sections/ 中的文件严格一致。

    行为：
        1. 读取 main.tex，提取 preamble 和正文前后缀（去掉 \\input 行）
        2. 如果 keep_stems 传了：删除 sections/ 中 stem 不在集合里的 .tex 文件
        3. 扫描 sections/ 中剩余 .tex → 生成 \\input 列表
        4. 重建 main.tex
        5. 再次清理：删除 sections/ 中存在但未被 \\input 引用的孤儿文件

    Args:
        proj_dir: 论文项目根目录
        keep_stems: 允许保留的文件 stem 集合（不含 .tex 后缀、不含路径前缀）。
                    传 None 则保留全部 .tex 文件。

    Returns:
        {"status": "ok", "inputs": [...], "deleted": [...]}
    """
    main_tex = find_main_tex(proj_dir)
    if main_tex is None:
        return {"status": "error", "message": "No main.tex found"}

    sections_dir = proj_dir / "sections"

    # ── 1. 按 keep_stems 清理 sections/ ──
    deleted = []
    if keep_stems is not None and sections_dir.exists():
        for f in list(sections_dir.iterdir()):
            if f.is_file() and f.suffix == ".tex" and f.stem not in keep_stems:
                f.unlink()
                deleted.append(f.name)

    # ── 2. 扫描 sections/ 中实际存在的 .tex ──
    tex_files: list[Path] = []
    if sections_dir.exists():
        tex_files = sorted(
            [f for f in sections_dir.iterdir() if f.is_file() and f.suffix == ".tex"],
            key=lambda f: f.stem.lower(),
        )

    # ── 3. 读取 main.tex，提取 preamble 和主体 ──
    content = main_tex.read_text(encoding="utf-8", errors="replace")
    preamble = _extract_preamble(content)
    prefix, suffix = _extract_body_parts(content)

    # ── 4. 生成 \\input 列表 ──
    input_lines = [_format_input(f, proj_dir) for f in tex_files]

    # ── 5. 重建 main.tex ──
    parts = [preamble.rstrip()]
    if prefix.strip():
        parts.append(prefix.strip())
    if input_lines:
        parts.append("\n".join(input_lines))
    if suffix.strip():
        parts.append(suffix.strip())
    parts.append("\\end{document}\n")

    main_tex.write_text("\n\n".join(parts), encoding="utf-8")

    return {
        "status": "ok",
        "inputs": [f"{_relative_stem(f, proj_dir)}" for f in tex_files],
        "count": len(tex_files),
        "deleted": deleted,
    }


# ═══════════════════════════════════════════════════════════
# 内部工具
# ═══════════════════════════════════════════════════════════

def _extract_preamble(text: str) -> str:
    """提取 \\begin{document} 及之前的内容。"""
    m = re.search(r"\\begin\{document\}", text)
    if m:
        return text[: m.end()]
    return text


def _extract_body_parts(text: str) -> tuple[str, str]:
    """提取 body 中去掉 \\input 行之后的前缀和后缀。

    Returns:
        (prefix, suffix) — prefix = \\begin{document} 之后到第一个 \\input 之前的内容；
                           suffix = 最后一个 \\input 之后到 \\end{document} 之前的内容。
    """
    begin_m = re.search(r"\\begin\{document\}", text)
    if not begin_m:
        return "", ""

    end_m = re.search(r"\\end\{document\}", text)
    body_start = begin_m.end()
    body_end = end_m.start() if end_m else len(text)
    body = text[body_start:body_end]

    input_pat = re.compile(r"^\s*\\(?:input|include)\{[^}]+\}.*$", re.MULTILINE)
    matches = list(input_pat.finditer(body))

    if not matches:
        return body.strip(), ""

    prefix = body[: matches[0].start()].strip()
    suffix = body[matches[-1].end():].strip()
    return prefix, suffix


def _format_input(file_path: Path, proj_dir: Path) -> str:
    """将文件路径转为 \\input{...} 行（不带 .tex 后缀，使用相对路径）。"""
    rel = _relative_stem(file_path, proj_dir)
    return f"\\input{{{rel}}}"


def _relative_stem(file_path: Path, proj_dir: Path) -> str:
    """获取文件相对于项目根目录的路径，不带 .tex 后缀。"""
    try:
        rel = str(file_path.resolve().relative_to(proj_dir.resolve())).replace("\\", "/")
    except ValueError:
        rel = file_path.name
    if rel.endswith(".tex"):
        rel = rel[:-4]
    return rel
