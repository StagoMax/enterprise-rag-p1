import httpx
import numpy as np

from enterprise_rag.llm import OpenAiCompatibleChatModel
from enterprise_rag.reranking import LlmReranker, parse_ranking


def model_returning(content: str, *, status: int = 200) -> OpenAiCompatibleChatModel:
    def handler(request: httpx.Request) -> httpx.Response:
        if status != 200:
            return httpx.Response(status, json={"error": "down"})
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    return OpenAiCompatibleChatModel(
        base_url="http://llm.test/v1",
        api_key="k",
        model="m",
        max_retries=0,
        disable_thinking=False,
        client=httpx.Client(transport=httpx.MockTransport(handler), base_url="http://llm.test/v1"),
    )


def order_of(scores: np.ndarray) -> list[int]:
    return list(np.argsort(-scores))


def test_parse_ranking_converts_to_zero_based():
    assert parse_ranking("[2, 1, 3]", 3) == [1, 0, 2]


def test_parse_ranking_tolerates_surrounding_text():
    assert parse_ranking("排序结果如下：[3, 1, 2] 完毕", 3) == [2, 0, 1]


def test_parse_ranking_fills_in_omitted_candidates():
    # 模型只给了 2 个，剩下的必须按原顺序补齐，不能丢候选。
    assert parse_ranking("[3]", 3) == [2, 0, 1]


def test_parse_ranking_drops_duplicates_and_out_of_range():
    assert parse_ranking("[2, 2, 9, 0, 1]", 3) == [1, 0, 2]


def test_parse_ranking_returns_empty_on_garbage():
    assert parse_ranking("我拒绝回答", 3) == []
    assert parse_ranking("[1, 2", 3) == []


def test_reranker_reorders_by_model_output():
    reranker = LlmReranker(model_returning("[3, 1, 2]"))
    scores = reranker.score("问题", ["A", "B", "C"])
    assert order_of(scores) == [2, 0, 1]
    assert reranker.last_degraded is False


def test_reranker_keeps_original_order_when_llm_unavailable():
    reranker = LlmReranker(model_returning("", status=503))
    scores = reranker.score("问题", ["A", "B", "C"])
    # 降级必须保持调用方给的顺序，而不是随机打乱检索结果。
    assert order_of(scores) == [0, 1, 2]
    assert reranker.last_degraded is True
    assert reranker.last_error


def test_reranker_keeps_original_order_on_unparseable_output():
    reranker = LlmReranker(model_returning("我觉得都挺相关的"))
    scores = reranker.score("问题", ["A", "B", "C"])
    assert order_of(scores) == [0, 1, 2]
    assert reranker.last_degraded is True


def test_reranker_handles_empty_and_single_candidate():
    reranker = LlmReranker(model_returning("[1]"))
    assert reranker.score("q", []).shape == (0,)
    assert reranker.score("q", ["only"]).shape == (1,)


def test_candidates_beyond_window_rank_below_window():
    reranker = LlmReranker(model_returning("[2, 1]"), max_candidates=2)
    scores = reranker.score("问题", ["A", "B", "C", "D"])
    ranked = order_of(scores)
    # 窗口内的两个必须排在窗口外的前面。
    assert set(ranked[:2]) == {0, 1}
    assert ranked[0] == 1


def test_prompt_contains_numbered_candidates():
    captured: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        captured.append(json.loads(request.content)["messages"][1]["content"])
        return httpx.Response(200, json={"choices": [{"message": {"content": "[1,2]"}}]})

    model = OpenAiCompatibleChatModel(
        base_url="http://llm.test/v1",
        api_key="k",
        model="m",
        disable_thinking=False,
        client=httpx.Client(transport=httpx.MockTransport(handler), base_url="http://llm.test/v1"),
    )
    LlmReranker(model).score("怎么处理 VPN-401", ["证书未登记", "无关内容"])
    assert "[1]" in captured[0] and "[2]" in captured[0]
    assert "怎么处理 VPN-401" in captured[0]


def test_reranker_satisfies_store_protocol_contract():
    """分数长度必须与输入候选数一致，否则 store 侧 zip(strict=True) 会炸。"""
    reranker = LlmReranker(model_returning("[2,1,3,4,5]"))
    documents = [f"doc {index}" for index in range(5)]
    assert reranker.score("q", documents).shape == (5,)
