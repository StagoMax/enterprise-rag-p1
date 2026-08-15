from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from enterprise_rag.chunking import count_tokens, token_spans
from enterprise_rag.parsing import BlockKind, ParsedBlock, ParsedDocument
from enterprise_sag.models import EvidenceUnit


@dataclass(frozen=True, slots=True)
class SagChunkingConfig:
    """Event-oriented chunks: structural boundaries, no overlap, stable evidence anchors."""

    target_tokens: int = 480
    max_tokens: int = 640
    version: str = "sag-event-unit-v1"

    def __post_init__(self) -> None:
        if self.target_tokens < 64:
            raise ValueError("target_tokens must be at least 64")
        if self.max_tokens < self.target_tokens:
            raise ValueError("max_tokens must be at least target_tokens")


def _content_hash(text: str) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    return hashlib.sha256(compact.encode("utf-8")).hexdigest()


def _split_oversized(text: str, maximum: int) -> list[str]:
    spans = token_spans(text)
    if len(spans) <= maximum:
        return [text.strip()] if text.strip() else []

    parts: list[str] = []
    start = 0
    while start < len(spans):
        end = min(start + maximum, len(spans))
        minimum = start + max(int(maximum * 0.6), 1)
        for candidate in range(end, minimum, -1):
            suffix = text[spans[candidate - 1][0] : spans[candidate - 1][1]]
            between = (
                text[spans[candidate - 1][1] : spans[candidate][0]]
                if candidate < len(spans)
                else ""
            )
            if suffix.endswith(("。", "！", "？", ".", "!", "?", ";", "；")) or "\n" in between:
                end = candidate
                break
        part = text[spans[start][0] : spans[end - 1][1]].strip()
        if part:
            parts.append(part)
        start = end
    return parts


def _block_path(block: ParsedBlock, fallback_title: str) -> tuple[str, ...]:
    path = tuple(part.strip() for part in block.heading_path if part.strip())
    return path or (fallback_title,)


def build_evidence_units(
    parsed: ParsedDocument,
    *,
    source_id: str,
    config: SagChunkingConfig,
) -> list[EvidenceUnit]:
    """Create non-overlapping event evidence units from parsed document structure."""

    title = parsed.title or parsed.source_name.rsplit(".", 1)[0]
    units: list[EvidenceUnit] = []
    current_path: tuple[str, ...] = (title,)
    current_texts: list[str] = []
    current_anchors: list[str] = []
    current_tokens = 0

    def add_unit(content: str, anchors: list[str], path: tuple[str, ...]) -> None:
        normalized = content.strip()
        if not normalized:
            return
        ordinal = len(units)
        digest = _content_hash(normalized)
        units.append(
            EvidenceUnit(
                evidence_id=f"evd_{source_id[4:16]}_{ordinal:05d}_{digest[:10]}",
                source_id=source_id,
                ordinal=ordinal,
                title=title,
                section_path=list(path),
                anchors=list(dict.fromkeys(anchors)),
                content=normalized,
                content_hash=digest,
            )
        )

    def flush() -> None:
        nonlocal current_tokens
        if current_texts:
            add_unit("\n\n".join(current_texts), current_anchors, current_path)
        current_texts.clear()
        current_anchors.clear()
        current_tokens = 0

    for block in sorted(parsed.blocks, key=lambda item: item.order):
        if block.kind is BlockKind.HEADING:
            flush()
            current_path = _block_path(block, title)
            continue

        path = _block_path(block, title)
        block_tokens = count_tokens(block.text)
        if path != current_path and current_texts:
            flush()
        current_path = path

        if block_tokens > config.max_tokens:
            flush()
            for part in _split_oversized(block.text, config.max_tokens):
                add_unit(part, [block.anchor], current_path)
            continue

        would_exceed = current_tokens + block_tokens > config.max_tokens
        reached_target = current_tokens >= config.target_tokens
        if current_texts and (would_exceed or reached_target):
            flush()
        current_texts.append(block.text.strip())
        current_anchors.append(block.anchor)
        current_tokens += block_tokens

    flush()
    return units
