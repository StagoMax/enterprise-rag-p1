from threading import RLock
from uuid import uuid4

from enterprise_rag.answering import EvidenceAnswerGenerator, format_tool_answer
from enterprise_rag.audit import JsonlAuditStore
from enterprise_rag.chunking import build_document, chunk_document
from enterprise_rag.config import Settings
from enterprise_rag.graph import VersionedKnowledgeGraph
from enterprise_rag.graph_retrieval import GraphRagRetriever
from enterprise_rag.models import (
    AuditEvent,
    Citation,
    DocumentInput,
    GraphEdge,
    IndexPublishRequest,
    IndexSnapshotInfo,
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
        graph: VersionedKnowledgeGraph,
        retriever: GraphRagRetriever,
        sql_tool: ReadOnlySqlTool,
        audit: JsonlAuditStore,
        answer_generator: EvidenceAnswerGenerator,
    ) -> None:
        self._settings = settings
        self._router = router
        self._store = store
        self._graph = graph
        self._retriever = retriever
        self._sql_tool = sql_tool
        self._audit = audit
        self._answer_generator = answer_generator
        self._index_lock = RLock()

    @property
    def answer_generator(self) -> EvidenceAnswerGenerator:
        return self._answer_generator

    def ingest(self, document_input: DocumentInput) -> tuple[str, int]:
        chunk_count = len(chunk_document(build_document(document_input)))
        version = f"manual-{uuid4()}"
        self.publish_index(
            IndexPublishRequest(version=version, documents=[document_input])
        )
        return document_input.document_id, chunk_count

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

    def publish_index(self, request: IndexPublishRequest) -> IndexSnapshotInfo:
        with self._index_lock:
            previous_index_version = self._store.active_version
            previous_graph_version = self._graph.active_version
            documents_and_chunks = []
            for document_input in request.documents:
                document = build_document(document_input)
                documents_and_chunks.append((document, chunk_document(document)))

            relations: list[GraphEdge]
            if request.replace_relations:
                relations = request.relations
            else:
                relations = [*self._graph.current_edges(), *request.relations]
            prospective_ids = self._store.document_ids() | {
                document.document_id for document, _ in documents_and_chunks
            }

            self._graph.publish(request.version, relations, prospective_ids)
            try:
                if documents_and_chunks:
                    self._store.upsert_documents(documents_and_chunks)
                self._store.commit(request.version)
            except Exception:
                if previous_index_version is not None:
                    self._store.rollback(previous_index_version)
                if previous_graph_version is not None:
                    self._graph.rollback(previous_graph_version)
                raise
            return self.current_index_info()

    def rollback_index(self, version: str) -> IndexSnapshotInfo:
        with self._index_lock:
            if not self._store.has_version(version) or not self._graph.has_version(version):
                raise ValueError(f"index version is not available for paired rollback: {version}")
            previous_index_version = self._store.active_version
            self._store.rollback(version)
            try:
                self._graph.rollback(version)
            except Exception:
                if previous_index_version is not None:
                    self._store.rollback(previous_index_version)
                raise
            return self.current_index_info()

    def current_index_info(self) -> IndexSnapshotInfo:
        version = self._store.active_version or "uncommitted"
        return IndexSnapshotInfo(
            version=version,
            documents=self.document_count(),
            chunks=self._store.chunk_count(),
            relations=self._graph.edge_count(),
            active=True,
        )

    def graph_summary(self) -> dict[str, object]:
        return {
            "active_version": self._graph.active_version,
            "relations": self._graph.edge_count(),
            "relation_counts": self._graph.relation_counts(),
            "available_versions": self._graph.versions(),
        }

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
        with self._index_lock:
            return self._query_locked(request, principal)

    def _query_locked(self, request: QueryRequest, principal: Principal) -> QueryResponse:
        trace_id = str(uuid4())
        decision = self._router.route(request.question)

        if decision.route == Route.HANDOFF_OR_REFUSE:
            return self._refusal(
                trace_id,
                principal,
                decision,
                "P2 实验服务只提供只读问答；该请求需要转交已授权工作流处理。",
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
                title="P2 只读销售数据库",
                version=result.schema_version,
                anchor=result.sql,
                retrieval_mode="tool",
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
        use_graph = self._settings.graph_enabled and (
            request.retrieval_mode == "graph"
            or (request.retrieval_mode == "auto" and decision.graph_expansion)
        )
        retrieval = self._retriever.search(
            request.question,
            principal.roles,
            top_k=self._settings.top_k,
            exact=exact,
            min_score=self._settings.min_retrieval_score,
            use_graph=use_graph,
        )
        hits = retrieval.hits
        if not hits:
            return self._refusal(
                trace_id,
                principal,
                decision,
                "当前授权范围内没有足够证据，无法确认该企业问题。",
            )

        restricted_source_ids = frozenset(
            self._store.document_ids()
            - self._store.authorized_document_ids(principal.roles)
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
                    title=self._answer_generator.redact_restricted_references(
                        hit.chunk.title,
                        restricted_source_ids,
                    ),
                    version=hit.chunk.version,
                    anchor=hit.chunk.anchor,
                    score=hit.score,
                    retrieval_mode=hit.retrieval_mode,
                    graph_path=hit.graph_path,
                )
            )
            cited_documents.add(hit.chunk.document_id)
            if len(citations) == 3:
                break
        if exact:
            best = hits[0]
            safe_content = self._answer_generator.redact_restricted_references(
                best.chunk.content,
                restricted_source_ids,
            )
            answer = f"精确检索结果：{safe_content}"
        else:
            answer = self._answer_generator.answer(
                request.question,
                hits,
                restricted_source_ids=restricted_source_ids,
            )

        source_ids = list(dict.fromkeys(hit.chunk.document_id for hit in hits))
        self._record(
            trace_id,
            principal,
            decision,
            allowed=True,
            reason="authorized evidence retrieved",
            source_ids=source_ids,
            metadata={
                "hit_count": len(hits),
                "exact": exact,
                "graph_used": retrieval.graph_used,
                "graph_path_count": len(retrieval.graph_paths),
                "index_version": self._store.active_version,
            },
        )
        return QueryResponse(
            answer=answer,
            route=decision.route,
            route_reason=decision.reason,
            citations=citations,
            trace_id=trace_id,
            metadata={
                "hit_count": len(hits),
                "graph_used": retrieval.graph_used,
                "graph_paths": [
                    path.model_dump(mode="json") for path in retrieval.graph_paths
                ],
                "index_version": self._store.active_version,
            },
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
