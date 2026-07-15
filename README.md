# AutoResearch

AI 驱动的学术论文协作写作平台。基于 LaTeX，通过解析器提取论文结构 → 模块化 Agent 流水线处理 → Web 编辑器统一视图。

## 架构

```
autolib/          ← 核心引擎（LaTeX 解析、知识图谱、缓存）
modules/          ← AI 处理模块（B/C/D/E 组，各自实现）
server/           ← FastAPI 后端（路由 + 服务）
frontend/         ← Web 编辑器（单 HTML 文件）
tasks/            ← 论文项目仓库（每篇论文一个目录）
cache/            ← 论文 PDF 缓存
```

## 快速开始

```bash
pip install -r requirements.txt
uvicorn server.main:app --reload --host 0.0.0.0 --port 8000
# 浏览器打开 http://127.0.0.1:8000
```

打开 `frontend/index.html`（或挂到 static 路由）。

## 核心模块

### autolib — 文档解析引擎

| 模块 | 功能 |
|---|---|
| `latex_parser.py` | LaTeX 结构化解析。从 `.tex` 源码提取 Section 树、label、cite、ref，支持多文件项目（`\input`/`\include` 递归），带容错和行号定位。依赖 `pylatexenc` 做 AST 分析。 |
| `doc_graph.py` | 文档知识图谱。在 Section 树之上建索引：cite key → BibTeX 元数据、label → 反向引用、兄弟节导航、光标定位（文件+行号→Section）、论文骨架轮廓。O(1) 查询，不依赖 AI。 |
| `context_svc.py` | 上下文格式化服务。分层组装（L1 当前段落 / L2 结构上下文 / L3 引用摘要 / L4 风格采样 / L5 论文骨架），带 token 预算控制，给 AI 提供精准定位的上下文包。位于 `server/services/context_svc.py`。 |
| `paper_cache.py` | 论文 PDF 缓存管理器。文件系统-based，进程内单例。 |
| `arxiv_downloader.py` | ArXiv 论文下载器。给定 ID → 下载 PDF → 缓存。 |

### modules — AI 处理模块

四组各自实现自己的处理逻辑，对外暴露单一入口函数：

| 模块 | 入口 | 状态 | 职责 |
|---|---|---|---|
| `b_agent` | `run(paper_dir, instruction)` | stub | Agent 流水线 + 文献检索，生成论文初稿 |
| `c_polish` | `run(text, context, style)` | stub | 润色引擎（学术风格/精简/流畅） |
| `d_lang_check` | `run(text)` | stub | 语法/拼写/风格检查 |
| `e_workflow` | `run(paper_dir, checkpoint)` | stub | 工作流状态机（阶段推进） |

### server — API 层

| 路由 | 端点 | 功能 |
|---|---|---|
| `projects.py` | `GET/POST/DELETE /api/projects` | 项目管理（列/建/删） |
| `papers.py` | `GET /api/papers/{name}/tree` | 文件树 |
| | `GET/PUT /api/papers/{name}/file` | 文件读写 |
| | `POST /api/papers/{name}/generate` | B 组生成初稿 |
| | `GET /api/papers/{name}/merged` | **合并视图**（多文件→单文档） |
| | `PUT /api/papers/{name}/merged` | **保存合并视图**（自动 offset/structural 策略） |
| `edit.py` | `POST /api/edit/preview` | 选中段落 → 润色/检查 → diff 预览 |
| | `POST /api/edit/apply` | 确认修改 → 写回文件 + git commit |
| `compile.py` | `POST /api/compile/{name}` | xelatex 编译 PDF |
| | `GET /api/compile/{name}/pdf` | 获取 PDF |

### server/services — 后端服务

| 模块 | 功能 |
|---|---|
| `merge_svc.py` | 统一文档视图：多文件合并展示 + 双策略保存（offset/structural） |
| `context_svc.py` | AI 上下文组装 |
| `compile_svc.py` | LaTeX 编译（xelatex，自动处理交叉引用） |
| `git_svc.py` | Git 版本管理（commit/log/diff/revert） |

## 统一文档视图

核心创新：前端展示一篇完整文档，背后由多个 `.tex` 文件组成。

### 展示

```
GET /api/papers/{name}/merged
→ { merged_text, segments, main_file }

物理文件                        用户看到
main.tex (preamble)     ┐
sections/intro.tex      ├──→  [一篇完整文档，可滚动编辑]
sections/method.tex     │    % === SOURCE 标记透明分隔
sections/results.tex   ┘
```

### 保存策略

- **Offset**（改动 < 1000 字符）：按 SOURCE 标记切分 → 写回原文件，毫秒级
- **Structural**（改动 ≥ 1000 字符或结构变化）：重新 parse Section 树 → 匹配旧节 → 新建/更新/删除文件 → 重建 `main.tex` 的 `\input` 列表

## 论文项目结构

```
tasks/my-paper/
├── main.tex              # 入口：preamble + \input 列表 + \end{document}
├── argument.md           # 论证结构（可选，AI 上下文用）
├── refs.bib              # 参考文献
├── sections/
│   ├── intro.tex
│   ├── method.tex
│   └── results.tex
└── build/
    └── main.pdf          # 编译产物
```

## 工作流

```
创建项目 → [B 组生成初稿] → 编辑器编辑
→ 选中段落 → [C 组润色 / D 组检查] → diff 预览 → accept/reject
→ [E 组管理阶段] → xelatex 编译 → 输出 PDF
```

每一步自动 git commit，可追溯回退。

## 技术栈

- **后端**: Python 3.12+ / FastAPI / pylatexenc
- **前端**: 原生 HTML/CSS/JS（暗色主题，代码编辑器 + diff 面板）
- **编译**: xelatex（需安装 MiKTeX 或 TeX Live）
- **版本控制**: Git

## 已知限制

- B/C/D/E 模块为 stub，需接入 LLM API（如 OpenAI/Claude）
- structural 策略在复杂 Section 重组场景可能不够精确
- 合并视图的 SOURCE 标记区域不可编辑（~35 字符分隔符）
- 仅支持单论文项目编辑，不支持多项目并行
