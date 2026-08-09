# AutoResearch Skill 开发规范协议

> 版本 v1.0 | 最后更新 2026-07-20
> 本协议定义 nature-skill 的开发标准，确保所有 Skill 可被 E 组工作流引擎统一编排。

---

## 一、总则

nature-skill 是 AutoResearch 的能力单元。每个 Skill 是一个独立的 Claude Code Skill，遵循统一的目录结构、接口规范和注册机制。

**设计原则**：
- **单一职责**：一个 Skill 只做一件事，做好一件事
- **零代码修改集成**：复制到 `.claude/skills/` 即可使用
- **静态层 + 动态层分离**：可复用内容放 `static/`，路由逻辑放 `SKILL.md`
- **可编排**：通过 E 组 `SkillRegistry` 注册后可被工作流引擎自动调度

---

## 二、Skill 目录结构

```
.claude/skills/<skill-name>/
├── SKILL.md          # 必填：Skill 入口，含路由协议
├── manifest.yaml      # 必填：轴声明、文件映射、按需引用表
├── static/            # 必填：可复用的静态内容片段
│   └── core/          # 核心原则、工作流、失败模式
│       ├── stance.md
│       ├── workflow.md
│       └── failure-modes.md
├── references/        # 可选：深度参考资料
└── scripts/           # 可选：辅助脚本
```

---

## 三、SKILL.md 规范

### 3.1 文件头（Frontmatter）

```yaml
---
name: <skill-name>              # 唯一标识，kebab-case
version: <major.minor.patch>    # 语义化版本
description: >-                 # 一句话描述 + 触发词
  <功能描述>。
  Use when <触发场景>。
  Triggers: <触发词列表>。
---
```

### 3.2 路由协议

SKILL.md 正文必须包含以下 5 步路由协议：

```
1. Load manifest + always_load 文件
2. 检测请求的轴值（从 manifest 的 detect 提示 + 用户输入）
3. 加载匹配的 static/ 片段（只加载选中的，不加载全部）
4. 按优先级应用：paper_type → section → journal → language
5. 按需引用 references/（不设为默认加载）
```

### 3.3 触发词注册

触发词用于 E 组 `SkillRegistry.resolve_intent()` 的路由匹配。两类触发词：

| 类型 | 示例 | 说明 |
|------|------|------|
| 精确触发词 | "中大润色""SYSU style" | 专属 Skill 的唯一标识 |
| 通用触发词 | "润色""语言""polish" | 可能匹配多个 Skill，由优先级决定 |

---

## 四、manifest.yaml 规范

```yaml
version: "1.0"
skill: <skill-name>

always_load:              # 每次调用必读的文件
  - static/core/stance.md
  - static/core/workflow.md

axes:                     # 请求分类维度
  paper_type:
    detect: "从用户输入推断"
    values:
      research: static/paper-type/research.md
      review: static/paper-type/review.md

  language:
    detect: "从草稿文本检测"
    values:
      zh: static/lang/zh.md
      en: static/lang/en.md

references:
  on_demand:              # 仅在用户明确要求时加载
    phrasebank: references/academic-phrasebank.md
    layout: references/latex-layout.md
```

---

## 五、static/ 内容编写规范

### 5.1 核心文件

| 文件 | 内容 | 必须 |
|------|------|------|
| `core/stance.md` | Skill 的立场：做什么、不做什么、边界 | 是 |
| `core/workflow.md` | 操作流程：步骤序列、每步的输入输出 | 是 |
| `core/failure-modes.md` | 常见失败模式及修复策略 | 推荐 |

### 5.2 轴值文件

每个轴值对应一个文件，只包含该值相关的规则：

- `paper-type/research.md`：研究型论文的写作策略
- `lang/zh.md`：中文论文特有的规则（"的/地/得"、全角标点）
- `journal/nature.md`：Nature 期刊特有要求

### 5.3 编写原则

1. **每条规则可独立验证**：不是"写得好一点"，而是"Methods 使用过去时"
2. **有反例**：每条规则配一个坏例子和一个好例子
3. **不冗余**：不重复其他文件已有的内容
4. **版本化**：重大修改更新文件名或 frontmatter version

---

## 六、注册到 E 组 SkillRegistry

在 `modules/e_workflow/__init__.py` 的 `SkillRegistry._register_all()` 中添加：

```python
S("sysu-polish", "1.0.0",
  "中山大学学位论文润色: 基于 nature-polishing，叠加中大学位论文格式规范",
  "polish",                              # category
  ["draft_done", "polish_done"],         # triggers_on（哪些 checkpoint 触发）
  "润色后的中大格式合规论文",              # produces
  ["G1", "G2", "G3", "G4", "G5", "G6"], # 关联 Gate
),
```

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| name | str | 与 SKILL.md frontmatter 的 name 一致 |
| version | str | 语义化版本号 |
| description | str | 一句话功能描述 |
| category | str | research / draft / polish / review / output / support |
| triggers_on | list[str] | 哪些 checkpoint 触发此 Skill |
| produces | str | 产出描述，供下游 Skill 判断依赖 |
| gates | list[str] | 关联的质量 Gate（G1-G6） |

---

## 七、测试要求

提交 Skill 前必须通过以下检查：

- [ ] `SKILL.md` frontmatter 完整（name, version, description）
- [ ] 目录结构符合规范（SKILL.md + manifest.yaml + static/core/）
- [ ] 所有 `manifest.yaml` 中引用的文件路径存在
- [ ] 所有 `always_load` 文件内容非空
- [ ] 触发词不与已有 Skill 产生歧义冲突
- [ ] 在 E 组 `SkillRegistry` 中注册后，`resolve_intent()` 能正确路由
- [ ] 至少通过一个有真实论文内容的端到端测试

---

## 八、开发者承诺

点击"同意"即表示您确认：

> 我开发的 nature-skill 遵循本规范定义的目录结构、接口标准和注册机制。
> 我的 Skill 不包含硬编码的 API Key、密码或其他敏感信息。
> 我的 Skill 的 static/ 内容为原创或符合引用来源的许可协议。
