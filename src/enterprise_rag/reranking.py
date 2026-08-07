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
from hashlib import sha256
from pathlib import Path

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
        cache_mode: str = "off",
        cache_path: Path | None = None,
        cache_namespace: str = "default",
    ) -> None:
        if cache_mode not in {"off", "record", "replay"}:
            raise ValueError(f"unsupported reranker cache mode: {cache_mode}")
        if cache_mode != "off" and cache_path is None:
            raise ValueError("reranker cache path is required for record/replay mode")
        self._model = model
        self._max_candidates = max_candidates
        self._candidate_characters = candidate_characters
        self._cache_mode = cache_mode
        self._cache_path = cache_path
        self._cache_namespace = cache_namespace
        self._cache: dict[str, list[float]] = {}
        self.last_error: str | None = None
        self.last_degraded = False
        self.call_count = 0
        self.degraded_count = 0
        self.external_call_count = 0
        self.cache_hit_count = 0
        self.deterministic_call_count = 0
        self.http_attempt_count = 0
        self._judgement_hasher = sha256()
        if cache_mode == "record" and cache_path is not None:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            if cache_path.exists():
                self._load_cache(cache_path)
            else:
                cache_path.touch()
        elif cache_mode == "replay" and cache_path is not None:
            self._load_cache(cache_path)

    def _load_cache(self, path: Path) -> None:
        if not path.exists():
            raise RuntimeError(f"reranker replay cache does not exist: {path}")
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            key = str(row["key"])
            scores = [float(value) for value in row["scores"]]
            previous = self._cache.get(key)
            if previous is not None and previous != scores:
                raise RuntimeError(f"reranker replay cache has conflicting rows for key {key}")
            self._cache[key] = scores

    def _cache_key(self, query: str, documents: Sequence[str]) -> str:
        payload = json.dumps(
            [
                self._cache_namespace,
                _SYSTEM_PROMPT,
                self._max_candidates,
                self._candidate_characters,
                query,
                list(documents),
            ],
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        return sha256(payload).hexdigest()

    def _record_cache(self, key: str, scores: np.ndarray) -> None:
        if self._cache_path is None:
            return
        values = [float(value) for value in scores]
        self._cache[key] = values
        with self._cache_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"key": key, "scores": values}) + "\n")

    def _observe_judgement(self, key: str, scores: np.ndarray) -> None:
        payload = json.dumps(
            {"key": key, "scores": [float(value) for value in scores]},
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        self._judgement_hasher.update(len(payload).to_bytes(8, "big"))
        self._judgement_hasher.update(payload)

    @property
    def judgement_digest(self) -> str:
        return self._judgement_hasher.hexdigest()

    def _finish(self, key: str, scores: np.ndarray) -> np.ndarray:
        self._observe_judgement(key, scores)
        return scores

    def score(self, query: str, documents: Sequence[str]) -> np.ndarray:
        self.last_error = None
        self.last_degraded = False
        count = len(documents)
        cache_key = self._cache_key(query, documents)
        self.call_count += 1
        if self._cache_mode == "replay":
            cached = self._cache.get(cache_key)
            if cached is None:
                raise RuntimeError(
                    "reranker replay cache miss; candidate generation changed between A/B runs"
                )
            if len(cached) != count:
                raise RuntimeError("reranker replay cache has an invalid score count")
            self.cache_hit_count += 1
            return self._finish(cache_key, np.asarray(cached, dtype=np.float32))

        if self._cache_mode == "record" and cache_key in self._cache:
            cached = self._cache[cache_key]
            if len(cached) != count:
                raise RuntimeError("reranker record cache has an invalid score count")
            self.cache_hit_count += 1
            return self._finish(cache_key, np.asarray(cached, dtype=np.float32))

        if count <= 1:
            scores = (
                np.empty(0, dtype=np.float32)
                if count == 0
                else np.ones(1, dtype=np.float32)
            )
            self.deterministic_call_count += 1
            if self._cache_mode == "record":
                self._record_cache(cache_key, scores)
            return self._finish(cache_key, scores)

        # 只重排前若干个；其余保持原有相对顺序并排在后面。
        window = min(count, self._max_candidates)
        entries = []
        for position in range(window):
            body = " ".join(documents[position].split())[: self._candidate_characters]
            entries.append(f"[{position + 1}] {body}")
        listing = "\n\n".join(entries)
        prompt = f"【问题】\n{query}\n\n【候选片段】\n{listing}"

        self.external_call_count += 1
        request_count_before = getattr(self._model, "request_count", None)
        try:
            raw = self._model.complete(_SYSTEM_PROMPT, prompt)
        except LlmUnavailableError as exc:
            self.last_error = str(exc)
            self.last_degraded = True
            self.degraded_count += 1
            if self._cache_mode == "record":
                raise RuntimeError(
                    "reranker record failed; refusing to create an incomplete A/B cache"
                ) from exc
            return self._finish(cache_key, self._identity(count))
        finally:
            request_count_after = getattr(self._model, "request_count", None)
            if isinstance(request_count_before, int) and isinstance(request_count_after, int):
                self.http_attempt_count += max(request_count_after - request_count_before, 0)

        order = parse_ranking(raw, window)
        if not order:
            self.last_error = f"无法解析重排输出：{raw[:120]}"
            self.last_degraded = True
            self.degraded_count += 1
            if self._cache_mode == "record":
                raise RuntimeError(
                    "reranker record produced an invalid ranking; refusing to cache it"
                )
            return self._finish(cache_key, self._identity(count))

        scores = np.zeros(count, dtype=np.float32)
        # 窗口内按名次给分，窗口外统一低于窗口内且保持原序。
        for rank, index in enumerate(order):
            scores[index] = float(count - rank)
        for position in range(window, count):
            scores[position] = float(count - window - position) * 0.001
        if self._cache_mode == "record":
            self._record_cache(cache_key, scores)
        return self._finish(cache_key, scores)

    @staticmethod
    def _identity(count: int) -> np.ndarray:
        """降级：保持调用方传入的原始顺序。"""
        return np.arange(count, 0, -1, dtype=np.float32)
