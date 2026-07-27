from collections.abc import Callable

from enterprise_rag.llm import ChatModel, LlmUnavailableError
from enterprise_rag.models import SearchHit

# Per-hit excerpt budget. Evaluation imports this: a gold answer longer than the
# budget cannot be surfaced in full, so answer-quality gating controls for it.
EXCERPT_CHARS = 360

_SYSTEM_PROMPT = """你是企业知识助手。严格遵守以下规则：

1. 只能使用【证据】中的内容回答。证据之外的知识、常识和推测都不得写入答案。
2. 每个结论后必须标注来源编号，格式为 [1]、[2]，编号对应证据条目。
3. 证据不足以回答问题时，只回答"当前授权范围内的证据不足以确认该问题。"，不要拼凑。
4. 证据之间矛盾时，指出矛盾并分别注明来源，不要自行裁决。
5. 出现"[受限引用已隐藏]"表示该内容对当前用户不可见，不得推测其内容。
6. 用中文回答，简洁准确，不复述问题，不整段拷贝证据原文。"""

_INSUFFICIENT = "当前授权范围内的证据不足以确认该问题。"

Redactor = Callable[[str, frozenset[str]], str]


class EvidenceAnswerGenerator:
    """Deterministic P1 generator; also the fallback when the LLM is unavailable."""

    @staticmethod
    def redact_restricted_references(content: str, restricted_ids: frozenset[str]) -> str:
        lowered_ids = {source_id.lower() for source_id in restricted_ids}
        safe_lines: list[str] = []
        for line in content.splitlines():
            lowered_line = line.lower()
            if any(source_id in lowered_line for source_id in lowered_ids):
                safe_lines.append("[受限引用已隐藏]")
            else:
                safe_lines.append(line)
        return "\n".join(safe_lines)

    def answer(
        self,
        question: str,
        hits: list[SearchHit],
        *,
        restricted_source_ids: frozenset[str] = frozenset(),
    ) -> str:
        del question
        excerpts: list[str] = []
        for hit in hits[:3]:
            safe_title = self.redact_restricted_references(
                hit.chunk.title,
                restricted_source_ids,
            )
            safe_content = self.redact_restricted_references(
                hit.chunk.content,
                restricted_source_ids,
            )
            compact = " ".join(safe_content.split())
            excerpts.append(f"《{safe_title}》：{compact[:EXCERPT_CHARS]}")
        return "根据当前已授权知识：\n" + "\n".join(excerpts)


def build_evidence_block(
    hits: list[SearchHit],
    redact: Redactor,
    restricted_source_ids: frozenset[str],
    *,
    evidence_characters: int,
) -> str:
    """把命中分块编号后交给模型。编号即引用锚，模型只能引用这里出现的编号。"""
    entries: list[str] = []
    for index, hit in enumerate(hits, start=1):
        title = redact(hit.chunk.title, restricted_source_ids)
        body = " ".join(redact(hit.chunk.content, restricted_source_ids).split())
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
