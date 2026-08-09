"""
academizer.py — AcademizerService: 封装 Writefull Academizer API

对齐任务拆解 P12 "双轨制转换算法" + P30 "Academizer Prompt 工程":

  Writefull Academizer API:
    - 输入: text + discipline 标签 + style_strength
    - 输出: academized_text + 逐条变更记录
    - 模型: Writefull 预训练的风格转换模型，在海量学术语料上优化

  我们的增强层（任务拆解 P9）:
    - 学科标签参数: [Computer Science], [Biology], [Medicine], [Physics], [General]
    - 六项绝对禁止修改规则（任务拆解 P30）
    - LaTeX 命令保护（拆装法 P23）

用法:
    from modules.d_lang_check.academizer import academize

    result = academize("We did a test.", discipline="computer-science")
    # → "An empirical investigation was conducted..."

    result, response = academize(..., return_full=True)
    # → (str, AcademizerResponse)  获取完整变更记录
"""

from __future__ import annotations

import json
import os
import re
import logging
from typing import Optional

from .models import AcademizerResponse, AcademizerChange

logger = logging.getLogger("autoresearch.d_lang_check.academizer")


# ═══════════════════════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════════════════════

_ENV_ACADEMIZER_SERVICE = os.environ.get("D_ACADEMIZER_SERVICE", "writefull")
_WRITEFULL_API_KEY = os.environ.get("WRITEFULL_API_KEY", "")
_WRITEFULL_API_URL = os.environ.get("WRITEFULL_API_URL", "https://api.writefull.com/v1")

# 支持的学科标签
VALID_DISCIPLINES = {
    "computer-science", "biology", "medicine", "physics",
    "chemistry", "engineering", "mathematics", "general",
}

# 支持的转换强度
VALID_STRENGTHS = {"light", "moderate", "heavy"}


# ═══════════════════════════════════════════════════════════════
# 公开接口
# ═══════════════════════════════════════════════════════════════

def academize(
    text: str,
    discipline: str = "general",
    style_strength: str = "moderate",
    return_full: bool = False,
) -> str | tuple[str, AcademizerResponse]:
    """调用 Writefull Academizer API 进行学术风格转换。

    Args:
        text:           待转换的文本
        discipline:     学科标签: computer-science | biology | medicine | physics | general
        style_strength: 转换强度: light | moderate | heavy
        return_full:    若 True，额外返回完整 AcademizerResponse

    Returns:
        str（return_full=False）或 (str, AcademizerResponse)

    Raises:
        ValueError: 无效的 discipline 或 style_strength

    Example:
        >>> academize("We did a test.", discipline="computer-science")
        "An empirical investigation was conducted..."
    """
    if discipline not in VALID_DISCIPLINES:
        raise ValueError(
            f"无效的学科标签: '{discipline}'。可选值: {sorted(VALID_DISCIPLINES)}"
        )
    if style_strength not in VALID_STRENGTHS:
        raise ValueError(
            f"无效的转换强度: '{style_strength}'。可选值: {sorted(VALID_STRENGTHS)}"
        )
    if not text or not text.strip():
        if return_full:
            return text, AcademizerResponse(
                academized_text=text,
                discipline=discipline,
                style_strength=style_strength,
            )
        return text

    service = create_academizer_service()

    response = service.academize(text, discipline, style_strength)

    if return_full:
        return response.academized_text, response
    return response.academized_text


# ═══════════════════════════════════════════════════════════════
# AcademizerService
# ═══════════════════════════════════════════════════════════════

class AcademizerService:
    """Writefull Academizer API 封装。

    当前为 Mock 模式——返回模拟的学术风格转换结果。
    接入真实 Writefull Academizer API 时:
      1. 设置 WRITEFULL_API_KEY 环境变量
      2. 在 _call_api() 中实现 HTTP 请求
      3. Mock 保留作为降级备选

    Writefull Academizer API 规范（预期）:
      - 端点: POST /v1/academizer/convert
      - 认证: Bearer token
      - 请求: {text, discipline, style_strength, options}
      - 响应: {academized_text, changes: [{original, replacement, rationale}], discipline, style_strength}
    """

    # 学术 Prompt（任务拆解 P30）
    SYSTEM_PROMPT = (
        "You are an independent reviewer with 20 years of experience "
        "for top journals (IEEE/Nature). Your task is to convert informal, "
        "colloquial text into formal academic writing style suitable for "
        "publication in a top-tier scientific journal."
    )

    # 六项绝对禁止修改规则（任务拆解 P30）
    PROHIBITED_MODIFICATIONS = [
        "Do NOT change the original meaning or conclusions",
        "Do NOT add experimental results, data, or findings not present in the original",
        "Do NOT change numbers, units, or measurements",
        "Do NOT change person names, place names, or established technical terminology",
        "Do NOT delete or modify citations (\\cite{...}) or cross-references (\\ref{...})",
        "Do NOT modify mathematical formulas, equations, or LaTeX commands",
    ]

    def __init__(self, api_key: str = "", api_url: str = ""):
        self._api_key = api_key
        self._api_url = api_url or _WRITEFULL_API_URL

    @property
    def name(self) -> str:
        return "AcademizerService (mock mode)" if not self._api_key else "AcademizerService"

    def health_check(self) -> dict:
        if self._api_key:
            return {
                "status": "ok",
                "message": f"Writefull Academizer API configured ({self._api_url})",
                "quota_remaining": None,
            }
        return {
            "status": "degraded",
            "message": "Mock mode - set WRITEFULL_API_KEY to connect real Academizer API",
            "quota_remaining": None,
        }

    def academize(
        self,
        text: str,
        discipline: str = "general",
        style_strength: str = "moderate",
    ) -> AcademizerResponse:
        """调用 Writefull Academizer API。

        Args:
            text:           待转换文本
            discipline:     学科标签
            style_strength: 转换强度

        Returns:
            AcademizerResponse
        """
        if not text or not text.strip():
            return AcademizerResponse(
                academized_text=text,
                discipline=discipline,
                style_strength=style_strength,
            )

        # LaTeX 保护：标记 LaTeX 命令（拆装法 Strip 阶段）
        protected_text, latex_map = self._strip_latex(text)

        # 调用 API
        try:
            if self._api_key:
                raw = self._call_api(protected_text, discipline, style_strength)
            else:
                raw = self._mock_academize()
        except Exception as e:
            logger.error(f"Academizer API 失败: {e}")
            raise

        # LaTeX 恢复：将 LaTeX 命令装回（拆装法 Restore 阶段）
        academized = self._restore_latex(raw.get("academized_text", text), latex_map)

        changes = [
            AcademizerChange(
                original=c.get("original", ""),
                replacement=c.get("replacement", ""),
                rationale=c.get("rationale", ""),
            )
            for c in raw.get("changes", [])
        ]

        return AcademizerResponse(
            academized_text=academized,
            changes=changes,
            discipline=discipline,
            style_strength=style_strength,
        )

    # ── LaTeX 保护: Strip / Restore（任务拆解 P23 "拆装法"）─

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

        # 保护: cite/ref/label/公式/环境块
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
        discipline: str,
        style_strength: str,
    ) -> dict:
        """调用 Writefull Academizer API。

        TODO: 接入真实 API。
        """
        raise NotImplementedError(
            "Writefull Academizer API 接入待实现。"
            "设置 WRITEFULL_API_KEY 后替换此方法。"
        )

    # ── Mock 实现 ────────────────────────────────────────────

    @staticmethod
    def _mock_academize() -> dict:
        """返回固定示例学术改写。不分析输入文本。

        对标 GeneratorService / ParaphraserService / CiteCheckerService 的 mock 模式：
        固定数据，仅用于验证流水线连通性。
        接入真实 API 后直接删除。
        """
        return {
            "academized_text": (
                "We conducted a substantial number of experiments to determine "
                "whether the proposed methodology is effective. The results "
                "indicate that the approach yields significant improvements "
                "across multiple evaluation metrics."
            ),
            "changes": [
                {
                    "original": "did a lot of tests",
                    "replacement": "conducted a substantial number of experiments",
                    "rationale": "Academic phrasing: informal 'did a lot of tests' replaced with formal 'conducted a substantial number of experiments'",
                },
                {
                    "original": "find out if",
                    "replacement": "determine whether",
                    "rationale": "Academic phrasing: informal 'find out if' replaced with formal 'determine whether'",
                },
                {
                    "original": "works",
                    "replacement": "yields significant improvements",
                    "rationale": "Academic phrasing: vague 'works' replaced with precise 'yields significant improvements'",
                },
            ],
        }


# ================================================================
# Service Factory
# ================================================================

def create_academizer_service(name: str | None = None) -> AcademizerService:
    """Create AcademizerService instance.
    Reads D_ACADEMIZER_SERVICE env var (default: writefull).
    """
    name = name or _ENV_ACADEMIZER_SERVICE
    if name == "writefull":
        return AcademizerService(api_key=_WRITEFULL_API_KEY, api_url=_WRITEFULL_API_URL)
    elif name == "mock":
        return AcademizerService()
    else:
        raise ValueError(
            f"Invalid AcademizerService: '{name}'. Valid: writefull, mock. Configure via D_ACADEMIZER_SERVICE."
        )
