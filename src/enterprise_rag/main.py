import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from enterprise_rag.answering import (
    CitationConstrainedAnswerGenerator,
)
from enterprise_rag.audit import JsonlAuditStore
from enterprise_rag.auth import PrincipalDependency, create_access_token
from enterprise_rag.bootstrap import (
    initialize_demo_data,
    load_documents,
    load_gold_questions,
    load_graph_edges,
    seed_documents,
)
from enterprise_rag.chunking import build_document, chunk_document
from enterprise_rag.components import build_runtime_components
from enterprise_rag.config import Settings, get_settings
from enterprise_rag.feedback import JsonlFeedbackStore
from enterprise_rag.graph import VersionedKnowledgeGraph
from enterprise_rag.graph_retrieval import GraphRagRetriever
from enterprise_rag.models import (
    AuditEvent,
    DocumentInput,
    FeedbackEvent,
    FeedbackRequest,
    IndexPublishRequest,
    IndexSnapshotInfo,
    QueryRequest,
    QueryResponse,
    TokenRequest,
    TokenResponse,
)
from enterprise_rag.router import RuleBasedRouter
from enterprise_rag.service import EnterpriseRagService
from enterprise_rag.sql_tool import ReadOnlySqlTool


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = resolved_settings
        initialize_demo_data(resolved_settings.demo_db_path)
        components = build_runtime_components(resolved_settings)
        app.state.runtime_components = components
        store = components.store
        if store.has_version(resolved_settings.index_version):
            # 持久化后端重启后直接挂载已发布版本，避免重复嵌入全量语料。
            store.rollback(resolved_settings.index_version)
        else:
            corpus_documents = load_documents(resolved_settings.corpus_path)
            source_documents = corpus_documents or seed_documents()
            chunking_config = resolved_settings.chunking_config()
            indexed_items = []
            for document_input in source_documents:
                document = build_document(document_input)
                indexed_items.append(
                    (document, chunk_document(document, config=chunking_config))
                )
            store.upsert_documents(indexed_items)
            store.commit(resolved_settings.index_version)
        graph = VersionedKnowledgeGraph(resolved_settings.graph_state_path)
        graph.bootstrap(
            resolved_settings.index_version,
            load_graph_edges(resolved_settings.relations_path),
            store.document_ids(),
        )
        retriever = GraphRagRetriever(
            store,
            graph,
            seed_count=resolved_settings.graph_seed_count,
            max_hops=resolved_settings.graph_max_hops,
            expansion_limit=resolved_settings.graph_expansion_limit,
            score_decay=resolved_settings.graph_score_decay,
        )

        app.state.service = EnterpriseRagService(
            settings=resolved_settings,
            router=RuleBasedRouter(),
            store=store,
            graph=graph,
            retriever=retriever,
            sql_tool=ReadOnlySqlTool(resolved_settings.demo_db_path),
            audit=JsonlAuditStore(resolved_settings.audit_path),
            answer_generator=components.answer_generator,
        )
        app.state.feedback = JsonlFeedbackStore(resolved_settings.feedback_path)
        yield

    app = FastAPI(
        title=resolved_settings.app_name,
        version="0.2.0",
        description="P2 experimental: ACL-first Graph RAG, versioned index, tools, and audit",
        lifespan=lifespan,
    )
    static_path = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=static_path), name="static")

    def service(request: Request) -> EnterpriseRagService:
        return request.app.state.service

    ServiceDependency = Annotated[EnterpriseRagService, Depends(service)]

    @app.get("/", include_in_schema=False)
    def root() -> FileResponse:
        return FileResponse(static_path / "index.html")

    @app.get("/health", tags=["system"])
    def health(request: Request) -> dict[str, object]:
        rag_service: EnterpriseRagService = request.app.state.service
        return {
            "status": "ok",
            "embedding_backend": resolved_settings.embedding_backend,
            "embedding_dimensions": (
                resolved_settings.nemotron_dimensions
                if resolved_settings.embedding_backend == "nemotron"
                else 1024
                if resolved_settings.embedding_backend == "bge_m3"
                else resolved_settings.hashing_dimensions
            ),
            "reranker_backend": resolved_settings.reranker_backend,
            "vector_backend": resolved_settings.vector_backend,
            # 只暴露生成后端是否真的启用，不回显任何凭据。
            "answer_generator": type(rag_service.answer_generator).__name__,
            "llm_model": (
                resolved_settings.llm_model
                if isinstance(
                    rag_service.answer_generator, CitationConstrainedAnswerGenerator
                )
                else None
            ),
            "documents": rag_service.document_count(),
            "chunks": rag_service.current_index_info().chunks,
            "relations": rag_service.current_index_info().relations,
            "index_version": rag_service.current_index_info().version,
            "graph_enabled": resolved_settings.graph_enabled,
        }

    @app.post("/dev/token", response_model=TokenResponse, tags=["development"])
    def dev_token(token_request: TokenRequest) -> TokenResponse:
        if not resolved_settings.dev_mode:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
        token, expires_in = create_access_token(token_request, resolved_settings)
        return TokenResponse(access_token=token, expires_in=expires_in)

    @app.post("/v1/query", response_model=QueryResponse, tags=["query"])
    def query(
        query_request: QueryRequest,
        principal: PrincipalDependency,
        rag_service: ServiceDependency,
    ) -> QueryResponse:
        return rag_service.query(query_request, principal)

    @app.post("/v1/documents", tags=["ingestion"])
    def ingest_document(
        document: DocumentInput,
        principal: PrincipalDependency,
        rag_service: ServiceDependency,
    ) -> dict[str, object]:
        if "knowledge_admin" not in principal.roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin role required")
        document_id, chunk_count = rag_service.ingest(document)
        return {"document_id": document_id, "chunk_count": chunk_count, "status": "indexed"}

    @app.get("/v1/index", response_model=IndexSnapshotInfo, tags=["ingestion"])
    def index_info(
        principal: PrincipalDependency,
        rag_service: ServiceDependency,
    ) -> IndexSnapshotInfo:
        if not ({"knowledge_admin", "security_auditor"} & principal.roles):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin role required")
        return rag_service.current_index_info()

    @app.post("/v1/index/publish", response_model=IndexSnapshotInfo, tags=["ingestion"])
    def publish_index(
        publish_request: IndexPublishRequest,
        principal: PrincipalDependency,
        rag_service: ServiceDependency,
    ) -> IndexSnapshotInfo:
        if "knowledge_admin" not in principal.roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin role required")
        try:
            return rag_service.publish_index(publish_request)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    @app.post(
        "/v1/index/rollback/{version}",
        response_model=IndexSnapshotInfo,
        tags=["ingestion"],
    )
    def rollback_index(
        version: str,
        principal: PrincipalDependency,
        rag_service: ServiceDependency,
    ) -> IndexSnapshotInfo:
        if "knowledge_admin" not in principal.roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin role required")
        try:
            return rag_service.rollback_index(version)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    @app.get("/v1/graph", tags=["ingestion"])
    def graph_info(
        principal: PrincipalDependency,
        rag_service: ServiceDependency,
    ) -> dict[str, object]:
        if not ({"knowledge_admin", "security_auditor"} & principal.roles):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin role required")
        return rag_service.graph_summary()

    @app.get("/v1/knowledge", tags=["ingestion"])
    def knowledge(
        principal: PrincipalDependency,
        rag_service: ServiceDependency,
    ) -> list[dict[str, object]]:
        return rag_service.authorized_documents(principal)

    @app.get("/v1/samples", tags=["query"])
    def samples(principal: PrincipalDependency) -> list[dict[str, str]]:
        rows = load_gold_questions(resolved_settings.gold_path)
        visible = [
            row
            for row in rows
            if set(row.get("roles", [])) & set(principal.roles)
            and row.get("category") in {"rag", "graph_rag", "exact_search", "tool"}
        ]
        graph_samples = [row for row in visible if row.get("category") == "graph_rag"][:2]
        other_samples = [row for row in visible if row.get("category") != "graph_rag"][:6]
        return [
            {
                "question": str(row["question"]),
                "category": str(row["category"]),
            }
            for row in [*graph_samples, *other_samples]
        ]

    @app.get("/v1/audit", response_model=list[AuditEvent], tags=["audit"])
    def audit_events(
        principal: PrincipalDependency,
        rag_service: ServiceDependency,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ) -> list[AuditEvent]:
        if "security_auditor" not in principal.roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="auditor role required",
            )
        return rag_service.recent_audit_events(limit)

    @app.get("/v1/evaluation", tags=["audit"])
    def evaluation(principal: PrincipalDependency) -> dict[str, object]:
        if "security_auditor" not in principal.roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="auditor role required",
            )
        path = resolved_settings.evaluation_report_path
        if not path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="report not generated",
            )
        return json.loads(path.read_text(encoding="utf-8"))

    @app.post("/v1/feedback", status_code=status.HTTP_202_ACCEPTED, tags=["query"])
    def feedback(
        feedback_request: FeedbackRequest,
        principal: PrincipalDependency,
        request: Request,
    ) -> dict[str, str]:
        store: JsonlFeedbackStore = request.app.state.feedback
        store.append(
            FeedbackEvent(
                **feedback_request.model_dump(),
                subject=principal.subject,
            )
        )
        return {"status": "accepted"}

    return app


app = create_app()
