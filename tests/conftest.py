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
        gold_path=tmp_path / "golden_questions.jsonl",
        min_retrieval_score=0.08,
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
