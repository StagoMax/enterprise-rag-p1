from __future__ import annotations

import argparse
import asyncio
import json
import threading
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Protocol

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from enterprise_rag.embeddings import EmbeddingProvider
from enterprise_rag.llm import OpenAiCompatibleChatModel
from enterprise_sag.context_pack import DraftContextPackBuilder
from enterprise_sag.extraction import DeepSeekEventExtractor, DeterministicEventExtractor
from enterprise_sag.ingestion import IncrementalIngestionService
from enterprise_sag.ingestion_models import (
    IngestionOptions,
    IngestionResult,
    SourceAssetView,
    TextIngestionRequest,
)
from enterprise_sag.models import ContextPackRequest
from enterprise_sag.runtime import (
    create_chat_model,
    create_embedding_provider,
    create_multi_route_retriever,
)
from enterprise_sag.settings import SagSettings
from enterprise_sag.store import SagSqliteStore


class PanelQueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    purpose: str = Field(default="evidence_review", min_length=1, max_length=80)
    top_k: int = Field(default=12, ge=1, le=30)
    maximum_tokens: int = Field(default=5000, ge=256, le=16000)
    use_deepseek: bool = True
    subject_refs: list[str] = Field(default_factory=list, max_length=12)
    namespaces: list[str] = Field(default_factory=list, max_length=12)


class PanelRuntime(Protocol):
    def status(self) -> dict[str, object]: ...

    def search(self, query: PanelQueryRequest) -> dict[str, object]: ...

    def ingest_bytes(
        self, content: bytes, filename: str, options: IngestionOptions
    ) -> IngestionResult: ...

    def list_sources(self) -> list[dict[str, object]]: ...

    def close(self) -> None: ...


class SagPanelRuntime:
    """One-process review runtime; searches are serialized to protect the local GPU model."""

    def __init__(self, settings: SagSettings | None = None) -> None:
        self.settings = settings or SagSettings()
        self.store = SagSqliteStore(self.settings.database_path.resolve())
        self._embeddings: EmbeddingProvider | None = None
        self._chat_model: OpenAiCompatibleChatModel | None = None
        self._ingestion: IncrementalIngestionService | None = None
        self._lock = threading.Lock()

    def _embedding_provider(self) -> EmbeddingProvider:
        if self._embeddings is None:
            self._embeddings = create_embedding_provider(self.settings)
        return self._embeddings

    def _deepseek(self) -> OpenAiCompatibleChatModel:
        if self._chat_model is None:
            self._chat_model = create_chat_model(self.settings)
        return self._chat_model

    def status(self) -> dict[str, object]:
        metadata = self.store.metadata()
        return {
            "status": "ready",
            "database": str(self.store.path),
            "index_version": metadata.get("index_version"),
            "embedding_backend": metadata.get("embedding_backend"),
            "embedding_dimensions": metadata.get("embedding_dimensions"),
            "stats": self.store.stats(),
            "integrity_check": self.store.integrity_check(),
            "model_loaded": self._embeddings is not None,
            "deepseek_configured": bool(
                self.settings.llm_base_url
                and self.settings.llm_api_key.get_secret_value()
                and self.settings.llm_model
            ),
            "agent_loop_integration": False,
            "prompt_injection": False,
        }

    def search(self, query: PanelQueryRequest) -> dict[str, object]:
        with self._lock:
            started = time.perf_counter()
            metadata = self.store.metadata()
            embeddings = self._embedding_provider()
            chat_model = self._deepseek() if query.use_deepseek else None
            before_requests = chat_model.request_count if chat_model is not None else 0
            retriever = create_multi_route_retriever(
                self.settings,
                self.store,
                embeddings,
                chat_model,
            )
            context_request = ContextPackRequest(
                query=" ".join(query.query.split()),
                purpose=query.purpose,
                subject_refs=query.subject_refs,
                allowed_namespaces=query.namespaces,
                maximum_tokens=query.maximum_tokens,
            )
            result = retriever.search(context_request, top_k=query.top_k)
            pack = DraftContextPackBuilder(maximum_tokens=query.maximum_tokens).build(
                request=context_request,
                plan=result.plan,
                index_version=str(metadata["index_version"]),
                hits=result.hits,
            )
            return {
                "pack": pack.model_dump(mode="json"),
                "diagnostics": {
                    "elapsed_seconds": round(time.perf_counter() - started, 3),
                    "route_candidates": result.candidate_counts,
                    "llm_requests": (
                        chat_model.request_count - before_requests if chat_model is not None else 0
                    ),
                    "embedding_backend": self.settings.embedding_backend,
                    "deepseek_enabled": query.use_deepseek,
                    "agent_loop_integration": False,
                    "prompt_injection": False,
                },
            }

    def _ingestion_service(self) -> IncrementalIngestionService:
        if self._ingestion is None:
            deterministic = DeterministicEventExtractor()
            if self.settings.extractor == "deepseek":
                fallback = deterministic if self.settings.allow_extractor_fallback else None
                extractor = DeepSeekEventExtractor(self._deepseek(), fallback=fallback)
            else:
                extractor = deterministic
            self._ingestion = IncrementalIngestionService(
                self.settings,
                store=self.store,
                embeddings=self._embedding_provider(),
                extractor=extractor,
                chat_model=self._chat_model,
            )
        return self._ingestion

    def ingest_bytes(
        self, content: bytes, filename: str, options: IngestionOptions
    ) -> IngestionResult:
        with self._lock:
            return self._ingestion_service().ingest_bytes(
                content,
                filename=filename,
                options=options,
            )

    def list_sources(self) -> list[dict[str, object]]:
        return self.store.list_source_assets()

    def close(self) -> None:
        if self._ingestion is not None:
            self._ingestion.close()
            self._ingestion = None
        if self._chat_model is not None:
            self._chat_model.close()
            self._chat_model = None


def create_panel_app(
    *,
    runtime: PanelRuntime | None = None,
    settings: SagSettings | None = None,
) -> FastAPI:
    resolved_runtime = runtime or SagPanelRuntime(settings)
    panel_static = Path(__file__).parent / "panel_static"
    shared_static = Path(__file__).parents[1] / "enterprise_rag" / "static"

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.runtime = resolved_runtime
        app.state.search_lock = asyncio.Lock()
        yield
        resolved_runtime.close()

    app = FastAPI(
        title="SAG Retrieval Inspector",
        version="0.1.0",
        description="Review-only multi-route SAG retrieval panel",
        lifespan=lifespan,
    )
    app.mount("/static", StaticFiles(directory=panel_static), name="panel-static")
    app.mount("/shared", StaticFiles(directory=shared_static), name="shared-static")

    @app.middleware("http")
    async def security_headers(request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"
        )
        return response

    @app.get("/", include_in_schema=False)
    def root() -> FileResponse:
        return FileResponse(panel_static / "index.html")

    @app.get("/api/status", tags=["panel"])
    async def panel_status(request: Request) -> dict[str, object]:
        try:
            return await run_in_threadpool(request.app.state.runtime.status)
        except Exception as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/api/search", tags=["panel"])
    async def panel_search(
        payload: PanelQueryRequest,
        request: Request,
    ) -> dict[str, object]:
        async with request.app.state.search_lock:
            try:
                return await run_in_threadpool(request.app.state.runtime.search, payload)
            except Exception as exc:
                raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.post(
        "/api/ingestions/upload",
        response_model=IngestionResult,
        status_code=201,
        tags=["ingestion"],
    )
    async def upload_source(
        request: Request,
        file: Annotated[UploadFile, File()],
        asset_id: Annotated[str | None, Form()] = None,
        source_key: Annotated[str | None, Form()] = None,
        namespace: Annotated[str, Form()] = "enterprise_knowledge",
        title: Annotated[str | None, Form()] = None,
        metadata_json: Annotated[str, Form()] = "{}",
    ) -> IngestionResult:
        try:
            metadata = json.loads(metadata_json)
            if not isinstance(metadata, dict):
                raise ValueError("metadata_json must be a JSON object")
            options = IngestionOptions(
                asset_id=asset_id or None,
                source_key=source_key or None,
                namespace=namespace,
                title=title or None,
                metadata=metadata,
            )
            maximum = (
                request.app.state.runtime.settings.ingestion_max_file_bytes
                if isinstance(request.app.state.runtime, SagPanelRuntime)
                else 100 * 1024 * 1024
            )
            content = await file.read(maximum + 1)
            if len(content) > maximum:
                raise ValueError(f"uploaded document exceeds {maximum} bytes")
            return await run_in_threadpool(
                request.app.state.runtime.ingest_bytes,
                content,
                file.filename or "upload.bin",
                options,
            )
        except (ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        finally:
            await file.close()

    @app.post(
        "/api/ingestions/text",
        response_model=IngestionResult,
        status_code=201,
        tags=["ingestion"],
    )
    async def ingest_text(
        payload: TextIngestionRequest,
        request: Request,
    ) -> IngestionResult:
        options = IngestionOptions.model_validate(
            payload.model_dump(exclude={"content", "filename"})
        )
        try:
            return await run_in_threadpool(
                request.app.state.runtime.ingest_bytes,
                payload.content.encode("utf-8"),
                payload.filename,
                options,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/api/sources", response_model=list[SourceAssetView], tags=["ingestion"])
    async def list_sources(request: Request) -> list[dict[str, object]]:
        try:
            return await run_in_threadpool(request.app.state.runtime.list_sources)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    return app


app = create_panel_app()


def run_panel(*, host: str = "127.0.0.1", port: int = 8765) -> int:
    uvicorn.run(create_panel_app(), host=host, port=port, log_level="info")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the local SAG Retrieval Inspector")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    return run_panel(host=args.host, port=args.port)


if __name__ == "__main__":
    raise SystemExit(main())
