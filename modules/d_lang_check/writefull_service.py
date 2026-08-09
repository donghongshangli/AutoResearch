"""
writefull_service.py — WritefullService: 封装 Writefull Language API

对齐任务拆解 P9 "Writefull API 接入策略" + P30 "八步处理流水线":

  处理流水线:
    1. 接收文本
    2. 空值检查 → (400 拒绝)
    3. 长度校验 → (413 截断提示)
    4. 调用 preprocess() 增强层（中文母语者常见错误预处理）
    5. 调用 Writefull Language API（当前 Mock 模式）
    6. 解析 JSON 响应 → Suggestion 列表
    7. 调用 postprocess() 增强层（去重、置信度过滤）
    8. 返回 LanguageFeedbackResponse + 异常兜底

Writefull Language API 规范:
  - 端点: POST /v1/language/check
  - 认证: Bearer token (WRITEFULL_API_KEY)
  - 请求: {text, focus, context, options}
  - 响应: {suggestions: [{start, end, original, replacement, type, reason, confidence}], quality_score}

当前状态: API token 待申请，使用 _mock_check() 模拟真实 API 行为。
接入真实 API 时只需替换 _call_api() 方法。
"""

from __future__ import annotations

import json
import os
import re
import logging
from typing import Optional

from .service import LanguageService, ServiceError
from .models import (
    LanguageFeedbackResponse,
    Suggestion,
    CheckResult,
    suggestion_to_check_result,
)

logger = logging.getLogger("autoresearch.d_lang_check.writefull")


# ═══════════════════════════════════════════════════════════════
# WritefullService
# ═══════════════════════════════════════════════════════════════

class WritefullService(LanguageService):
    """Writefull Language API 封装。

    当前为 Mock 模式——返回符合 Writefull API 格式的模拟数据。
    接入真实 API 时:
      1. 设置环境变量 WRITEFULL_API_KEY
      2. 在 _call_api() 中实现 HTTP 请求
      3. Mock 保留作为降级备选

    增强层（任务拆解 P9 "我们的工作"）:
      - preprocess(): 中文母语者常见错误模式预处理
      - postprocess(): 去重、LaTeX 保护过滤
    """

    MAX_TEXT_LENGTH = 50000  # 单次检查最大字符数

    def __init__(
        self,
        api_key: str = "",
        api_url: str = "https://api.writefull.com/v1",
    ):
        self._api_key = api_key
        self._api_url = api_url

    @property
    def name(self) -> str:
        return "WritefullService (mock mode)" if not self._api_key else "WritefullService"

    # ── 公共接口 ─────────────────────────────────────────────

    def check_language(
        self,
        text: str,
        focus: list[str] | None = None,
        context: str = "",
        intent: str = "",
    ) -> LanguageFeedbackResponse:
        """调用 Writefull Language API 检查文本。

        八步流水线（任务拆解 P30）。
        """
        # 1-3. 输入校验
        if not text or not text.strip():
            return LanguageFeedbackResponse(suggestions=[], quality_score=1.0)

        if len(text) > self.MAX_TEXT_LENGTH:
            raise ServiceError(
                f"文本过长 ({len(text)} 字符，上限 {self.MAX_TEXT_LENGTH})",
                code="TEXT_TOO_LONG", status=413,
            )

        # 4. 增强层预处理（中文母语者常见错误）
        processed_text = self.preprocess(text)

        # 5. 调用 Writefull API
        try:
            if self._api_key:
                raw_response = self._call_api(processed_text, focus, context, intent)
            else:
                # Mock 模式: 返回符合 API 格式的模拟数据
                raw_response = self._mock_check(processed_text, focus or [])
        except ServiceError:
            raise
        except Exception as e:
            logger.error(f"Writefull API 调用失败: {e}")
            raise ServiceError(
                f"Writefull API 不可用: {e}",
                code="API_ERROR", status=502,
            )

        # 6. 解析响应
        response = self._parse_response(raw_response, text)

        # 7. 增强层后处理
        response = self.postprocess(response)

        # 8. 返回
        return response

    def health_check(self) -> dict:
        if self._api_key:
            return {
                "status": "ok",
                "message": f"Writefull API configured ({self._api_url})",
                "quota_remaining": None,
            }
        return {
            "status": "degraded",
            "message": "Mock mode — 设置 WRITEFULL_API_KEY 环境变量以接入真实 API",
            "quota_remaining": None,
        }

    # ── 增强层: 预处理 ───────────────────────────────────────

    def preprocess(self, text: str) -> str:
        """预处理: 中文母语者常见错误模式增强。

        规则（来自任务拆解 P8 "中式英语优化"）:
          - 连续动词流水句检测 → 标记为待检查
          - 中文标点 → 替换为英文标点（不修改原文，仅在分析时替换）
        """
        # 这里不做修改——Writefull API 本身支持中文母语者的错误检测。
        # 预处理仅做标记和日志记录。
        # 未来可根据 Writefull API 的实际行为添加定制预处理规则。
        return text

    def postprocess(self, response: LanguageFeedbackResponse) -> LanguageFeedbackResponse:
        """后处理增强:
        1. 去重: 移除位置重叠的重复建议
        2. 置信度过滤: 低于阈值的建议降级为 info
        3. LaTeX 保护区过滤: 由上层 latex_protect.py 处理
        """
        if not response.suggestions:
            return response

        # 去重: 同一位置的建议只保留置信度最高的
        seen: dict[tuple[int, int], Suggestion] = {}
        for sug in response.suggestions:
            key = (sug.start, sug.end)
            if key not in seen or sug.confidence > seen[key].confidence:
                seen[key] = sug

        response.suggestions = sorted(
            seen.values(), key=lambda s: (s.start, s.confidence),
        )
        return response

    # ── API 调用（Stub — 接入时替换）────────────────────────

    def _call_api(
        self,
        text: str,
        focus: list[str] | None,
        context: str,
        intent: str,
    ) -> dict:
        """调用 Writefull Language API。

        TODO: 接入真实 Writefull API。
        替换以下伪代码为实际 HTTP 请求:

            import httpx
            headers = {
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "text": text,
                "focus": focus or [],
                "context": context,
                "intent": intent,
                "format": "json",   # 或 "track_changes" (Word 兼容)
            }
            response = httpx.post(
                f"{self._api_url}/language/check",
                json=payload,
                headers=headers,
                timeout=30,
            )
            response.raise_for_status()
            return response.json()
        """
        raise NotImplementedError(
            "Writefull API 接入待实现。设置 WRITEFULL_API_KEY 后替换此方法。\n"
            "当前使用 Mock 模式——调用 _mock_check() 返回模拟数据。"
        )

    def _parse_response(self, raw: dict, original_text: str) -> LanguageFeedbackResponse:
        """解析 Writefull API JSON 响应 → LanguageFeedbackResponse。"""
        suggestions = []
        for item in raw.get("suggestions", []):
            suggestions.append(Suggestion(
                start=int(item.get("start", 0)),
                end=int(item.get("end", 0)),
                original=item.get("original", ""),
                replacement=item.get("replacement", ""),
                type=item.get("type", ""),
                reason=item.get("reason", ""),
                confidence=float(item.get("confidence", 1.0)),
            ))

        return LanguageFeedbackResponse(
            suggestions=suggestions,
            quality_score=float(raw.get("quality_score", 0.0)),
            word_count=int(raw.get("word_count", len(original_text.split()))),
            model_version=raw.get("model_version", "writefull-mock-v1"),
        )

    # ── Mock 实现 ────────────────────────────────────────────
    # 最小 Mock: 仅用于验证流水线连通性。
    # 不做真实检查——真实检查由 Writefull API 提供。
    # 接入 API 后删除 _mock_check()，替换为 _call_api() 的 HTTP 实现。

    def _mock_check(self, text: str, focus: list[str]) -> dict:
        """Mock Writefull Language API 响应。

        返回最小示例数据以验证流水线。
        接入真实 Writefull API 后此方法直接删除。
        """
        suggestions = []

        # 仅检测最明显的 3 类问题作为示例
        # 1. 常见拼写错误 (5 个高频词)
        for wrong, correct in [
            ("recieve", "receive"), ("seperate", "separate"),
            ("independant", "independent"), ("acheive", "achieve"),
            ("succesful", "successful"),
        ]:
            for m in re.finditer(r'\b' + wrong + r'\b', text, re.IGNORECASE):
                suggestions.append(Suggestion(
                    start=m.start(), end=m.end(),
                    original=m.group(), replacement=correct,
                    type="spelling",
                    reason=f"Spelling: '{wrong}' → '{correct}'",
                    confidence=0.96,
                ))

        # 2. 中文标点混入 (我们的增强层)
        for cn, en in {'，': ',', '。': '.', '：': ':', '；': ';'}.items():
            for m in re.finditer(re.escape(cn), text):
                suggestions.append(Suggestion(
                    start=m.start(), end=m.end(),
                    original=cn, replacement=en,
                    type="punctuation",
                    reason=f"Chinese punctuation '{cn}' in English text → '{en}'",
                    confidence=0.99,
                ))

        # 3. 缩略形式
        for m in re.finditer(
            r"\b(don't|doesn't|isn't|aren't|wasn't|weren't|haven't|hasn't|"
            r"won't|wouldn't|shouldn't|couldn't|can't)\b",
            text, re.IGNORECASE,
        ):
            suggestions.append(Suggestion(
                start=m.start(), end=m.end(),
                original=m.group(), replacement="",
                type="style",
                reason=f"Avoid contraction '{m.group()}' in academic writing",
                confidence=0.92,
            ))

        # 质量评分
        total_words = len(text.split())
        issue_count = len(suggestions)
        score = max(0.0, min(1.0, 1.0 - (issue_count * 0.05)))

        return {
            "suggestions": [
                {
                    "start": s.start, "end": s.end,
                    "original": s.original, "replacement": s.replacement,
                    "type": s.type, "reason": s.reason, "confidence": s.confidence,
                }
                for s in suggestions
            ],
            "quality_score": round(score, 2),
            "word_count": total_words,
            "model_version": "writefull-mock-v1",
        }


# ═══════════════════════════════════════════════════════════════
# 便捷函数: Writefull 格式 → 前端契约
# ═══════════════════════════════════════════════════════════════

def writefull_response_to_check_results(
    response: LanguageFeedbackResponse,
    text: str,
    source: str = "writefull",
) -> list[CheckResult]:
    """将 Writefull API 响应转为前端 CheckResult 列表。"""
    return [
        suggestion_to_check_result(sug, text, source)
        for sug in response.suggestions
    ]
