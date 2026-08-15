from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from enterprise_rag.embeddings import HashingEmbeddingProvider
from enterprise_sag.cli import main as sag_cli_main
from enterprise_sag.temporal_consolidation import DeepSeekTemporalConsolidationPlanner
from enterprise_sag.temporal_models import (
    AssertionDraft,
    AssertionLifecycle,
    ConsolidationProposal,
    MemoryEventCreate,
    RelationDraft,
    TemporalQuery,
    TemporalQueryMode,
    TemporalRelationType,
    TemporalUsageEvent,
    UsageOutcome,
)
from enterprise_sag.temporal_service import TemporalMemoryService
from enterprise_sag.temporal_store import TemporalMemoryStore


class _StaticChatModel:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[tuple[str, str]] = []

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        return self.response


def _service(tmp_path: Path) -> TemporalMemoryService:
    store = TemporalMemoryStore(tmp_path / "temporal.sqlite")
    return TemporalMemoryService(
        store,
        HashingEmbeddingProvider(128),
        embedding_backend="hashing-test",
    )


def _append_policy(
    service: TemporalMemoryService,
    *,
    content: str,
    occurred_at: datetime,
):
    return service.append_interaction(
        MemoryEventCreate(
            subject_id="user:test",
            content=content,
            occurred_at=occurred_at,
            observed_at=occurred_at,
            source_ref="session:test",
        )
    )


def _apply_policy(
    service: TemporalMemoryService,
    *,
    event_id: str,
    value: str,
    valid_from: datetime,
    candidate_ids: list[str] | None = None,
    supersedes: str | None = None,
):
    relations = []
    if supersedes:
        relations.append(
            RelationDraft(
                source_local_id="format_policy",
                target_assertion_id=supersedes,
                relation_type=TemporalRelationType.SUPERSEDES,
                effective_at=valid_from,
                confidence=0.98,
                rationale="用户明确用新的发布规则替代旧规则",
            )
        )
    proposal = ConsolidationProposal(
        event_id=event_id,
        subject_id="user:test",
        candidate_assertion_ids=candidate_ids or [],
        assertions=[
            AssertionDraft(
                local_id="format_policy",
                predicate="publishing.format_policy",
                object_text=value,
                scope="feishu_article",
                valid_from=valid_from,
                confidence=0.96,
                importance=0.8,
            )
        ],
        relations=relations,
        planner="manual-test",
    )
    return service.apply_consolidation(proposal)


def test_append_path_preserves_raw_event_and_ledger_rejects_mutation(tmp_path: Path) -> None:
    service = _service(tmp_path)
    content = "以后处理飞书文章时，先导出 Word。\n原文换行必须保留。"
    event = service.append_interaction(MemoryEventCreate(subject_id="user:test", content=content))

    assert service.store.get_event(event.event_id).content == content
    assert service.store.pending_events()[0].event_id == event.event_id
    with sqlite3.connect(service.store.path) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(
                "UPDATE memory_events SET content = 'changed' WHERE event_id = ?",
                (event.event_id,),
            )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("DELETE FROM memory_events WHERE event_id = ?", (event.event_id,))


def test_supersession_keeps_history_and_latest_query_uses_new_state(tmp_path: Path) -> None:
    service = _service(tmp_path)
    first_time = datetime(2026, 8, 7, 9, tzinfo=UTC)
    second_time = datetime(2026, 8, 10, 9, tzinfo=UTC)
    first_event = _append_policy(
        service,
        content="以后处理飞书文章时，先导出成 Word，再修改成不同格式发布。",
        occurred_at=first_time,
    )
    first_result = _apply_policy(
        service,
        event_id=first_event.event_id,
        value="先导出 Word，再按平台修改成不同格式",
        valid_from=first_time,
    )
    old_assertion_id = first_result.assertion_ids[0]
    first_known_at = service.store.resolve_states(
        "user:test",
        valid_at=second_time,
        known_at=datetime.now(UTC),
    )[0].assertion.recorded_at

    second_event = _append_policy(
        service,
        content="不修改了，所有平台发布相同格式。",
        occurred_at=second_time,
    )
    second_result = _apply_policy(
        service,
        event_id=second_event.event_id,
        value="所有平台发布相同格式",
        valid_from=second_time,
        candidate_ids=[old_assertion_id],
        supersedes=old_assertion_id,
    )
    new_assertion_id = second_result.assertion_ids[0]

    states = service.store.resolve_states(
        "user:test",
        valid_at=datetime.now(UTC),
        known_at=datetime.now(UTC),
    )
    lifecycle = {state.assertion.assertion_id: state.lifecycle for state in states}
    assert lifecycle[old_assertion_id] == AssertionLifecycle.SUPERSEDED
    assert lifecycle[new_assertion_id] == AssertionLifecycle.ACTIVE
    assert service.store.stats()["temporal_assertions"] == 2
    assert service.store.stats()["assertion_relations"] == 1

    for _ in range(20):
        service.record_usage(
            TemporalUsageEvent(
                assertion_id=old_assertion_id,
                outcome=UsageOutcome.SUCCESSFUL,
            )
        )
    latest = service.search(
        TemporalQuery(
            query="飞书文章应该用什么发布格式",
            subject_id="user:test",
            mode=TemporalQueryMode.LATEST_VALID,
        )
    )
    assert [hit.assertion.assertion_id for hit in latest] == [new_assertion_id]
    assert latest[0].assertion.object_text == "所有平台发布相同格式"

    historical = service.search(
        TemporalQuery(
            query="飞书文章发布格式",
            subject_id="user:test",
            mode=TemporalQueryMode.HISTORICAL,
            valid_at=first_time + timedelta(hours=2),
            known_at=datetime.now(UTC),
        )
    )
    assert [hit.assertion.assertion_id for hit in historical] == [old_assertion_id]
    assert historical[0].lifecycle == AssertionLifecycle.ACTIVE

    known_before_update = service.store.resolve_states(
        "user:test",
        valid_at=second_time + timedelta(hours=1),
        known_at=first_known_at,
    )
    assert [(state.assertion.assertion_id, state.lifecycle) for state in known_before_update] == [
        (old_assertion_id, AssertionLifecycle.ACTIVE)
    ]


def test_contradiction_marks_fact_contested_without_deleting_it(tmp_path: Path) -> None:
    service = _service(tmp_path)
    first_time = datetime(2026, 8, 8, 9, tzinfo=UTC)
    first_event = _append_policy(
        service,
        content="我更偏好 PostgreSQL。",
        occurred_at=first_time,
    )
    first = service.apply_consolidation(
        ConsolidationProposal(
            event_id=first_event.event_id,
            subject_id="user:test",
            assertions=[
                AssertionDraft(
                    local_id="database_preference",
                    predicate="technology.database.preference",
                    object_text="偏好 PostgreSQL",
                    valid_from=first_time,
                )
            ],
            planner="manual-test",
        )
    )
    old_id = first.assertion_ids[0]
    second_time = datetime(2026, 8, 9, 9, tzinfo=UTC)
    second_event = _append_policy(
        service,
        content="我更偏好 MySQL，但暂时不能确定是不是长期变化。",
        occurred_at=second_time,
    )
    service.apply_consolidation(
        ConsolidationProposal(
            event_id=second_event.event_id,
            subject_id="user:test",
            candidate_assertion_ids=[old_id],
            assertions=[
                AssertionDraft(
                    local_id="database_preference",
                    predicate="technology.database.preference",
                    object_text="偏好 MySQL",
                    valid_from=second_time,
                )
            ],
            relations=[
                RelationDraft(
                    source_local_id="database_preference",
                    target_assertion_id=old_id,
                    relation_type=TemporalRelationType.CONTRADICTS,
                    effective_at=second_time,
                )
            ],
            planner="manual-test",
        )
    )

    states = service.store.resolve_states(
        "user:test",
        valid_at=datetime.now(UTC),
        known_at=datetime.now(UTC),
    )
    by_id = {state.assertion.assertion_id: state for state in states}
    assert by_id[old_id].lifecycle == AssertionLifecycle.CONTESTED
    assert by_id[old_id].contradiction_count == 1
    assert len(states) == 2


@pytest.mark.parametrize(
    ("relation_type", "expected_lifecycle"),
    [
        (TemporalRelationType.CORRECTS, AssertionLifecycle.CORRECTED),
        (TemporalRelationType.RETRACTS, AssertionLifecycle.RETRACTED),
    ],
)
def test_correction_and_retraction_are_relations_not_destructive_updates(
    tmp_path: Path,
    relation_type: TemporalRelationType,
    expected_lifecycle: AssertionLifecycle,
) -> None:
    service = _service(tmp_path)
    old_time = datetime(2026, 8, 8, 9, tzinfo=UTC)
    old_event = _append_policy(
        service,
        content="系统理解为用户喜欢吃苹果。",
        occurred_at=old_time,
    )
    old = service.apply_consolidation(
        ConsolidationProposal(
            event_id=old_event.event_id,
            subject_id="user:test",
            assertions=[
                AssertionDraft(
                    local_id="food_preference",
                    predicate="preference.food",
                    object_text="喜欢吃苹果",
                    valid_from=old_time,
                )
            ],
            planner="manual-test",
        )
    )
    old_id = old.assertion_ids[0]
    change_time = datetime(2026, 8, 10, 9, tzinfo=UTC)
    change_event = _append_policy(
        service,
        content="之前的理解不准确，请撤回那条苹果偏好。",
        occurred_at=change_time,
    )
    service.apply_consolidation(
        ConsolidationProposal(
            event_id=change_event.event_id,
            subject_id="user:test",
            candidate_assertion_ids=[old_id],
            assertions=[
                AssertionDraft(
                    local_id="correction",
                    predicate="preference.food.correction",
                    object_text="旧的苹果偏好不再适用",
                    valid_from=change_time,
                )
            ],
            relations=[
                RelationDraft(
                    source_local_id="correction",
                    target_assertion_id=old_id,
                    relation_type=relation_type,
                    effective_at=change_time,
                )
            ],
            planner="manual-test",
        )
    )

    states = service.store.resolve_states(
        "user:test",
        valid_at=datetime.now(UTC),
        known_at=datetime.now(UTC),
    )
    old_state = next(state for state in states if state.assertion.assertion_id == old_id)
    assert old_state.lifecycle == expected_lifecycle
    assert old_state.valid_to == change_time
    assert service.store.stats()["temporal_assertions"] == 2


def test_reinforcement_relation_increases_salience_without_changing_validity(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    first_time = datetime(2026, 8, 8, 9, tzinfo=UTC)
    first_event = _append_policy(
        service,
        content="回答技术问题时优先给出直接结论。",
        occurred_at=first_time,
    )
    first = service.apply_consolidation(
        ConsolidationProposal(
            event_id=first_event.event_id,
            subject_id="user:test",
            assertions=[
                AssertionDraft(
                    local_id="answer_style",
                    predicate="response.style",
                    object_text="技术问题优先给出直接结论",
                    valid_from=first_time,
                )
            ],
            planner="manual-test",
        )
    )
    target_id = first.assertion_ids[0]
    second_time = datetime(2026, 8, 10, 9, tzinfo=UTC)
    second_event = _append_policy(
        service,
        content="再次确认，技术问题请先说结论。",
        occurred_at=second_time,
    )
    service.apply_consolidation(
        ConsolidationProposal(
            event_id=second_event.event_id,
            subject_id="user:test",
            candidate_assertion_ids=[target_id],
            assertions=[
                AssertionDraft(
                    local_id="answer_style_confirmation",
                    predicate="response.style.confirmation",
                    object_text="再次确认技术问题先给结论",
                    valid_from=second_time,
                )
            ],
            relations=[
                RelationDraft(
                    source_local_id="answer_style_confirmation",
                    target_assertion_id=target_id,
                    relation_type=TemporalRelationType.REINFORCES,
                    effective_at=second_time,
                )
            ],
            planner="manual-test",
        )
    )

    state = next(
        item
        for item in service.store.resolve_states(
            "user:test",
            valid_at=datetime.now(UTC),
            known_at=datetime.now(UTC),
        )
        if item.assertion.assertion_id == target_id
    )
    assert state.lifecycle == AssertionLifecycle.ACTIVE
    assert state.reinforcement_count == 1
    hit = next(
        item
        for item in service.search(TemporalQuery(query="技术问题如何回答", subject_id="user:test"))
        if item.assertion.assertion_id == target_id
    )
    assert hit.relation_reinforcement_count == 1
    assert hit.reinforcement_score > 0


def test_deepseek_planner_only_proposes_reviewable_temporal_changes(tmp_path: Path) -> None:
    service = _service(tmp_path)
    first_time = datetime(2026, 8, 7, 9, tzinfo=UTC)
    first_event = _append_policy(
        service,
        content="先导出 Word，再按平台修改格式。",
        occurred_at=first_time,
    )
    first = _apply_policy(
        service,
        event_id=first_event.event_id,
        value="先导出 Word，再按平台修改格式",
        valid_from=first_time,
    )
    old_id = first.assertion_ids[0]
    second_time = datetime(2026, 8, 10, 9, tzinfo=UTC)
    second_event = _append_policy(
        service,
        content="所有平台都发布相同格式。",
        occurred_at=second_time,
    )
    model = _StaticChatModel(
        '{"assertions":[{"local_id":"format_policy",'
        '"predicate":"publishing.format_policy","object_text":"所有平台发布相同格式",'
        '"scope":"feishu_article","valid_from":"2026-08-10T09:00:00+00:00",'
        '"confidence":0.98,"importance":0.8}],"relations":['
        '{"source_local_id":"format_policy","target_assertion_id":"'
        + old_id
        + '","relation_type":"supersedes","effective_at":null,'
        '"confidence":0.97,"rationale":"新规则明确替代旧规则"}]}'
    )
    planner = DeepSeekTemporalConsolidationPlanner(model)

    proposal = service.propose_consolidation(second_event.event_id, planner)

    assert proposal.event_id == second_event.event_id
    assert proposal.assertions[0].object_text == "所有平台发布相同格式"
    assert proposal.relations[0].target_assertion_id == old_id
    assert proposal.relations[0].relation_type == TemporalRelationType.SUPERSEDES
    assert service.store.stats()["temporal_assertions"] == 1
    assert len(service.store.pending_events()) == 1
    assert "不得删除、" in model.calls[0][0]
    assert "不可信数据" in model.calls[0][0]


def test_applying_same_proposal_is_idempotent(tmp_path: Path) -> None:
    service = _service(tmp_path)
    event = service.append_interaction(
        MemoryEventCreate(subject_id="user:test", content="长期使用中文回答。")
    )
    proposal = ConsolidationProposal(
        proposal_id="mcp_idempotent",
        event_id=event.event_id,
        subject_id="user:test",
        assertions=[
            AssertionDraft(
                local_id="language",
                predicate="response.language",
                object_text="使用中文回答",
            )
        ],
        planner="manual-test",
    )

    first = service.apply_consolidation(proposal)
    second = service.apply_consolidation(proposal)

    assert first.applied is True
    assert second.applied is False
    assert service.store.stats()["temporal_assertions"] == 1
    assert service.store.stats()["consolidation_runs"] == 1
    assert first.agent_loop_integration is False
    assert first.prompt_injection is False


def test_memory_cli_append_is_a_separate_no_llm_operation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "cli-temporal.sqlite"
    assert sag_cli_main(["memory", "init", "--memory-database-path", str(database)]) == 0
    capsys.readouterr()

    assert (
        sag_cli_main(
            [
                "memory",
                "append",
                "只追加这条交互，不要立刻抽取。",
                "--subject-id",
                "user:cli",
                "--memory-database-path",
                str(database),
            ]
        )
        == 0
    )
    payload = capsys.readouterr().out

    assert '"status": "appended"' in payload
    assert '"extraction_started": false' in payload
    assert '"llm_requests": 0' in payload
    assert TemporalMemoryStore(database).stats()["memory_events"] == 1
