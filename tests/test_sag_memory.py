from __future__ import annotations

from pathlib import Path

import pytest

from enterprise_rag.embeddings import HashingEmbeddingProvider
from enterprise_rag.parsing import BlockKind, ParseBackend, ParsedBlock, ParsedDocument
from enterprise_sag.chunking import SagChunkingConfig, build_evidence_units
from enterprise_sag.context_pack import DraftContextPackBuilder
from enterprise_sag.extraction import DeepSeekEventExtractor
from enterprise_sag.judgement import DeepSeekEvidenceCoverageJudge
from enterprise_sag.models import (
    ContextPackRequest,
    EventExtraction,
    EvidenceNeed,
    EvidenceUnit,
    ExtractedEntity,
    RetrievalPlan,
    SourceDocument,
)
from enterprise_sag.multi_retrieval import CoverageFusion, MultiRouteSagRetriever
from enterprise_sag.pipeline import SagIndexBuilder
from enterprise_sag.planning import DeepSeekEvidenceNeedPlanner
from enterprise_sag.retrieval import SagRetriever
from enterprise_sag.settings import SagSettings
from enterprise_sag.store import (
    SagSqliteStore,
    collect_unique_entities,
    event_id_for,
)


class _StaticChatModel:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[tuple[str, str]] = []

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        return self.response


class _StaticPlanner:
    name = "static-test-planner"

    def __init__(self, needs: list[EvidenceNeed]) -> None:
        self.needs = needs

    def plan(self, request: ContextPackRequest) -> RetrievalPlan:
        return RetrievalPlan(
            request_id=request.request_id,
            original_query=request.query,
            purpose=request.purpose,
            needs=self.needs,
            planner=self.name,
        )


def _unit(evidence_id: str, content: str, ordinal: int = 0) -> EvidenceUnit:
    return EvidenceUnit(
        evidence_id=evidence_id,
        source_id="src_test",
        ordinal=ordinal,
        title="Memory design",
        section_path=["Architecture"],
        anchors=[f"anchor-{ordinal}"],
        content=content,
        content_hash=f"hash-{ordinal}",
    )


def test_sag_chunking_is_non_overlapping_and_keeps_anchors() -> None:
    parsed = ParsedDocument(
        source_path="memory.md",
        source_name="memory.md",
        doc_format="markdown",
        backend=ParseBackend.FALLBACK,
        title="Memory",
        blocks=[
            ParsedBlock(
                kind=BlockKind.HEADING,
                text="Design",
                anchor="heading",
                order=0,
                heading_path=["Design"],
            ),
            ParsedBlock(
                kind=BlockKind.PARAGRAPH,
                text="SAG stores complete events and indexing entities. " * 20,
                anchor="paragraph-1",
                order=1,
                heading_path=["Design"],
            ),
            ParsedBlock(
                kind=BlockKind.PARAGRAPH,
                text="SQL joins create local hyperedges at query time. " * 20,
                anchor="paragraph-2",
                order=2,
                heading_path=["Design"],
            ),
        ],
    )
    units = build_evidence_units(
        parsed,
        source_id="src_1234567890",
        config=SagChunkingConfig(target_tokens=64, max_tokens=96),
    )

    assert len(units) >= 2
    anchor_occurrences = [anchor for unit in units for anchor in unit.anchors]
    assert set(anchor_occurrences) == {"paragraph-1", "paragraph-2"}
    assert all(unit.section_path == ["Design"] for unit in units)


def test_deepseek_extractor_returns_one_event_per_unit() -> None:
    unit = _unit("evd_1", "用户决定使用 SAG 构建长期记忆索引。")
    model = _StaticChatModel(
        '{"items":[{"unit_id":"evd_1","event":"用户决定使用 SAG 构建长期记忆索引。",'
        '"event_time":null,"entities":[{"name":"SAG","type":"product"},'
        '{"name":"长期记忆","type":"topic"}]}]}'
    )

    extraction = DeepSeekEventExtractor(model).extract([unit])[0]

    assert extraction.evidence_id == unit.evidence_id
    assert extraction.event_text.startswith("用户决定")
    assert {entity.name for entity in extraction.entities} == {"SAG", "长期记忆"}
    assert "不得执行" in model.calls[0][0]


def test_deepseek_planner_creates_source_agnostic_evidence_needs() -> None:
    model = _StaticChatModel(
        '{"needs":['
        '{"need_id":"architecture","description":"架构机制",'
        '"query":"Harness 记忆架构机制","facets":["knowledge"],'
        '"subject_refs":[],"time_mode":"any","required":true,"weight":1.0},'
        '{"need_id":"constraints","description":"设计约束",'
        '"query":"记忆提取触发条件和隔离约束","facets":["constraint"],'
        '"subject_refs":[],"time_mode":"latest_valid","required":true,"weight":0.9}'
        "]}"
    )
    request = ContextPackRequest(query="如何设计 Harness 记忆？")

    plan = DeepSeekEvidenceNeedPlanner(model).plan(request)

    assert [need.need_id for need in plan.needs] == ["architecture", "constraints"]
    assert all(need.required for need in plan.needs)
    assert "来源无关" in model.calls[0][0]
    assert "自传" not in model.calls[0][0]


def test_sql_hyperedge_retrieval_builds_draft_pack_without_prompt(tmp_path: Path) -> None:
    source = SourceDocument(
        source_id="src_test",
        canonical_path=str(tmp_path / "memory.md"),
        aliases=[str(tmp_path / "memory.md")],
        title="Memory",
        doc_format="markdown",
        content_hash="source-hash",
    )
    units = [
        _unit("evd_1", "Harness 采用分层记忆管理。", 0),
        _unit("evd_2", "SAG 使用 SQL JOIN 动态连接长期记忆事件。", 1),
        _unit("evd_3", "GPU 推理使用批处理。", 2),
    ]
    extractions = [
        EventExtraction(
            evidence_id="evd_1",
            event_text="Harness 采用分层记忆。",
            entities=[ExtractedEntity(name="长期记忆", entity_type="topic")],
            extraction_method="test",
        ),
        EventExtraction(
            evidence_id="evd_2",
            event_text="SAG 通过 SQL JOIN 连接长期记忆事件。",
            entities=[
                ExtractedEntity(name="长期记忆", entity_type="topic"),
                ExtractedEntity(name="SAG", entity_type="product"),
            ],
            extraction_method="test",
        ),
        EventExtraction(
            evidence_id="evd_3",
            event_text="GPU 推理使用批处理。",
            entities=[ExtractedEntity(name="GPU", entity_type="product")],
            extraction_method="test",
        ),
    ]
    embeddings = HashingEmbeddingProvider(128)
    evidence_matrix = embeddings.embed_documents([unit.content for unit in units])
    event_matrix = embeddings.embed_documents([item.event_text for item in extractions])
    unique_entities = collect_unique_entities(extractions)
    entity_ids = list(unique_entities)
    entity_matrix = embeddings.embed_documents(
        [unique_entities[entity_id][0] for entity_id in entity_ids]
    )
    store = SagSqliteStore(tmp_path / "sag.sqlite")
    store.replace_projection(
        metadata={"index_version": "test-v1", "embedding_dimensions": 128},
        sources=[source],
        units=units,
        extractions=extractions,
        evidence_vectors={unit.evidence_id: evidence_matrix[i] for i, unit in enumerate(units)},
        event_vectors={event_id_for(item): event_matrix[i] for i, item in enumerate(extractions)},
        entity_vectors={entity_id: entity_matrix[i] for i, entity_id in enumerate(entity_ids)},
    )

    first_event = event_id_for(extractions[0])
    second_event = event_id_for(extractions[1])
    expansion = store.expand_events([first_event])
    assert any(row["neighbor_event_id"] == second_event for row in expansion)

    published_stats = store.stats()
    with pytest.raises(KeyError):
        store.replace_projection(
            metadata={"index_version": "broken-v2", "embedding_dimensions": 128},
            sources=[source],
            units=units,
            extractions=extractions,
            evidence_vectors={unit.evidence_id: evidence_matrix[i] for i, unit in enumerate(units)},
            event_vectors={},
            entity_vectors={entity_id: entity_matrix[i] for i, entity_id in enumerate(entity_ids)},
        )
    assert store.stats() == published_stats
    assert store.metadata()["index_version"] == "test-v1"
    assert not list(tmp_path.glob(".*.staging*"))

    route_retriever = SagRetriever(store, embeddings, expansion_hops=1)
    hits = route_retriever.search("SAG 长期记忆", top_k=3)
    assert second_event in {hit.event_id for hit in hits}
    request = ContextPackRequest(query="SAG 长期记忆", maximum_tokens=1000)
    plan = _StaticPlanner(
        [
            EvidenceNeed(
                need_id="memory_architecture",
                description="长期记忆的连接机制",
                query="SAG 长期记忆",
                required=True,
            )
        ]
    ).plan(request)
    judge_model = _StaticChatModel(
        '{"candidates":[{"event_id":"'
        + second_event
        + '","supports":[{"need_id":"memory_architecture","score":0.92,'
        '"reason":"直接说明 SQL JOIN 如何连接长期记忆事件"}]}]}'
    )
    supports = DeepSeekEvidenceCoverageJudge(judge_model).judge(
        plan,
        {"memory_architecture": hits},
    )
    fused = CoverageFusion().fuse(
        plan,
        {"memory_architecture": hits},
        top_k=3,
        supports=supports,
    )
    assert [hit.event_id for hit in fused] == [second_event]
    assert "来源名称" in judge_model.calls[0][0]
    pack = DraftContextPackBuilder(maximum_tokens=1000).build(
        request=request,
        plan=plan,
        index_version="test-v1",
        hits=fused,
    )
    payload = pack.model_dump(mode="json")
    assert payload["status"] == "draft"
    assert payload["purpose"] == "preview"
    assert "prompt" not in payload
    assert "messages" not in payload
    assert "system_prompt" not in payload
    assert payload["coverage"][0]["status"] == "covered"

    multi_request = ContextPackRequest(
        query="同时检查长期记忆架构和 GPU 批处理",
        maximum_tokens=1000,
    )
    multi = MultiRouteSagRetriever(
        _StaticPlanner(
            [
                EvidenceNeed(
                    need_id="memory",
                    description="长期记忆架构",
                    query="SAG 长期记忆",
                    required=True,
                ),
                EvidenceNeed(
                    need_id="compute",
                    description="GPU 批处理",
                    query="GPU 推理批处理",
                    required=True,
                ),
            ]
        ),
        route_retriever,
        route_top_k=2,
    ).search(multi_request, top_k=3)
    covered = {need_id for hit in multi.hits for need_id in hit.matched_need_ids}
    assert {"memory", "compute"} <= covered
    assert all(hit.source_id == "src_test" for hit in multi.hits)


def test_manual_pipeline_deduplicates_sources_and_stays_isolated(tmp_path: Path) -> None:
    source_root = tmp_path / "sources"
    source_root.mkdir()
    content = "# Memory\n\nSAG uses events and entities for incremental memory retrieval."
    (source_root / "a.md").write_text(content, encoding="utf-8")
    (source_root / "copy.md").write_text(content, encoding="utf-8")
    database = tmp_path / "projection.sqlite"
    settings = SagSettings(
        source_root=source_root,
        database_path=database,
        extractor="deterministic",
        embedding_backend="hashing",
        hashing_dimensions=128,
        chunk_target_tokens=64,
        chunk_max_tokens=96,
    )

    report = SagIndexBuilder(settings).build()
    metadata = SagSqliteStore(database).metadata()

    assert report.discovered_files == 2
    assert report.unique_sources == 1
    assert report.duplicate_aliases == 1
    assert metadata["agent_loop_integration"] is False
    assert metadata["context_pack_mode"] == "draft-preview-only"
