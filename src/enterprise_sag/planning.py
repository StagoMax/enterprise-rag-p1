from __future__ import annotations

import json
import re
from typing import Protocol

from enterprise_rag.llm import ChatModel
from enterprise_sag.models import ContextPackRequest, EvidenceNeed, RetrievalPlan

_JSON_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)
_NEED_ID = re.compile(r"^[a-z][a-z0-9_]{0,47}$")
_TIME_MODES = frozenset({"any", "latest_valid", "historical"})


class EvidenceNeedPlanner(Protocol):
    name: str

    def plan(self, request: ContextPackRequest) -> RetrievalPlan: ...


class SingleNeedPlanner:
    """Deterministic fallback that preserves the request without inventing routes."""

    name = "single-need-fallback-v1"

    def plan(self, request: ContextPackRequest) -> RetrievalPlan:
        return RetrievalPlan(
            request_id=request.request_id,
            original_query=request.query,
            purpose=request.purpose,
            needs=[
                EvidenceNeed(
                    need_id="primary_evidence",
                    description="直接回答当前请求所需的证据",
                    query=request.query,
                    subject_refs=request.subject_refs,
                    required=True,
                )
            ],
            planner=self.name,
        )


class DeepSeekEvidenceNeedPlanner:
    """Create source-agnostic evidence needs from a typed Context Pack request."""

    name = "deepseek-evidence-need-planner-v1"

    def __init__(
        self,
        chat_model: ChatModel,
        *,
        max_needs: int = 5,
        fallback: EvidenceNeedPlanner | None = None,
    ) -> None:
        if not 1 <= max_needs <= 6:
            raise ValueError("max_needs must be between 1 and 6")
        self._chat_model = chat_model
        self._max_needs = max_needs
        self._fallback = fallback or SingleNeedPlanner()

    @staticmethod
    def _system_prompt(max_needs: int) -> str:
        return f"""你是通用证据需求规划器，不是问答模型。把 ContextPackRequest 分解为 1-{max_needs}
个互不重复、可以分别检索的 EvidenceNeed。只描述需要什么证据，不回答问题。

规划必须与来源无关：不得针对文件名、文档类型、某个特定数据集设置优先级或配额。只有请求
明确需要主体背景、偏好、约束、经历、目标、时序状态或关系证据时，才建立相应 Need。
query 必须是可独立执行的检索问题。required 只用于缺失就无法完成请求的核心 Need。
subject_refs 只能从输入提供的 subject_refs 中选择，不得发明身份。
description 和 query 必须与输入 query 使用相同语言，不要擅自翻译。

严格返回 JSON：
{{"needs":[{{"need_id":"lower_snake_case","description":"...","query":"...",
"facets":["..."],"subject_refs":["..."],"time_mode":"any|latest_valid|historical",
"required":true,"weight":1.0}}]}}

need_id 必须是英文小写 snake_case；weight 范围 0.1-3.0；至少一个 Need required=true。
不要输出来源名称、答案、分析过程或 Markdown。"""

    def _parse(self, text: str, request: ContextPackRequest) -> RetrievalPlan:
        cleaned = _JSON_FENCE.sub("", text.strip())
        payload = json.loads(cleaned)
        raw_needs = payload.get("needs") if isinstance(payload, dict) else None
        if not isinstance(raw_needs, list) or not raw_needs:
            raise ValueError("Planner response must contain a non-empty needs list")

        allowed_subjects = set(request.subject_refs)
        needs: list[EvidenceNeed] = []
        seen: set[str] = set()
        for index, raw in enumerate(raw_needs[: self._max_needs], start=1):
            if not isinstance(raw, dict):
                continue
            raw_id = raw.get("need_id")
            need_id = raw_id.strip() if isinstance(raw_id, str) else f"need_{index}"
            if not _NEED_ID.fullmatch(need_id) or need_id in seen:
                need_id = f"need_{index}"
            description = raw.get("description")
            query = raw.get("query")
            if not isinstance(description, str) or not description.strip():
                continue
            if not isinstance(query, str) or not query.strip():
                continue
            raw_facets = raw.get("facets")
            facets = [
                value.strip().lower()
                for value in raw_facets or []
                if isinstance(value, str) and value.strip()
            ][:8]
            raw_subjects = raw.get("subject_refs")
            subject_refs = [
                value
                for value in raw_subjects or []
                if isinstance(value, str) and value in allowed_subjects
            ]
            time_mode = raw.get("time_mode", "any")
            if time_mode not in _TIME_MODES:
                time_mode = "any"
            raw_weight = raw.get("weight", 1.0)
            weight = float(raw_weight) if isinstance(raw_weight, int | float) else 1.0
            weight = min(max(weight, 0.1), 3.0)
            needs.append(
                EvidenceNeed(
                    need_id=need_id,
                    description=" ".join(description.split()),
                    query=" ".join(query.split()),
                    facets=list(dict.fromkeys(facets)),
                    subject_refs=list(dict.fromkeys(subject_refs)),
                    time_mode=time_mode,
                    required=bool(raw.get("required", False)),
                    weight=weight,
                )
            )
            seen.add(need_id)
        if not needs:
            raise ValueError("Planner response did not contain a usable EvidenceNeed")
        if not any(need.required for need in needs):
            needs[0] = needs[0].model_copy(update={"required": True})
        return RetrievalPlan(
            request_id=request.request_id,
            original_query=request.query,
            purpose=request.purpose,
            needs=needs,
            planner=self.name,
        )

    def plan(self, request: ContextPackRequest) -> RetrievalPlan:
        try:
            response = self._chat_model.complete(
                self._system_prompt(self._max_needs),
                json.dumps(request.model_dump(mode="json"), ensure_ascii=False),
            )
            return self._parse(response, request)
        except Exception:
            return self._fallback.plan(request)
