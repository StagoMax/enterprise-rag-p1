from __future__ import annotations

import uuid

from enterprise_rag.chunking import count_tokens
from enterprise_sag.models import (
    ContextPackItem,
    ContextPackRequest,
    DraftContextPack,
    FusedSagSearchHit,
    NeedCoverage,
    RetrievalPlan,
)


class DraftContextPackBuilder:
    """Build a review-only structured artifact; it never renders or mutates a prompt."""

    def __init__(self, *, maximum_tokens: int = 4000) -> None:
        if maximum_tokens < 256:
            raise ValueError("maximum_tokens must be at least 256")
        self._maximum_tokens = maximum_tokens

    def build(
        self,
        *,
        request: ContextPackRequest,
        plan: RetrievalPlan,
        index_version: str,
        hits: list[FusedSagSearchHit],
    ) -> DraftContextPack:
        items: list[ContextPackItem] = []
        excluded: list[dict[str, str]] = []
        consumed = 0
        ordered_hits = self._coverage_first(plan, hits)
        for hit in ordered_hits:
            item_tokens = count_tokens(hit.evidence_content) + count_tokens(hit.event_text)
            if consumed + item_tokens > self._maximum_tokens:
                excluded.append(
                    {
                        "event_id": hit.event_id,
                        "reason": "token-budget-exceeded",
                    }
                )
                continue
            items.append(
                ContextPackItem(
                    event_id=hit.event_id,
                    evidence_id=hit.evidence_id,
                    content=hit.evidence_content,
                    event_summary=hit.event_text,
                    source_path=hit.source_path,
                    title=hit.title,
                    section_path=hit.section_path,
                    anchors=hit.anchors,
                    score=hit.score,
                    selection_reason="multi-route-coverage-fusion",
                    matched_need_ids=hit.matched_need_ids,
                    route_traces=hit.route_traces,
                    estimated_tokens=item_tokens,
                )
            )
            consumed += item_tokens
        selected_by_need: dict[str, list[str]] = {need.need_id: [] for need in plan.needs}
        for item in items:
            for need_id in item.matched_need_ids:
                selected_by_need.setdefault(need_id, []).append(item.event_id)
        coverage = [
            NeedCoverage(
                need_id=need.need_id,
                required=need.required,
                status="covered" if selected_by_need[need.need_id] else "uncovered",
                selected_event_ids=selected_by_need[need.need_id],
                reason=(
                    "selected-evidence"
                    if selected_by_need[need.need_id]
                    else (
                        "token-budget-exceeded"
                        if any(need.need_id in hit.matched_need_ids for hit in hits)
                        else "no-validated-evidence"
                    )
                ),
            )
            for need in plan.needs
        ]
        return DraftContextPack(
            pack_id=f"cp_{uuid.uuid4().hex}",
            query=" ".join(request.query.split()),
            request=request,
            plan=plan,
            coverage=coverage,
            index_version=index_version,
            items=items,
            excluded_items=excluded,
            estimated_tokens=consumed,
            maximum_tokens=self._maximum_tokens,
        )

    @staticmethod
    def _coverage_first(
        plan: RetrievalPlan,
        hits: list[FusedSagSearchHit],
    ) -> list[FusedSagSearchHit]:
        """Order required coverage before utility without introducing source quotas."""

        ordered: list[FusedSagSearchHit] = []
        selected: set[str] = set()
        for need in plan.needs:
            if not need.required:
                continue
            candidate = next(
                (
                    hit
                    for hit in hits
                    if need.need_id in hit.matched_need_ids and hit.event_id not in selected
                ),
                None,
            )
            if candidate is not None:
                ordered.append(candidate)
                selected.add(candidate.event_id)
        ordered.extend(hit for hit in hits if hit.event_id not in selected)
        return ordered
