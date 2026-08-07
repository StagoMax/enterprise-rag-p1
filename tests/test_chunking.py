import pytest

from enterprise_rag.answering import EvidenceAnswerGenerator
from enterprise_rag.chunking import (
    LEGACY_CHUNKING_VERSION,
    STRUCTURED_CHUNKING_VERSION,
    ChunkingConfig,
    build_document,
    chunk_document,
    count_tokens,
)
from enterprise_rag.models import DocumentInput, SearchHit


def make_document(content: str):
    return build_document(
        DocumentInput(
            document_id="technote-1",
            title="Technote",
            content=content,
            owner="support",
            business_class="technical-guide",
            allowed_roles={"engineering"},
            version="1",
        )
    )


def test_structured_chunks_have_strict_child_and_parent_token_bounds() -> None:
    document = make_document(
        "SUMMARY\n\nA short overview.\n\n"
        "CAUSE\n\n"
        + "connection authentication failure detail " * 160
        + "\n\nRESOLVING THE PROBLEM\n\n"
        + "Install FP-42 and restart the integration service. " * 120
    )
    config = ChunkingConfig(
        child_max_tokens=48,
        child_overlap_tokens=8,
        parent_max_tokens=144,
    )

    chunks = chunk_document(document, config=config)

    assert chunks
    assert max(chunk.token_count for chunk in chunks) <= config.child_max_tokens
    assert max(count_tokens(chunk.parent_content or "") for chunk in chunks) <= (
        config.parent_max_tokens
    )
    assert all(chunk.parent_id for chunk in chunks)
    assert all(chunk.chunking_version == STRUCTURED_CHUNKING_VERSION for chunk in chunks)


def test_structure_headings_are_carried_into_retrieval_chunks() -> None:
    document = make_document(
        "SUMMARY\n\nGeneral background.\n\n"
        "CAUSE\n\nThe certificate alias is missing.\n\n"
        "RESOLVING THE PROBLEM\n\nCreate the alias and restart the server."
    )

    chunks = chunk_document(document)

    titles = " | ".join(chunk.section_title or "" for chunk in chunks)
    assert all(
        title in titles for title in ("SUMMARY", "CAUSE", "RESOLVING THE PROBLEM")
    )
    resolution = next(
        chunk for chunk in chunks if "RESOLVING THE PROBLEM" in (chunk.section_title or "")
    )
    assert "Section: RESOLVING THE PROBLEM" in resolution.content
    assert "Create the alias" in resolution.content
    assert "Create the alias" in (resolution.parent_content or "")
    assert "p1:c1" in resolution.anchor


def test_parent_context_is_used_for_answering_but_child_remains_focused() -> None:
    document = make_document(
        "RESOLVING THE PROBLEM\n\n"
        "The diagnostic precondition is recorded first. "
        "The required remediation is to install FP-77 and restart the server."
    )
    config = ChunkingConfig(
        child_max_tokens=16,
        child_overlap_tokens=2,
        parent_max_tokens=64,
    )
    chunks = chunk_document(document, config=config)
    child = next(chunk for chunk in chunks if "diagnostic precondition" in chunk.content)
    assert "FP-77" not in child.content
    assert "FP-77" in (child.parent_content or "")

    hit = SearchHit(chunk=child, score=1.0, lexical_score=1.0, dense_score=1.0)
    answer = EvidenceAnswerGenerator().answer("Which remediation installs FP-77?", [hit])

    assert "install FP-77" in answer


def test_chunking_is_deterministic_for_the_same_document_and_contract() -> None:
    document = make_document("CAUSE\n\n" + "failure detail " * 100)
    config = ChunkingConfig(child_max_tokens=32, child_overlap_tokens=4, parent_max_tokens=96)

    first = chunk_document(document, config=config)
    second = chunk_document(document, config=config)

    assert [chunk.model_dump() for chunk in first] == [chunk.model_dump() for chunk in second]


def test_legacy_strategy_remains_available_for_ablation() -> None:
    document = make_document("first paragraph\n\nsecond paragraph")

    chunks = chunk_document(
        document,
        config=ChunkingConfig(strategy="legacy", version=LEGACY_CHUNKING_VERSION),
        max_characters=20,
        overlap_characters=4,
    )

    assert chunks
    assert all(chunk.parent_content is None for chunk in chunks)
    assert all(chunk.chunking_version == LEGACY_CHUNKING_VERSION for chunk in chunks)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"child_max_tokens": 8},
        {"child_max_tokens": 32, "child_overlap_tokens": 32},
        {"child_max_tokens": 64, "parent_max_tokens": 32},
    ],
)
def test_invalid_chunking_contract_is_rejected(kwargs: dict[str, int]) -> None:
    with pytest.raises(ValueError):
        ChunkingConfig(**kwargs)
