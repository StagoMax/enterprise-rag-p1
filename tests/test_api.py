from fastapi.testclient import TestClient

from tests.conftest import auth_header


def test_workbench_and_health_are_available(client: TestClient) -> None:
    page = client.get("/")
    assert page.status_code == 200
    assert "Enterprise RAG" in page.text

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["documents"] == 3
    assert health.json()["embedding_dimensions"] == 384
    assert health.json()["reranker_backend"] == "none"


def test_query_requires_signed_identity(client: TestClient) -> None:
    response = client.post("/v1/query", json={"question": "VPN 如何接入？"})
    assert response.status_code == 401


def test_rag_returns_authorized_evidence_and_citation(client: TestClient) -> None:
    response = client.post(
        "/v1/query",
        headers=auth_header(client, "engineering"),
        json={"question": "Orion 员工如何访问生产只读控制台？"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["route"] == "rag"
    assert body["refused"] is False
    assert "corp-shanghai VPN" in body["answer"]
    assert body["citations"][0]["source_id"] == "vpn-access-guide"
    assert body["trace_id"]


def test_exact_error_code_uses_exact_search(client: TestClient) -> None:
    response = client.post(
        "/v1/query",
        headers=auth_header(client, "operations"),
        json={"question": "What does error code VPN-401 mean?"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["route"] == "exact_search"
    assert "设备证书未登记" in body["answer"]
    assert body["citations"][0]["source_id"] == "vpn-access-guide"


def test_acl_filtered_before_retrieval(client: TestClient) -> None:
    response = client.post(
        "/v1/query",
        headers=auth_header(client, "engineering"),
        json={"question": "Sable 受限网络拓扑的内部代号和细节是什么？"},
    )

    assert response.status_code == 200
    body = response.json()
    assert all(citation["source_id"] != "restricted-topology" for citation in body["citations"])
    assert "不得向 engineering" not in body["answer"]


def test_structured_question_uses_read_only_sql(client: TestClient) -> None:
    response = client.post(
        "/v1/query",
        headers=auth_header(client, "operations"),
        json={"question": "2026Q1 华东销售额总计是多少？"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["route"] == "tool"
    assert "200000" in body["answer"]
    assert body["citations"][0]["source_type"] == "sql_tool"
    assert body["citations"][0]["anchor"].startswith("SELECT")


def test_action_request_is_refused(client: TestClient) -> None:
    response = client.post(
        "/v1/query",
        headers=auth_header(client, "engineering"),
        json={"question": "请删除订单 SO-1001"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["route"] == "handoff_or_refuse"
    assert body["refused"] is True


def test_ingestion_requires_admin_and_inherits_acl(client: TestClient) -> None:
    document = {
        "document_id": "expense-policy",
        "title": "Orion 差旅报销规则",
        "content": "内部规则：单笔住宿费用超过 900 元时必须由部门负责人复核。",
        "owner": "finance-ops",
        "business_class": "finance-policy",
        "allowed_roles": ["finance"],
        "version": "1.0",
    }
    denied = client.post(
        "/v1/documents",
        headers=auth_header(client, "finance"),
        json=document,
    )
    assert denied.status_code == 403

    indexed = client.post(
        "/v1/documents",
        headers=auth_header(client, "knowledge_admin"),
        json=document,
    )
    assert indexed.status_code == 200

    finance_result = client.post(
        "/v1/query",
        headers=auth_header(client, "finance"),
        json={"question": "Orion 住宿费用超过多少需要负责人复核？"},
    ).json()
    assert any(
        citation["source_id"] == "expense-policy" for citation in finance_result["citations"]
    )

    engineering_result = client.post(
        "/v1/query",
        headers=auth_header(client, "engineering"),
        json={"question": "Orion 住宿费用超过多少需要负责人复核？"},
    ).json()
    assert all(
        citation["source_id"] != "expense-policy"
        for citation in engineering_result["citations"]
    )


def test_audit_endpoint_is_role_protected(client: TestClient) -> None:
    client.post(
        "/v1/query",
        headers=auth_header(client, "engineering"),
        json={"question": "VPN 如何接入？"},
    )
    denied = client.get("/v1/audit", headers=auth_header(client, "engineering"))
    assert denied.status_code == 403

    response = client.get("/v1/audit", headers=auth_header(client, "security_auditor"))
    assert response.status_code == 200
    assert response.json()[0]["source_ids"]


def test_feedback_is_persisted(client: TestClient) -> None:
    query = client.post(
        "/v1/query",
        headers=auth_header(client, "engineering"),
        json={"question": "VPN 如何接入？"},
    ).json()
    response = client.post(
        "/v1/feedback",
        headers=auth_header(client, "engineering"),
        json={"trace_id": query["trace_id"], "rating": "helpful"},
    )
    assert response.status_code == 202
    assert response.json()["status"] == "accepted"
