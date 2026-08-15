from __future__ import annotations

import hashlib
import json
from dataclasses import asdict

from enterprise_sag.chunking import SagChunkingConfig
from enterprise_sag.settings import SagSettings


def pipeline_contract(
    settings: SagSettings,
    *,
    extractor_name: str,
    embedding_dimensions: int,
) -> dict[str, object]:
    chunking = SagChunkingConfig(
        target_tokens=settings.chunk_target_tokens,
        max_tokens=settings.chunk_max_tokens,
    )
    payload: dict[str, object] = {
        "parser": "structured-document-parser-v1",
        "chunking": asdict(chunking),
        "extractor": extractor_name,
        "extractor_model": settings.llm_model if extractor_name.startswith("deepseek") else None,
        "embedding_backend": settings.embedding_backend,
        "embedding_model": (
            settings.nemotron_model_id
            if settings.embedding_backend == "nemotron"
            else "hashing-embedding-v1"
        ),
        "embedding_dimensions": embedding_dimensions,
    }
    digest = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return {**payload, "signature": f"sagpipe_{digest[:24]}"}


def compatibility_fields(contract: dict[str, object]) -> dict[str, object]:
    """Fields that must match the active projection before an incremental publish."""

    return {
        key: contract[key]
        for key in (
            "chunking",
            "extractor",
            "embedding_backend",
            "embedding_dimensions",
        )
    }
