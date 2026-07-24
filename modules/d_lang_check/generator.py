"""
generator.py — GeneratorService: 标题 & 摘要生成

对齐任务拆解 P16 "生成式摘要" + 两周计划 Day 4 "标题和摘要生成模块":

  标题生成 (Title Generation):
    - 一次性输出 5 个不同侧重点的候选标题
    - 类型: method (方法突出) / conclusion (结论突出) / question (疑问句式)
            / concise (简洁型) / descriptive (描述型)

  摘要生成 (Abstract Generation):
    - B-M-R-C 四要素强制引导算法:
      B (Background):  研究背景与前沿问题
      M (Methods):     创新技术路线
      R (Results):     核心实验数据
      C (Conclusion):  理论/应用价值
    - 核心约束（P30）: 绝不编造原文没有的数据

  Writefull Generate API 规范（预期）:
    - 端点: POST /v1/generate
    - 认证: Bearer token
    - 请求: {text, task_type ("title"|"abstract"), options}

当前状态: API token 待申请，使用 Mock 模式（固定示例数据，完全不分析输入文本）。
接入真实 API 时替换 _call_api() 方法，_mock_*() 方法直接删除。

配置:
  D_GENERATE_SERVICE=writefull  主力（默认，当前 Mock 模式）
  WRITEFULL_API_KEY=xxx         真实 API key（待申请）
"""

from __future__ import annotations

import os
import re
import logging
from typing import Optional

from .models import TitleCandidate, AbstractResult

logger = logging.getLogger("autoresearch.d_lang_check.generator")

# 环境变量
_ENV_GENERATE_SERVICE = os.environ.get('D_GENERATE_SERVICE', 'writefull')
_WRITEFULL_API_KEY = os.environ.get("WRITEFULL_API_KEY", "")
_WRITEFULL_API_URL = os.environ.get("WRITEFULL_API_URL", "https://api.writefull.com/v1")

# 支持的侧重点类型
VALID_TITLE_FOCUS = {
    "method", "conclusion", "question", "concise", "descriptive", "balanced",
}

# 支持的学科
VALID_DISCIPLINES = {
    "computer-science", "biology", "medicine", "physics",
    "chemistry", "engineering", "mathematics", "general",
}


# ═══════════════════════════════════════════════════════════════
# 公开接口
# ═══════════════════════════════════════════════════════════════

def generate_title(
    text: str,
    count: int = 5,
    focus: str = "balanced",
    discipline: str = "general",
    intent: str = "",
) -> list[TitleCandidate]:
    """调用生成服务，生成标题候选列表。

    Args:
        text:       论文文本（Mock 模式下不分析，始终返回固定示例）
        count:      候选标题数量（默认 5）
        focus:      侧重点: balanced | method | conclusion | question | concise | descriptive
        discipline: 学科标签
        intent:     用户补充意图

    Returns:
        list[TitleCandidate]

    Raises:
        ValueError: 无效的 focus 或 discipline

    Example:
        >>> titles = generate_title("any paper text...")
        >>> for t in titles:
        ...     print(f"[{t.focus}] {t.text}")
    """
    if focus not in VALID_TITLE_FOCUS:
        raise ValueError(
            f"无效的侧重点: '{focus}'。可选值: {sorted(VALID_TITLE_FOCUS)}"
        )
    if discipline not in VALID_DISCIPLINES:
        raise ValueError(
            f"无效的学科标签: '{discipline}'。可选值: {sorted(VALID_DISCIPLINES)}"
        )
    if not text or not text.strip():
        return []

    service = create_generator_service()
    return service.generate_titles(text, count, focus, discipline, intent)


def generate_abstract(
    text: str,
    discipline: str = "general",
    max_words: int = 250,
    intent: str = "",
    return_full: bool = False,
) -> str | tuple[str, AbstractResult]:
    """调用生成服务，生成 B-M-R-C 结构化摘要。

    Args:
        text:       论文文本（Mock 模式下不分析，始终返回固定示例）
        discipline: 学科标签
        max_words:  目标词数（默认 250）
        intent:     用户补充意图
        return_full: 若 True，额外返回完整 AbstractResult

    Returns:
        str（return_full=False）或 (str, AbstractResult)

    Example:
        >>> abstract = generate_abstract("any paper text...")
        >>> abstract, result = generate_abstract(..., return_full=True)
    """
    if discipline not in VALID_DISCIPLINES:
        raise ValueError(
            f"无效的学科标签: '{discipline}'。可选值: {sorted(VALID_DISCIPLINES)}"
        )
    if not text or not text.strip():
        if return_full:
            return "", AbstractResult(abstract="", model_version="generator-mock-v1")
        return ""

    service = create_generator_service()
    result = service.generate_abstract(text, discipline, max_words, intent)

    if return_full:
        return result.abstract, result
    return result.abstract


# ═══════════════════════════════════════════════════════════════
# GeneratorService
# ═══════════════════════════════════════════════════════════════

class GeneratorService:
    """Writefull Generate API 封装。

    当前为 Mock 模式——返回固定示例数据，完全不分析输入文本。
    对标 MockService 的设计原则: "越简单越好，方便后期直接替换"。

    接入真实 Writefull Generate API 时:
      1. 设置 WRITEFULL_API_KEY 环境变量
      2. 在 _call_api() 中实现 HTTP 请求
      3. 删除 _mock_generate_titles() / _mock_generate_abstract()
    """

    MAX_INPUT_LENGTH = 100000  # 单次生成最大字符数

    def __init__(self, api_key: str = "", api_url: str = ""):
        self._api_key = api_key
        self._api_url = api_url or _WRITEFULL_API_URL

    @property
    def name(self) -> str:
        return "GeneratorService (mock mode)" if not self._api_key else "GeneratorService"

    def health_check(self) -> dict:
        if self._api_key:
            return {
                "status": "ok",
                "message": f"Writefull Generate API configured ({self._api_url})",
                "quota_remaining": None,
            }
        return {
            "status": "degraded",
            "message": "Mock mode — 设置 WRITEFULL_API_KEY 以接入真实 Generate API",
            "quota_remaining": None,
        }

    # ── 公共方法 ─────────────────────────────────────────────

    def generate_titles(
        self,
        text: str,
        count: int = 5,
        focus: str = "balanced",
        discipline: str = "general",
        intent: str = "",
    ) -> list[TitleCandidate]:
        """生成标题候选列表。"""
        if not text or not text.strip():
            return []
        if len(text) > self.MAX_INPUT_LENGTH:
            text = text[:self.MAX_INPUT_LENGTH]

        # LaTeX 保护: strip
        protected_text, latex_map = self._strip_latex(text)

        try:
            if self._api_key:
                raw = self._call_api(protected_text, task="title", count=count,
                                     focus=focus, discipline=discipline, intent=intent)
            else:
                raw = self._mock_generate_titles()
        except Exception as e:
            logger.error(f"标题生成失败: {e}")
            raise

        titles = []
        for c in raw.get("candidates", [])[:count]:
            # LaTeX 保护: restore
            title_text = self._restore_latex(c.get("title", ""), latex_map)
            title_text = re.sub(r'<<LATEX_\d+>>', '', title_text).strip()
            titles.append(TitleCandidate(
                text=title_text,
                focus=c.get("focus", "balanced"),
                rationale=c.get("rationale", ""),
            ))
        return titles

    def generate_abstract(
        self,
        text: str,
        discipline: str = "general",
        max_words: int = 250,
        intent: str = "",
    ) -> AbstractResult:
        """生成 B-M-R-C 结构化摘要。"""
        if not text or not text.strip():
            return AbstractResult(abstract="", model_version="generator-mock-v1")
        if len(text) > self.MAX_INPUT_LENGTH:
            text = text[:self.MAX_INPUT_LENGTH]

        # LaTeX 保护: strip
        protected_text, latex_map = self._strip_latex(text)

        try:
            if self._api_key:
                raw = self._call_api(protected_text, task="abstract",
                                     discipline=discipline, max_words=max_words,
                                     intent=intent)
            else:
                raw = self._mock_generate_abstract()
        except Exception as e:
            logger.error(f"摘要生成失败: {e}")
            raise

        # LaTeX 保护: restore
        full = self._restore_latex(raw.get("full_abstract", ""), latex_map)
        full = re.sub(r'<<LATEX_\d+>>', '', full).strip()
        words = full.split()
        if len(words) > max_words:
            full = " ".join(words[:max_words])

        def _clean(s: str) -> str:
            return re.sub(r'<<LATEX_\d+>>', '', s).strip()

        return AbstractResult(
            abstract=full,
            background=_clean(self._restore_latex(raw.get("background", ""), latex_map)),
            methods=_clean(self._restore_latex(raw.get("methods", ""), latex_map)),
            results=_clean(self._restore_latex(raw.get("results", ""), latex_map)),
            conclusion=_clean(self._restore_latex(raw.get("conclusion", ""), latex_map)),
            word_count=len(full.split()) if full else 0,
            model_version=raw.get("model_version", "generator-mock-v1"),
        )

    # ── LaTeX 保护: Strip / Restore（对标 academizer.py 拆装法）───

    _LATEX_PLACEHOLDER_RE = re.compile(r'<<LATEX_(\d+)>>')

    def _strip_latex(self, text: str) -> tuple[str, dict[int, str]]:
        """Strip: 将 LaTeX 命令替换为占位符 <<LATEX_N>>。"""
        latex_map: dict[int, str] = {}
        counter = [0]

        def _replace(m):
            idx = counter[0]
            latex_map[idx] = m.group(0)
            counter[0] += 1
            return f"<<LATEX_{idx}>>"

        cleaned = re.sub(
            r'\\(?:cite|citet|citep|citealt|citealp|citeauthor|citeyear|nocite)'
            r'\s*(?:\[[^\]]*\])?\s*\{[^}]*\}',
            _replace, text,
        )
        cleaned = re.sub(
            r'\\(?:ref|eqref|pageref|autoref|[Cc]ref|label)\s*\{[^}]*\}',
            _replace, cleaned,
        )
        cleaned = re.sub(r'\$[^$]+\$', _replace, cleaned)
        cleaned = re.sub(r'\$\$[\s\S]*?\$\$', _replace, cleaned)
        cleaned = re.sub(r'\\begin\{[^}]+\}[\s\S]*?\\end\{[^}]+\}', _replace, cleaned)

        return cleaned, latex_map

    def _restore_latex(self, text: str, latex_map: dict[int, str]) -> str:
        """Restore: 将占位符还原为原始 LaTeX 命令。"""
        def _restore(m):
            idx = int(m.group(1))
            return latex_map.get(idx, m.group(0))
        return self._LATEX_PLACEHOLDER_RE.sub(_restore, text)

    # ── API 调用（Stub — 接入时替换）────────────────────────

    def _call_api(
        self,
        text: str,
        task: str = "title",
        **kwargs,
    ) -> dict:
        """调用 Writefull Generate API。

        TODO: 接入真实 API。
        替换以下伪代码为实际 HTTP 请求:

            import httpx
            headers = {
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            }
            payload = {"text": text, "task_type": task, **kwargs}
            response = httpx.post(
                f"{self._api_url}/generate",
                json=payload, headers=headers, timeout=60,
            )
            response.raise_for_status()
            return response.json()
        """
        raise NotImplementedError(
            "Writefull Generate API 接入待实现。设置 WRITEFULL_API_KEY 后替换此方法。\n"
            "当前使用 Mock 模式——返回固定示例数据。"
        )

    # ── Mock 实现（最简固定数据，完全不分析输入文本）──────────
    # 对标 MockService: 返回固定示例，仅用于验证流水线连通性。
    # 接入真实 API 后直接删除这两个方法。

    @staticmethod
    def _mock_generate_titles() -> dict:
        """返回 5 条固定示例标题。不分析输入文本。"""
        return {
            "candidates": [
                {
                    "title": "A Novel Architecture for Efficient Document Generation: A Systematic Investigation",
                    "focus": "method",
                    "rationale": "Method-emphasis: highlights the key technical innovation.",
                },
                {
                    "title": "Advancing Long-Range Text Generation: State-of-the-Art Performance via Structured Memory",
                    "focus": "conclusion",
                    "rationale": "Conclusion-emphasis: leads with the main finding to grab attention.",
                },
                {
                    "title": "Can Structured Memory Architectures Address the Challenges of Long-Form Document Generation?",
                    "focus": "question",
                    "rationale": "Question format: engages readers by framing the work as an open problem.",
                },
                {
                    "title": "Document Generation via Structured Memory",
                    "focus": "concise",
                    "rationale": "Concise: shortest direct expression for venues with character limits.",
                },
                {
                    "title": "On the Scalability of Neural Document Generation: A Hierarchical Memory-Based Framework",
                    "focus": "descriptive",
                    "rationale": "Descriptive: covers scope, domain, and methodology comprehensively.",
                },
            ],
            "model_version": "generator-mock-v1",
        }

    @staticmethod
    def _mock_generate_abstract() -> dict:
        """返回固定 B-M-R-C 示例摘要。不分析输入文本。"""
        background = (
            "Recent advances in large language models have transformed document generation, "
            "yet critical challenges remain in maintaining coherence across long contexts. "
            "Existing approaches often fail to address the fundamental trade-off between "
            "computational efficiency and output quality, limiting their applicability to "
            "real-world document-length tasks."
        )
        methods = (
            "We propose a novel structured memory architecture that integrates three core "
            "components: (1) an adaptive chunking module for dynamic context segmentation, "
            "(2) a cross-chunk attention aggregator for global coherence preservation, and "
            "(3) a post-hoc verification mechanism ensuring factual consistency. The proposed "
            "framework is evaluated against established baselines on multiple long-form "
            "benchmarks including arXiv-Long and GovReport."
        )
        results = (
            "Experimental evaluation demonstrates that the proposed architecture achieves "
            "state-of-the-art performance across all metrics. Specifically, we observe a 23% "
            "improvement in ROUGE-L scores and a 15% reduction in factual inconsistency rates "
            "compared to existing methods. Ablation studies confirm that each component "
            "contributes meaningfully to the overall gains, validating the design choices."
        )
        conclusion = (
            "This work demonstrates that principled integration of structured memory techniques "
            "can substantially advance document-scale text generation. The findings have direct "
            "implications for practical applications including automated report generation, "
            "academic writing assistance, and long-form content creation. Future research "
            "directions include extending the framework to multi-modal settings and exploring "
            "deployment in resource-constrained environments."
        )

        full_abstract = f"{background}\n\n{methods}\n\n{results}\n\n{conclusion}"

        return {
            "background": background,
            "methods": methods,
            "results": results,
            "conclusion": conclusion,
            "full_abstract": full_abstract,
            "model_version": "generator-mock-v1",
        }

# ================================================================
# Service Factory
# ================================================================

def create_generator_service(name: str | None = None) -> GeneratorService:
    """Create GeneratorService instance.
    Reads D_GENERATE_SERVICE env var (default: writefull).
    """
    name = name or _ENV_GENERATE_SERVICE

    if name == "writefull":
        return GeneratorService(
            api_key=_WRITEFULL_API_KEY,
            api_url=_WRITEFULL_API_URL,
        )
    elif name == "mock":
        return GeneratorService()
    else:
        raise ValueError(
            f"Invalid GenerateService: '{name}'. "
            f"Valid: writefull, mock. "
            f"Configure via D_GENERATE_SERVICE env var."
        )
