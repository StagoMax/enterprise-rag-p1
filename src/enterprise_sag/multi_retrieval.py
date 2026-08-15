from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from enterprise_sag.judgement import EvidenceCoverageJudge, RelativeScoreCoverageJudge
from enterprise_sag.models import (
    ContextPackRequest,
    EvidenceNeed,
    EvidenceSupport,
    FusedSagSearchHit,
    NeedRouteTrace,
    RetrievalPlan,
    SagSearchHit,
)
from enterprise_sag.planning import EvidenceNeedPlanner
from enterprise_sag.retrieval import SagRetriever

_SPACE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class MultiRouteSearchResult:
    plan: RetrievalPlan
    hits: list[FusedSagSearchHit]
    candidate_counts: dict[str, int]


@dataclass(slots=True)
class _AccumulatedCandidate:
    hit: SagSearchHit
    contribution: float
    traces: list[NeedRouteTrace]


def _character_ngrams(text: str, width: int = 3) -> set[str]:
    normalized = _SPACE.sub("", text).lower()
    if len(normalized) <= width:
        return {normalized} if normalized else set()
    return {normalized[index : index + width] for index in range(len(normalized) - width + 1)}


def _near_duplicate(left: str, right: str, threshold: float = 0.88) -> bool:
    left_grams = _character_ngrams(left)
    right_grams = _character_ngrams(right)
    if not left_grams or not right_grams:
        return left.strip() == right.strip()
    return len(left_grams & right_grams) / len(left_grams | right_grams) >= threshold


class CoverageFusion:
    """Fuse evidence-need rankings without source names, source quotas, or source weights."""

    def __init__(self, *, rrf_k: int = 10) -> None:
        if rrf_k < 1:
            raise ValueError("rrf_k must be positive")
        self._rrf_k = rrf_k

    def fuse(
        self,
        plan: RetrievalPlan,
        route_hits: Mapping[str, Sequence[SagSearchHit]],
        *,
        top_k: int,
        supports: Sequence[EvidenceSupport] | None = None,
    ) -> list[FusedSagSearchHit]:
        if top_k < 1:
            return []
        need_by_id = {need.need_id: need for need in plan.needs}
        support_by_pair = (
            {(item.need_id, item.event_id): item for item in supports}
            if supports is not None
            else None
        )
        accumulated: dict[str, _AccumulatedCandidate] = {}
        for need in plan.needs:
            hits = list(route_hits.get(need.need_id, ()))
            maximum = max((hit.score for hit in hits), default=0.0)
            denominator = max(maximum, 1e-12)
            for rank, hit in enumerate(hits, start=1):
                support = (
                    support_by_pair.get((need.need_id, hit.event_id))
                    if support_by_pair is not None
                    else EvidenceSupport(
                        need_id=need.need_id,
                        event_id=hit.event_id,
                        score=1.0,
                        reason="unjudged-direct-fusion",
                    )
                )
                if support is None:
                    continue
                normalized = max(min(hit.score / denominator, 1.0), 0.0)
                rank_score = (self._rrf_k + 1) / (self._rrf_k + rank)
                contribution = need.weight * (0.55 * rank_score + 0.45 * normalized) * support.score
                trace = NeedRouteTrace(
                    need_id=need.need_id,
                    route_rank=rank,
                    route_score=hit.score,
                    normalized_route_score=round(normalized, 6),
                    fusion_contribution=round(contribution, 6),
                    semantic_support_score=support.score,
                    semantic_support_reason=support.reason,
                    retrieval_trace=hit.trace,
                )
                current = accumulated.get(hit.event_id)
                if current is None:
                    accumulated[hit.event_id] = _AccumulatedCandidate(
                        hit=hit,
                        contribution=contribution,
                        traces=[trace],
                    )
                else:
                    current.contribution += contribution
                    current.traces.append(trace)

        total_weight = max(sum(need.weight for need in plan.needs), 1e-12)
        fused = [
            self._to_fused(candidate, need_by_id, total_weight)
            for candidate in accumulated.values()
        ]
        fused.sort(key=lambda item: item.score, reverse=True)
        return self._coverage_aware_select(plan, fused, route_hits, top_k=top_k)

    @staticmethod
    def _to_fused(
        candidate: _AccumulatedCandidate,
        need_by_id: Mapping[str, EvidenceNeed],
        total_weight: float,
    ) -> FusedSagSearchHit:
        hit = candidate.hit
        traces = sorted(
            candidate.traces,
            key=lambda item: (-need_by_id[item.need_id].weight, item.route_rank),
        )
        matched = [
            need.need_id
            for need in need_by_id.values()
            if need.need_id in {t.need_id for t in traces}
        ]
        return FusedSagSearchHit(
            event_id=hit.event_id,
            evidence_id=hit.evidence_id,
            source_id=hit.source_id,
            source_path=hit.source_path,
            title=hit.title,
            section_path=hit.section_path,
            anchors=hit.anchors,
            event_text=hit.event_text,
            evidence_content=hit.evidence_content,
            score=round(candidate.contribution / total_weight, 6),
            matched_need_ids=matched,
            route_traces=traces,
        )

    @staticmethod
    def _coverage_aware_select(
        plan: RetrievalPlan,
        fused: Sequence[FusedSagSearchHit],
        route_hits: Mapping[str, Sequence[SagSearchHit]],
        *,
        top_k: int,
    ) -> list[FusedSagSearchHit]:
        by_event = {hit.event_id: hit for hit in fused}
        selected: list[FusedSagSearchHit] = []
        selected_ids: set[str] = set()

        def add(candidate: FusedSagSearchHit, *, coverage_required: bool) -> None:
            if candidate.event_id in selected_ids:
                return
            duplicate = any(
                _near_duplicate(candidate.event_text, existing.event_text) for existing in selected
            )
            if duplicate and not coverage_required:
                return
            selected.append(candidate)
            selected_ids.add(candidate.event_id)

        for need in plan.needs:
            if not need.required or len(selected) >= top_k:
                continue
            candidate = next(
                (
                    by_event[hit.event_id]
                    for hit in route_hits.get(need.need_id, ())
                    if hit.event_id in by_event
                ),
                None,
            )
            if candidate is not None:
                add(candidate, coverage_required=True)

        for candidate in fused:
            if len(selected) >= top_k:
                break
            add(candidate, coverage_required=False)
        selected.sort(key=lambda item: item.score, reverse=True)
        return selected


class MultiRouteSagRetriever:
    """Plan independent EvidenceNeeds, execute the same SAG engine, then fuse coverage."""

    def __init__(
        self,
        planner: EvidenceNeedPlanner,
        route_retriever: SagRetriever,
        *,
        route_top_k: int = 16,
        fusion: CoverageFusion | None = None,
        coverage_judge: EvidenceCoverageJudge | None = None,
    ) -> None:
        if route_top_k < 1:
            raise ValueError("route_top_k must be positive")
        self._planner = planner
        self._route_retriever = route_retriever
        self._route_top_k = route_top_k
        self._fusion = fusion or CoverageFusion()
        self._coverage_judge = coverage_judge or RelativeScoreCoverageJudge()

    def search(
        self,
        request: ContextPackRequest,
        *,
        top_k: int = 10,
    ) -> MultiRouteSearchResult:
        plan = self._planner.plan(request)
        route_hits = {
            need.need_id: self._route_retriever.search(need.query, top_k=self._route_top_k)
            for need in plan.needs
        }
        supports = self._coverage_judge.judge(plan, route_hits)
        hits = self._fusion.fuse(plan, route_hits, top_k=top_k, supports=supports)
        return MultiRouteSearchResult(
            plan=plan,
            hits=hits,
            candidate_counts={need_id: len(items) for need_id, items in route_hits.items()},
        )
