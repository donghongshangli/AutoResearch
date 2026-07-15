# B/C/D/E 组 request.json Schema

> 每个 task 下按需创建 B/C/D/E 文件夹，用户请求写入 `request.json`（新覆旧）。
> 各组模块从其对应的 request.json 读取任务信息。

**`_meta` 通用字段（所有组共用，框架自动填入）：**

| 字段 | 类型 | 说明 |
|:--|:--|:--|
| `task` | string | 操作类型：generate / polish / lang_check / workflow |
| `project` | string | 当前论文项目名（tasks/ 下的文件夹名，前端自动取） |
| `paper_dir` | string | 项目目录绝对路径 |
| `created_at` | string | ISO 时间戳 |
| `scope` | string | 仅 C/D 组有：selection / full |

> **`project` 自动从当前打开的项目获取。如果用户未打开任何项目就点击 B/C/D/E 按钮，前端弹窗提示"请先选择/创建项目"。**


---

## B 组 — 生成初稿

**文件：** `tasks/{project}/B/request.json`

```json
{
  "_meta": {
    "task": "generate",
    "project": "my-paper",
    "paper_dir": "tasks/my-paper",
    "created_at": "2026-07-13T02:00:00"
  },
  "topic": "string (必填) — 论文主题 / 标题",
  "outline": "string (可选) — 大纲结构，自由文本描述各 section 要写什么",
  "ref_domains": ["array", "of", "strings (可选) — 参考文献领域 / 关键词偏好"],
  "ref_count": 0,
  "constraints": "string (可选) — 格式 / 页数 / 语言等约束",
  "intent": "string (可选) — 用户补充意图"
}
```

| 字段 | 类型 | 必填 | 说明 |
|:--|:--|:--:|:--|
| `_meta` | object | ✅ | 框架自动填入 |
| `topic` | string | ✅ | 论文主题 |
| `outline` | string | | 大纲结构（自由文本） |
| `ref_domains` | string[] | | 文献检索关键词 |
| `ref_count` | int | | 期望引用数量（默认 10） |
| `constraints` | string | | 格式/页数/语言等约束 |
| `intent` | string | | 补充意图 |

**示例：**
```json
{
  "_meta": {
    "task": "generate",
    "project": "my-paper",
    "paper_dir": "tasks/my-paper",
    "created_at": "2026-07-13T02:00:00"
  },
  "topic": "基于上下文感知的多智能体论文写作框架",
  "outline": "1. Introduction\n2. Related Work\n3. Methodology\n4. Experiments\n5. Conclusion",
  "ref_domains": ["large language models", "multi-agent systems"],
  "ref_count": 15,
  "constraints": "IEEE 格式，英文，正文不超过 8 页",
  "intent": "重点突出模块化 Agent 设计"
}
```


---

## C 组 — 润色

**文件：** `tasks/{project}/C/request.json`

```json
{
  "_meta": {
    "task": "polish",
    "project": "my-paper",
    "scope": "selection | full",
    "paper_dir": "tasks/my-paper",
    "created_at": "2026-07-13T02:00:00"
  },
  "selection": {
    "text": "string — 用户选中原文（scope=selection 时必填）",
    "file": "string — 所在 tex 文件",
    "section_title": "string — 所在 section",
    "start_line": 0,
    "end_line": 0
  },
  "context": "string — 框架拼装的上下文包（自动填入）",
  "style": "academic | concise | fluent",
  "intent": "string — 用户补充意图"
}
```

| 字段 | 类型 | 必填 | 说明 |
|:--|:--|:--:|:--|
| `_meta` | object | ✅ | 框架自动填入。`scope`=selection 表示段落润色，full 表示全文 |
| `selection` | object | scope=selection 时必填 | 选中文本及其定位 |
| `selection.text` | string | ✅ | 用户选中的 LaTeX 原文 |
| `selection.file` | string | ✅ | 所在 .tex 文件路径 |
| `selection.section_title` | string | | 所在 Section 标题 |
| `selection.start_line` | int | ✅ | 起始行号 |
| `selection.end_line` | int | ✅ | 结束行号 |
| `context` | string | ✅ | 框架自动拼装的上下文包 |
| `style` | string | | academic / concise / fluent |
| `intent` | string | | 补充意图 |

**示例（段落润色）：**
```json
{
  "_meta": {
    "task": "polish",
    "project": "my-paper",
    "scope": "selection",
    "paper_dir": "tasks/my-paper",
    "created_at": "2026-07-13T02:00:00"
  },
  "selection": {
    "text": "The transformer architecture has been widely used...",
    "file": "sections/intro.tex",
    "section_title": "Introduction",
    "start_line": 12,
    "end_line": 18
  },
  "context": "# 当前段落 (Introduction)\n\n...\n# 结构上下文\n...",
  "style": "academic",
  "intent": "改得更学术化，减少口语表达，保持原有引用不变"
}
```

**示例（全文润色）：**
```json
{
  "_meta": {
    "task": "polish",
    "project": "my-paper",
    "scope": "full",
    "paper_dir": "tasks/my-paper",
    "created_at": "2026-07-13T02:00:00"
  },
  "selection": null,
  "context": "# 论文结构\n- Introduction (1,234 字符)\n- Related Work (2,567 字符)\n...",
  "style": "academic",
  "intent": "全文润色，统一学术风格"
}
```


---

## D 组 — 语言检查

**文件：** `tasks/{project}/D/request.json`

```json
{
  "_meta": {
    "task": "lang_check",
    "project": "my-paper",
    "scope": "selection | full",
    "paper_dir": "tasks/my-paper",
    "created_at": "2026-07-13T02:00:00"
  },
  "selection": {
    "text": "string — 用户选中原文（scope=selection 时必填）",
    "file": "string",
    "section_title": "string",
    "start_line": 0,
    "end_line": 0
  },
  "context": "string — 框架拼装的上下文包（自动填入）",
  "focus": ["grammar", "spelling", "tense", "logic"],
  "intent": "string — 用户补充意图"
}
```

| 字段 | 类型 | 必填 | 说明 |
|:--|:--|:--:|:--|
| `_meta` | object | ✅ | 同 C 组 |
| `selection` | object | scope=selection 时必填 | 同 C 组 |
| `context` | string | ✅ | 框架自动拼装 |
| `focus` | string[] | | 检查重点，可选值：grammar / spelling / tense / logic / style。空数组或省略 = 全查 |
| `intent` | string | | 补充意图 |

**示例：**
```json
{
  "_meta": {
    "task": "lang_check",
    "project": "my-paper",
    "scope": "selection",
    "paper_dir": "tasks/my-paper",
    "created_at": "2026-07-13T02:00:00"
  },
  "selection": {
    "text": "The results shows that our method...",
    "file": "sections/experiment.tex",
    "section_title": "Results",
    "start_line": 45,
    "end_line": 52
  },
  "context": "# 当前段落 (Results)\n\n...",
  "focus": ["grammar", "tense"],
  "intent": "重点查时态一致性和主谓一致"
}
```


---

## E 组 — 工作流

**文件：** `tasks/{project}/E/request.json`

```json
{
  "_meta": {
    "task": "workflow",
    "project": "my-paper",
    "paper_dir": "tasks/my-paper",
    "created_at": "2026-07-13T02:00:00"
  },
  "checkpoint": "string — 当前阶段标识",
  "trigger": "manual | auto",
  "intent": "string — 用户补充意图"
}
```

| 字段 | 类型 | 必填 | 说明 |
|:--|:--|:--:|:--|
| `_meta` | object | ✅ | 框架自动填入 |
| `checkpoint` | string | ✅ | 当前阶段，如 draft_done / polish_done / check_done |
| `trigger` | string | | manual（手动推进）/ auto（自动检测） |
| `intent` | string | | 补充意图 |

**示例：**
```json
{
  "_meta": {
    "task": "workflow",
    "project": "my-paper",
    "paper_dir": "tasks/my-paper",
    "created_at": "2026-07-13T02:00:00"
  },
  "checkpoint": "draft_done",
  "trigger": "manual",
  "intent": "B 组已生成初稿，推进到润色阶段"
}
```
