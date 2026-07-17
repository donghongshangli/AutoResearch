"""
paraphraser.py — ParaphraserService: 段落改写

对齐两周计划 Day 3 "段落改写模块" + 任务拆解 P30 "段落改写":

  五维度段落优化:
    1. 句子顺序合理性 (Sentence Order) — 依存句法分析后重排
    2. 衔接补偿 (Coherence) — 逻辑连接词增补
    3. 冗余消除 (Redundancy) — 语义相似度去重
    4. 主题句清晰度 (Topic Sentence) — 位置启发式识别
    5. 过长句子拆分 (Long Sentence) — 句法树深度阈值裁剪

  核心约束: 一次只处理一个段落（不一开始就处理整篇论文）。

  Writefull Paraphrase API 规范（预期）:
    - 端点: POST /v1/paraphrase
    - 认证: Bearer token
    - 请求: {text, style, preserve_keywords, options}
    - 响应: {rewritten_text, changes: [{original, replacement, reason}], triggered_dimensions}

当前状态: API token 待申请，使用 Mock 模式（固定示例数据，完全不分析输入文本）。
接入真实 API 时替换 _call_api() 方法，_mock_paraphrase() 直接删除。

配置:
  D_PARAPHRASE_SERVICE=writefull  主力（默认，当前 Mock 模式）
  WRITEFULL_API_KEY=xxx           真实 API key（待申请）
"""

from __future__ import annotations

import os
import re
import logging
from typing import Optional

from .models import ParaphraseChange, ParaphraseResult

logger = logging.getLogger("autoresearch.d_lang_check.paraphraser")

# 环境变量
_ENV_PARAPHRASE_SERVICE = os.environ.get("D_PARAPHRASE_SERVICE", "writefull")
_WRITEFULL_API_KEY = os.environ.get("WRITEFULL_API_KEY", "")
_WRITEFULL_API_URL = os.environ.get("WRITEFULL_API_URL", "https://api.writefull.com/v1")

# 支持的改写风格
VALID_PARAPHRASE_STYLES = {"academic", "concise", "fluent", "balanced"}

# 五维度名称（任务拆解 P30）
PARAPHRASE_DIMENSIONS = [
    "sentence_order",    # 句子顺序合理性
    "coherence",         # 衔接补偿
    "redundancy",        # 冗余消除
    "topic_sentence",    # 主题句清晰度
    "long_sentence",     # 过长句子拆分
]


# ═══════════════════════════════════════════════════════════════
# 公开接口
# ═══════════════════════════════════════════════════════════════

def paraphrase(
    text: str,
    style: str = "academic",
    preserve_keywords: list[str] | None = None,
    intent: str = "",
    return_full: bool = False,
) -> str | tuple[str, ParaphraseResult]:
    """调用生成服务，对段落进行学术改写。

    Args:
        text:              待改写的段落文本（一次一个段落）
        style:             改写风格: academic | concise | fluent | balanced
        preserve_keywords: 需要保留不变的关键词列表
        intent:            用户补充意图
        return_full:       若 True，额外返回完整 ParaphraseResult

    Returns:
        str（return_full=False）或 (str, ParaphraseResult)

    Raises:
        ValueError: 无效的 style

    Example:
        >>> result = paraphrase("The model works well on data.")
        >>> result, detail = paraphrase(..., return_full=True)
    """
    if style not in VALID_PARAPHRASE_STYLES:
        raise ValueError(
            f"无效的改写风格: '{style}'。可选值: {sorted(VALID_PARAPHRASE_STYLES)}"
        )
    if not text or not text.strip():
        if return_full:
            return "", ParaphraseResult(model_version="paraphraser-mock-v1")
        return ""

    service = create_paraphraser_service()
    result = service.paraphrase(text, style, preserve_keywords or [], intent)

    if return_full:
        return result.rewritten_text, result
    return result.rewritten_text


# ═══════════════════════════════════════════════════════════════
# ParaphraserService
# ═══════════════════════════════════════════════════════════════

class ParaphraserService:
    """Writefull Paraphrase API 封装。

    当前为 Mock 模式——返回固定示例数据，完全不分析输入文本。
    对标 MockService 的设计原则: "越简单越好，方便后期直接替换"。

    接入真实 Writefull Paraphrase API 时:
      1. 设置 WRITEFULL_API_KEY 环境变量
      2. 在 _call_api() 中实现 HTTP 请求
      3. 删除 _mock_paraphrase()
    """

    MAX_INPUT_LENGTH = 10000  # 段落改写单次最大字符数

    def __init__(self, api_key: str = "", api_url: str = ""):
        self._api_key = api_key
        self._api_url = api_url or _WRITEFULL_API_URL

    @property
    def name(self) -> str:
        return "ParaphraserService (mock mode)" if not self._api_key else "ParaphraserService"

    def health_check(self) -> dict:
        if self._api_key:
            return {
                "status": "ok",
                "message": f"Writefull Paraphrase API configured ({self._api_url})",
                "quota_remaining": None,
            }
        return {
            "status": "degraded",
            "message": "Mock mode — 设置 WRITEFULL_API_KEY 以接入真实 Paraphrase API",
            "quota_remaining": None,
        }

    # ── 公共方法 ─────────────────────────────────────────────

    def paraphrase(
        self,
        text: str,
        style: str = "academic",
        preserve_keywords: list[str] | None = None,
        intent: str = "",
    ) -> ParaphraseResult:
        """对单个段落进行学术改写。"""
        if not text or not text.strip():
            return ParaphraseResult(model_version="paraphraser-mock-v1")
        if len(text) > self.MAX_INPUT_LENGTH:
            text = text[:self.MAX_INPUT_LENGTH]

        # LaTeX 保护: strip
        protected_text, latex_map = self._strip_latex(text)

        try:
            if self._api_key:
                raw = self._call_api(
                    protected_text, style=style,
                    preserve_keywords=preserve_keywords or [], intent=intent,
                )
            else:
                raw = self._mock_paraphrase()
        except Exception as e:
            logger.error(f"段落改写失败: {e}")
            raise

        # LaTeX 保护: restore
        rewritten = self._restore_latex(raw.get("rewritten_text", ""), latex_map)
        rewritten = re.sub(r'<<LATEX_\d+>>', '', rewritten).strip()

        changes = []
        for c in raw.get("changes", []):
            orig_restored = self._restore_latex(c.get("original", ""), latex_map)
            repl_restored = self._restore_latex(c.get("replacement", ""), latex_map)
            changes.append(ParaphraseChange(
                original=re.sub(r'<<LATEX_\d+>>', '', orig_restored).strip(),
                replacement=re.sub(r'<<LATEX_\d+>>', '', repl_restored).strip(),
                reason=c.get("reason", ""),
            ))

        return ParaphraseResult(
            rewritten_text=rewritten,
            changes=changes,
            triggered_dimensions=raw.get("triggered_dimensions", []),
            model_version=raw.get("model_version", "paraphraser-mock-v1"),
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
        style: str = "academic",
        preserve_keywords: list[str] | None = None,
        intent: str = "",
    ) -> dict:
        """调用 Writefull Paraphrase API。

        TODO: 接入真实 API。
        替换以下伪代码为实际 HTTP 请求:

            import httpx
            headers = {
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "text": text,
                "style": style,
                "preserve_keywords": preserve_keywords or [],
                "intent": intent,
            }
            response = httpx.post(
                f"{self._api_url}/paraphrase",
                json=payload, headers=headers, timeout=30,
            )
            response.raise_for_status()
            return response.json()
        """
        raise NotImplementedError(
            "Writefull Paraphrase API 接入待实现。设置 WRITEFULL_API_KEY 后替换此方法。\n"
            "当前使用 Mock 模式——返回固定示例数据。"
        )

    # ── Mock 实现（最简固定数据，完全不分析输入文本）──────────
    # 对标 MockService: 返回固定示例，仅用于验证流水线连通性。
    # 接入真实 API 后直接删除此方法。

    @staticmethod
    def _mock_paraphrase() -> dict:
        """返回固定示例改写。5 维度全覆盖。不分析输入文本。"""
        return {
            "rewritten_text": (
                "The transformer-based architecture has been widely adopted across "
                "natural language processing tasks. However, its performance on small "
                "datasets remains limited due to insufficient training signals. "
                "Furthermore, the model exhibits degraded output quality under "
                "data-scarce conditions. To address these limitations, we propose "
                "integrating auxiliary pretraining objectives that leverage external "
                "knowledge sources during fine-tuning."
            ),
            "changes": [
                {
                    "original": "been widely used",
                    "replacement": "been widely adopted across",
                    "reason": "[coherence] Added domain scope for smoother flow",
                },
                {
                    "original": "perform well",
                    "replacement": "exhibits degraded output quality",
                    "reason": "[sentence_order + academic] Restructured for formal register",
                },
                {
                    "original": "doesn't work well on small datasets",
                    "replacement": "remains limited due to insufficient training signals",
                    "reason": "[redundancy] Merged with subsequent sentence; removed vague 'doesn't work well'",
                },
                {
                    "original": "However, the results show it struggles with few examples.",
                    "replacement": "Furthermore, the model exhibits degraded output quality under data-scarce conditions.",
                    "reason": "[topic_sentence] Strengthened topic sentence to clearly signal limitation",
                },
                {
                    "original": "We suggest using more data or adding extra training steps.",
                    "replacement": "To address these limitations, we propose integrating auxiliary pretraining objectives that leverage external knowledge sources during fine-tuning.",
                    "reason": "[long_sentence] Merged two short choppy sentences into one flowing complex sentence with explicit methodology",
                },
            ],
            "triggered_dimensions": [
                "sentence_order",
                "coherence",
                "redundancy",
                "topic_sentence",
                "long_sentence",
            ],
            "model_version": "paraphraser-mock-v1",
        }


# ═══════════════════════════════════════════════════════════════
# 服务工厂
# ═══════════════════════════════════════════════════════════════

def create_paraphraser_service(name: str | None = None) -> ParaphraserService:
    """创建 ParaphraserService 实例。

    对标 create_language_service() / create_generator_service() 工厂模式。

    Args:
        name: "writefull" | "mock" | None（默认从 D_PARAPHRASE_SERVICE 环境变量读取）

    Returns:
        ParaphraserService 实例

    Raises:
        ValueError: 无效的服务名称
    """
    name = name or _ENV_PARAPHRASE_SERVICE

    if name == "writefull":
        return ParaphraserService(
            api_key=_WRITEFULL_API_KEY,
            api_url=_WRITEFULL_API_URL,
        )
    elif name == "mock":
        return ParaphraserService()
    else:
        raise ValueError(
            f"无效的 ParaphraserService: '{name}'。"
            f"可选值: writefull, mock。"
            f"通过环境变量 D_PARAPHRASE_SERVICE 配置。"
        )