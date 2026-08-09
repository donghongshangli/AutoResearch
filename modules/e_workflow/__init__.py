"""
E 组 — 流程编排与标准化组 (nature-skills 方向)

AutoResearch 的中央编排器：管理全部 17 个 nature-skill 的注册、发现与编排，
驱动 6 道质量 Gate，基于 checkpoint 状态机推进论文流水线。

运行环境: Claude Code（无需手动安装 nature-skills）

单一入口: run(paper_dir, progress=None) → dict
任务从 E/request.json 读取，结构见 docs/request-schema.md

### 功能说明
- Skill 注册/发现/编排: 管理 17 个 nature-skill 的元数据和调用策略
- 6 道质量 Gate: G1引用核验 / G2数据完整性 / G3逻辑一致性 / G4过度声称 / G5格式合规 / G6隐私审查
- 工作流状态机: idle → draft_done → polish_done → check_done → ready
- 论文上下文准备: 利用 autolib 为 Skill 调用装配结构化上下文

### 外部依赖
- autolib: LatexParser, DocGraph, find_main_tex
- server.services.context_svc: build_context, read_argument
- nature-skills: 17 个 Claude Code Skill（来自 nature-skills 仓库，LLM 调用由 Claude Code 管理）

### 产出影响
- 涉及的 .tex section: 全部
- 引用关系: 使用 DocGraph 查询
- 涉及 refs.bib: 是 (G1 引用核验)
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Callable, Optional


# ═══════════════════════════════════════════════════════════════
# 区块 1: 数据模型
# ═══════════════════════════════════════════════════════════════

@dataclass
class SkillInfo:
    """nature-skill 元数据 — 注册用，不实现 Skill 内部逻辑。"""

    name: str              # "nature-polishing"
    version: str           # "6.1.0"
    description: str       # 一句话描述
    category: str          # research | draft | polish | review | output | support
    triggers_on: list[str] # 哪些 checkpoint 触发
    produces: str          # 产出描述
    gates: list[str]       # 关联的质量 Gate


@dataclass
class GateResult:
    """质量门检查结果。"""

    gate_id: str           # "G1" ~ "G6"
    name: str              # citation_verification
    name_zh: str           # 引用核验
    status: str            # pass | warn | fail
    score: int = 0
    passed: bool = True
    issues: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════
# 区块 2: Skill 注册中心 — 17 个 nature-skill
# ═══════════════════════════════════════════════════════════════

class SkillRegistry:
    """Skill 注册/发现/编排管理框架。

    注册全部 17 个 nature-skill 的元数据，不实现 Skill 内部逻辑。
    Skill 通过 Claude Code 的 Skill 工具调用，本模块负责决定何时调用哪个。
    """

    def __init__(self):
        self._skills: dict[str, SkillInfo] = {}
        self._register_all()

    def _register_all(self):
        """注册全部 17 个 nature-skill。"""
        S = SkillInfo  # 缩写

        # ── 研究阶段 (Research Phase) ──
        research_skills = [
            S("nature-academic-search", "2.0.0",
              "多源文献检索: PubMed/arXiv/Crossref/Semantic Scholar/CNKI 五源并行搜索，六维打分排序",
              "research", ["idle", "draft_done"], "文献候选列表 + 评分报告", []),
            S("nature-literature-pipeline", "1.0.0",
              "全自动文献发现流水线: 多源搜索→六维打分→精读→格式化交付→归档",
              "research", ["idle", "draft_done"], "结构化文献报告 + 归档", ["G1"]),
            S("nature-downloader", "1.0.0",
              "论文下载: 配置学校/图书馆访问权限，复用 Chrome 机构会话，下载合法 OA/授权 PDF",
              "research", ["idle"], "已下载的论文 PDF", []),
            S("nature-reader", "2.0.0",
              "论文精读: 中英对照 Markdown 阅读器，图表/表格感知，来源锚定，支持 PDF/DOI/arXiv/HTML",
              "research", ["idle"], "结构化 Markdown 阅读笔记", []),
        ]

        # ── 写作阶段 (Draft Phase) ──
        draft_skills = [
            S("nature-writing", "1.0.0",
              "Nature 风格论文写作: 从作者提供的 claim/result/figure/notes/中文草稿 起草各章节",
              "draft", ["draft_done"], "论文章节 .tex 文件", ["G3", "G4"]),
            S("nature-proposal-writer", "1.0.0",
              "研究提案写作: 撰写结构化研究计划书（背景/目标/方法/预期成果/时间表）",
              "draft", ["idle"], "结构化研究提案", ["G3"]),
        ]

        # ── 润色阶段 (Polish Phase) ──
        polish_skills = [
            S("nature-polishing", "6.1.0",
              "Nature 风格学术润色: 12 步 checklist（断句→章节识别→沙漏结构→时态审计→"
              "句子修改→词汇升级→模板检查→引用审查→期刊风格→过度声称→校对→纯文本输出），"
              "支持 LaTeX 排版修复",
              "polish", ["draft_done", "polish_done"],
              "润色后文本 + 步骤报告 + 排版修复", ["G1", "G2", "G3", "G4", "G5"]),
            S("nature-citation", "2.0.0",
              "引用检索与添加: 将长文本切分为可引用段落，仅在 Nature Portfolio/AAAS Science/"
              "Cell Press 旗舰及子刊中检索，输出参考管理器就绪格式",
              "polish", ["draft_done", "polish_done"],
              "带引用的文本 + BibTeX/EndNote/RIS 导出", ["G1"]),
            S("nature-figure", "2.0.0",
              "Nature 级科研绘图: Python/R 图表制作/审核/修改，AI 生成示意图，"
              "配色可访问性检查，多面板排版",
              "polish", ["draft_done", "polish_done"],
              "审核报告 + 修改后的图表文件", ["G2", "G5"]),
            S("nature-statistics", "1.0.0",
              "统计报告审计: p 值/置信区间/样本量/重复次数/多重比较校正的 Nature 级审核",
              "polish", ["polish_done", "check_done"],
              "统计报告审核意见 + 修改建议", ["G2", "G3"]),
            S("nature-data", "2.0.0",
              "数据声明: 准备/审核/修改 Nature 级 Data Availability Statement，"
              "FAIR 元数据清单，数据仓库推荐",
              "polish", ["polish_done", "check_done"],
              "Data Availability Statement + FAIR 清单", ["G2", "G6"]),
        ]

        # ── 审核阶段 (Review Phase) ──
        review_skills = [
            S("nature-ref-verifier", "1.0.0",
              "参考文献交叉验证: 多源核验作者/标题/年份/卷/页码，标记冲突，输出结构化报告",
              "review", ["polish_done", "check_done"],
              "引用验证报告 + 冲突标记", ["G1"]),
            S("nature-reviewer", "1.0.0",
              "Nature 级审稿模拟: 从审稿人视角评估论文，生成审稿报告/同行评议式批判",
              "review", ["polish_done", "check_done"],
              "模拟审稿报告", ["G3", "G4"]),
            S("nature-response", "1.0.0",
              "修改回复: 起草/审核/修改 Nature 级逐点回复信、反驳信、修改封面信",
              "review", ["check_done"],
              "逐点回复信 + 修改说明", ["G3"]),
        ]

        # ── 产出阶段 (Output Phase) ──
        output_skills = [
            S("nature-paper2ppt", "1.0.0",
              "论文转 PPT: 从论文生成 Nature 风格中文 PPT，适用于组会/答辩/学术报告",
              "output", ["check_done"],
              "PPTX 演示文稿", []),
            S("nature-paper-to-patent", "1.0.0",
              "论文转专利: 将论文/技术报告转化为有据可查的中国发明专利草案，"
              "含权利要求对齐的流程图和方法图",
              "output", ["check_done"],
              "中国发明专利草案 + 流程图", ["G6"]),
        ]

        # ── 支持工具 (Support) ──
        support_skills = [
            S("nature-experiment-log", "1.0.0",
              "实验日志标准化: 接收原始材料（图片/语音/文字），输出 YAML frontmatter 标准日志，"
              "适用于 Obsidian 知识库",
              "support", ["idle"],
              "带 YAML frontmatter 的标准化实验日志", []),
        ]

        for s in (research_skills + draft_skills + polish_skills +
                  review_skills + output_skills + support_skills):
            self._skills[s.name] = s

    # ── 公开接口 ──

    def get(self, name: str) -> SkillInfo | None:
        return self._skills.get(name)

    def list_all(self) -> list[SkillInfo]:
        return list(self._skills.values())

    def list_by_category(self, category: str) -> list[SkillInfo]:
        return [s for s in self._skills.values() if s.category == category]

    def for_checkpoint(self, checkpoint: str) -> list[SkillInfo]:
        """返回当前 checkpoint 应调用的 Skill 列表。"""
        return [s for s in self._skills.values() if checkpoint in s.triggers_on]

    def resolve_intent(self, intent: str) -> list[str]:
        """根据用户意图解析应调用的 Skill 名称列表。

        轻量级关键词路由——复杂的 Prompt→Workflow 转化由 nature-polishing 内部完成。
        """
        if not intent:
            return []

        il = intent.lower()
        selected: list[str] = []

        rules = [
            (["全文润色", "润色", "语言", "表达", "时态", "语法", "句子", "polish",
              "language", "grammar", "tense", "wording", "fluency", "改写"],
             ["nature-polishing"]),
            (["写", "草稿", "起草", "撰写", "初稿", "章节", "write", "draft",
              "section", "段落"],
             ["nature-writing"]),
            (["引用", "文献", "参考", "citation", "reference", "bib",
              "bibliography", "引文", "加引用", "补引用", "找引用"],
             ["nature-citation"]),
            (["图", "figure", "图表", "绘图", "可视化", "colormap",
              "plot", "chart", "图片", "示意图"],
             ["nature-figure"]),
            (["数据", "data", "数据可用", "FAIR", "仓库", "repository",
              "数据集", "dataset", "数据声明"],
             ["nature-data"]),
            (["统计", "统计报告", "p值", "p value", "置信区间", "样本量",
              "显著性", "statistics", "statistical"],
             ["nature-statistics"]),
            (["检索", "搜索", "查找文献", "文献检索", "search", "literature",
              "semantic scholar", "pubmed", "arxiv", "cnki"],
             ["nature-academic-search"]),
            (["下载论文", "下载pdf", "下载全文", "获取全文", "download paper", "download pdf", "paywall"],
             ["nature-downloader"]),
            (["阅读", "精读", "翻译", "read", "translate", "解读", "读书笔记"],
             ["nature-reader"]),
            (["引用验证", "参考文献检查", "ref check", "验证引用", "引用核对",
              "ref verify"],
             ["nature-ref-verifier"]),
            (["审稿", "审稿人", "review", "评审", "审阅"],
             ["nature-reviewer"]),
            (["回复", "修改回复", "response", "rebuttal", "审稿意见",
              "逐点回复", "response letter"],
             ["nature-response"]),
            (["ppt", "幻灯片", "演示", "presentation", "组会", "答辩",
              "slides", "报告ppt"],
             ["nature-paper2ppt"]),
            (["专利", "patent", "发明专利", "专利草案"],
             ["nature-paper-to-patent"]),
            (["提案", "proposal", "研究计划", "开题", "研究方案", "课题"],
             ["nature-proposal-writer"]),
            (["实验记录", "实验日志", "experiment log", "实验报告", "lab notebook"],
             ["nature-experiment-log"]),
            (["文献发现", "文献流水线", "literature pipeline", "自动找文献",
              "文献调研"],
             ["nature-literature-pipeline"]),
        ]

        for keywords, skills in rules:
            if any(kw in il for kw in keywords):
                selected.extend(skills)

        seen = set()
        return [s for s in selected if not (s in seen or seen.add(s))]


# 全局单例
_skill_registry = SkillRegistry()


# ═══════════════════════════════════════════════════════════════
# 区块 4: 论文上下文准备器
# ═══════════════════════════════════════════════════════════════

class PaperContext:
    """加载论文解析结果，为 Skill 调用和 Gate 检查提供统一数据源。"""

    def __init__(self, paper_dir: str):
        self.paper_dir = Path(paper_dir)
        self.paper = None     # PaperAST | None
        self.graph = None     # DocGraph | None
        self.errors: list[str] = []
        self._init()

    def _init(self):
        try:
            from autolib.latex_parser import LatexParser
            from autolib.doc_graph import DocGraph
            from autolib.utils import find_main_tex

            main = find_main_tex(self.paper_dir)
            if main:
                parser = LatexParser(str(self.paper_dir))
                self.paper = parser.parse_project(main)
                bib_path = str(self.paper_dir / "refs.bib")
                bib = [bib_path] if Path(bib_path).exists() else None
                self.graph = DocGraph(self.paper, bib)
        except ImportError:
            self.errors.append("pylatexenc 未安装，LaTeX 解析不可用")
        except Exception as e:
            self.errors.append(f"论文解析失败: {e}")

    @property
    def is_ready(self) -> bool:
        return self.paper is not None and self.graph is not None

    def read_all_tex(self) -> str:
        """拼接项目中所有 .tex 文件。"""
        parts = []
        main = self.paper_dir / "main.tex"
        if main.exists():
            parts.append(main.read_text(encoding="utf-8", errors="replace"))
        sections = self.paper_dir / "sections"
        if sections.is_dir():
            for f in sorted(sections.glob("*.tex")):
                parts.append(f.read_text(encoding="utf-8", errors="replace"))
        return "\n\n".join(parts) if parts else ""

    def read_argument(self) -> str:
        p = self.paper_dir / "argument.md"
        return p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""

    def build_skill_context(self) -> str:
        """为 nature-skill 调用组装论文上下文摘要。

        包含章节结构、引用统计、argument.md（如有）。
        供上层在触发 Skill 时作为上下文注入。
        """
        parts = [f"论文目录: {self.paper_dir}"]

        if self.paper and self.paper.sections:
            parts.append("\n## 章节结构")
            for sec in self.paper.all_sections:
                parts.append(
                    f"- {sec.title} [{len(sec.content)} 字符, "
                    f"{len(sec.cites)} 引用]"
                )
            parts.append(f"\n共 {len(self.paper.all_cites)} 篇引用文献")

        if self.graph:
            uncached = self.graph.uncached_cites()
            broken = self.graph.broken_refs()
            if uncached:
                parts.append(f"\n⚠ 缺失 bib 条目: {', '.join(uncached[:10])}")
            if broken:
                parts.append(f"\n⚠ 悬空交叉引用: {', '.join(broken[:10])}")

        arg = self.read_argument()
        if arg:
            parts.append(f"\n## 论文论证结构 (argument.md)\n{arg[:3000]}")

        return "\n".join(parts)


# ═══════════════════════════════════════════════════════════════
# 区块 5: 6 道质量控制 Gate
# ═══════════════════════════════════════════════════════════════

# 过度声称模式 (G4)
OVERCLAIMING_PATTERNS: list[tuple[str, str]] = [
    (r"\bfirst\s+ever\b", "声称'首次'"),
    (r"\bfirst\s+of\s+its\s+kind\b", "声称'同类首创'"),
    (r"\bunprecedented\b", "'unprecedented'"),
    (r"\brevolutionary\b", "'revolutionary'"),
    (r"\bground[\s-]?breaking\b", "'groundbreaking'"),
    (r"\bcompletely\s+novel\b", "声称'完全新颖'"),
    (r"\bentirely\s+new\b", "声称'全新'"),
    (r"\bnever\s+before\b", "声称'前所未有'"),
    (r"\bparadigm\s+shift\b", "声称'范式转变'"),
    (r"\bbreakthrough\b", "'breakthrough'"),
    (r"\bgame[\s-]?changing\b", "'game-changing'"),
    (r"\bstate[\s-]of[\s-]the[\s-]art\b", "'state-of-the-art'（谨慎使用）"),
    (r"\bhighly\s+significant\b", "过度强调显著性"),
    (r"\bvery\s+unique\b", "'very unique' 语法不当"),
    (r"\b(absolutely|definitely|undoubtedly)\b", "绝对化修饰"),
    (r"\bwithout\s+(any\s+)?doubt\b", "绝对化修饰"),
    (r"\bproves?\s+that\b", "'prove' 过于绝对"),
    (r"\bcompletely\s+solves?\b", "声称'完全解决'"),
    (r"\bperfect\b", "声称'完美'"),
    (r"\boptimal\b(?!\s+(control|solution|design|policy|strategy))", "未限定的 'optimal'"),
    (r"\b(always|never)\b", "过度泛化"),
    (r"\b(dramatically|remarkably|strikingly)\b", "夸大修饰"),
]

REQUIRED_SECTIONS = {
    "introduction": ["introduction", "intro", "background"],
    "methods": ["method", "methods", "methodology", "approach", "proposed method",
                "framework", "model architecture", "system design"],
    "results": ["result", "results", "experiment", "experiments", "evaluation",
                "performance", "analysis", "findings"],
    "conclusion": ["conclusion", "conclusions", "discussion", "discussion and conclusion",
                   "concluding remarks", "summary"],
}


class GateRunner:
    """6 道质量 Gate 执行器。

    E 组核心贡献 — 建立科研 AI 使用规范与质量控制标准。
    Python 能自动检查的直接跑（引用完整性/LaTeX 格式/隐私模式匹配），
    需要语义理解的（逻辑一致性/过度声称的上下文判断）标记需 AI 辅助。
    """

    def __init__(self, ctx: PaperContext):
        self.ctx = ctx

    def run_all(self) -> list[GateResult]:
        return [
            self._g1(), self._g2(), self._g3(),
            self._g4(), self._g5(), self._g6(),
        ]

    # ── G1: 引用核验 ─────────────────────────────────────────

    def _g1(self) -> GateResult:
        issues, score = [], 100
        if self.ctx.graph:
            uc = self.ctx.graph.uncached_cites()
            if uc:
                score -= min(50, len(uc) * 5)
                issues.append(f"{len(uc)} 个引用缺 bib 条目: {', '.join(uc[:5])}")
            br = self.ctx.graph.broken_refs()
            if br:
                score -= min(30, len(br) * 5)
                issues.append(f"{len(br)} 个悬空交叉引用: {', '.join(br[:5])}")
            if self.ctx.paper:
                empty = [s.title for s in self.ctx.paper.all_sections
                         if not s.cites and len(s.content) > 500]
                if empty:
                    score -= min(20, len(empty) * 5)
                    issues.append(f"{len(empty)} 个长章节无引用: {', '.join(empty[:3])}")
        if not (self.ctx.paper_dir / "refs.bib").exists():
            score = max(0, score - 30)
            issues.append("refs.bib 不存在")
        passed = score >= 70
        return GateResult("G1", "citation_verification", "引用核验",
                          "pass" if passed else "fail", score, passed, issues)

    # ── G2: 数据完整性 ───────────────────────────────────────

    def _g2(self) -> GateResult:
        issues, score = [], 100
        text = self.ctx.read_all_tex()
        for prefix, name in [("fig:", "图"), ("tab:", "表"), ("eq:", "公式")]:
            refs = set(re.findall(rf'\\ref\{{{prefix}', text))
            labels = set(re.findall(rf'\\label\{{{prefix}', text))
            dangling = refs - labels
            if dangling:
                score -= min(20, len(dangling) * 5)
                issues.append(f"{len(dangling)} 个{name}引用无对应 label: "
                              f"{', '.join(list(dangling)[:5])}")
            unused = labels - refs
            if unused:
                score -= min(10, len(unused) * 3)
                issues.append(f"{len(unused)} 个{name} label 未被引用: "
                              f"{', '.join(list(unused)[:5])}")
        if re.search(r'\?\?', text):
            score -= 10
            issues.append("存在未解析的交叉引用 (??)")
        passed = score >= 70
        return GateResult("G2", "data_integrity", "数据完整性",
                          "pass" if passed else "fail", score, passed, issues)

    # ── G3: 逻辑一致性 ───────────────────────────────────────

    def _g3(self) -> GateResult:
        issues, score = [], 80
        if not self.ctx.paper or not self.ctx.paper.sections:
            return GateResult("G3", "logic_consistency", "逻辑一致性",
                              "warn", 70, True,
                              ["无章节数据 — 建议人工审查或调用 nature-reviewer"])
        sections = self.ctx.paper.all_sections
        abs_sec = conc_sec = None
        for s in sections:
            tl = s.title.lower()
            if "abstract" in tl and abs_sec is None:
                abs_sec = s
            if any(kw in tl for kw in ["conclusion", "discussion"]) and conc_sec is None:
                conc_sec = s
        if abs_sec and conc_sec:
            abs_terms = set(re.findall(r'\b\w{6,}\b', abs_sec.content.lower()))
            conc_terms = set(re.findall(r'\b\w{6,}\b', conc_sec.content.lower()))
            if len(abs_terms & conc_terms) < 5:
                score -= 20
                issues.append("Abstract 与 Conclusion 术语重叠度低，可能逻辑断裂")
        arg = self.ctx.read_argument()
        if arg:
            paper_text = self.ctx.read_all_tex().lower()
            claims = re.findall(r'[-*]\s*(.*?)(?:\n|$)', arg)
            missing = []
            for claim in claims[:10]:
                keywords = [w for w in claim.lower().split() if len(w) > 5]
                if keywords and not any(kw in paper_text for kw in keywords[:3]):
                    missing.append(claim[:80])
            if missing:
                score -= min(30, len(missing) * 10)
                issues.append(f"{len(missing)} 个 argument.md 主张在论文中未体现")
        passed = score >= 60
        return GateResult("G3", "logic_consistency", "逻辑一致性",
                          "pass" if passed else "warn", score, passed, issues,
                          {"needs_ai_review": len(issues) > 0})

    # ── G4: 过度声称 ─────────────────────────────────────────

    def _g4(self) -> GateResult:
        issues, score = [], 100
        text = self.ctx.read_all_tex()
        for pattern, desc in OVERCLAIMING_PATTERNS:
            matches = list(re.finditer(pattern, text, re.IGNORECASE))
            if len(matches) > 2:
                score -= min(30, len(matches) * 3)
                issues.append(f"'{desc}' 出现 {len(matches)} 次")
        if self.ctx.paper:
            for s in self.ctx.paper.all_sections:
                if any(a in s.title.lower() for a in REQUIRED_SECTIONS["introduction"]):
                    count = len(re.findall(
                        r'\bwe\s+will\s+(?:show|demonstrate|prove|establish)\b',
                        s.content, re.IGNORECASE))
                    if count:
                        score -= count * 5
                        issues.append(f"Introduction 中 'we will show' 出现 {count} 次")
                    break
        passed = score >= 60
        return GateResult("G4", "overclaiming", "过度声称",
                          "pass" if passed else "fail", score, passed, issues)

    # ── G5: 格式合规 ─────────────────────────────────────────

    def _g5(self) -> GateResult:
        issues, score = [], 100
        text = self.ctx.read_all_tex()
        for pattern, msg in [
            (r'\\documentclass', "缺少 \\documentclass"),
            (r'\\begin\{document\}', "缺少 \\begin{document}"),
            (r'\\end\{document\}', "缺少 \\end{document}"),
            (r'\\title\{', "缺少 \\title"),
            (r'\\author\{', "缺少 \\author"),
            (r'\\(?:bibliography|printbibliography|addbibresource)', "缺少参考文献配置"),
        ]:
            if not re.search(pattern, text):
                score -= 15
                issues.append(msg)
        if text.count('{') != text.count('}'):
            score -= 20
            issues.append(f"花括号不配对: {{ {text.count('{')} vs }} {text.count('}')}")
        begins = set(re.findall(r'\\begin\{([^}]+)\}', text))
        ends = set(re.findall(r'\\end\{([^}]+)\}', text))
        unmatched = begins - ends
        if unmatched:
            score -= 20
            issues.append(f"未闭合 environment: {', '.join(list(unmatched)[:5])}")
        passed = score >= 70
        return GateResult("G5", "format_compliance", "格式合规",
                          "pass" if passed else "fail", score, passed, issues)

    # ── G6: 隐私审查 ─────────────────────────────────────────

    def _g6(self) -> GateResult:
        issues, score = [], 100
        text = self.ctx.read_all_tex()
        emails = re.findall(r'[\w.+-]+@[\w-]+\.[\w.-]+', text)
        if emails:
            score -= min(30, len(emails) * 10)
            issues.append(f"包含邮箱: {', '.join(emails[:5])}")
        if re.findall(r'\b(?:University|College|Institute|School|Department|'
                      r'Lab(?:oratory)?)\s+of\b', text):
            score -= 10
            issues.append("包含机构信息（盲审时需匿名化）")
        if 'orcid' in text.lower():
            score -= 5
            issues.append("包含 ORCID")
        fund = re.findall(r'\b\d{5,}\b', text)
        if fund:
            score -= 10
            issues.append(f"可能包含基金号: {', '.join(fund[:5])}")
        passed = score >= 70
        return GateResult("G6", "privacy_review", "隐私审查",
                          "pass" if passed else "warn", score, passed, issues)


# ═══════════════════════════════════════════════════════════════
# 区块 6: 工作流状态机
# ═══════════════════════════════════════════════════════════════

class WorkflowEngine:
    """工作流编排核心。

    根据 checkpoint 决定:
    - 下一步是什么 (next)
    - 需要调用哪些 nature-skill (skills_to_invoke)
    - 是否需要运行 6 道 Gate (run_gates)
    """

    PIPELINE = {
        "idle": {
            "next": "generate",
            "description": "等待 B 组生成初稿。可调用 nature-academic-search / "
                           "nature-literature-pipeline 进行文献调研，"
                           "nature-reader 精读参考论文。",
            "run_skills": ["nature-academic-search"],  # 默认推荐
            "run_gates": False,
        },
        "draft_done": {
            "next": "polish",
            "description": "初稿完成 → 调用 nature-polishing (12 步 checklist 润色) "
                           "+ nature-citation (引用补充) "
                           "+ nature-figure (图表审核)",
            "run_skills": ["nature-polishing", "nature-citation", "nature-figure"],
            "run_gates": False,  # nature-polishing 内部已有质量检查
        },
        "polish_done": {
            "next": "check",
            "description": "润色完成 → 运行 6 道 Gate 质量门禁 "
                           "+ 可选 nature-ref-verifier / nature-reviewer / nature-statistics / nature-data",
            "run_skills": ["nature-ref-verifier", "nature-statistics", "nature-data"],
            "run_gates": True,
        },
        "check_done": {
            "next": "compile",
            "description": "全部 Gate 通过 → 最终编译。"
                           "可选 nature-paper2ppt / nature-paper-to-patent 生成衍生输出。",
            "run_skills": [],
            "run_gates": True,  # 最终验证
        },
    }

    def __init__(
        self,
        paper_dir: str,
        checkpoint: str = "idle",
        trigger: str = "manual",
        intent: str = "",
        progress: Optional[Callable] = None,
    ):
        self.paper_dir = Path(paper_dir)
        self.checkpoint = checkpoint
        self.trigger = trigger
        self.intent = intent
        self.progress = progress or (lambda *a: None)

        # ── 加载论文 ──
        self.progress("init", "加载论文结构...", 5)
        self.ctx = PaperContext(str(paper_dir))
        if self.ctx.errors:
            self.progress("init", f"警告: {self.ctx.errors[0]}", 8)

    def execute(self) -> dict:
        """执行工作流，返回结构化指令。"""
        self.progress("start",
                      f"E 组工作流启动 | checkpoint={self.checkpoint}", 10)

        stage = self.PIPELINE.get(self.checkpoint, self.PIPELINE["idle"])

        # ── 解析用户意图，调整 Skill 列表 ──
        run_skills = list(stage["run_skills"])
        if self.intent:
            resolved = _skill_registry.resolve_intent(self.intent)
            if resolved:
                run_skills = resolved  # 用户意图优先
                self.progress("intent",
                              f"意图匹配: {', '.join(run_skills)}", 15)

        # ── 准备 Skill 调用上下文 ──
        skill_context = ""
        if run_skills:
            self.progress("context", "准备 Skill 调用上下文...", 20)
            skill_context = self.ctx.build_skill_context()

        # ── 运行质量 Gate ──
        gate_results: list[GateResult] = []
        if stage["run_gates"]:
            self.progress("gate", "执行 6 道质量 Gate...", 30)
            runner = GateRunner(self.ctx)
            gate_results = runner.run_all()
            passed_n = sum(1 for g in gate_results if g.passed)
            self.progress("gate",
                          f"Gate 完成: {passed_n}/{len(gate_results)} 通过", 70)

        # ── 组装返回 ──
        done: list[str] = []
        notes = stage["description"]

        if run_skills:
            done.extend(run_skills)
            notes += f"\n\n待调用 Skill ({len(run_skills)} 个): {', '.join(run_skills)}"

        if gate_results:
            failed = [g.gate_id for g in gate_results if not g.passed]
            done.append(f"gates_{len(gate_results)}")
            if failed:
                notes += f"\n未通过 Gate: {', '.join(failed)}"
            else:
                notes += "\n全部 Gate 通过"

        if self.ctx.errors:
            notes += f"\n⚠ {self.ctx.errors[0]}"

        # ── Skill 调用包 ──
        skill_instructions = None
        if run_skills:
            skill_instructions = {
                "skills": run_skills,
                "paper_dir": str(self.paper_dir),
                "context": skill_context,
                "checkpoint": self.checkpoint,
                "intent": self.intent,
            }

        self.progress("done",
                      f"工作流完成 → next={stage['next']}", 100)

        return {
            "next": stage["next"],
            "done": done,
            "notes": notes,
            "skills_to_invoke": skill_instructions,
            "gates": [
                {
                    "gate_id": g.gate_id,
                    "name_zh": g.name_zh,
                    "status": g.status,
                    "score": g.score,
                    "passed": g.passed,
                    "issues": g.issues,
                }
                for g in gate_results
            ],
        }


# ═══════════════════════════════════════════════════════════════
# 区块 7: 入口函数
# ═══════════════════════════════════════════════════════════════

def run(paper_dir: str, progress: Optional[Callable] = None) -> dict:
    """E 组工作流引擎单一入口。

    运行环境: Claude Code，无需手动安装 nature-skills。
    LLM 调用由 nature-skill（Claude Code Skill）内部完成，使用当前 Claude Code 会话的默认模型。

    参数:
        paper_dir: 论文项目目录（tasks/{paper}/）
        progress:  可选进度回调 progress(stage, message, percent)

    返回:
        {
            "next": str,                # generate | polish | check | compile
            "done": list[str],          # 已完成项
            "notes": str,               # 人类可读说明
            "skills_to_invoke": {       # 待调用 Skill 及上下文 (null 表示无需调用)
                "skills": ["nature-polishing", ...],
                "paper_dir": "...",
                "context": "论文结构 + 引用统计 + argument.md...",
                "checkpoint": "...",
                "intent": "..."
            },
            "gates": [                  # Gate 检查结果
                {"gate_id": "G1", "name_zh": "引用核验", "status": "pass", "score": 100, ...}
            ]
        }
    """
    proj_dir = Path(paper_dir)
    req_path = proj_dir / "E" / "request.json"

    # ── 读取 request.json ──
    if req_path.exists():
        try:
            req = json.loads(req_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, Exception):
            req = {}
        checkpoint = req.get("checkpoint", "idle")
        trigger = req.get("trigger", "manual")
        intent = req.get("intent", "")
    else:
        checkpoint = "idle"
        trigger = "manual"
        intent = ""

    # ── 执行工作流 ──
    engine = WorkflowEngine(
        paper_dir=str(proj_dir),
        checkpoint=checkpoint,
        trigger=trigger,
        intent=intent,
        progress=progress,
    )

    return engine.execute()
