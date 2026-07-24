"""
mock_service.py — MockService: 测试用固定模拟数据

对齐任务拆解 P10 "接口适配层" + P20 "Mock服务与测试驱动开发":

  MockService 是 LanguageService 的简单实现：
    - 返回固定示例数据（不包含检查逻辑）
    - 用于: 前后端联调、自动化测试、API 不可用时的降级
    - 策略: Mock 优先 → 并行开发 → 真实接入 → 平稳切换

  与 WritefullService._mock_check() 的区别:
    - WritefullService._mock_check(): 模拟 API 返回格式，有一定文本扫描能力
    - MockService: 纯粹固定数据，完全不分析文本

用法:
    svc = MockService()
    response = svc.check_language("any text here")
    # → 返回固定的示例 Suggestion 列表
"""

from .service import LanguageService, ServiceError
from .models import LanguageFeedbackResponse, Suggestion


class MockService(LanguageService):
    """测试用 Mock 服务。

    返回固定数据，不做任何文本分析。
    用于前后端联调和自动化测试。
    """

    def __init__(self):
        self._mock_suggestions = self._build_mock_data()

    @property
    def name(self) -> str:
        return "MockService (static test data)"

    def check_language(
        self,
        text: str,
        focus: list[str] | None = None,
        context: str = "",
        intent: str = "",
    ) -> LanguageFeedbackResponse:
        """返回固定 Mock 数据。

        不分析输入文本——始终返回相同的示例响应。
        用于验证流水线（前端→API→解析→渲染）的连通性。
        """
        if not text or not text.strip():
            return LanguageFeedbackResponse(suggestions=[], quality_score=1.0)

        if len(text) > 50000:
            raise ServiceError("文本过长", code="TEXT_TOO_LONG", status=413)

        return LanguageFeedbackResponse(
            suggestions=self._mock_suggestions,
            quality_score=0.85,
            word_count=len(text.split()),
            model_version="mock-test-v1",
        )

    def health_check(self) -> dict:
        return {
            "status": "ok",
            "message": "MockService is always available",
            "quota_remaining": None,
        }

    @staticmethod
    def _build_mock_data() -> list[Suggestion]:
        """构建固定的示例 Suggestion 数据。

        模拟 Writefull API 可能返回的典型修改建议。
        """
        return [
            Suggestion(
                start=0, end=12,
                original="The results",
                replacement="The findings",
                type="style",
                reason="'results' → 'findings' is preferred in academic writing for qualitative outcomes",
                confidence=0.85,
            ),
            Suggestion(
                start=24, end=29,
                original="shows",
                replacement="demonstrates",
                type="style",
                reason="'show' is informal in academic context; consider 'demonstrate' or 'indicate'",
                confidence=0.88,
            ),
            Suggestion(
                start=36, end=42,
                original="a lot",
                replacement="a substantial amount",
                type="style",
                reason="'a lot' is informal; use quantitative or formal alternative",
                confidence=0.92,
            ),
        ]
