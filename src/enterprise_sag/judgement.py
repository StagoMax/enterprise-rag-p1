from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Protocol

from enterprise_rag.llm import ChatModel
from enterprise_sag.models import EvidenceSupport, RetrievalPlan, SagSearchHit

_JSON_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


class EvidenceCoverageJudge(Protocol):
    name: str

    def judge(
        self,
        plan: RetrievalPlan,
        route_hits: Mapping[str, Sequence[SagSearchHit]],
    ) -> list[EvidenceSupport]: ...


class RelativeScoreCoverageJudge:
    """Offline fallback: retain only the calibrated head of each route."""

    name = "relative-score-coverage-v1"

    def __init__(self, *, relative_threshold: float = 0.72) -> None:
        if not 0.0 <= relative_threshold <= 1.0:
            raise ValueError("relative_threshold must be in [0, 1]")
        self._relative_threshold = relative_threshold

    def judge(
        self,
        plan: RetrievalPlan,
        route_hits: Mapping[str, Sequence[SagSearchHit]],
    ) -> list[EvidenceSupport]:
        del plan
        output: list[EvidenceSupport] = []
        for need_id, values in route_hits.items():
            hits = list(values)
            maximum = max((hit.score for hit in hits), default=0.0)
            denominator = max(maximum, 1e-12)
            for rank, hit in enumerate(hits, start=1):
                normalized = max(min(hit.score / denominator, 1.0), 0.0)
                if rank > 1 and normalized < self._relative_threshold:
                    continue
                output.append(
                    EvidenceSupport(
                        need_id=need_id,
                        event_id=hit.event_id,
                        score=round(0.5 + 0.5 * normalized, 6),
                        reason="relative-route-head",
                    )
                )
        return output


class DeepSeekEvidenceCoverageJudge:
    """Validate Event-to-Need support once, after high-recall SAG candidate generation."""

    name = "deepseek-evidence-coverage-judge-v1"

    def __init__(
        self,
        chat_model: ChatModel,
        *,
        candidates_per_need: int = 10,
        minimum_support: float = 0.58,
        fallback: EvidenceCoverageJudge | None = None,
    ) -> None:
        if candidates_per_need < 1:
            raise ValueError("candidates_per_need must be positive")
        if not 0.0 <= minimum_support <= 1.0:
            raise ValueError("minimum_support must be in [0, 1]")
        self._chat_model = chat_model
        self._candidates_per_need = candidates_per_need
        self._minimum_support = minimum_support
        self._fallback = fallback or RelativeScoreCoverageJudge()

    @staticmethod
    def _system_prompt() -> str:
        return """你是证据覆盖判定器，不是问答模型。判断每个 Event 是否直接支持一个或多个
EvidenceNeed。候选进入召回集不代表它支持 Need；只共享宽泛词、间接 SQL 邻居、主题相似但
不能提供所需证据时必须拒绝。不得依据来源名称、文档类型或来源数量作判断。

只允许从 candidate.allowed_need_ids 中选择。score 表示直接支持强度，0 到 1；低于 0.58 的
支持不要输出。严格返回 JSON：
{"candidates":[{"event_id":"...","supports":[
{"need_id":"...","score":0.86,"reason":"一句可审计理由"}]}]}

可以返回空 supports。不得回答原问题，不得输出 Markdown 或分析过程。"""

    def _payload(
        self,
        plan: RetrievalPlan,
        route_hits: Mapping[str, Sequence[SagSearchHit]],
    ) -> tuple[str, set[tuple[str, str]]]:
        candidates: dict[str, dict[str, object]] = {}
        allowed_pairs: set[tuple[str, str]] = set()
        for need in plan.needs:
            for hit in list(route_hits.get(need.need_id, ()))[: self._candidates_per_need]:
                item = candidates.setdefault(
                    hit.event_id,
                    {
                        "event_id": hit.event_id,
                        "event": hit.event_text,
                        "title": hit.title,
                        "section": hit.section_path,
                        "allowed_need_ids": [],
                    },
                )
                allowed = item["allowed_need_ids"]
                if isinstance(allowed, list) and need.need_id not in allowed:
                    allowed.append(need.need_id)
                allowed_pairs.add((need.need_id, hit.event_id))
        payload = {
            "needs": [
                {
                    "need_id": need.need_id,
                    "description": need.description,
                    "query": need.query,
                }
                for need in plan.needs
            ],
            "candidates": list(candidates.values()),
        }
        return json.dumps(payload, ensure_ascii=False), allowed_pairs

    def _parse(
        self,
        text: str,
        allowed_pairs: set[tuple[str, str]],
    ) -> list[EvidenceSupport]:
        cleaned = _JSON_FENCE.sub("", text.strip())
        payload = json.loads(cleaned)
        candidates = payload.get("candidates") if isinstance(payload, dict) else None
        if not isinstance(candidates, list):
            raise ValueError("Coverage judge response must contain candidates")
        output: list[EvidenceSupport] = []
        seen: set[tuple[str, str]] = set()
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            event_id = candidate.get("event_id")
            supports = candidate.get("supports")
            if not isinstance(event_id, str) or not isinstance(supports, list):
                continue
            for support in supports:
                if not isinstance(support, dict):
                    continue
                need_id = support.get("need_id")
                raw_score = support.get("score")
                pair = (need_id, event_id)
                if (
                    not isinstance(need_id, str)
                    or pair not in allowed_pairs
                    or pair in seen
                    or not isinstance(raw_score, int | float)
                ):
                    continue
                score = min(max(float(raw_score), 0.0), 1.0)
                if score < self._minimum_support:
                    continue
                reason = support.get("reason")
                output.append(
                    EvidenceSupport(
                        need_id=need_id,
                        event_id=event_id,
                        score=score,
                        reason=(
                            " ".join(reason.split())[:240]
                            if isinstance(reason, str) and reason.strip()
                            else "semantic-support"
                        ),
                    )
                )
                seen.add(pair)
        return output

    def judge(
        self,
        plan: RetrievalPlan,
        route_hits: Mapping[str, Sequence[SagSearchHit]],
    ) -> list[EvidenceSupport]:
        try:
            payload, allowed_pairs = self._payload(plan, route_hits)
            response = self._chat_model.complete(self._system_prompt(), payload)
            return self._parse(response, allowed_pairs)
        except Exception:
            return self._fallback.judge(plan, route_hits)
