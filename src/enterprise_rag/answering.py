from enterprise_rag.models import SearchHit


class EvidenceAnswerGenerator:
    """Deterministic P1 generator; replaceable by a citation-constrained vLLM adapter."""

    def answer(self, question: str, hits: list[SearchHit]) -> str:
        del question
        excerpts: list[str] = []
        for hit in hits[:3]:
            compact = " ".join(hit.chunk.content.split())
            excerpts.append(f"《{hit.chunk.title}》：{compact[:360]}")
        return "根据当前已授权知识：\n" + "\n".join(excerpts)


def format_tool_answer(rows: list[dict[str, object]]) -> str:
    if not rows:
        return "权威数据源未返回记录。"
    if len(rows) == 1 and len(rows[0]) == 1:
        key, value = next(iter(rows[0].items()))
        return f"权威数据库查询结果：{key} = {value}。"
    return f"权威数据库返回 {len(rows)} 条记录：{rows}"

