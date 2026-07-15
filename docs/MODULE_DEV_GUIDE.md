# 模块开发指南 — 写给 B/C/D/E 组

> 这是你的入口文档。读完它，你就能开始写自己的模块了 —— 不需要通读整个项目。

---

## 一、你在哪一组？

找到你的组，打开对应的文件：

| 组 | 职责 | 你需要改的唯一文件 |
|:--:|------|:--|
| B | Agent 流水线 + 文献检索，生成论文初稿 | `modules/b_agent/__init__.py` |
| C | 润色引擎（学术风格 / 精简 / 流畅） | `modules/c_polish/__init__.py` |
| D | 语法 / 拼写 / 风格检查 | `modules/d_lang_check/__init__.py` |
| E | 工作流状态机（阶段推进） | `modules/e_workflow/__init__.py` |

**你只需要改这一个文件。** 前端、后端路由、API 已经全部对接好。

---

## 二、框架帮你干了什么

下面这些事你不用操心：

- **多文件合成单文档** —— merged view 把多个 `.tex` 拼成一篇完整论文
- **写入自动保持一致性** —— 编辑后保存，框架自动拆回正确文件
- **LaTeX 解析和引用追踪** —— `\section`、`\cite`、`\ref`、`\label` 全自动解析
- **编译和 Git 版本控制** —— 每次编辑自动 commit，xelatex 已配置好
- **上下文自动组装** —— 你读到的 `context` 已经是框架按分层策略拼好的

**一句话：数据层的事你不用管。你的模块只管"收到请求 → 调用 AI → 返回输出"。**

---

## 三、你的任务：从 request.json 读取，实现 run()

### 3.1 运行机制

用户点击按钮 → 后端写入 `tasks/{项目名}/{你的组}/request.json` → 调用你的 `run(paper_dir)` → 你的函数读 request.json，干完活，返回结果。

```
tasks/my-paper/
├── B/
│   └── request.json    ← B 组读取这个
├── C/
│   └── request.json    ← C 组读取这个
├── D/
│   └── request.json    ← D 组读取这个
├── E/
│   └── request.json    ← E 组读取这个
├── main.tex
├── refs.bib
└── sections/
```

**所有组的 `run()` 签名统一：** `def run(paper_dir: str, progress=None) -> dict | str | list[dict]`。参数只有 `paper_dir` 和可选的 `progress` 回调，任务详情从自己组的 `request.json` 里读。

### 3.2 request.json 结构

完整 schema 见 `docs/request-schema.md`。这里列最终版：

**B 组** — `tasks/{project}/B/request.json`
```json
{
  "_meta": { "task": "generate", "project": "my-paper", "paper_dir": "...", "created_at": "..." },
  "topic": "论文主题（必填）",
  "outline": "大纲结构（自由文本）",
  "ref_domains": ["关键词1", "关键词2"],
  "ref_count": 15,
  "constraints": "IEEE 格式，英文，8 页",
  "intent": "用户补充意图"
}
```

**C 组** — `tasks/{project}/C/request.json`
```json
{
  "_meta": { "task": "polish", "project": "my-paper", "scope": "selection", "paper_dir": "...", "created_at": "..." },
  "selection": {
    "text": "用户选中的 LaTeX 原文（scope=selection 时存在）",
    "file": "sections/intro.tex",
    "section_title": "Introduction",
    "start_line": 12,
    "end_line": 18
  },
  "context": "框架组装的上下文包（自动填充，可直接拼进 prompt）",
  "style": "academic",
  "intent": "改得更学术化"
}
```

`scope` 为 `"full"` 时 `selection` 为 `null`，`context` 为论文骨架。

**D 组** — `tasks/{project}/D/request.json`
```json
{
  "_meta": { "task": "lang_check", "project": "my-paper", "scope": "selection", "paper_dir": "...", "created_at": "..." },
  "selection": { "text": "...", "file": "...", "start_line": 45, "end_line": 52 },
  "context": "框架组装的上下文包（自动填充）",
  "focus": ["grammar", "tense"],
  "intent": "重点查时态一致性"
}
```

`scope` 同 C 组。`focus` 可选值：grammar / spelling / tense / logic / style，空数组 = 全查。

**E 组** — `tasks/{project}/E/request.json`
```json
{
  "_meta": { "task": "workflow", "project": "my-paper", "paper_dir": "...", "created_at": "..." },
  "checkpoint": "draft_done",
  "trigger": "manual",
  "intent": "推进到润色阶段"
}
```

### 3.3 各组的返回格式

| 组 | `run(paper_dir)` 返回类型 |
|:--:|:--|
| B | `dict` — `{"status": "ok", "files": ["sections/intro.tex", ...]}` |
| C | `str` — 润色后的文本，保留原有 LaTeX 命令 |
| D | `list[dict]` — `[{"type": "grammar", "line": 1, "message": "...", "fix": "..."}, ...]` |
| E | `dict` — `{"next": "polish", "done": [...], "notes": "..."}` |

### 3.4 progress 回调

各组 `run()` 的第二个参数 `progress` 是可选回调：`progress(stage: str, message: str, percent: int) -> None`。

调用它即可向前端 SSE 推送进度（如 `progress("generating", "生成 Introduction", 45)`）。不调用也没关系，前端会在 done/error 时才展示结果。

### 3.5 读取 request.json 的代码模板

```python
import json
from pathlib import Path

def run(paper_dir: str):
    proj_dir = Path(paper_dir)
    req_path = proj_dir / "C" / "request.json"   # 改成你的组
    req = json.loads(req_path.read_text(encoding="utf-8"))

    text = req["selection"]["text"]      # C/D 组取原文
    context = req["context"]             # 上下文包，直接拼进 prompt
    intent = req["intent"]               # 用户指令
    # ...
```

**context 实际样例**（C/D 组，框架自动填入）：

```
# 当前段落 (Introduction)

The field of large language models has seen rapid advancement. However, long-range
document generation remains an open challenge \cite{prism2025}\cite{llama2023}.

# 结构上下文
位置: Introduction
所属节: Introduction
父节引用: 2 篇文献, 0 个交叉引用
兄弟节: Related Work, Proposed Method

# 引用上下文

引用文献:
- [prism2025] PRISM: Efficient Long-Range Document Generation with Structured Memory
  Zhang, Wei, Li, Ming (2025)
  We present PRISM, a novel approach for efficient long-range document generation...

交叉引用:
- \ref{sec:method} → Proposed Method: A three-layer architecture is designed to...
```

---

## 四、你可以调用的工具

### 4.1 文档知识图谱

```python
from autolib.doc_graph import DocGraph
from autolib.latex_parser import LatexParser

parser = LatexParser(paper_dir)
paper = parser.parse_project("main.tex")
graph = DocGraph(paper, ["refs.bib"])
```

```python
# 引用查询
graph.cite_info("prism2025")           # cite key → 文献元数据
graph.ref_target("sec:method")         # \ref → 目标 Section
graph.ref_backlinks("sec:method")      # 谁引用了这个 label

# 结构导航
graph.section_neighbors("sec:method")   # {prev, next, parent, siblings, path}
graph.outline()                         # 全文 Section 树轮廓
graph.locate("sections/intro.tex", 45)  # 行号 → Section

# 引用上下文
graph.expand_context(section)           # 一键拉引用摘要

# 健康检查
graph.broken_refs()                     # 悬空引用
graph.uncached_cites()                  # 缺 bib 的 cite
```

### 4.2 上下文格式化

```python
from server.services.context_svc import build_context, read_argument, sample_peers

ctx = build_context(section, graph, layers=["L1","L2","L3"], max_tokens=6000, project_dir=proj_dir)
arg = read_argument(proj_dir)                   # 读 argument.md
peers = sample_peers(section, graph, k=3)       # 风格采样
```

### 4.3 论文下载

```python
from autolib.arxiv_downloader import download_paper
from autolib.paper_cache import PaperCache

download_paper("2412.18914")           # 下载 arXiv PDF
PaperCache().check("arxiv", "2412.18914")  # 查缓存
```

---

## 五、※ autolib/ 只读，不要修改

```
autolib/          ← 框架核心，各组公用
  latex_parser.py
  doc_graph.py
  paper_cache.py
  arxiv_downloader.py
```

**修改 autolib/ 里的任何文件 → 所有人的环境一起炸。**

需要新功能（缺某种 LaTeX 结构、知识图谱缺某个查询接口），**找同学 A，他来加。**

同理，**不要修改** `server/`、`frontend/index.html`。

---

## 六、.tex 文件组的正确操作方式

```
tasks/my-paper/
├── main.tex              ← 骨架（documentclass + preamble + \input 列表）
├── argument.md           ← 论证结构（AI 上下文）
├── refs.bib              ← 共享文献库
└── sections/
    ├── intro.tex
    ├── method.tex
    └── results.tex
```

**读：** 随便读。用 `LatexParser` + `DocGraph` 查询。

**写：** 走框架 API。前端保存会经 merged view → offset/structural 拆分。**不要直接 fopen 修改 .tex 文件**。

**B 组产出 .tex 规范：**

1. **label 命名：** `sec:xxx` / `fig:xxx` / `tab:xxx` / `eq:xxx`
2. **cite key 对齐 refs.bib**。用 `graph.uncached_cites()` 检查
3. **别改 main.tex 的 preamble。** 新增宏包写在交付清单里
4. **section 文件命名：** 小写英文 + 连字符，如 `related-work.tex`

---

## 七、交付清单

`run()` 写完后，在文件顶部的 docstring 里填：

```python
"""
X 组 — 功能名称

### 功能说明
（简要描述做了什么）

### 外部依赖
- API: OpenAI GPT-4o / DeepSeek / ...（需要什么 key）
- Python 包: 新增依赖写在这里

### 产出影响
- 涉及的 .tex section:
- 引用关系:
- 涉及 refs.bib: 是 / 否

### 新增 LaTeX 宏包
- （如有）
"""
```

---

## 附录：快速自测

```bash
cd AutoResearch
pip install -r requirements.txt
uvicorn server.main:app --reload --host 0.0.0.0 --port 8000
# 浏览器打开 http://127.0.0.1:8000
```

打开 `frontend/index.html`，选择论文项目：
- **B 组：** 点 "B: 生成" → 看返回的文件列表
- **C 组：** 选中文字 → "C: 润色" → diff 预览
- **D 组：** 选中文字 → "D: 检查" → 问题列表
- **E 组：** POST `/api/request/E`（前端按钮待加）

