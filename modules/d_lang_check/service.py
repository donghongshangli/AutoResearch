"""
service.py — LanguageService 抽象接口 + 服务工厂

对齐任务拆解 P10 "接口适配层"设计:
  LanguageService (ABC)
    ├── WritefullService   ← 主力: 封装 Writefull Language API
    ├── MockService        ← 测试: 固定模拟数据
    └── BackupLLMService   ← 备用: LLM fallback

配置方式 (环境变量):
  D_LANG_SERVICE=writefull  → WritefullService（默认）
  D_LANG_SERVICE=mock       → MockService
  D_LANG_SERVICE=backup     → BackupLLMService

依赖隔离: 上层模块只依赖 LanguageService 接口，不感知具体实现。
"""

from __future__ import annotations

import os
import logging
from abc import ABC, abstractmethod
from typing import Optional

from .models import LanguageFeedbackResponse, CheckResult

logger = logging.getLogger("autoresearch.d_lang_check.service")

# 环境变量配置
_ENV_SERVICE = os.environ.get("D_LANG_SERVICE", "writefull")
_ENV_WRITEFULL_API_KEY = os.environ.get("WRITEFULL_API_KEY", "")
_ENV_WRITEFULL_API_URL = os.environ.get("WRITEFULL_API_URL", "https://api.writefull.com/v1")


# ═══════════════════════════════════════════════════════════════
# 抽象接口
# ═══════════════════════════════════════════════════════════════

class LanguageService(ABC):
    """Writefull 语言服务的抽象接口。

    所有实现（Writefull / Mock / BackupLLM）必须实现此接口。
    上层模块只依赖此接口，不感知底层 API 细节。
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """服务标识名称，用于日志和调试。"""
        ...

    @abstractmethod
    def check_language(
        self,
        text: str,
        focus: list[str] | None = None,
        context: str = "",
        intent: str = "",
    ) -> LanguageFeedbackResponse:
        """调用语言检查服务。

        Args:
            text:    待检查的文本（LaTeX 源码）
            focus:   检查维度列表，空=全查
            context: 框架组装的上下文包 (L1-L5)
            intent:  用户补充意图

        Returns:
            LanguageFeedbackResponse: 包含 suggestions 列表 + 质量评分

        Raises:
            ServiceError: API 调用失败时抛出（上层负责降级）
        """
        ...

    @abstractmethod
    def health_check(self) -> dict:
        """健康检查: 服务是否可用。

        Returns:
            {"status": "ok"|"degraded"|"unavailable", "message": "...", "quota_remaining": int|None}
        """
        ...

    def preprocess(self, text: str) -> str:
        """预处理钩子: API 调用前的文本清洗。

        子类可重写。默认不做处理。
        增强层（针对中文母语者常见错误）在此实现。
        """
        return text

    def postprocess(self, response: LanguageFeedbackResponse) -> LanguageFeedbackResponse:
        """后处理钩子: API 响应后的增强过滤。

        子类可重写。默认不做处理。
        可用于: 去重、置信度过滤、格式标准化。
        """
        return response


class ServiceError(Exception):
    """语言服务异常。"""
    def __init__(self, message: str, code: str = "SERVICE_ERROR", status: int = 500):
        super().__init__(message)
        self.code = code
        self.status = status


# ═══════════════════════════════════════════════════════════════
# 服务工厂
# ═══════════════════════════════════════════════════════════════

def create_language_service(name: str | None = None) -> LanguageService:
    """创建 LanguageService 实例。

    Args:
        name: "writefull" | "mock" | "backup" | None（默认从 D_LANG_SERVICE 环境变量读取）

    Returns:
        LanguageService 实例

    Raises:
        ValueError: 无效的服务名称
    """
    name = name or _ENV_SERVICE

    if name == "writefull":
        from .writefull_service import WritefullService
        return WritefullService(
            api_key=_ENV_WRITEFULL_API_KEY,
            api_url=_ENV_WRITEFULL_API_URL,
        )
    elif name == "mock":
        from .mock_service import MockService
        return MockService()
    elif name == "backup":
        from .backup_service import BackupLLMService
        return BackupLLMService()
    else:
        raise ValueError(
            f"无效的 LanguageService: '{name}'。"
            f"可选值: writefull, mock, backup。"
            f"通过环境变量 D_LANG_SERVICE 配置。"
        )


def get_available_services() -> dict[str, str]:
    """列出所有可用的语言服务及其状态。"""
    services = {}
    for name in ["writefull", "mock", "backup"]:
        try:
            svc = create_language_service(name)
            health = svc.health_check()
            services[name] = health.get("status", "unknown")
        except Exception as e:
            services[name] = f"error: {e}"
    return services
