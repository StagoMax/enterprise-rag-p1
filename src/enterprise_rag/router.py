import re

from enterprise_rag.models import Route, RouteDecision


class RuleBasedRouter:
    """Auditable P1 baseline. A learned router can replace it behind this contract."""

    _action_patterns = (
        r"^\s*(?:please\s+)?(?:create|delete|update|approve|submit|cancel)\b",
        r"请.{0,12}(?:创建|删除|修改|审批|提交|取消|执行)",
    )
    _tool_patterns = (
        r"销售额|订单数量|总计|合计|平均值|最大值|最小值|多少条",
        r"\b(total|sum|average|count|revenue|sales)\b",
    )
    _exact_patterns = (
        r"错误码|编号|版本号|文档号|条款号",
        r"\b[A-Z]{2,10}-\d{2,10}\b",
        r"\bswg\w+\b",
        r"\bdocument\s+(?:id|number)\b",
    )

    @staticmethod
    def _matches(patterns: tuple[str, ...], question: str) -> bool:
        return any(re.search(pattern, question, flags=re.IGNORECASE) for pattern in patterns)

    def route(self, question: str) -> RouteDecision:
        if self._matches(self._action_patterns, question):
            return RouteDecision(
                route=Route.HANDOFF_OR_REFUSE,
                confidence=0.98,
                reason="请求包含执行或修改动作，P1 只允许只读访问",
                requires_citation=False,
            )
        if self._matches(self._tool_patterns, question):
            return RouteDecision(
                route=Route.TOOL,
                confidence=0.92,
                reason="问题要求结构化聚合或精确数值，应查询权威数据库",
            )
        if self._matches(self._exact_patterns, question):
            return RouteDecision(
                route=Route.EXACT_SEARCH,
                confidence=0.9,
                reason="问题包含编号、错误码或版本等精确定位条件",
            )
        return RouteDecision(
            route=Route.RAG,
            confidence=0.75,
            reason="问题需要从企业专属文档中检索并解释",
        )
