from uuid import uuid4

from enterprise_rag.answering import EvidenceAnswerGenerator, format_tool_answer
from enterprise_rag.audit import JsonlAuditStore
from enterprise_rag.chunking import build_document, chunk_document
from enterprise_rag.config import Settings
from enterprise_rag.models import (
    AuditEvent,
    Citation,
    DocumentInput,
    Principal,
    QueryRequest,
    QueryResponse,
    Route,
    RouteDecision,
)
from enterprise_rag.retrieval import InMemoryHybridStore
from enterprise_rag.router import RuleBasedRouter
from enterprise_rag.sql_tool import ReadOnlySqlTool


class EnterpriseRagService:
    def __init__(
        self,
        settings: Settings,
        router: RuleBasedRouter,
        store: InMemoryHybridStore,
        sql_tool: ReadOnlySqlTool,
        audit: JsonlAuditStore,
        answer_generator: EvidenceAnswerGenerator,
    ) -> None:
        self._settings = settings
        self._router = router
        self._store = store
        self._sql_tool = sql_tool
        self._audit = audit
        self._answer_generator = answer_generator

    def ingest(self, document_input: DocumentInput) -> tuple[str, int]:
        document = build_document(document_input)
        chunks = chunk_document(document)
        self._store.upsert_document(document, chunks)
        return document.document_id, len(chunks)

    def ingest_many(self, document_inputs: list[DocumentInput]) -> tuple[int, int]:
        items = []
        chunk_count = 0
        for document_input in document_inputs:
            document = build_document(document_input)
            chunks = chunk_document(document)
            chunk_count += len(chunks)
            items.append((document, chunks))
        self._store.upsert_documents(items)
        return len(items), chunk_count

    def _record(
        self,
        trace_id: str,
        principal: Principal,
        decision: RouteDecision,
        *,
        allowed: bool,
        reason: str,
        source_ids: list[str] | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        self._audit.append(
            AuditEvent(
                trace_id=trace_id,
                subject=principal.subject,
                roles=sorted(principal.roles),
                route=decision.route,
                allowed=allowed,
                reason=reason,
                source_ids=source_ids or [],
                metadata=metadata or {},
            )
        )

    def _refusal(
        self,
        trace_id: str,
        principal: Principal,
        decision: RouteDecision,
        reason: str,
    ) -> QueryResponse:
        self._record(trace_id, principal, decision, allowed=False, reason=reason)
        return QueryResponse(
            answer=reason,
            route=decision.route,
            route_reason=decision.reason,
            trace_id=trace_id,
            refused=True,
        )

    def query(self, request: QueryRequest, principal: Principal) -> QueryResponse:
        trace_id = str(uuid4())
        decision = self._router.route(request.question)

        if decision.route == Route.HANDOFF_OR_REFUSE:
            return self._refusal(
                trace_id,
                principal,
                decision,
                "P1 只提供只读问答；该请求需要转交已授权工作流处理。",
            )

        if decision.route == Route.TOOL:
            try:
                result = self._sql_tool.execute_question(request.question)
            except (ValueError, OSError) as exc:
                return self._refusal(
                    trace_id,
                    principal,
                    decision,
                    f"权威数据工具未能安全执行查询：{exc}",
                )
            citation = Citation(
                source_type="sql_tool",
                source_id=result.source_id,
                title="P1 只读销售数据库",
                version=result.schema_version,
                anchor=result.sql,
            )
            self._record(
                trace_id,
                principal,
                decision,
                allowed=True,
                reason="read-only SQL tool completed",
                source_ids=[result.source_id],
                metadata={"sql": result.sql, "row_count": len(result.rows)},
            )
            return QueryResponse(
                answer=format_tool_answer(result.rows),
                route=decision.route,
                route_reason=decision.reason,
                citations=[citation],
                trace_id=trace_id,
                metadata={"row_count": len(result.rows)},
            )

        exact = decision.route == Route.EXACT_SEARCH
        hits = self._store.search(
            request.question,
            principal.roles,
            top_k=self._settings.top_k,
            exact=exact,
            min_score=self._settings.min_retrieval_score,
        )
        if not hits:
            return self._refusal(
                trace_id,
                principal,
                decision,
                "当前授权范围内没有足够证据，无法确认该企业问题。",
            )

        citations = []
        cited_documents: set[str] = set()
        for hit in hits:
            if hit.chunk.document_id in cited_documents:
                continue
            citations.append(
                Citation(
                    source_type="document",
                    source_id=hit.chunk.document_id,
                    title=hit.chunk.title,
                    version=hit.chunk.version,
                    anchor=hit.chunk.anchor,
                    score=hit.score,
                )
            )
            cited_documents.add(hit.chunk.document_id)
            if len(citations) == 3:
                break
        if exact:
            best = hits[0]
            answer = f"精确检索结果：{best.chunk.content}"
        else:
            answer = self._answer_generator.answer(request.question, hits)

        source_ids = list(dict.fromkeys(hit.chunk.document_id for hit in hits))
        self._record(
            trace_id,
            principal,
            decision,
            allowed=True,
            reason="authorized evidence retrieved",
            source_ids=source_ids,
            metadata={"hit_count": len(hits), "exact": exact},
        )
        return QueryResponse(
            answer=answer,
            route=decision.route,
            route_reason=decision.reason,
            citations=citations,
            trace_id=trace_id,
            metadata={"hit_count": len(hits)},
        )

    def recent_audit_events(self, limit: int = 100) -> list[AuditEvent]:
        return self._audit.recent(limit)

    def authorized_documents(self, principal: Principal) -> list[dict[str, object]]:
        return [
            {
                "document_id": document.document_id,
                "title": document.title,
                "owner": document.owner,
                "business_class": document.business_class,
                "sensitivity": document.sensitivity,
                "version": document.version,
                "source_uri": document.source_uri,
            }
            for document in self._store.authorized_documents(principal.roles)
        ]

    def document_count(self) -> int:
        return sum(1 for _ in self._store.documents())
