from __future__ import annotations

from fastapi.testclient import TestClient

from enterprise_sag.ingestion_models import IngestionOptions, IngestionResult
from enterprise_sag.panel import PanelQueryRequest, create_panel_app


class _FakePanelRuntime:
    def __init__(self) -> None:
        self.closed = False
        self.requests: list[PanelQueryRequest] = []
        self.ingestions: list[tuple[bytes, str, IngestionOptions]] = []

    def status(self) -> dict[str, object]:
        return {
            "status": "ready",
            "index_version": "sag-test-v1",
            "stats": {"events": 2, "entities": 3},
            "integrity_check": "ok",
            "agent_loop_integration": False,
            "prompt_injection": False,
        }

    def search(self, query: PanelQueryRequest) -> dict[str, object]:
        self.requests.append(query)
        return {
            "pack": {
                "status": "draft",
                "plan": {
                    "planner": "fake-planner",
                    "needs": [
                        {
                            "need_id": "architecture",
                            "description": "架构证据",
                            "query": query.query,
                            "facets": ["architecture"],
                            "required": True,
                            "weight": 1.0,
                            "time_mode": "any",
                        }
                    ],
                },
                "coverage": [
                    {
                        "need_id": "architecture",
                        "status": "covered",
                        "reason": "selected-evidence",
                    }
                ],
                "items": [],
                "excluded_items": [],
                "estimated_tokens": 0,
                "maximum_tokens": query.maximum_tokens,
            },
            "diagnostics": {
                "elapsed_seconds": 0.01,
                "route_candidates": {"architecture": 2},
                "llm_requests": 0,
                "agent_loop_integration": False,
                "prompt_injection": False,
            },
        }

    def ingest_bytes(
        self, content: bytes, filename: str, options: IngestionOptions
    ) -> IngestionResult:
        self.ingestions.append((content, filename, options))
        return IngestionResult(
            job_id="ing_test",
            status="published",
            asset_id="ast_1234567890abcdef12345678",
            version_id="ver_1234567890abcdef12345678",
            version_number=1,
            source_id="src_1234567890abcdef12345678",
            content_hash="a" * 64,
            namespace=options.namespace,
            title=options.title or "测试资料",
            stored_path="data/assets/test.md",
            index_version="sag-test-v2",
            pipeline_signature="sagpipe_test",
        )

    def list_sources(self) -> list[dict[str, object]]:
        return []

    def close(self) -> None:
        self.closed = True


def test_panel_serves_review_interface_and_status() -> None:
    runtime = _FakePanelRuntime()
    app = create_panel_app(runtime=runtime)

    with TestClient(app) as client:
        page = client.get("/")
        assert page.status_code == 200
        assert "SAG 检索审阅台" in page.text
        assert "不生成答案" in page.text
        assert "新增资料（增量）" in page.text
        assert page.headers["x-frame-options"] == "DENY"

        status = client.get("/api/status")
        assert status.status_code == 200
        assert status.json()["index_version"] == "sag-test-v1"
        assert status.json()["agent_loop_integration"] is False

        assert client.get("/static/app.css").status_code == 200
        assert client.get("/static/app.js").status_code == 200

    assert runtime.closed is True


def test_panel_search_forwards_structured_request_without_agent_integration() -> None:
    runtime = _FakePanelRuntime()
    app = create_panel_app(runtime=runtime)

    with TestClient(app) as client:
        response = client.post(
            "/api/search",
            json={
                "query": "怎么管理长期记忆？",
                "purpose": "architecture_review",
                "top_k": 7,
                "maximum_tokens": 2048,
                "use_deepseek": False,
                "subject_refs": ["user:test"],
                "namespaces": ["memory"],
            },
        )

    assert response.status_code == 200
    assert response.json()["pack"]["status"] == "draft"
    assert response.json()["diagnostics"]["prompt_injection"] is False
    assert len(runtime.requests) == 1
    request = runtime.requests[0]
    assert request.top_k == 7
    assert request.use_deepseek is False
    assert request.subject_refs == ["user:test"]


def test_panel_rejects_invalid_query_parameters_before_search() -> None:
    runtime = _FakePanelRuntime()
    app = create_panel_app(runtime=runtime)

    with TestClient(app) as client:
        response = client.post(
            "/api/search",
            json={"query": "", "top_k": 99, "maximum_tokens": 12},
        )

    assert response.status_code == 422
    assert runtime.requests == []


def test_panel_accepts_file_and_structured_text_ingestion() -> None:
    runtime = _FakePanelRuntime()
    app = create_panel_app(runtime=runtime)

    with TestClient(app) as client:
        upload = client.post(
            "/api/ingestions/upload",
            files={"file": ("policy.md", "# 规则\n\n统一格式。", "text/markdown")},
            data={
                "source_key": "policy/current",
                "namespace": "enterprise",
                "title": "发布规则",
                "metadata_json": '{"department":"content"}',
            },
        )
        structured = client.post(
            "/api/ingestions/text",
            json={
                "content": "# FAQ\n\n支持增量导入。",
                "filename": "faq.md",
                "source_key": "faq",
                "namespace": "enterprise",
            },
        )
        sources = client.get("/api/sources")

    assert upload.status_code == 201
    assert upload.json()["asset_id"].startswith("ast_")
    assert structured.status_code == 201
    assert sources.status_code == 200
    assert len(runtime.ingestions) == 2
    assert runtime.ingestions[0][1] == "policy.md"
    assert runtime.ingestions[0][2].metadata == {"department": "content"}
    assert runtime.ingestions[1][0].decode() == "# FAQ\n\n支持增量导入。"


def test_panel_rejects_non_object_upload_metadata() -> None:
    runtime = _FakePanelRuntime()
    app = create_panel_app(runtime=runtime)

    with TestClient(app) as client:
        response = client.post(
            "/api/ingestions/upload",
            files={"file": ("policy.md", "content", "text/markdown")},
            data={"metadata_json": "[]"},
        )

    assert response.status_code == 400
    assert runtime.ingestions == []
