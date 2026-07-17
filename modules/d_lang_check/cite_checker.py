"""
cite_checker.py — CiteCheckerService: Writefull Cite 引用遗漏检测

对齐任务拆解 P17 "Writefull Cite 引用检测" + P18 "实现方案" + P19 "API 设计":

  Writefull Cite 是引用完整性检查工具，不是查重工具（P18）。

  三阶段审计流水线（P17）:
    阶段 1 — Writefull Cite API 初筛（Claim 识别）:
      Writefull 专有分类模型，逐句扫描全文。
      判断「常识」vs「需要引用的观点」。
      策略: 高召回率 — 宁可多报，绝不漏报。

    阶段 2 — 规则过滤（正则引擎）:
      正则检查句子是否已有引用标记:
        \cite{...}、\citep{...}、\citet{...} 等 LaTeX 命令
        [1]、[n] 数字引用
        (Author, Year) 作者-年份格式
      已有标记 → 放行，降低误报率。

    阶段 3 — 文献推荐（Semantic Scholar API）:
      对确认缺引用的句子，调用 Semantic Scholar 检索 Top-5 最相关文献。
      Mock 模式下为空列表。

  P19 返回格式:
    {citation_needed: bool, confidence: float, reason: str, suggested_action: str}

  核心指标（P17）: 精确率 91%，召回率 94%，F1 0.925（Writefull 官方数据）。

  设计理念（P17）: 灰色地带给轻度提醒，最终裁判权交给作者。

当前状态: API token 待申请，使用 Mock 模式（固定示例数据，完全不分析输入文本）。
接入真实 API 时替换 _call_api() 方法，_mock_check_cites() 直接删除。

配置:
  D_CITE_SERVICE=writefull  主力（默认，当前 Mock 模式）
  WRITEFULL_API_KEY=xxx     真实 API key（待申请）
"""

from __future__ import annotations

import os
import re
import logging
from typing import Optional

from .models import CitationIssue, CiteCheckResult, cite_check_to_frontend

logger = logging.getLogger("autoresearch.d_lang_check.cite_checker")

# 环境变量
_ENV_CITE_SERVICE = os.environ.get("D_CITE_SERVICE", "writefull")
_WRITEFULL_API_KEY = os.environ.get("WRITEFULL_API_KEY", "")
_WRITEFULL_API_URL = os.environ.get("WRITEFULL_API_URL", "https://api.writefull.com/v1")

# 引用标记正则引擎（阶段 2 — P18）
# LaTeX cite 命令（复用 latex_protect.py 模式）
_LATEX_CITE_RE = re.compile(
    r'\\(?:cite|citet|citep|citealt|citealp|citeauthor|citeyear|nocite)'
    r'\s*(?:\[[^\]]*\])?\s*\{[^}]*\}',
)
# 数字引用: [1], [1,2], [1-3]
_BRACKET_CITE_RE = re.compile(r'\[\d+(?:[,;-]\d+)*\]')
# 作者-年份: (Author, 2020), (Smith et al., 2021)
_AUTHOR_YEAR_RE = re.compile(r'\([A-Z][a-z]+(?:\s+et\s+al\.)?(?:,\s*\d{4}[a-z]?)\)')
# 上标引用（常见于化学/医学期刊）: ¹²³ 或 ¹
_SUPERSCRIPT_CITE_RE = re.compile(r'[¹²³⁴⁵⁶⁷⁸⁹⁰]+')

# 支持的学科
VALID_DISCIPLINES = {
    "computer-science", "biology", "medicine", "physics",
    "chemistry", "engineering", "mathematics", "general",
}

# 风险等级
RISK_LEVELS = {"high", "medium", "low"}


# ═══════════════════════════════════════════════════════════════
# 公开接口
# ═══════════════════════════════════════════════════════════════

def check_citations(
    text: str,
    discipline: str = "general",
    intent: str = "",
    return_full: bool = False,
) -> list[dict] | tuple[list[dict], CiteCheckResult]:
    """调用 CiteCheckerService，检测引用遗漏。

    Args:
        text:       待检测的论文文本
        discipline: 学科标签（影响常识 vs 论断的判定边界）
        intent:     用户补充意图
        return_full: 若 True，额外返回完整 CiteCheckResult

    Returns:
        list[dict]（return_full=False）或 (list[dict], CiteCheckResult)

    Example:
        >>> issues = check_citations("Transformer models achieve SOTA...")
        >>> for i in issues:
        ...     print(f"[{i['risk_level']}] L{i['line']}: {i['reason']}")
        >>> issues, result = check_citations(..., return_full=True)
    """
    if discipline not in VALID_DISCIPLINES:
        raise ValueError(
            f"无效的学科标签: '{discipline}'。可选值: {sorted(VALID_DISCIPLINES)}"
        )
    if not text or not text.strip():
        if return_full:
            return [], CiteCheckResult(model_version="citechecker-mock-v1")
        return []

    service = create_cite_checker_service()
    result = service.check_cites(text, discipline, intent)

    issues = cite_check_to_frontend(result)

    if return_full:
        return issues, result
    return issues


# ═══════════════════════════════════════════════════════════════
# CiteCheckerService
# ═══════════════════════════════════════════════════════════════

class CiteCheckerService:
    """Writefull Cite API 封装。

    当前为 Mock 模式——返回固定示例数据，完全不分析输入文本。
    对标 MockService 的设计原则: "越简单越好，方便后期直接替换"。

    接入真实 Writefull Cite API 时:
      1. 设置 WRITEFULL_API_KEY 环境变量
      2. 在 _call_api() 中实现 HTTP 请求
      3. 删除 _mock_check_cites()
    """

    MAX_INPUT_LENGTH = 100000  # 单次检测最大字符数

    def __init__(self, api_key: str = "", api_url: str = ""):
        self._api_key = api_key
        self._api_url = api_url or _WRITEFULL_API_URL

    @property
    def name(self) -> str:
        return "CiteCheckerService (mock mode)" if not self._api_key else "CiteCheckerService"

    def health_check(self) -> dict:
        if self._api_key:
            return {
                "status": "ok",
                "message": f"Writefull Cite API configured ({self._api_url})",
                "quota_remaining": None,
            }
        return {
            "status": "degraded",
            "message": "Mock mode — 设置 WRITEFULL_API_KEY 以接入真实 Cite API",
            "quota_remaining": None,
        }

    # ── 公共方法 ─────────────────────────────────────────────

    def check_cites(
        self,
        text: str,
        discipline: str = "general",
        intent: str = "",
    ) -> CiteCheckResult:
        """三阶段审计流水线（P17）。"""
        if not text or not text.strip():
            return CiteCheckResult(model_version="citechecker-mock-v1")
        if len(text) > self.MAX_INPUT_LENGTH:
            text = text[:self.MAX_INPUT_LENGTH]

        # LaTeX 保护: strip
        protected_text, latex_map = self._strip_latex(text)

        # ── 阶段 1: Writefull Cite API（Mock 模式）──
        try:
            if self._api_key:
                raw = self._call_api(protected_text, discipline=discipline, intent=intent)
            else:
                raw = self._mock_check_cites()
        except Exception as e:
            logger.error(f"引用检测失败: {e}")
            raise

        # ── 阶段 2: 正则过滤 — 检查已有引用标记 ──
        claims = []
        total_sentences = self._count_sentences(protected_text)
        cited = 0

        for item in raw.get("claims", []):
            raw_sentence = item.get("sentence", "")
            # LaTeX 恢复
            sentence = self._restore_latex(raw_sentence, latex_map)
            sentence = re.sub(r'<<LATEX_\d+>>', '', sentence).strip()

            # 检查是否已有引用标记
            has_citation = self._has_citation_marker(sentence)
            if has_citation:
                cited += 1
                continue  # 过滤掉，不报告

            # 阶段 3 推荐（Mock 空列表）
            claims.append(CitationIssue(
                sentence=sentence,
                line=item.get("line", 1),
                reason=item.get("reason", ""),
                risk_level=item.get("risk_level", "medium"),
                confidence=float(item.get("confidence", 0.0)),
                suggested_action=item.get("suggested_action", ""),
                recommended_citations=item.get("recommended_citations", []),
            ))

        return CiteCheckResult(
            issues=claims,
            total_sentences=total_sentences,
            cited_sentences=cited,
            uncited_claims=len(claims),
            model_version=raw.get("model_version", "citechecker-mock-v1"),
        )

    # ── 阶段 2 辅助: 引用标记检测（P18 正则引擎）───────────

    @staticmethod
    def _has_citation_marker(sentence: str) -> bool:
        """检查句子是否已有引用标记。

        解析格式（P18）:
          \\cite{...}、\\citep{...}、\\citet{...} 等 LaTeX 命令
          [1]、[1,2]、[1-3] 数字引用
          (Author, 2020)、(Smith et al., 2021) 作者-年份
        """
        return bool(
            _LATEX_CITE_RE.search(sentence) or
            _BRACKET_CITE_RE.search(sentence) or
            _AUTHOR_YEAR_RE.search(sentence) or
            _SUPERSCRIPT_CITE_RE.search(sentence)
        )

    @staticmethod
    def _count_sentences(text: str) -> int:
        """粗略统计句子数。"""
        return max(1, len(re.split(r'[.!?]\s+', text)))

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
        discipline: str = "general",
        intent: str = "",
    ) -> dict:
        """调用 Writefull Cite API。

        TODO: 接入真实 API。
        替换以下伪代码为实际 HTTP 请求:

            import httpx
            headers = {
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "text": text,
                "discipline": discipline,
                "intent": intent,
            }
            response = httpx.post(
                f"{self._api_url}/cite/check",
                json=payload, headers=headers, timeout=60,
            )
            response.raise_for_status()
            return response.json()
        """
        raise NotImplementedError(
            "Writefull Cite API 接入待实现。设置 WRITEFULL_API_KEY 后替换此方法。\n"
            "当前使用 Mock 模式——返回固定示例数据。"
        )

    # ── Mock 实现（最简固定数据，完全不分析输入文本）──────────
    # 对标 MockService: 返回固定示例，仅用于验证流水线连通性。
    # 接入真实 API 后直接删除此方法。

    @staticmethod
    def _mock_check_cites() -> dict:
        """返回固定示例引用检测结果。不分析输入文本。

        三阶段审计流水线的 Mock:
          阶段 1 — 固定 4 条 Claim（模拟高召回策略）
          阶段 2 — 4 条中 1 条已被正则过滤（模拟有已有引用的句子）
          阶段 3 — 空推荐列表（Mock 不调用 Semantic Scholar）
        """
        return {
            "claims": [
                {
                    "sentence": "Recent studies have shown that transformer-based "
                                "models achieve state-of-the-art performance on a "
                                "wide range of NLP benchmarks.",
                    "line": 3,
                    "reason": "This statement references external research findings "
                             "that require citation support.",
                    "risk_level": "high",
                    "confidence": 0.94,
                    "suggested_action": "Add citations to recent transformer "
                                        "benchmarking studies (e.g., Vaswani et al., "
                                        "2017; Devlin et al., 2019).",
                    "recommended_citations": [],
                },
                {
                    "sentence": "Prior work has demonstrated that fine-tuning "
                                "pre-trained language models significantly improves "
                                "downstream task accuracy.",
                    "line": 7,
                    "reason": "This sentence references prior work without providing "
                             "specific citations.",
                    "risk_level": "high",
                    "confidence": 0.91,
                    "suggested_action": "Add citations to foundational fine-tuning "
                                        "papers (e.g., Howard & Ruder, 2018; "
                                        "Radford et al., 2018).",
                    "recommended_citations": [],
                },
                {
                    "sentence": "It is well known that deeper networks can capture "
                                "more complex feature representations.",
                    "line": 12,
                    "reason": "This appears to be common knowledge in the deep "
                             "learning community, but may benefit from a citation "
                             "in interdisciplinary contexts.",
                    "risk_level": "low",
                    "confidence": 0.45,
                    "suggested_action": "Consider adding a supporting citation if "
                                        "the target audience includes non-experts. "
                                        "This is a gray-area claim — final decision "
                                        "is left to the author.",
                    "recommended_citations": [],
                },
                {
                    "sentence": "The proposed method outperforms existing approaches "
                                "by 15% on the standard benchmark dataset \\cite{bengio2013}.",
                    "line": 18,
                    "reason": "This sentence already contains \\cite{...} markers. "
                              "(Filtered by Stage 2 — not reported to user)",
                    "risk_level": "medium",
                    "confidence": 0.88,
                    "suggested_action": "Citation already present. No action needed.",
                    "recommended_citations": [],
                },
            ],
            "model_version": "citechecker-mock-v1",
        }


# ═══════════════════════════════════════════════════════════════
# 服务工厂
# ═══════════════════════════════════════════════════════════════

def create_cite_checker_service(name: str | None = None) -> CiteCheckerService:
    """创建 CiteCheckerService 实例。

    对标 create_language_service() / create_generator_service()
    / create_paraphraser_service() 工厂模式。

    Args:
        name: "writefull" | "mock" | None（默认从 D_CITE_SERVICE 环境变量读取）

    Returns:
        CiteCheckerService 实例

    Raises:
        ValueError: 无效的服务名称
    """
    name = name or _ENV_CITE_SERVICE

    if name == "writefull":
        return CiteCheckerService(
            api_key=_WRITEFULL_API_KEY,
            api_url=_WRITEFULL_API_URL,
        )
    elif name == "mock":
        return CiteCheckerService()
    else:
        raise ValueError(
            f"无效的 CiteCheckerService: '{name}'。"
            f"可选值: writefull, mock。"
            f"通过环境变量 D_CITE_SERVICE 配置。"
        )