"""
merge_svc.py — 统一文档视图服务

将多文件 LaTeX 项目合并为单文档：
- merge_project:   多文件 → 一个 merged_text + segments 映射
- save_merged:     用户修改 → 自动写回原文件（offset / structural 双策略）

策略选择：
- 改动 < 1000 字符 → offset 拆分，直接切回原文件（毫秒级）
- 改动 ≥ 1000 字符 → 重新 parse Section 树，匹配写回 + 新建/删除文件
"""

import re
from pathlib import Path
from typing import Optional

from autolib.latex_parser import LatexParser
from autolib.utils import find_main_tex
from autolib.project_sync import sync_main_tex

SEP_TEMPLATE = "\n% === SOURCE: {} ===\n"


# ═══════════════════════════════════════════════════════════
# 公开接口
# ═══════════════════════════════════════════════════════════

def merge_project(proj_dir: str | Path, project_root: Optional[str] = None) -> dict:
    """合并多文件 LaTeX 项目为统一文档。

    Returns:
        {
            merged_text: "完整文档文本（preamble + 所有 body 内容）",
            segments:    [{"file": "sections/intro.tex", "start": 500, "end": 1500}, ...],
            main_file:   "main.tex"
        }
    """
    proj_dir = Path(proj_dir)
    root = project_root or str(proj_dir)
    parser = LatexParser(root)

    # 1. 找到主文件
    main_tex = find_main_tex(proj_dir)
    if main_tex is None:
        return {"merged_text": "", "segments": [], "main_file": ""}

    # 2. 提取 preamble（\documentclass ... \begin{document}）
    main_raw = main_tex.read_text(encoding="utf-8", errors="replace")
    preamble = _extract_preamble(main_raw)

    # 3. 解析项目，拿到所有文件（DFS include 顺序）
    paper = parser.parse_project(main_tex)

    # 4. 拼接 merged_text：preamble + 子文件内容 + \end{document}
    return _build_merged(preamble, paper, proj_dir, main_tex.name)


def save_merged(proj_dir: str | Path, merged_text: str, segments: list[dict]) -> dict:
    """保存统一视图的修改，自动选策略。

    Returns:
        {"status": "ok", "strategy": "offset"|"structural", "updated": [...]}
    """
    proj_dir = Path(proj_dir)

    old = merge_project(proj_dir)
    len_diff = abs(len(merged_text) - len(old["merged_text"]))

    if len_diff < 1000 and segments:
        return _save_offset(proj_dir, merged_text, segments)
    else:
        return _save_structural(proj_dir, merged_text, segments)


# ═══════════════════════════════════════════════════════════
# 内部：合并
# ═══════════════════════════════════════════════════════════

def _build_merged(
    preamble: str, paper, proj_dir: Path, main_name: str
) -> dict:
    """拼装 merged_text 和 segments。

    结构：
      preamble (开头到 \\begin{document})
      + main_body（abstract/keywords/\\bibliography 等，去掉了 \\input 行）
      + 子文件内容（按 include 顺序）
      + \\end{document}
    main.tex 只占 1 个 segment，写回时重建（preamble + body + \\input 列表 + \\end{document}）。
    """
    main_tex = proj_dir / main_name
    main_raw = main_tex.read_text(encoding="utf-8", errors="replace")

    main_body = _extract_body_content(main_raw)
    # 收集 original \\input 列表（写回时用来重建 main.tex）
    input_lines = re.findall(r"\\input\{([^}]+)\}", main_raw)
    input_lines += re.findall(r"\\include\{([^}]+)\}", main_raw)

    parts = [preamble]
    segments = []
    offset = len(preamble) + 1

    # ── main.tex body ──
    if main_body.strip():
        _append_segment(parts, segments, main_name, main_body, proj_dir, offset)
        offset = sum(len(p) + 1 for p in parts)

    # ── 子文件（按 include 顺序）──
    body_files = [
        f for f in paper.files
        if Path(f).name != main_name and Path(f).suffix.lower() == ".tex"
    ]

    for file_path in body_files:
        path = Path(file_path)
        if not path.exists():
            continue

        content = path.read_text(encoding="utf-8", errors="replace")
        if not content.strip():
            continue

        try:
            rel = str(path.resolve().relative_to(proj_dir.resolve())).replace("\\", "/")
        except ValueError:
            rel = path.name

        _append_segment(parts, segments, rel, content, proj_dir, offset)
        offset = sum(len(p) + 1 for p in parts)

    # ── 收尾 ──
    parts.append(r"\end{document}")

    return {
        "merged_text": "\n".join(parts),
        "segments": segments,
        "main_file": main_name,
        "_input_list": [l.replace("\\", "/") for l in input_lines],  # 内部用
    }


def _extract_body_content(main_raw: str) -> str:
    """提取 main.tex body 内容：\\begin{document} 之后 / \\end{document} 之前的正文，
    去掉 \\input/\\include 行，保留 abstract、keywords、\\bibliography 等。"""
    m = re.search(r"\\begin\{document\}", main_raw)
    if not m:
        return ""

    doc_end = re.search(r"\\end\{document\}", main_raw)
    end_pos = doc_end.start() if doc_end else len(main_raw)

    body = main_raw[m.end():end_pos]
    # 去掉 \\input{...} 和 \\include{...} 行
    body = re.sub(r"\\input\{[^}]*\}\s*", "", body)
    body = re.sub(r"\\include\{[^}]*\}\s*", "", body)
    # 压缩多余空行
    body = re.sub(r"\n{3,}", "\n\n", body)

    return body.strip()


def _append_segment(
    parts: list, segments: list, file_name: str, content: str,
    proj_dir: Path, offset: int,
) -> None:
    """添加一个 segment 到 merged 构建中。"""
    sep = SEP_TEMPLATE.format(file_name)
    parts.append(sep + content)

    segments.append({
        "file": file_name,
        "start": offset + len(sep),
        "end": offset + len(sep) + len(content),
    })


# ═══════════════════════════════════════════════════════════
# 内部：保存 — offset 策略
# ═══════════════════════════════════════════════════════════

def _save_offset(proj_dir: Path, merged_text: str, segments: list[dict]) -> dict:
    """按 SOURCE 标记分割 merged_text，写回各 section 文件，
    然后调用 sync_main_tex 统一重建 main.tex + 清理孤儿文件。

    不依赖 segment 的 offset（用户编辑后可能位移），
    而是从 merged_text 中按 % === SOURCE: {file} === 切分。
    """
    marker_pattern = re.compile(r"\n% === SOURCE: (.+?) ===\n")

    # 按 SOURCE 标记分割
    parts = marker_pattern.split(merged_text)

    # parts[0] = preamble (everything before first SOURCE marker)
    # parts[1] = file1_name, parts[2] = file1_content
    # parts[3] = file2_name, parts[4] = file2_content
    # ... parts[-1] = trailing content after last chunk (\end{document})

    updated = []
    keep_stems: set[str] = set()

    i = 1
    while i + 1 < len(parts):
        file_name = parts[i].strip()
        content = parts[i + 1]

        # 安全检查（防止路径穿越）
        try:
            file_path = (proj_dir / file_name).resolve()
            file_path.relative_to(proj_dir.resolve())
        except ValueError:
            i += 2
            continue

        if _is_main_segment(proj_dir, file_name):
            # main.tex body — 不单独写文件，由 sync_main_tex 统一重建
            # 但保留 main.tex body 内容：写入 main.tex 供 sync_main_tex 读取
            # （sync_main_tex 从磁盘读 prefix/suffix 来重建）
            main_tex = find_main_tex(proj_dir)
            if main_tex:
                _write_main_body_only(main_tex, content)
            i += 2
            continue

        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        updated.append(file_name)
        keep_stems.add(Path(file_name).stem)
        i += 2

    # ── 统一重建 main.tex + 清理孤儿 ──
    sync_result = sync_main_tex(proj_dir, keep_stems=keep_stems)
    updated.append("main.tex")

    return {
        "status": "ok",
        "strategy": "offset",
        "updated": updated,
        "inputs": sync_result.get("inputs", []),
        "deleted": sync_result.get("deleted", []),
    }


def _write_main_body_only(main_tex: Path, body_content: str) -> None:
    """将 body 内容写回 main.tex，保留原始 preamble 和 \\end{document}。

    用于 offset 策略：用户在合并视图中修改了 main.tex 的 body 部分，
    只更新 body，不动 preamble 和 \\end{document}。
    """
    original = main_tex.read_text(encoding="utf-8", errors="replace") if main_tex.exists() else ""
    preamble = _extract_preamble(original)
    body = body_content.strip()

    # 去掉 body 末尾的 \\end{document}（如果有）
    end_doc = re.search(r"\\end\{document\}", body)
    if end_doc:
        body = body[: end_doc.start()].strip()

    main_tex.write_text(
        preamble.rstrip() + "\n\n" + body + "\n\n\\end{document}\n",
        encoding="utf-8",
    )


# ═══════════════════════════════════════════════════════════
# 内部：保存 — structural 策略（大改时走 Section 树 diff）
# ═══════════════════════════════════════════════════════════

def _save_structural(
    proj_dir: Path, merged_text: str, segments: list[dict]
) -> dict:
    """重新解析 merged_text → 匹配旧 Section 树 → 写回 + 重排文件 + 清理孤儿。

    最终调 sync_main_tex 统一重建 main.tex 并清理无引用文件。
    """
    parser = LatexParser(str(proj_dir))

    # 1. 清洗：去 source 标记 + 确保有 preamble
    clean = _clean_merged(merged_text)
    if r"\documentclass" not in clean:
        old = merge_project(proj_dir)
        old_preamble = _extract_preamble(old.get("merged_text", ""))
        clean = old_preamble + "\n" + clean
    if r"\end{document}" not in clean:
        clean += "\n\\end{document}"

    # 2. 写入临时文件解析
    tmp = proj_dir / "_merged_tmp.tex"
    tmp.write_text(clean, encoding="utf-8")
    try:
        result = parser.parse_file(str(tmp))
    finally:
        if tmp.exists():
            tmp.unlink()

    # 3. 单文件项目快速路径：直接写回 main.tex
    main_tex = find_main_tex(proj_dir)
    if main_tex is None:
        return {"status": "error", "message": "No main.tex found"}

    old_paper = parser.parse_project(main_tex)
    all_main = all(Path(s.file).name == main_tex.name for s in old_paper.all_sections)
    if all_main or len(old_paper.files) == 1:
        main_tex.write_text(clean, encoding="utf-8")
        return {"status": "ok", "strategy": "structural", "updated": [main_tex.name]}

    # 4. 多文件项目：Section 树匹配
    old_sections = old_paper.all_sections
    new_sections: list = []
    _flatten_sections(result.sections, new_sections)

    updated = _match_and_write(proj_dir, main_tex, old_sections, new_sections)

    return {"status": "ok", "strategy": "structural", "updated": updated}


def _match_and_write(
    proj_dir: Path,
    main_tex: Path,
    old_sections: list,
    new_sections: list,
) -> list[str]:
    """匹配新旧 Section 树，写回文件，删除被替换的旧文件。

    最后调 sync_main_tex 重建 main.tex 的 \\input 列表 + 清理孤儿。
    """
    old_by_title: dict[str, any] = {}
    for sec in old_sections:
        old_by_title[sec.title.lower().strip()] = sec

    updated = []
    keep_stems: set[str] = set()
    sections_dir = proj_dir / "sections"
    sections_dir.mkdir(parents=True, exist_ok=True)

    for new_sec in new_sections:
        title_key = new_sec.title.lower().strip()
        old_sec = old_by_title.get(title_key)

        if old_sec:
            # 匹配到旧节 → 原地位更新
            file_path = _resolve_section_file(old_sec, proj_dir)
            if file_path and file_path.exists():
                _update_section_in_file(file_path, old_sec, new_sec)
                rel = _relative_to(file_path, proj_dir)
            else:
                rel = f"sections/{_title_to_slug(old_sec.title)}.tex"
                file_path = proj_dir / rel
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(
                    f"\\section{{{new_sec.title}}}\n{new_sec.content}\n",
                    encoding="utf-8",
                )
            updated.append(rel)
            keep_stems.add(Path(rel).stem)
        else:
            # 新 Section → 创建文件
            slug = _title_to_slug(new_sec.title)
            new_file = sections_dir / f"{slug}.tex"
            new_file.write_text(
                f"\\section{{{new_sec.title}}}\n{new_sec.content}\n",
                encoding="utf-8",
            )
            rel = _relative_to(new_file, proj_dir)
            updated.append(rel)
            keep_stems.add(slug)

    # ── 删除未被匹配的旧 Section 文件 ──
    new_titles = {s.title.lower().strip() for s in new_sections}
    for sec in old_sections:
        if sec.title.lower().strip() not in new_titles:
            old_file = _resolve_section_file(sec, proj_dir)
            if old_file and old_file.exists():
                old_file.unlink()
                updated.append(f"[removed] {Path(sec.file).name} -> {sec.title}")

    # ── 统一重建 main.tex + 清理孤儿 ──
    sync_result = sync_main_tex(proj_dir, keep_stems=keep_stems)
    updated.insert(0, main_tex.name)

    # 合并 deleted 信息
    for name in sync_result.get("deleted", []):
        updated.append(f"[removed] {name}")

    return list(dict.fromkeys(updated))


def _update_section_in_file(file_path: Path, old_sec, new_sec) -> None:
    """在文件中原地更新某个 Section 的内容。"""
    if not file_path.exists():
        return

    content = file_path.read_text(encoding="utf-8", errors="replace")
    lines = content.split("\n")

    start = max(0, old_sec.line_start - 1)
    end = min(len(lines), old_sec.line_end)

    new_content = new_sec.content
    # 如果旧节有 \section{...} 命令，保留它
    section_cmd = ""
    for i in range(start, min(start + 3, len(lines))):
        if "\\section" in lines[i] or "\\subsection" in lines[i]:
            section_cmd = lines[i] + "\n"
            break

    new_lines = section_cmd.split("\n") + new_content.split("\n")
    lines = lines[:start] + [l for i, l in enumerate(new_lines) if l or i != len(new_lines) - 1] + lines[end:]
    file_path.write_text("\n".join(lines), encoding="utf-8")


# ═══════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════

def _extract_preamble(text: str) -> str:
    """提取 preamble：从开头到 \\begin{document} 为止。"""
    m = re.search(r"\\begin\{document\}", text)
    if m:
        return text[: m.end()]
    return ""


def _clean_merged(text: str) -> str:
    """清理 merged_text：去除 SOURCE 标记。"""
    return re.sub(r"\n?% === SOURCE: .+? ===\n?", "\n", text).strip()


def _flatten_sections(sections: list, out: list) -> None:
    """递归展平 Section 树为列表。"""
    for sec in sections:
        out.append(sec)
        _flatten_sections(sec.children, out)


def _title_to_slug(title: str) -> str:
    """标题 → 文件名 slug。"""
    slug = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff-]", "-", title.strip())
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug[:40] if slug else "untitled"


def _relative_to(path: Path, base: Path) -> str:
    """绝对路径 → 项目根相对路径。"""
    try:
        return str(path.resolve().relative_to(base.resolve())).replace("\\", "/")
    except ValueError:
        return path.name


def _is_main_segment(proj_dir: Path, file_name: str) -> bool:
    """判断 segment 是否属于主文件。"""
    if file_name in ("main.tex", "paper.tex"):
        return True
    f = proj_dir / file_name
    if f.exists():
        try:
            return "\\documentclass" in f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            pass
    return False


def _resolve_section_file(section, proj_dir: Path) -> Optional[Path]:
    """根据 Section.file 解析为绝对路径。"""
    if not section.file:
        return None
    path = Path(section.file)
    if path.is_absolute():
        return path
    # 相对于 proj_dir 解析
    candidate = proj_dir / path.name
    return candidate if candidate.exists() else None
