"""LLM 重排器。

诊断结论：1,000 文档规模下 11 个 Top-1 失败里有 10 个，错误文档在 BM25 阶段就已经排第一，
与嵌入模型无关；调融合权重的天花板只有 +0.025。唯一有空间的杠杆是在更大的候选池上重排
（oracle 上限：池 20 时 0.9875）。现成的 ms-marco cross-encoder 因 512 token 截断反而使
引用准确率从 0.875 掉到 0.825，所以这里改用长上下文的生成模型来判断相关性。

重排只改变顺序，不引入新证据，也不放宽 ACL：候选集在进入这里之前已经过滤完毕。
"""

import json
import re
from collections.abc import Sequence

import numpy as np

from enterprise_rag.llm import ChatModel, LlmUnavailableError

_SYSTEM_PROMPT = """你是检索重排器。给定一个问题和若干候选文档片段，
按"能否直接回答该问题"从高到低排序。

规则：
1. 只输出 JSON 数组，形如 [3, 1, 5]，元素是候选编号，最相关的排最前。
2. 必须且只能包含给定的候选编号，每个编号出现一次，不得新增或省略。
3. 判断依据是片段能否支撑答案，而不是词面重合度。
   宽泛的通用故障排查文档通常不如直接讲清该问题的文档相关。
4. 不要输出解释、不要输出 JSON 以外的任何内容。"""

_JSON_ARRAY = re.compile(r"\[[\s\d,]*\]")


def parse_ranking(raw: str, candidate_count: int) -> list[int]:
    """从模型输出里解析排名。容忍多余文本、重复和缺项。

    返回 0-based 顺序；无法解析时返回空列表，由调用方保持原顺序。
    """
    match = _JSON_ARRAY.search(raw)
    if not match:
        return []
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []

    order: list[int] = []
    seen: set[int] = set()
    for item in parsed:
        if not isinstance(item, int):
            continue
        index = item - 1  # 提示词里用 1-based 编号
        if 0 <= index < candidate_count and index not in seen:
            seen.add(index)
            order.append(index)
    # 模型漏掉的候选按原顺序补在后面，保证不丢结果。
    order.extend(index for index in range(candidate_count) if index not in seen)
    return order


class LlmReranker:
    """满足 embeddings.Reranker 协议，可直接替换 CrossEncoderReranker。"""

    def __init__(
        self,
        model: ChatModel,
        *,
        max_candidates: int = 20,
        candidate_characters: int = 700,
    ) -> None:
        self._model = model
        self._max_candidates = max_candidates
        self._candidate_characters = candidate_characters
        self.last_error: str | None = None
        self.last_degraded = False

    def score(self, query: str, documents: Sequence[str]) -> np.ndarray:
        self.last_error = None
        self.last_degraded = False
        count = len(documents)
        if count == 0:
            return np.empty(0, dtype=np.float32)
        if count == 1:
            return np.ones(1, dtype=np.float32)

        # 只重排前若干个；其余保持原有相对顺序并排在后面。
        window = min(count, self._max_candidates)
        entries = []
        for position in range(window):
            body = " ".join(documents[position].split())[: self._candidate_characters]
            entries.append(f"[{position + 1}] {body}")
        listing = "\n\n".join(entries)
        prompt = f"【问题】\n{query}\n\n【候选片段】\n{listing}"

        try:
            raw = self._model.complete(_SYSTEM_PROMPT, prompt)
        except LlmUnavailableError as exc:
            self.last_error = str(exc)
            self.last_degraded = True
            return self._identity(count)

        order = parse_ranking(raw, window)
        if not order:
            self.last_error = f"无法解析重排输出：{raw[:120]}"
            self.last_degraded = True
            return self._identity(count)

        scores = np.zeros(count, dtype=np.float32)
        # 窗口内按名次给分，窗口外统一低于窗口内且保持原序。
        for rank, index in enumerate(order):
            scores[index] = float(count - rank)
        for position in range(window, count):
            scores[position] = float(count - window - position) * 0.001
        return scores

    @staticmethod
    def _identity(count: int) -> np.ndarray:
        """降级：保持调用方传入的原始顺序。"""
        return np.arange(count, 0, -1, dtype=np.float32)
