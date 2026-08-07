import httpx
import pytest

from enterprise_rag.answering import (
    CitationConstrainedAnswerGenerator,
    EvidenceAnswerGenerator,
    select_excerpt,
)
from enterprise_rag.llm import (
    LlmUnavailableError,
    OpenAiCompatibleChatModel,
    strip_reasoning,
)
from enterprise_rag.models import Chunk, DocumentStatus, SearchHit


def make_hit(document_id: str = "doc-1", content: str = "VPN-401 表示设备证书未登记") -> SearchHit:
    return SearchHit(
        chunk=Chunk(
            chunk_id=f"{document_id}:1.0:0",
            document_id=document_id,
            title="VPN 接入手册",
            content=content,
            position=0,
            anchor="section:1",
            allowed_roles=frozenset({"engineering"}),
            version="1.0",
            status=DocumentStatus.ACTIVE,
            business_class="technical-guide",
        ),
        score=0.9,
        lexical_score=0.8,
        dense_score=1.0,
    )


def build_model(handler, **kwargs) -> OpenAiCompatibleChatModel:
    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, base_url="http://llm.test/v1")
    return OpenAiCompatibleChatModel(
        base_url="http://llm.test/v1",
        api_key="test-key",
        model="test-model",
        client=client,
        **kwargs,
    )


def completion(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def test_strip_reasoning_removes_closed_block():
    assert strip_reasoning("<think>internal</think>答案是 4") == "答案是 4"


def test_strip_reasoning_drops_truncated_block():
    # max_tokens 截断会留下未闭合的 <think>，整段都不能当答案返回。
    assert strip_reasoning("<think>还在推理没写完") == ""


def test_strip_reasoning_is_case_insensitive_and_multiline():
    assert strip_reasoning("<THINK>\nline1\nline2\n</THINK>\n结论") == "结论"


def test_complete_returns_stripped_content():
    model = build_model(lambda request: completion("<think>x</think>结论 [1]"))
    assert model.complete("sys", "user") == "结论 [1]"


def test_thinking_disabled_is_sent_by_default():
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        seen.append(json.loads(request.content))
        return completion("ok")

    build_model(handler).complete("sys", "user")
    assert seen[0]["thinking"] == {"type": "disabled"}


def test_backend_rejecting_thinking_param_is_retried_without_it():
    calls: list[bool] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        body = json.loads(request.content)
        calls.append("thinking" in body)
        if "thinking" in body:
            return httpx.Response(400, json={"error": "unknown field thinking"})
        return completion("兼容模式答案")

    assert build_model(handler).complete("sys", "user") == "兼容模式答案"
    assert calls == [True, False]


def test_retries_then_succeeds_on_transient_503():
    attempts: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        if len(attempts) < 2:
            return httpx.Response(503, json={"error": "busy"})
        return completion("恢复后的答案")

    model = build_model(handler, max_retries=2, disable_thinking=False)
    assert model.complete("sys", "user") == "恢复后的答案"
    assert len(attempts) == 2
    assert model.request_count == 2


def test_persistent_failure_raises_unavailable():
    model = build_model(
        lambda request: httpx.Response(503, json={"error": "busy"}),
        max_retries=1,
        disable_thinking=False,
    )
    with pytest.raises(LlmUnavailableError):
        model.complete("sys", "user")


def test_non_retryable_error_raises_immediately():
    attempts: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        return httpx.Response(401, json={"error": "unauthorized"})

    model = build_model(handler, max_retries=3, disable_thinking=False)
    with pytest.raises(LlmUnavailableError):
        model.complete("sys", "user")
    assert len(attempts) == 1


def test_structured_provider_error_is_preserved_for_diagnosis():
    model = build_model(
        lambda request: httpx.Response(
            403,
            json={
                "error": {
                    "code": "insufficient_user_quota",
                    "message": "quota exhausted",
                }
            },
        ),
        disable_thinking=False,
    )

    with pytest.raises(LlmUnavailableError, match="insufficient_user_quota"):
        model.complete("sys", "user")


def test_thinking_only_response_is_treated_as_unavailable():
    model = build_model(lambda request: completion("<think>只有推理没有正文"))
    with pytest.raises(LlmUnavailableError):
        model.complete("sys", "user")


def test_generator_degrades_to_excerpts_when_llm_unavailable():
    model = build_model(
        lambda request: httpx.Response(503, json={"error": "down"}),
        max_retries=0,
        disable_thinking=False,
    )
    generator = CitationConstrainedAnswerGenerator(model)
    answer = generator.answer("VPN-401 是什么？", [make_hit()])
    assert generator.last_degraded is True
    assert generator.last_error
    # 降级后仍必须给出可核验的原文，而不是空答案或编造内容。
    assert "根据当前已授权知识" in answer
    assert "VPN-401" in answer


def test_generator_refuses_without_evidence():
    model = build_model(lambda request: completion("不该被调用"))
    generator = CitationConstrainedAnswerGenerator(model)
    assert generator.answer("无证据问题", []) == "当前授权范围内的证据不足以确认该问题。"


def test_generator_sends_numbered_evidence_and_redacts_restricted():
    captured: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        captured.append(json.loads(request.content)["messages"][1]["content"])
        return completion("结论 [1]")

    generator = CitationConstrainedAnswerGenerator(build_model(handler))
    hit = make_hit(content="参见 restricted-topology 的拓扑细节")
    generator.answer("问题", [hit], restricted_source_ids=frozenset({"restricted-topology"}))
    prompt = captured[0]
    assert "[1]" in prompt
    # 受限文档编号不得出现在送往模型的证据里。
    assert "restricted-topology" not in prompt
    assert "[受限引用已隐藏]" in prompt


def test_redaction_preserves_authorized_text_surrounding_a_restricted_id():
    content = "Oracle 11gR2 is supported; details are in restricted-topology."

    safe = EvidenceAnswerGenerator.redact_restricted_references(
        content,
        frozenset({"restricted-topology"}),
    )

    assert "Oracle 11gR2 is supported" in safe
    assert "restricted-topology" not in safe
    assert "[受限引用已隐藏]" in safe


def test_extractive_generator_still_available_as_baseline():
    answer = EvidenceAnswerGenerator().answer("问题", [make_hit()])
    assert "根据当前已授权知识" in answer


def test_question_aware_excerpt_selects_late_matching_evidence():
    content = (
        "General release notes and unrelated setup details. " * 20
        + "The remediation is to install fix pack FP-42 and restart the server."
    )

    excerpt = select_excerpt("Which fix pack remediates the issue?", content, limit=90)

    assert "FP-42" in excerpt
    assert excerpt.endswith("restart the server.")


def test_excerpt_prefers_focused_answer_over_verbose_reference() -> None:
    content = (
        "For Linux WebSphere ulimit settings, refer to the detailed Linux WebSphere "
        "ulimit settings guide at https://example.test/docs/ulimit with additional "
        "background and operating-system instructions.\n"
        "WebSphere Support recommends setting the Linux ulimit to 131072."
    )

    excerpt = select_excerpt(
        "What ulimit setting is recommended for WebSphere on Linux?",
        content,
        limit=100,
    )

    assert "131072" in excerpt
    assert "example.test" not in excerpt


def test_question_aware_excerpt_combines_complementary_statements():
    content = (
        "Before migration, create a database backup. "
        "The dashboard contains general migration announcements. "
        "After migration, validate the schema checksum."
    )

    excerpt = select_excerpt(
        "What backup is required before migration and what validation follows migration?",
        content,
        limit=105,
    )

    assert "create a database backup" in excerpt
    assert "validate the schema checksum" in excerpt
    assert "general migration announcements" not in excerpt
    assert " ... " in excerpt


def test_question_aware_excerpt_keeps_short_content_intact():
    content = "  Install FP-42.\n\nRestart the server after installation.  "

    assert select_excerpt("How is FP-42 installed?", content, limit=100) == (
        "Install FP-42. Restart the server after installation."
    )


def test_question_aware_excerpt_is_bounded_and_has_stable_single_line_layout():
    content = (
        "Unrelated introductory material that should not be selected.\n\n"
        "The required fix is FP-77. Restart the service after installing FP-77.\n\n"
        "Unrelated closing material that should not be selected."
    )

    first = select_excerpt("Which fix is required?", content, limit=70)
    second = select_excerpt("Which fix is required?", content, limit=70)

    assert first == second
    assert len(first) <= 70
    assert "\n" not in first
    assert first == "The required fix is FP-77. Restart the service after installing FP-77."


def test_generator_selects_late_query_relevant_evidence_for_model():
    captured: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        captured.append(json.loads(request.content)["messages"][1]["content"])
        return completion("结论 [1]")

    content = (
        "General release notes and unrelated setup details. " * 20
        + "The remediation is to install fix pack FP-42 and restart the server."
    )
    generator = CitationConstrainedAnswerGenerator(
        build_model(handler),
        evidence_characters=90,
    )

    generator.answer("Which fix pack remediates the issue?", [make_hit(content=content)])

    assert "FP-42" in captured[0]
    assert captured[0].count("General release notes") == 0
