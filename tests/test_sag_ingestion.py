from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from enterprise_rag.embeddings import HashingEmbeddingProvider
from enterprise_sag.cli import main
from enterprise_sag.extraction import DeterministicEventExtractor
from enterprise_sag.ingestion import IncrementalIngestionService
from enterprise_sag.ingestion_models import IngestionOptions
from enterprise_sag.pipeline import SagIndexBuilder
from enterprise_sag.settings import SagSettings
from enterprise_sag.store import SagSqliteStore


def _service(tmp_path: Path, name: str = "index") -> IncrementalIngestionService:
    settings = SagSettings(
        database_path=tmp_path / f"{name}.sqlite",
        asset_store_path=tmp_path / f"{name}-assets",
        extractor="deterministic",
        embedding_backend="hashing",
        hashing_dimensions=64,
        chunk_target_tokens=64,
        chunk_max_tokens=96,
    )
    return IncrementalIngestionService(
        settings,
        embeddings=HashingEmbeddingProvider(64),
        extractor=DeterministicEventExtractor(),
    )


def test_incremental_ingestion_is_idempotent_and_keeps_immutable_versions(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    options = IngestionOptions(
        source_key="handbook/format-policy",
        namespace="enterprise",
        title="发布格式规范",
        metadata={"department": "content"},
    )
    old = "# 发布格式\n\n飞书文章先导出 Word，再按平台修改格式。"
    first = service.ingest_bytes(old.encode(), filename="policy.md", options=options)
    duplicate = service.ingest_bytes(old.encode(), filename="policy.md", options=options)

    assert first.status == "published"
    assert duplicate.status == "unchanged"
    assert duplicate.version_id == first.version_id
    assert service.store.stats()["sources"] == 1

    new = "# 发布格式\n\n所有平台发布完全相同的格式，不再针对平台分别修改。"
    second = service.ingest_bytes(new.encode(), filename="policy.md", options=options)
    assert second.status == "published"
    assert second.asset_id == first.asset_id
    assert second.version_number == 2
    assert second.previous_version_id == first.version_id
    assert service.store.stats()["sources"] == 1

    active_text = "\n".join(str(item["content"]) for item in service.store.load_events())
    assert "完全相同" in active_text
    assert "先导出 Word" not in active_text

    with sqlite3.connect(service.store.path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM source_versions").fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM sources").fetchone()[0] == 2
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(
                "UPDATE source_versions SET title='changed' WHERE version_id=?",
                (first.version_id,),
            )


def test_incremental_final_projection_matches_clean_build_for_current_documents(
    tmp_path: Path,
) -> None:
    options = IngestionOptions(source_key="manual", namespace="knowledge")
    current = "# 当前规则\n\n数据库连接统一使用只读账号，并记录审计事件。"

    incremental = _service(tmp_path, "incremental")
    incremental.ingest_bytes(
        "# 旧规则\n\n数据库连接使用共享管理员账号。".encode(),
        filename="manual.md",
        options=options,
    )
    incremental.ingest_bytes(current.encode(), filename="manual.md", options=options)

    clean = _service(tmp_path, "clean")
    clean.ingest_bytes(current.encode(), filename="manual.md", options=options)

    def active_signature(store: SagSqliteStore) -> list[tuple[str, str, str]]:
        return sorted(
            (
                str(item["event_id"]),
                str(item["event_text"]),
                str(item["content"]),
            )
            for item in store.load_events()
        )

    assert active_signature(incremental.store) == active_signature(clean.store)
    assert incremental.store.stats() == clean.store.stats()


def test_metadata_change_creates_source_version_but_reuses_content_projection(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    content = "# 产品说明\n\nSAG 在查询时通过 SQL 关系生成局部超边。"
    first = service.ingest_bytes(
        content.encode(),
        filename="sag.md",
        options=IngestionOptions(source_key="sag", metadata={"level": "internal"}),
    )
    second = service.ingest_bytes(
        content.encode(),
        filename="sag.md",
        options=IngestionOptions(
            source_key="sag", title="公开 SAG 说明", metadata={"level": "public"}
        ),
    )

    assert second.version_number == 2
    assert second.source_id == first.source_id
    assert second.reused_projection is True
    assets = service.store.list_source_assets()
    assert assets[0]["metadata"] == {"level": "public"}
    assert service.store.load_events()[0]["title"] == "公开 SAG 说明"
    assert service.store.load_events()[0]["source_path"] == second.stored_path


def test_full_rebuild_preserves_uploaded_assets_and_source_history(tmp_path: Path) -> None:
    source_root = tmp_path / "root"
    source_root.mkdir()
    root_document = source_root / "root.md"
    root_document.write_text("# 根目录资料\n\n第一版规则。", encoding="utf-8")
    settings = SagSettings(
        source_root=source_root,
        database_path=tmp_path / "combined.sqlite",
        asset_store_path=tmp_path / "assets",
        extractor="deterministic",
        embedding_backend="hashing",
        hashing_dimensions=64,
        chunk_target_tokens=64,
        chunk_max_tokens=96,
    )
    SagIndexBuilder(settings).build()
    service = IncrementalIngestionService(
        settings,
        embeddings=HashingEmbeddingProvider(64),
        extractor=DeterministicEventExtractor(),
    )
    uploaded = service.ingest_bytes(
        "# 上传资料\n\n这是通过接口接入的资料。".encode(),
        filename="uploaded.md",
        options=IngestionOptions(source_key="api/uploaded"),
    )

    root_document.write_text("# 根目录资料\n\n第二版规则。", encoding="utf-8")
    SagIndexBuilder(settings).build()

    store = SagSqliteStore(settings.database_path)
    active_text = "\n".join(str(item["content"]) for item in store.load_events())
    assert "第二版规则" in active_text
    assert "第一版规则" not in active_text
    assert "通过接口接入" in active_text
    assert store.stats()["sources"] == 2
    assets = store.list_source_assets()
    assert any(item["asset_id"] == uploaded.asset_id for item in assets)
    with sqlite3.connect(store.path) as connection:
        root_versions = connection.execute(
            """SELECT COUNT(*) FROM source_versions sv
               JOIN source_assets sa ON sa.asset_id=sv.asset_id
               WHERE sa.origin='root'"""
        ).fetchone()[0]
    assert root_versions == 2


def test_cli_ingest_exposes_transport_independent_incremental_entry(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    document = tmp_path / "input.md"
    document.write_text("# 手册\n\n可以通过命令行增量接入资料。", encoding="utf-8")
    database = tmp_path / "cli.sqlite"
    assets = tmp_path / "cli-assets"

    exit_code = main(
        [
            "ingest",
            str(document),
            "--database-path",
            str(database),
            "--asset-store-path",
            str(assets),
            "--source-key",
            "cli/manual",
            "--extractor",
            "deterministic",
            "--embedding-backend",
            "hashing",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "published"
    assert payload["version_number"] == 1
