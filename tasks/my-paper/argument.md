# 论文论证结构

> 此文件由 B 组 Agent 流水线在生成论文时顺产产出，人工可修订。
> AI 阅读论文时不必重读全文——扫一眼就知道论证脉络。

## 全局论证链

<!-- 箭头表示论证推进方向 -->
问题定义 → 相关工作 → 提出方法 → 实验验证 → 结果讨论 → 结论

## Section 角色

<!-- 格式: section_id → 角色 (说明, 行号范围) -->
- sec:intro → 背景前提（行 1-45）
- sec:problem → 问题细化（行 46-89）
- sec:related → 相关工作（行 90-140）
- sec:method → 核心方法（行 141-280）
- sec:experiment → 实验验证（行 281-380）
- sec:discussion → 结果讨论（行 381-430）
- sec:conclusion → 结论（行 431-480）

## 论证关系

<!-- 格式: 源 → 目标 : 关系描述 -->
- sec:intro → sec:problem : "具体来说，我们关注以下问题"
- sec:problem → sec:method : "为解决上述问题，我们提出"
- sec:method → sec:experiment : "通过以下实验验证"
- sec:experiment → sec:discussion : "实验结果表明"
- sec:discussion → sec:conclusion : "综上所述"

## 写作风格锚点

<!-- AI 润色时的风格约束 -->
- 偏好短句，多用主动语态
- 实验描述用过去时，方法陈述用现在时
- 公式编号引用格式: 式(1)、式(2)
- 图表引用格式: 图1、表2
- 中文论文，英文术语首次出现时括号注原文
