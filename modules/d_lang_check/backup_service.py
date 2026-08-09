"""
backup_service.py — BackupLLMService: 备用大模型 fallback

对齐任务拆解 P10 "接口适配层" + P28 "MVP版本定位":

  当 Writefull API 不可用时，降级到通用 LLM（OpenAI / Anthropic / DeepSeek）。
  使用学术 Prompt 模拟 Writefull 的行为。

  Prompt 工程（任务拆解 P30）:
    - System: "拥有 20 年审稿经验的顶刊 IEEE/Nature 独立审稿人"
    - 六项绝对禁止修改规则
    - 结构化输出: JSON 数组 [{type, line, message, fix}]

  当前状态: Stub。接入 LLM 时替换 _call_llm() 方法。

配置:
  BACKUP_LLM_MODEL   — 模型名 (默认: claude-haiku-4-5)
  BACKUP_LLM_API_KEY — API key 环境变量名 (默认: ANTHROPIC_API_KEY)
"""

from __future__ import annotations

import json
import os
import logging
from typing import Optional

from .service import LanguageService, ServiceError
from .models import LanguageFeedbackResponse, Suggestion

logger = logging.getLogger("autoresearch.d_lang_check.backup")


class BackupLLMService(LanguageService):
    """备用 LLM 语言检查服务。

    当 Writefull API 不可用时自动降级到此服务。
    使用通用 LLM + 学术 Prompt 模拟 Writefull 行为。
    """

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
    ):
        self._model = model or os.environ.get("BACKUP_LLM_MODEL", "claude-haiku-4-5")
        self._api_key = api_key or os.environ.get(
            os.environ.get("BACKUP_LLM_API_KEY_ENV", "ANTHROPIC_API_KEY"), ""
        )

    @property
    def name(self) -> str:
        return f"BackupLLMService ({self._model})"

    def check_language(
        self,
        text: str,
        focus: list[str] | None = None,
        context: str = "",
        intent: str = "",
    ) -> LanguageFeedbackResponse:
        """调用备用 LLM 进行语言检查。"""
        if not text or not text.strip():
            return LanguageFeedbackResponse(suggestions=[], quality_score=1.0)

        if len(text) > 50000:
            raise ServiceError("文本过长", code="TEXT_TOO_LONG", status=413)

        if not self._api_key:
            raise ServiceError(
                f"备用 LLM 未配置 API key (环境变量: {os.environ.get('BACKUP_LLM_API_KEY_ENV', 'ANTHROPIC_API_KEY')})",
                code="NO_API_KEY", status=401,
            )

        # TODO: 调用 LLM API
        # prompt = self._build_prompt(text, focus, context, intent)
        # raw = self._call_llm(prompt)
        # return self._parse_response(raw)

        raise NotImplementedError(
            "BackupLLMService._call_llm() 待实现。"
            "接入 LLM API 后，此服务将作为 Writefull 的降级备选。"
        )

    def health_check(self) -> dict:
        if self._api_key:
            return {"status": "ok", "message": f"Backup LLM ({self._model}) configured"}
        return {
            "status": "degraded",
            "message": f"API key not set. Set ANTHROPIC_API_KEY or BACKUP_LLM_API_KEY_ENV.",
            "quota_remaining": None,
        }

    # ── Prompt 模板（任务拆解 P30）───────────────────────────

    PROMPT_TEMPLATE = """You are an independent reviewer with 20 years of experience for top journals (IEEE/Nature).

Review the following academic text for language issues: {focus}

## Absolute Prohibitions (DO NOT modify):
1. Do NOT change the original meaning or conclusions
2. Do NOT add experimental results or data
3. Do NOT change numbers, units, or measurements
4. Do NOT change person names or technical terminology
5. Do NOT delete any citations (\\cite{...})
6. Do NOT modify mathematical formulas or equations

{context}
{intent}
## Text to review:
---
{text}
---

Return a JSON array of issues found:
[
  {{
    "type": "grammar|spelling|punctuation|style|phrasing",
    "start": <char_offset_start>,
    "end": <char_offset_end>,
    "original": "<original text>",
    "replacement": "<suggested replacement>",
    "reason": "<explanation>",
    "confidence": <0.0-1.0>
  }}
]

Return ONLY the JSON array, no other text."""

    def _build_prompt(
        self,
        text: str,
        focus: list[str] | None,
        context: str,
        intent: str,
    ) -> str:
        dims = ", ".join(focus) if focus else "grammar, spelling, punctuation, style"
        ctx_block = f"\n## Context:\n{context}" if context else ""
        intent_block = f"\n## User Intent:\n{intent}" if intent else ""
        return self.PROMPT_TEMPLATE.format(
            focus=dims,
            context=ctx_block,
            intent=intent_block,
            text=text,
        )

    def _call_llm(self, prompt: str) -> str:
        """调用 LLM API。

        TODO: 接入实际 LLM API。
        """
        raise NotImplementedError("_call_llm() 待实现")
