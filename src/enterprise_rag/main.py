import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from enterprise_rag.answering import EvidenceAnswerGenerator
from enterprise_rag.audit import JsonlAuditStore
from enterprise_rag.auth import PrincipalDependency, create_access_token
from enterprise_rag.bootstrap import (
    initialize_demo_data,
    load_documents,
    load_gold_questions,
    seed_documents,
)
from enterprise_rag.chunking import build_document, chunk_document
from enterprise_rag.config import Settings, get_settings
from enterprise_rag.embeddings import (
    BgeM3EmbeddingProvider,
    CrossEncoderReranker,
    HashingEmbeddingProvider,
    NemotronEmbeddingProvider,
)
from enterprise_rag.feedback import JsonlFeedbackStore
from enterprise_rag.models import (
    AuditEvent,
    DocumentInput,
    FeedbackEvent,
    FeedbackRequest,
    QueryRequest,
    QueryResponse,
    TokenRequest,
    TokenResponse,
)
from enterprise_rag.retrieval import InMemoryHybridStore
from enterprise_rag.router import RuleBasedRouter
from enterprise_rag.service import EnterpriseRagService
from enterprise_rag.sql_tool import ReadOnlySqlTool


def _embedding_provider(settings: Settings):
    if settings.embedding_backend == "nemotron":
        return NemotronEmbeddingProvider(
            model_id=settings.nemotron_model_id,
            dimensions=settings.nemotron_dimensions,
            device=settings.nemotron_device,
        )
    if settings.embedding_backend == "bge_m3":
        return BgeM3EmbeddingProvider(
            model_id=settings.bge_model_id,
            device=settings.bge_device,
        )
    return HashingEmbeddingProvider(settings.hashing_dimensions)


def _reranker(settings: Settings):
    if settings.reranker_backend == "cross_encoder":
        return CrossEncoderReranker(
            settings.reranker_model_id,
            device=settings.reranker_device,
        )
    return None


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = resolved_settings
        initialize_demo_data(resolved_settings.demo_db_path)
        store = InMemoryHybridStore(
            _embedding_provider(resolved_settings),
            dense_weight=resolved_settings.dense_weight,
            reranker=_reranker(resolved_settings),
        )
        corpus_documents = load_documents(resolved_settings.corpus_path)
        source_documents = corpus_documents or seed_documents()
        indexed_items = []
        for document_input in source_documents:
            document = build_document(document_input)
            indexed_items.append((document, chunk_document(document)))
        store.upsert_documents(indexed_items)

        app.state.service = EnterpriseRagService(
            settings=resolved_settings,
            router=RuleBasedRouter(),
            store=store,
            sql_tool=ReadOnlySqlTool(resolved_settings.demo_db_path),
            audit=JsonlAuditStore(resolved_settings.audit_path),
            answer_generator=EvidenceAnswerGenerator(),
        )
        app.state.feedback = JsonlFeedbackStore(resolved_settings.feedback_path)
        yield

    app = FastAPI(
        title=resolved_settings.app_name,
        version="0.1.0",
        description="P1: routing, ACL-first retrieval, citations, read-only SQL, and audit",
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
            "documents": rag_service.document_count(),
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
            and row.get("category") in {"rag", "exact_search", "tool"}
        ]
        return [
            {
                "question": str(row["question"]),
                "category": str(row["category"]),
            }
            for row in visible[:8]
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
