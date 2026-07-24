"""
models.py — Writefull API 数据模型 + 内部 DTO

严格对齐 Writefull API 返回格式（任务拆解 P9 + P30）:

  Writefull Language API 返回:
    {
      "suggestions": [
        {
          "start": int,       // 字符偏移起点 (0-based)
          "end": int,         // 字符偏移终点
          "original": str,    // 原文片段
          "replacement": str, // 修改建议
          "type": str,        // 错误类型: grammar | spelling | punctuation | style | phrasing
          "reason": str       // 修改原因（英文）
        }
      ],
      "quality_score": float  // 0.0-1.0 整体语言质量评分
    }

  Writefull Academizer API 返回:
    {
      "academized_text": str,       // 学术风格转换后文本
      "changes": [                  // 逐条变更记录
        {
          "original": str,
          "replacement": str,
          "rationale": str          // 转换理由
        }
      ],
      "discipline": str,            // 学科标签
      "style_strength": str         // 转换强度: light | moderate | heavy
    }

内部 DTO（前端契约）:
  CheckResult: {type, line, message, fix}  — 见 frontend/index.html:1128

用法:
    from modules.d_lang_check.models import (
        LanguageFeedbackResponse, Suggestion,
        AcademizerResponse, AcademizerChange,
        CheckResult,
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ═══════════════════════════════════════════════════════════════
# Writefull API 数据模型
# ═══════════════════════════════════════════════════════════════

@dataclass
class Suggestion:
    """Writefull Language API 返回的单条修改建议。"""
    start: int
    """字符偏移起点 (0-based, inclusive)"""
    end: int
    """字符偏移终点 (0-based, exclusive)"""
    original: str
    """原文片段"""
    replacement: str
    """Writefull 建议的替换文本"""
    type: str
    """错误类型: grammar | spelling | punctuation | style | phrasing"""
    reason: str
    """修改原因说明（英文）"""
    confidence: float = 1.0
    """Writefull 给的置信度 (0.0-1.0)"""


@dataclass
class LanguageFeedbackResponse:
    """Writefull Language API 完整响应。"""
    suggestions: list[Suggestion] = field(default_factory=list)
    quality_score: float = 0.0
    """整体语言质量评分 (0.0-1.0)"""
    word_count: int = 0
    """处理的文本词数"""
    model_version: str = ""
    """Writefull 模型版本标识"""


@dataclass
class AcademizerChange:
    """Writefull Academizer API 返回的单条变更。"""
    original: str
    replacement: str
    rationale: str = ""
    """转换理由（英文）"""


@dataclass
class AcademizerResponse:
    """Writefull Academizer API 完整响应。"""
    academized_text: str
    """学术风格转换后的文本"""
    changes: list[AcademizerChange] = field(default_factory=list)
    """逐条变更记录"""
    discipline: str = "general"
    """学科标签: computer-science | biology | medicine | physics | general"""
    style_strength: str = "moderate"
    """转换强度: light | moderate | heavy"""


# ═══════════════════════════════════════════════════════════════
# 内部 DTO — 前端契约
# ═══════════════════════════════════════════════════════════════

@dataclass
class CheckResult:
    """单条检查结果。前端渲染契约: {type, line, message, fix}。

    前端代码 (frontend/index.html:1128-1134):
        issues.map(iss =>
          `<span>#${i+1} L${iss.line}: ${iss.message}</span>
           ${iss.fix ? `<div>-> ${iss.fix}</div>` : ''}`
        )
    """
    type: str
    """检查维度: grammar | spelling | tense | logic | style"""
    line: int
    """行号 (1-based)"""
    message: str
    """问题描述（中文）"""
    fix: str = ""
    """建议修正文本"""
    severity: str = "warning"
    """严重程度: error | warning | info"""
    rule_id: str = ""
    """来源标识: writefull:xxx | mock:xxx | backup:xxx"""


# ═══════════════════════════════════════════════════════════════
# 格式转换工具
# ═══════════════════════════════════════════════════════════════

def suggestion_to_check_result(sug: Suggestion, text: str, source: str = "writefull") -> CheckResult:
    """将 Writefull API 返回的 Suggestion 转为前端 CheckResult 格式。

    定位策略:
      - 如果 start/end 有效（>0），则按字符偏移计算行号
      - 如果 start/end 无效（=0），则尝试在原文中搜索 original 文本来定位
    """
    if sug.start > 0 and sug.end > sug.start:
        line = text[:sug.start].count('\n') + 1
    elif sug.original:
        pos = text.find(sug.original)
        line = text[:pos].count('\n') + 1 if pos >= 0 else 1
    else:
        line = 1

    # Writefull type → 前端 type
    type_map = {
        "grammar": "grammar",
        "spelling": "spelling",
        "tense": "tense",
        "style": "style",
        "logic": "logic",
        "punctuation": "style",
    }
    frontend_type = type_map.get(sug.type, "style")

    # severity: grammar/spelling = error, logic/tense = warning, style/punctuation = info
    severity_map = {
        "grammar": "error", "spelling": "error",
        "tense": "warning", "logic": "warning",
        "style": "info", "punctuation": "info",
    }

    return CheckResult(
        type=frontend_type,
        line=line,
        message=sug.reason,
        fix=sug.replacement,
        severity=severity_map.get(sug.type, "warning"),
        rule_id=f"{source}:{sug.type}",
    )


def check_results_to_frontend(results: list[CheckResult]) -> list[dict]:
    """将 CheckResult 列表转为前端 JSON 格式。"""
    return [
        {
            "type": r.type,
            "line": r.line,
            "message": r.message,
            "fix": r.fix,
        }
        for r in results
    ]


# ═══════════════════════════════════════════════════════════════
# 标题 & 摘要生成数据模型
# ═══════════════════════════════════════════════════════════════

@dataclass
class TitleCandidate:
    """单条候选标题。

    标题生成一次性输出 5 个不同侧重点的候选（任务拆解 P16）:
      - method:     方法突出型 — 突出技术创新点
      - conclusion: 结论突出型 — 突出研究发现
      - question:   疑问句式 — 引发读者思考
      - concise:    简洁型 — 最短直接表达
      - descriptive: 描述型 — 全面描述研究工作
    """
    text: str
    """标题文本"""
    focus: str
    """侧重点类型: method | conclusion | question | concise | descriptive"""
    rationale: str = ""
    """为什么生成这个标题（英文，简短）"""


@dataclass
class AbstractResult:
    """B-M-R-C 结构化摘要生成结果（任务拆解 P16）。

    B-M-R-C 四要素强制引导算法:
      - Background:  这篇论文解决什么前沿问题？
      - Methods:     用了什么创新技术路线？
      - Results:     核心实验数据是什么？
      - Conclusion:  有什么理论或应用价值？

    核心约束: 禁止虚构未在原文中出现的数据（任务拆解 P30）。
    """
    abstract: str = ""
    """完整摘要文本（B-M-R-C 拼接）"""
    background: str = ""
    """B 段落: 研究背景与前沿问题"""
    methods: str = ""
    """M 段落: 创新技术路线与方法"""
    results: str = ""
    """R 段落: 核心实验数据与发现"""
    conclusion: str = ""
    """C 段落: 理论/应用价值与展望"""
    word_count: int = 0
    """摘要词数"""
    model_version: str = ""
    """生成模型版本标识"""


# ═══════════════════════════════════════════════════════════════
# 标题 & 摘要生成 — 前端格式转换
# ═══════════════════════════════════════════════════════════════

def title_candidates_to_frontend(candidates: list[TitleCandidate]) -> list[dict]:
    """将 TitleCandidate 列表转为前端 JSON 格式。"""
    return [
        {
            "text": c.text,
            "focus": c.focus,
            "rationale": c.rationale,
        }
        for c in candidates
    ]


def abstract_result_to_frontend(result: AbstractResult) -> dict:
    """将 AbstractResult 转为前端 JSON 格式。"""
    return {
        "abstract": result.abstract,
        "background": result.background,
        "methods": result.methods,
        "results": result.results,
        "conclusion": result.conclusion,
        "word_count": result.word_count,
        "model_version": result.model_version,
    }


# ═══════════════════════════════════════════════════════════════
# 段落改写数据模型（Day 3）
# ═══════════════════════════════════════════════════════════════

@dataclass
class ParaphraseChange:
    """段落改写的单条变更记录。"""
    original: str
    """原文片段"""
    replacement: str
    """改写后文本"""
    reason: str = ""
    """变更原因（对应触发的维度）"""


@dataclass
class ParaphraseResult:
    """段落改写完整结果。
    
    五维度优化（任务拆解 P30）:
      1. 句子顺序合理性 — 依存句法分析后重排
      2. 衔接补偿 — 逻辑连接词增补
      3. 冗余消除 — 语义相似度去重
      4. 主题句清晰度 — 位置启发式识别
      5. 过长句子拆分 — 句法树深度阈值裁剪
    
    核心约束: 一次只处理一个段落。
    """
    rewritten_text: str = ""
    """改写后的完整段落"""
    changes: list[ParaphraseChange] = field(default_factory=list)
    """逐条变更记录"""
    triggered_dimensions: list[str] = field(default_factory=list)
    """本次改写触发的维度列表"""
    model_version: str = ""


def paraphrase_result_to_frontend(result: ParaphraseResult) -> dict:
    """将 ParaphraseResult 转为前端 JSON 格式。"""
    return {
        "rewritten_text": result.rewritten_text,
        "changes": [
            {"original": c.original, "replacement": c.replacement, "reason": c.reason}
            for c in result.changes
        ],
        "triggered_dimensions": result.triggered_dimensions,
        "model_version": result.model_version,
    }


# ═══════════════════════════════════════════════════════════════
# 引用遗漏检测数据模型（Writefull Cite — P17/P18）
# ═══════════════════════════════════════════════════════════════

@dataclass
class CitationIssue:
    """单条引用遗漏问题。

    Writefull Cite 三阶段审计流水线（任务拆解 P17）:
      1. Claim 识别 — Writefull Cite API 判断「常识」vs「需要引用的观点」(高召回率)
      2. 规则过滤 — 正则检查 \cite{}、[n]、(Author, Year) 等标记是否已存在
      3. 文献推荐 — Semantic Scholar API 推荐 Top-5 最相关文献
    """
    sentence: str
    """需要引用的句子原文"""
    line: int
    """句子所在行号 (1-based)"""
    reason: str
    """为什么需要引用（英文）"""
    risk_level: str = "medium"
    """风险等级: high | medium | low — 灰色地带给轻度提醒（P17）"""
    confidence: float = 0.0
    """Writefull Cite 置信度 (0.0-1.0)"""
    suggested_action: str = ""
    """建议操作（P19 格式）"""
    recommended_citations: list[str] = field(default_factory=list)
    """推荐的文献（Semantic Scholar Top-5，Mock 模式为空）"""


@dataclass
class CiteCheckResult:
    """引用检测完整结果。

    Writefull Cite 不是查重工具——它是引用完整性检查工具（P18）。
    核心指标: 精确率 91%，召回率 94%，F1 0.925（Writefull 官方数据 P18）。
    设计理念: 灰色地带给轻度提醒，最终裁判权交给作者（P17）。
    """
    issues: list[CitationIssue] = field(default_factory=list)
    """引用遗漏问题列表"""
    total_sentences: int = 0
    """分析的句子总数"""
    cited_sentences: int = 0
    """已有引用的句子数"""
    uncited_claims: int = 0
    """缺少引用的论断数"""
    model_version: str = ""


def cite_check_to_frontend(result: CiteCheckResult) -> list[dict]:
    """将 CiteCheckResult 转为前端 JSON 格式。

    P19 格式: {citation_needed, confidence, reason, suggested_action}
    """
    return [
        {
            "sentence": iss.sentence,
            "line": iss.line,
            "reason": iss.reason,
            "risk_level": iss.risk_level,
            "confidence": iss.confidence,
            "suggested_action": iss.suggested_action,
            "recommended_citations": iss.recommended_citations,
        }
        for iss in result.issues
    ]
