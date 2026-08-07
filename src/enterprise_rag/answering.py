import re
from collections.abc import Callable

from enterprise_rag.llm import ChatModel, LlmUnavailableError
from enterprise_rag.models import SearchHit

# Per-hit excerpt budget. Evaluation imports this: a gold answer longer than the
# budget cannot be surfaced in full, so answer-quality gating controls for it.
EXCERPT_CHARS = 360

_EXCERPT_TOKEN_PATTERN = re.compile(
    r"[a-z0-9]+(?:[._:/-][a-z0-9]+)*|[\u4e00-\u9fff]+",
    re.IGNORECASE,
)
_REFERENCE_TOKEN_PATTERN = re.compile(
    r"[a-z0-9]+(?:[._:-][a-z0-9]+)*",
    re.IGNORECASE,
)
_REDACTED_REFERENCE = "[受限引用已隐藏]"
_SENTENCE_BOUNDARY_PATTERN = re.compile(r"(?<=[。！？；])|(?<=[.!?;])(?=\s|$)")
_EXCERPT_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "by",
        "document",
        "for",
        "from",
        "how",
        "identify",
        "in",
        "is",
        "its",
        "of",
        "on",
        "related",
        "the",
        "to",
        "what",
        "which",
        "with",
    }
)

_SYSTEM_PROMPT = """你是企业知识助手。严格遵守以下规则：

1. 只能使用【证据】中的内容回答。证据之外的知识、常识和推测都不得写入答案。
2. 每个结论后必须标注来源编号，格式为 [1]、[2]，编号对应证据条目。
3. 证据不足以回答问题时，只回答"当前授权范围内的证据不足以确认该问题。"，不要拼凑。
4. 证据之间矛盾时，指出矛盾并分别注明来源，不要自行裁决。
5. 出现"[受限引用已隐藏]"表示该内容对当前用户不可见，不得推测其内容。
6. 用中文回答，简洁准确，不复述问题，不整段拷贝证据原文。"""

_INSUFFICIENT = "当前授权范围内的证据不足以确认该问题。"

Redactor = Callable[[str, frozenset[str]], str]


def _evidence_content(hit: SearchHit) -> str:
    """Expand a retrieved child to its bounded logical parent when available."""

    return hit.chunk.parent_content or hit.chunk.content


def _stem_english_term(term: str) -> str:
    for suffix in ("ations", "ation", "ments", "ment", "ingly", "ing", "edly", "ed", "es", "s"):
        if term.endswith(suffix) and len(term) - len(suffix) >= 5:
            return term[: -len(suffix)]
    return term


def _question_terms(question: str) -> frozenset[str]:
    terms: set[str] = set()
    for token in _EXCERPT_TOKEN_PATTERN.findall(question.lower()):
        if token[0].isascii():
            if len(token) > 1 and token not in _EXCERPT_STOPWORDS:
                terms.add(_stem_english_term(token))
            continue

        # Character bigrams provide deterministic matching for Chinese without
        # requiring a language-specific tokenizer.
        if len(token) == 1:
            continue
        terms.update(token[index : index + 2] for index in range(len(token) - 1))
    return frozenset(terms)


def _evidence_units(content: str) -> list[str]:
    units: list[str] = []
    seen: set[str] = set()
    for paragraph in content.splitlines() or [content]:
        compact_paragraph = " ".join(paragraph.split())
        if not compact_paragraph:
            continue
        for sentence in _SENTENCE_BOUNDARY_PATTERN.split(compact_paragraph):
            unit = sentence.strip()
            key = unit.casefold()
            if unit and key not in seen:
                units.append(unit)
                seen.add(key)
    return units


def _term_weight(term: str) -> int:
    if any(character.isdigit() or character in "._:/-" for character in term):
        return 4
    return 2 if len(term) >= 6 else 1


def _matching_terms(text: str, terms: frozenset[str]) -> frozenset[str]:
    lowered = text.lower()
    return frozenset(term for term in terms if term in lowered)


def _clip_unit(text: str, limit: int, terms: frozenset[str]) -> str:
    """Bound an oversized sentence, preferring a word boundary near a query match."""
    if len(text) <= limit:
        return text
    if limit <= 0:
        return ""

    lowered = text.lower()
    match_positions = [lowered.find(term) for term in terms if term in lowered]
    focus = min(match_positions) if match_positions else 0
    start = min(max(focus - limit // 3, 0), len(text) - limit)
    end = start + limit

    if start:
        next_space = text.find(" ", start, min(focus + 1, end))
        if next_space >= 0:
            start = next_space + 1
    if end < len(text):
        previous_space = text.rfind(" ", start, end)
        if previous_space > start:
            end = previous_space
    clipped = text[start:end].strip()
    return clipped[:limit]


def _join_selected_units(selected: list[int], units: list[str]) -> str:
    ordered = sorted(selected)
    parts: list[str] = []
    previous: int | None = None
    for index in ordered:
        if previous is not None:
            parts.append(" " if index == previous + 1 else " ... ")
        parts.append(units[index])
        previous = index
    return "".join(parts)


def _leading_units(units: list[str], limit: int, terms: frozenset[str]) -> str:
    selected: list[int] = []
    used_characters = 0
    for index, unit in enumerate(units):
        size = len(unit) + (1 if selected else 0)
        if used_characters + size > limit:
            break
        selected.append(index)
        used_characters += size
    if selected:
        return _join_selected_units(selected, units)
    return _clip_unit(units[0], limit, terms)


def select_excerpt(question: str, content: str, *, limit: int = EXCERPT_CHARS) -> str:
    """Select query-relevant, complete evidence units within a character budget."""
    if limit <= 0:
        return ""
    compact = " ".join(content.split())
    if len(compact) <= limit:
        return compact

    units = _evidence_units(content)
    if not units:
        return ""

    terms = _question_terms(question)
    matches = [_matching_terms(unit, terms) for unit in units]
    relevant = {index for index, matched in enumerate(matches) if matched}
    if not relevant:
        return _leading_units(units, limit, terms)

    selected: list[int] = []
    covered: set[str] = set()
    while relevant:
        fitting = [
            index
            for index in relevant
            if len(_join_selected_units([*selected, index], units)) <= limit
        ]
        if not fitting:
            break

        def rank(index: int) -> tuple[int, int, int, int, int]:
            new_weight = sum(_term_weight(term) for term in matches[index] - covered)
            total_weight = sum(_term_weight(term) for term in matches[index])
            occurrences = sum(units[index].lower().count(term) for term in matches[index])
            return new_weight, total_weight, -len(units[index]), occurrences, -index

        best = max(fitting, key=rank)
        selected.append(best)
        covered.update(matches[best])
        relevant.remove(best)

    if not selected:
        best = max(
            relevant,
            key=lambda index: (
                sum(_term_weight(term) for term in matches[index]),
                -len(units[index]),
                sum(units[index].lower().count(term) for term in matches[index]),
                -index,
            ),
        )
        return _clip_unit(units[best], limit, matches[best])

    # A directly adjacent sentence often contains the action or condition that
    # completes a matched statement without repeating the query vocabulary.
    neighbors: list[int] = []
    for index in selected:
        neighbors.extend(
            candidate for candidate in (index + 1, index - 1) if 0 <= candidate < len(units)
        )
    for index in dict.fromkeys(neighbors):
        if index in selected:
            continue
        if len(_join_selected_units([*selected, index], units)) <= limit:
            selected.append(index)

    return _join_selected_units(selected, units)


class EvidenceAnswerGenerator:
    """Deterministic P1 generator; also the fallback when the LLM is unavailable."""

    @staticmethod
    def redact_restricted_references(content: str, restricted_ids: frozenset[str]) -> str:
        lowered_ids = {source_id.lower() for source_id in restricted_ids}
        if not lowered_ids:
            return content

        def redact_token(match: re.Match[str]) -> str:
            return _REDACTED_REFERENCE if match.group(0).lower() in lowered_ids else match.group(0)

        return _REFERENCE_TOKEN_PATTERN.sub(redact_token, content)

    def answer(
        self,
        question: str,
        hits: list[SearchHit],
        *,
        restricted_source_ids: frozenset[str] = frozenset(),
    ) -> str:
        excerpts: list[str] = []
        for hit in hits[:3]:
            safe_title = self.redact_restricted_references(
                hit.chunk.title,
                restricted_source_ids,
            )
            safe_content = self.redact_restricted_references(
                _evidence_content(hit),
                restricted_source_ids,
            )
            excerpt = select_excerpt(question, safe_content)
            excerpts.append(f"《{safe_title}》：{excerpt}")
        return "根据当前已授权知识：\n" + "\n".join(excerpts)


def build_evidence_block(
    hits: list[SearchHit],
    redact: Redactor,
    restricted_source_ids: frozenset[str],
    *,
    evidence_characters: int,
    question: str = "",
) -> str:
    """把命中分块编号后交给模型。编号即引用锚，模型只能引用这里出现的编号。"""
    entries: list[str] = []
    for index, hit in enumerate(hits, start=1):
        title = redact(hit.chunk.title, restricted_source_ids)
        safe_content = redact(_evidence_content(hit), restricted_source_ids)
        body = select_excerpt(question, safe_content, limit=evidence_characters)
        entries.append(
            f"[{index}] 《{title}》（文档 {hit.chunk.document_id}，"
            f"版本 {hit.chunk.version}，锚点 {hit.chunk.anchor}）\n"
            f"{body[:evidence_characters]}"
        )
    return "\n\n".join(entries)


class CitationConstrainedAnswerGenerator(EvidenceAnswerGenerator):
    """受引用约束的生成式回答。模型不可用时降级为摘录，绝不静默编造。"""

    def __init__(
        self,
        model: ChatModel,
        *,
        evidence_limit: int = 5,
        evidence_characters: int = 1600,
    ) -> None:
        self._model = model
        self._evidence_limit = evidence_limit
        self._evidence_characters = evidence_characters
        self.last_error: str | None = None
        self.last_degraded = False

    def answer(
        self,
        question: str,
        hits: list[SearchHit],
        *,
        restricted_source_ids: frozenset[str] = frozenset(),
    ) -> str:
        self.last_error = None
        self.last_degraded = False
        if not hits:
            return _INSUFFICIENT

        evidence = build_evidence_block(
            hits[: self._evidence_limit],
            self.redact_restricted_references,
            restricted_source_ids,
            evidence_characters=self._evidence_characters,
            question=question,
        )
        try:
            return self._model.complete(
                _SYSTEM_PROMPT,
                f"【问题】\n{question}\n\n【证据】\n{evidence}",
            )
        except LlmUnavailableError as exc:
            # 降级到可核验的原文摘录，而不是中断查询或让模型凭空作答。
            self.last_error = str(exc)
            self.last_degraded = True
            return super().answer(
                question,
                hits,
                restricted_source_ids=restricted_source_ids,
            )


def format_tool_answer(rows: list[dict[str, object]]) -> str:
    if not rows:
        return "权威数据源未返回记录。"
    if len(rows) == 1 and len(rows[0]) == 1:
        key, value = next(iter(rows[0].items()))
        return f"权威数据库查询结果：{key} = {value}。"
    return f"权威数据库返回 {len(rows)} 条记录：{rows}"
