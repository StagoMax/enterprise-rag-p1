import json
from pathlib import Path

from enterprise_rag.answering import EvidenceAnswerGenerator
from enterprise_rag.chunking import build_document, chunk_document
from enterprise_rag.config import Settings
from enterprise_rag.models import DocumentInput, Principal
from scripts import evaluate_p2


def settings_for(tmp_path: Path) -> Settings:
    return Settings(
        embedding_backend="hashing",
        vector_backend="memory",
        reranker_backend="none",
        llm_backend="extractive",
        RAG_LLM_BASE_URL="",
        RAG_LLM_API_KEY="",
        RAG_LLM_MODEL="",
        corpus_path=tmp_path / "documents.jsonl",
        relations_path=tmp_path / "relations.jsonl",
        gold_path=tmp_path / "golden_questions.jsonl",
        graph_state_path=tmp_path / "graph-state.json",
        audit_path=tmp_path / "audit.jsonl",
        demo_db_path=tmp_path / "demo.sqlite",
        index_version="evaluation-test-v1",
        min_retrieval_score=0.0,
    )


def test_evaluation_service_uses_the_shared_answer_factory(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import enterprise_rag.components as component_factory

    sentinel = EvidenceAnswerGenerator()
    monkeypatch.setattr(
        component_factory,
        "build_answer_generator",
        lambda settings, chat_model: sentinel,
    )

    service = evaluate_p2.build_service(settings_for(tmp_path))

    assert service.answer_generator is sentinel


def test_semantic_and_exact_search_metrics_are_reported_separately() -> None:
    semantic_rows = [
        {"category": "rag", "evidence_recalled": True, "top1_correct": False},
        {"category": "rag", "evidence_recalled": False, "top1_correct": False},
    ]
    exact_rows = [{"category": "exact_search", "evidence_recalled": True, "top1_correct": True}]

    assert evaluate_p2._retrieval_slice_metrics(semantic_rows) == {
        "recall_at_3": 0.5,
        "top1_citation_accuracy": 0.0,
    }
    assert evaluate_p2._retrieval_slice_metrics(exact_rows) == {
        "recall_at_3": 1.0,
        "top1_citation_accuracy": 1.0,
    }


def test_quality_confidence_gate_uses_lower_bound_and_excludes_isolation() -> None:
    checks = evaluate_p2._confidence_checks(
        {
            "semantic_rag_recall_at_3": 0.85,
            "permission_isolation": 1.0,
        },
        {
            "semantic_rag_recall_at_3": {"low": 0.82, "high": 0.95, "n": 100},
            "permission_isolation": {"low": 0.98, "high": 1.0, "n": 180},
        },
    )

    assert checks == {"semantic_rag_recall_at_3": False}


def test_scoped_quality_thresholds_exclude_unselected_categories() -> None:
    thresholds = evaluate_p2._quality_thresholds(
        {"rag"},
        has_fitting_answers=True,
    )

    assert "semantic_rag_recall_at_3" in thresholds
    assert "answer_span_hit_rate_fitting" in thresholds
    assert "graph_joint_recall_at_3" not in thresholds
    assert "tool_answer_accuracy" not in thresholds
    assert "refusal_accuracy" not in thresholds


def test_evaluate_rejects_an_empty_category_scope(tmp_path: Path) -> None:
    try:
        evaluate_p2.evaluate(settings_for(tmp_path), categories=frozenset())
    except ValueError as exc:
        assert str(exc) == "categories must not be empty"
    else:
        raise AssertionError("empty category scope should fail")


def test_report_records_effective_components_and_keeps_diagnostics_opt_in(
    tmp_path: Path,
) -> None:
    report = evaluate_p2.evaluate(settings_for(tmp_path))
    output = tmp_path / "report.json"

    evaluate_p2.write_report(report, output)

    persisted = json.loads(output.read_text(encoding="utf-8"))
    assert persisted["reranker_backend"] == "none"
    assert persisted["answer_generator"] == "EvidenceAnswerGenerator"
    assert persisted["configuration"]["answer_generator"]["backend"] == "extractive"
    assert persisted["candidate_diagnostics"] == {
        "enabled": False,
        "limit": 20,
        "reranked": False,
        "queries": [],
    }
    assert "semantic_rag_recall_at_3" in persisted["metrics"]
    assert "exact_search_recall_at_3" in persisted["metrics"]
    assert persisted["results"] == []


def test_candidate_trace_records_branch_scores_and_ranks(tmp_path: Path) -> None:
    settings = settings_for(tmp_path)
    components = evaluate_p2.build_runtime_components(settings)
    documents = [
        DocumentInput(
            document_id="gold-doc",
            title="MQ authorization error",
            owner="test",
            business_class="guide",
            allowed_roles={"engineering"},
            version="1",
            source_uri="test://gold",
            content="MQRC_NOT_AUTHORIZED 2035 means the user lacks queue permission.",
        ),
        DocumentInput(
            document_id="negative-doc",
            title="Generic connection error",
            owner="test",
            business_class="guide",
            allowed_roles={"engineering"},
            version="1",
            source_uri="test://negative",
            content="Connection troubleshooting and general queue diagnostics.",
        ),
    ]
    components.store.upsert_documents(
        [(document := build_document(item), chunk_document(document)) for item in documents]
    )
    components.store.commit(settings.index_version)

    trace = evaluate_p2._candidate_trace(
        settings,
        components,
        "What causes MQRC_NOT_AUTHORIZED 2035?",
        Principal(subject="test", roles=frozenset({"engineering"}), tenant_id="demo"),
        {"gold-doc"},
        20,
    )

    assert trace[0]["final_rank"] == 1
    assert {row["document_id"] for row in trace} == {"gold-doc", "negative-doc"}
    assert all(
        {
            "title",
            "business_class",
            "anchor",
            "base_rank",
            "base_score",
            "lexical_score",
            "dense_score",
        }
        <= row.keys()
        for row in trace
    )
    assert next(row for row in trace if row["document_id"] == "negative-doc")[
        "requires_relevance_review"
    ]
