"""Metric primitives for the P2 golden-set evaluation.

Kept free of retrieval/service imports so the maths stays unit-testable on its own.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence

_LATIN_TOKEN = re.compile(r"[a-z0-9]+")
_CJK_CHAR = re.compile(r"[一-鿿]")

# Deliberately small: the corpus is IBM technotes, so trimming generic English
# filler is enough. A larger list would start deleting real technical content.
_STOPWORDS = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "been", "but", "by", "can",
        "for", "from", "had", "has", "have", "if", "in", "into", "is", "it",
        "its", "of", "on", "or", "that", "the", "then", "there", "these",
        "this", "to", "was", "were", "when", "which", "will", "with", "you",
        "your",
    }
)


def tokenize(text: str) -> set[str]:
    """Bag of content tokens: latin words plus individual CJK characters.

    CJK is split per character because the project ships no segmenter; for
    recall-style overlap that is close enough and stays dependency-free.
    """
    lowered = text.lower()
    tokens = {token for token in _LATIN_TOKEN.findall(lowered) if token not in _STOPWORDS}
    tokens.update(_CJK_CHAR.findall(lowered))
    return tokens


def content_recall(gold: str, candidate: str) -> float:
    """Fraction of the gold answer's content tokens present in the candidate.

    Recall rather than F1: the extractive generator emits whole chunk excerpts,
    so it is always far longer than the gold span and precision would punish it
    for context it was designed to include.
    """
    gold_tokens = tokenize(gold)
    if not gold_tokens:
        return 0.0
    return len(gold_tokens & tokenize(candidate)) / len(gold_tokens)


def reciprocal_rank(ranked: Sequence[str], relevant: set[str]) -> float:
    if not relevant:
        return 0.0
    for position, item in enumerate(ranked, start=1):
        if item in relevant:
            return 1.0 / position
    return 0.0


def ndcg_at_k(ranked: Sequence[str], relevant: set[str], k: int) -> float:
    """Binary-relevance nDCG@k."""
    if not relevant or k <= 0:
        return 0.0
    gain = sum(
        1.0 / math.log2(position + 1)
        for position, item in enumerate(ranked[:k], start=1)
        if item in relevant
    )
    ideal = sum(
        1.0 / math.log2(position + 1)
        for position in range(1, min(len(relevant), k) + 1)
    )
    if ideal == 0.0:
        return 0.0
    return gain / ideal


def wilson_interval(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion.

    Used instead of the normal approximation because several P2 slices are tiny
    (n=20) and saturate at 1.0, where the normal interval collapses to zero width
    and reports a certainty the sample size does not support.
    """
    if total <= 0:
        return (0.0, 0.0)
    proportion = successes / total
    denominator = 1.0 + z * z / total
    centre = proportion + z * z / (2 * total)
    margin = z * math.sqrt(proportion * (1.0 - proportion) / total + z * z / (4 * total * total))
    low = (centre - margin) / denominator
    high = (centre + margin) / denominator
    return (max(0.0, low), min(1.0, high))
