from datetime import UTC, datetime, timedelta

import jwt
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
    assert health.json()["relations"] == 0
    assert health.json()["index_version"] == "test-bootstrap-v1"


def test_source_catalog_is_acl_filtered_searchable_and_paginated(
    client: TestClient,
) -> None:
    response = client.get(
        "/v1/knowledge/sources",
        params={"query": "VPN", "offset": 0, "limit": 1},
        headers=auth_header(client, "engineering"),
    )

    assert response.status_code == 200
    page = response.json()
    assert page["index_total"] == 3
    assert page["authorized_total"] == 2
    assert page["total"] == 1
    assert page["offset"] == 0
    assert page["limit"] == 1
    assert page["has_more"] is False
    assert [item["document_id"] for item in page["items"]] == ["vpn-access-guide"]


def test_source_catalog_does_not_expose_unauthorized_metadata(client: TestClient) -> None:
    response = client.get(
        "/v1/knowledge/sources",
        params={"query": "薪酬"},
        headers=auth_header(client, "engineering"),
    )

    assert response.status_code == 200
    page = response.json()
    assert page["total"] == 0
    assert page["items"] == []


def test_query_requires_signed_identity(client: TestClient) -> None:
    response = client.post("/v1/query", json={"question": "VPN 如何接入？"})
    assert response.status_code == 401


def test_empty_or_missing_tenant_is_rejected(client: TestClient) -> None:
    invalid_request = client.post(
        "/dev/token",
        json={"subject": "test", "roles": ["engineering"], "tenant_id": ""},
    )
    assert invalid_request.status_code == 422

    settings = client.app.state.settings
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": "test",
            "roles": ["engineering"],
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        settings.jwt_secret,
        algorithm="HS256",
    )
    response = client.post(
        "/v1/query",
        headers={"Authorization": f"Bearer {token}"},
        json={"question": "VPN"},
    )
    assert response.status_code == 401


def test_invalid_role_claims_are_rejected(client: TestClient) -> None:
    invalid_request = client.post(
        "/dev/token",
        json={"subject": "test", "roles": ["engineering\nrestricted"]},
    )
    assert invalid_request.status_code == 422

    settings = client.app.state.settings
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": "test",
            "roles": ["engineering\n"],
            "tenant_id": "demo",
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        settings.jwt_secret,
        algorithm="HS256",
    )
    response = client.post(
        "/v1/query",
        headers={"Authorization": f"Bearer {token}"},
        json={"question": "VPN"},
    )
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


def test_context_pack_is_review_only_and_budgeted(client: TestClient) -> None:
    response = client.post(
        "/v1/context-packs",
        headers=auth_header(client, "engineering"),
        json={
            "query": "Orion 员工如何访问生产只读控制台？",
            "retrieval_mode": "hybrid",
            "top_k": 5,
            "maximum_tokens": 256,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["pack"]["status"] == "draft"
    assert body["pack"]["retrieval_engine"] == "graph_rag"
    assert body["pack"]["estimated_tokens"] <= 256
    assert body["pack"]["items"][0]["document_id"] == "vpn-access-guide"
    assert "answer" not in body
    assert body["diagnostics"]["agent_loop_integration"] is False
    assert body["diagnostics"]["prompt_injection"] is False


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


def test_uploaded_document_is_incrementally_indexed(client: TestClient) -> None:
    denied = client.post(
        "/v1/documents/upload",
        headers=auth_header(client, "engineering"),
        files={"file": ("publishing.txt", "所有平台统一使用同一发布格式。", "text/plain")},
    )
    assert denied.status_code == 403

    indexed = client.post(
        "/v1/documents/upload",
        headers=auth_header(client, "knowledge_admin"),
        files={"file": ("publishing.txt", "所有平台统一使用同一发布格式。", "text/plain")},
        data={
            "source_key": "publishing-guideline",
            "namespace": "enterprise_knowledge",
            "title": "多平台发布规范",
            "metadata_json": '{"allowed_roles":["engineering"],"version":"2.0"}',
        },
    )

    assert indexed.status_code == 201
    body = indexed.json()
    assert body["status"] == "indexed"
    assert body["document_id"] == "publishing-guideline"
    assert body["chunk_count"] == 1
    assert body["content_hash"]

    retrieved = client.post(
        "/v1/context-packs",
        headers=auth_header(client, "engineering"),
        json={"query": "多平台应该使用什么发布格式？", "retrieval_mode": "hybrid"},
    )
    assert retrieved.status_code == 200
    assert any(
        item["document_id"] == "publishing-guideline"
        for item in retrieved.json()["pack"]["items"]
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


def test_graph_rag_expands_only_authorized_document_paths(client: TestClient) -> None:
    payload = {
        "version": "graph-authorized-v1",
        "documents": [
            {
                "document_id": "atlas-runbook",
                "title": "Orion Atlas deployment runbook",
                "content": (
                    "Atlas deployments use the approved operational sequence.\n"
                    "For restricted key locations, see atlas-secret."
                ),
                "owner": "platform",
                "business_class": "engineering-guide",
                "allowed_roles": ["engineering"],
            },
            {
                "document_id": "atlas-recovery",
                "title": "Orion Atlas recovery procedure",
                "content": "Recovery requires restoring the last signed checkpoint.",
                "owner": "platform",
                "business_class": "engineering-guide",
                "allowed_roles": ["engineering"],
            },
            {
                "document_id": "atlas-secret",
                "title": "Orion Atlas restricted key map",
                "content": "Restricted recovery key location.",
                "owner": "security",
                "business_class": "restricted-design",
                "allowed_roles": ["restricted"],
            },
        ],
        "relations": [
            {
                "source_id": "atlas-runbook",
                "target_id": "atlas-recovery",
                "relation": "references",
            },
            {
                "source_id": "atlas-runbook",
                "target_id": "atlas-secret",
                "relation": "references",
            },
        ],
    }
    published = client.post(
        "/v1/index/publish",
        headers=auth_header(client, "knowledge_admin"),
        json=payload,
    )
    assert published.status_code == 200
    assert published.json()["relations"] == 2

    response = client.post(
        "/v1/query",
        headers=auth_header(client, "engineering"),
        json={
            "question": "From the Orion Atlas deployment runbook, follow its documented reference.",
            "retrieval_mode": "graph",
        },
    )
    assert response.status_code == 200
    body = response.json()
    sources = [citation["source_id"] for citation in body["citations"]]
    assert sources[:2] == ["atlas-runbook", "atlas-recovery"]
    assert "atlas-secret" not in sources
    serialized_paths = str(body["metadata"]["graph_paths"])
    assert "atlas-recovery" in serialized_paths
    assert "atlas-secret" not in serialized_paths
    assert "atlas-secret" not in str(body)
    assert "受限引用已隐藏" in body["answer"]
    assert body["citations"][1]["retrieval_mode"] == "graph"
    assert body["citations"][1]["graph_path"] == ["atlas-runbook", "atlas-recovery"]

    exact_response = client.post(
        "/v1/query",
        headers=auth_header(client, "engineering"),
        json={"question": "Find document ID atlas-runbook."},
    ).json()
    assert "atlas-secret" not in str(exact_response)
    assert "受限引用已隐藏" in exact_response["answer"]


def test_index_publish_and_paired_rollback(client: TestClient) -> None:
    admin = auth_header(client, "knowledge_admin")
    published = client.post(
        "/v1/index/publish",
        headers=admin,
        json={
            "version": "rollback-candidate-v1",
            "documents": [
                {
                    "document_id": "temporary-guide",
                    "title": "Temporary Orion guide",
                    "content": "This document exists only in the candidate index.",
                    "owner": "knowledge-ops",
                    "business_class": "engineering-guide",
                    "allowed_roles": ["engineering"],
                }
            ],
        },
    )
    assert published.status_code == 200
    assert published.json()["version"] == "rollback-candidate-v1"
    assert published.json()["documents"] == 4

    rolled_back = client.post(
        "/v1/index/rollback/test-bootstrap-v1",
        headers=admin,
    )
    assert rolled_back.status_code == 200
    assert rolled_back.json()["version"] == "test-bootstrap-v1"
    assert rolled_back.json()["documents"] == 3

    result = client.post(
        "/v1/query",
        headers=auth_header(client, "engineering"),
        json={"question": "Find document ID temporary-guide."},
    ).json()
    assert result["refused"] is True
    assert all(citation["source_id"] != "temporary-guide" for citation in result["citations"])
