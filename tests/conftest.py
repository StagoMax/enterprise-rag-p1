from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from enterprise_rag.config import Settings
from enterprise_rag.main import create_app


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    settings = Settings(
        dev_mode=True,
        jwt_secret="test-secret-for-enterprise-rag-p1-over-32-bytes",
        embedding_backend="hashing",
        audit_path=tmp_path / "audit.jsonl",
        feedback_path=tmp_path / "feedback.jsonl",
        demo_db_path=tmp_path / "demo.sqlite",
        corpus_path=tmp_path / "documents.jsonl",
        relations_path=tmp_path / "relations.jsonl",
        graph_state_path=tmp_path / "graph-state.json",
        gold_path=tmp_path / "golden_questions.jsonl",
        index_version="test-bootstrap-v1",
        min_retrieval_score=0.08,
        # 测试必须自洽：Settings 会读取 .env，若不显式关闭生成后端，
        # 接口测试会真的去调用外部 LLM，既慢又不可复现。
        llm_backend="extractive",
        vector_backend="memory",
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def auth_header(client: TestClient, *roles: str) -> dict[str, str]:
    response = client.post(
        "/dev/token",
        json={"subject": "test-user", "roles": list(roles), "tenant_id": "demo"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
