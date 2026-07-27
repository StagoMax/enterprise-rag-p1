import math

import pytest

from enterprise_rag.evaluation import (
    content_recall,
    ndcg_at_k,
    reciprocal_rank,
    tokenize,
    wilson_interval,
)


def test_tokenize_drops_stopwords_and_keeps_technical_tokens():
    tokens = tokenize("The ulimit is set to 131072 on Linux")
    assert "ulimit" in tokens
    assert "131072" in tokens
    assert "linux" in tokens
    assert "the" not in tokens
    assert "is" not in tokens


def test_tokenize_splits_cjk_per_character():
    assert tokenize("权限隔离") == {"权", "限", "隔", "离"}


def test_content_recall_full_and_partial():
    gold = "set nproc to 131072"
    assert content_recall(gold, "you should set nproc to 131072 on Linux") == 1.0
    assert content_recall(gold, "completely unrelated text") == 0.0
    assert content_recall(gold, "set nproc") == pytest.approx(2 / 3)


def test_content_recall_empty_gold_is_zero():
    assert content_recall("", "anything") == 0.0
    assert content_recall("the and of", "anything") == 0.0


def test_content_recall_ignores_extra_context():
    # The extractive generator pads with surrounding chunk text; recall must not
    # punish that, which is why it is recall and not F1.
    assert content_recall("nproc value", "《doc》: the nproc value is important " * 20) == 1.0


def test_reciprocal_rank():
    assert reciprocal_rank(["a", "b", "c"], {"a"}) == 1.0
    assert reciprocal_rank(["a", "b", "c"], {"b"}) == 0.5
    assert reciprocal_rank(["a", "b", "c"], {"c"}) == pytest.approx(1 / 3)
    assert reciprocal_rank(["a", "b"], {"z"}) == 0.0
    assert reciprocal_rank([], {"a"}) == 0.0
    assert reciprocal_rank(["a"], set()) == 0.0


def test_ndcg_perfect_and_ordered():
    assert ndcg_at_k(["a", "b", "c"], {"a"}, 3) == 1.0
    assert ndcg_at_k(["a", "b"], {"a", "b"}, 3) == 1.0
    # One relevant doc at rank 2 instead of rank 1.
    assert ndcg_at_k(["x", "a", "y"], {"a"}, 3) == pytest.approx(1 / math.log2(3))


def test_ndcg_edge_cases():
    assert ndcg_at_k(["a"], set(), 3) == 0.0
    assert ndcg_at_k(["a"], {"a"}, 0) == 0.0
    assert ndcg_at_k(["x", "y"], {"a"}, 2) == 0.0


def test_ndcg_respects_k_cutoff():
    # Relevant item sits at rank 3, outside k=2.
    assert ndcg_at_k(["x", "y", "a"], {"a"}, 2) == 0.0


def test_wilson_interval_brackets_the_estimate():
    low, high = wilson_interval(17, 20)
    assert low < 0.85 < high


def test_wilson_interval_saturated_small_sample_is_not_certain():
    # The reason this metric exists: 20/20 is not evidence of a true rate of 1.0.
    low, high = wilson_interval(20, 20)
    assert high == pytest.approx(1.0)
    assert 0.80 < low < 0.90


def test_wilson_interval_narrows_as_n_grows():
    small = wilson_interval(50, 100)
    large = wilson_interval(500, 1000)
    assert (large[1] - large[0]) < (small[1] - small[0])


def test_wilson_interval_degenerate_inputs():
    assert wilson_interval(0, 0) == (0.0, 0.0)
    low, high = wilson_interval(0, 10)
    assert low == 0.0
    assert 0.0 < high < 0.5
