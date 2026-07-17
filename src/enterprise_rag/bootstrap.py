import json
from pathlib import Path

from enterprise_rag.models import DocumentInput
from enterprise_rag.sql_tool import initialize_demo_database


def seed_documents() -> list[DocumentInput]:
    return [
        DocumentInput(
            document_id="vpn-access-guide",
            title="Orion 企业 VPN 接入手册",
            owner="it-platform",
            business_class="technical-guide",
            allowed_roles={"engineering", "operations"},
            version="1.2",
            source_uri="demo://it/vpn-access-guide",
            content=(
                "Orion 员工访问生产只读控制台时，必须先连接 corp-shanghai VPN。"
                "首次登录需要使用企业身份与硬件安全密钥完成双因素认证。\n\n"
                "错误码 VPN-401 表示设备证书未登记。用户应在资产门户登记设备，"
                "等待状态变为 Approved 后重新连接。服务台不得绕过设备证书检查。"
            ),
        ),
        DocumentInput(
            document_id="release-gate-policy",
            title="Orion P1 发布门禁规范",
            owner="engineering-enablement",
            business_class="engineering-policy",
            allowed_roles={"engineering"},
            version="2.0",
            source_uri="demo://engineering/release-gate-policy",
            content=(
                "Orion P1 服务发布前必须通过路由、引用、权限和 SQL 安全回归测试。"
                "任何未授权分块召回都应阻断发布。\n\n"
                "质量门槛为路由正确率不低于 90%，权限测试必须零越权。"
                "索引或模型版本变更后必须重新运行固定金标集。"
            ),
        ),
        DocumentInput(
            document_id="restricted-topology",
            title="Orion 受限网络拓扑说明",
            owner="security-architecture",
            business_class="restricted-design",
            sensitivity="restricted",
            allowed_roles={"restricted"},
            version="1.0",
            source_uri="demo://security/restricted-topology",
            content=(
                "该文档仅供受限安全角色使用。内部代号为 Sable，"
                "其详细拓扑不得向 engineering 或 operations 角色返回。"
            ),
        ),
    ]


def initialize_demo_data(path: Path) -> None:
    initialize_demo_database(path)


def load_documents(path: Path) -> list[DocumentInput]:
    if not path.exists():
        return []
    documents: list[DocumentInput] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                documents.append(DocumentInput.model_validate_json(line))
    return documents


def load_gold_questions(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]
