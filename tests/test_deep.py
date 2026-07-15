"""深度功能测试 — request_svc + merge_svc + safe_boundary"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tempfile, shutil, json
from autolib.latex_parser import LatexParser
from autolib.doc_graph import DocGraph
from autolib.utils import find_main_tex
from server.services.request_svc import (
    write_request, _safe_boundary,
    _line_starts_in_command, _line_ends_in_command,
)
from server.services.merge_svc import merge_project, save_merged

passed = 0
failed = 0

def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  OK  {name}")
    else:
        failed += 1
        print(f"  FAIL {name}: {detail}")


# ============================================================
# 测试 1: _line_starts_in_command
# ============================================================
print("=== _line_starts_in_command ===")
check("上一行未闭合括号 -> 检测到切割",
      _line_starts_in_command("bold text}", "Some text \\textbf{") == True)
check("上一行正常 -> 不检测切割",
      _line_starts_in_command("Normal text", "Previous line.") == False)
check("本行以 } 开头 -> 命令已闭合",
      _line_starts_in_command("} and more text", "\\textbf{bold") == False)
check("本行以 % 开头 -> 注释",
      _line_starts_in_command("% comment", "\\textbf{bold") == False)
check("空行 -> 不检测",
      _line_starts_in_command("   ", "anything") == False)

print("\n=== _line_ends_in_command ===")
check("转义花括号不计入深度",
      _line_ends_in_command("text \\{escaped") == False)
check("未闭合花括号检测到",
      _line_ends_in_command("text {not closed") == True)
check("正常文本",
      _line_ends_in_command("normal text {closed}") == False)


# ============================================================
# 测试 2: _safe_boundary
# ============================================================
print("\n=== _safe_boundary ===")
d = Path(tempfile.mkdtemp())
proj = d / "test-paper"
proj.mkdir()
sections = proj / "sections"
sections.mkdir(parents=True)

# 向前扩展测试
intro = sections / "intro.tex"
intro.write_text(
    "Line 1: Normal text.\n"
    "Line 2: \\textbf{bold text spanning\n"
    "Line 3: two lines} and more.\n"
    "Line 4: After command.\n",
    encoding="utf-8",
)

sel = {"text": "two lines} and more.", "file": "sections/intro.tex",
       "section_title": "", "start_line": 3, "end_line": 3}
fixed = _safe_boundary(sel, proj)
check("向前扩展 start_line", fixed["start_line"] == 2,
      f"期望=2, 实际={fixed['start_line']}")

# 向后扩展测试
method = sections / "method.tex"
method.write_text(
    "Line 1: \\begin{itemize}\n"
    "Line 2: \\item with \\textbf{unclosed\n"
    "Line 3: bold text\n"
    "Line 4: } closing\n"
    "Line 5: \\end{itemize}\n",
    encoding="utf-8",
)

sel = {"text": "bold text", "file": "sections/method.tex",
       "section_title": "", "start_line": 3, "end_line": 3}
fixed = _safe_boundary(sel, proj)
check("向后扩展 end_line", fixed["end_line"] == 4,
      f"期望=4, 实际={fixed['end_line']}")

# 无需扩展的情况
sel = {"text": "Line 1: Normal text.", "file": "sections/intro.tex",
       "section_title": "", "start_line": 1, "end_line": 1}
fixed = _safe_boundary(sel, proj)
check("无需扩展时不改动 start", fixed["start_line"] == 1)
check("无需扩展时不改动 end", fixed["end_line"] == 1)


# ============================================================
# 测试 3: request_svc write_request
# ============================================================
print("\n=== write_request ===")

# 创建论文文件供 context 组装使用
main = proj / "main.tex"
main.write_text(r"""\documentclass{article}
\begin{document}
\section{Introduction}\label{sec:intro}
Intro text \cite{test2024}.
\section{Method}\label{sec:method}
Method \ref{sec:intro}.
\end{document}
""", encoding="utf-8")

bib = proj / "refs.bib"
bib.write_text(
    "@article{test2024,title={Test},author={A},year={2024},abstract={Abstract.}}",
    encoding="utf-8",
)

# B 组
path = write_request("test-paper", "B", {"topic": "Test", "outline": "1. Intro\n2. Method", "ref_count": 10})
req = json.loads(path.read_text(encoding="utf-8"))
check("B 组 topic", req["topic"] == "Test")
check("B 组 _meta", req["_meta"]["task"] == "generate")

# C 组
sel = {"text": "Intro text \\cite{test2024}.", "file": "main.tex",
       "section_title": "", "start_line": 4, "end_line": 4}
path = write_request("test-paper", "C", {"style": "academic"}, scope="selection", selection=sel)
req = json.loads(path.read_text(encoding="utf-8"))
check("C 组 _meta", req["_meta"]["task"] == "polish")

# D 组
path = write_request("test-paper", "D", {"focus": ["grammar"]}, scope="selection", selection=sel)
req = json.loads(path.read_text(encoding="utf-8"))
check("D 组 _meta", req["_meta"]["task"] == "lang_check")

# E 组
path = write_request("test-paper", "E", {"checkpoint": "draft_done", "trigger": "manual"})
req = json.loads(path.read_text(encoding="utf-8"))
check("E 组 checkpoint", req["checkpoint"] == "draft_done")


# ============================================================
# 测试 4: merge_svc
# ============================================================
print("\n=== merge_svc ===")
result = merge_project(proj)
check("merge_project merged_text", len(result["merged_text"]) > 0,
      f"len={len(result['merged_text'])}")
check("merge_project segments", len(result["segments"]) > 0)

saved = save_merged(proj, result["merged_text"], result["segments"])
check("save_merged offset", saved["status"] == "ok",
      f"status={saved['status']}")
check("save_merged 有更新", len(saved.get("updated", [])) > 0)


# ============================================================
# 测试 5: autolib 集成
# ============================================================
print("\n=== autolib ===")
found = find_main_tex(proj)
check("find_main_tex", found is not None and found.name == "main.tex")

parser = LatexParser(str(proj))
paper = parser.parse_project(found)
graph = DocGraph(paper, [str(bib)])
check("DocGraph cite_info", graph.cite_info("test2024") is not None)
check("DocGraph outline", len(graph.outline()) == 2)

shutil.rmtree(d)


# ============================================================
print(f"\n{'='*50}")
print(f"{passed}/{passed+failed} passed")
if failed:
    print(f"FAILED: {failed}")
    exit(1)
