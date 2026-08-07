from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Literal

from enterprise_rag.models import Chunk, DocumentInput, DocumentRecord

STRUCTURED_CHUNKING_VERSION = "structured-parent-child-v1"
LEGACY_CHUNKING_VERSION = "legacy-characters-v1"

_TOKEN = re.compile(
    r"[A-Za-z0-9]+(?:[._:/-][A-Za-z0-9]+)*|[\u3400-\u9fff]|[^\s]",
    re.UNICODE,
)
_MARKDOWN_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*$")
_NUMBERED_HEADING = re.compile(r"^(\d+(?:\.\d+){0,5})[.、)\s]\s*(\S.*)$")
_CJK_HEADING = re.compile(
    r"^(?:第[一二三四五六七八九十百\d]+[章节部分]|[一二三四五六七八九十]+、)\s*\S"
)
_BOUNDARY_PUNCTUATION = frozenset(".!?;。！？；")
_KNOWN_SECTION_TITLES = frozenset(
    {
        "ABSTRACT",
        "AFFECTED PRODUCTS AND VERSIONS",
        "ANSWER",
        "CAUSE",
        "CHANGE HISTORY",
        "CONTENT",
        "DESCRIPTION",
        "DIAGNOSING THE PROBLEM",
        "ENVIRONMENT",
        "ERROR DESCRIPTION",
        "GET NOTIFIED ABOUT FUTURE SECURITY BULLETINS",
        "LOCAL FIX",
        "OBJECTIVE",
        "PROBLEM",
        "PROBLEM CONCLUSION",
        "PRODUCT ALIAS/SYNONYM",
        "QUESTION",
        "REFERENCE",
        "RELATED INFORMATION",
        "REMEDIATION/FIXES",
        "RESOLVING THE PROBLEM",
        "SOLUTION",
        "SUMMARY",
        "SYMPTOM",
        "TROUBLESHOOTING",
        "VULNERABILITY DETAILS",
        "WORKAROUNDS AND MITIGATIONS",
        "问题",
        "原因",
        "解决方案",
        "摘要",
    }
)


@dataclass(frozen=True, slots=True)
class ChunkingConfig:
    """Deterministic structure-aware child retrieval and parent evidence windows."""

    strategy: Literal["legacy", "structured_parent_child"] = "structured_parent_child"
    child_max_tokens: int = 384
    child_overlap_tokens: int = 64
    parent_max_tokens: int = 1200
    version: str = STRUCTURED_CHUNKING_VERSION

    def __post_init__(self) -> None:
        if self.child_max_tokens < 16:
            raise ValueError("child_max_tokens must be at least 16")
        if not 0 <= self.child_overlap_tokens < self.child_max_tokens:
            raise ValueError("child_overlap_tokens must be between 0 and child_max_tokens")
        if self.parent_max_tokens < self.child_max_tokens:
            raise ValueError("parent_max_tokens must be at least child_max_tokens")
        if not self.version.strip():
            raise ValueError("chunking version must not be empty")


@dataclass(frozen=True, slots=True)
class _Section:
    heading_path: tuple[str, ...]
    paragraphs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _BoundedSection:
    section_index: int
    heading_path: tuple[str, ...]
    header: str
    body: str


def _paragraphs(content: str) -> list[str]:
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    return [part.strip() for part in re.split(r"\n\s*\n", normalized) if part.strip()]


def token_spans(text: str) -> list[tuple[int, int]]:
    """Return deterministic approximate token offsets for chunk-size enforcement.

    English technical identifiers stay intact when reasonably short; very long URLs or
    machine-generated identifiers are subdivided so one regex token cannot bypass the
    storage and embedding budget. CJK characters are counted individually.
    """

    spans: list[tuple[int, int]] = []
    for match in _TOKEN.finditer(text):
        start, end = match.span()
        if end - start <= 24:
            spans.append((start, end))
            continue
        spans.extend((offset, min(offset + 16, end)) for offset in range(start, end, 16))
    return spans


def count_tokens(text: str) -> int:
    return len(token_spans(text))


def build_document(document: DocumentInput) -> DocumentRecord:
    checksum = hashlib.sha256(document.content.encode("utf-8")).hexdigest()
    return DocumentRecord(**document.model_dump(), checksum=checksum)


def _heading(paragraph: str) -> tuple[int, str] | None:
    lines = [line.strip() for line in paragraph.splitlines() if line.strip()]
    if not lines:
        return None
    candidate = lines[0]
    markdown = _MARKDOWN_HEADING.match(candidate)
    if markdown:
        return len(markdown.group(1)), markdown.group(2).strip()

    numbered = _NUMBERED_HEADING.match(candidate)
    if numbered and len(candidate) <= 160:
        return min(len(numbered.group(1).split(".")), 6), candidate

    normalized = candidate.rstrip(":：").strip()
    if normalized.upper() in _KNOWN_SECTION_TITLES:
        return 1, normalized
    if _CJK_HEADING.match(normalized) and len(normalized) <= 80:
        return 1, normalized

    letters = [character for character in normalized if character.isalpha()]
    words = normalized.split()
    uppercase_ratio = (
        sum(character.isupper() for character in letters) / len(letters) if letters else 0.0
    )
    if (
        1 <= len(words) <= 12
        and len(normalized) <= 120
        and uppercase_ratio >= 0.9
        and not normalized.endswith(tuple(_BOUNDARY_PUNCTUATION))
    ):
        return 1, normalized
    return None


def _structured_sections(content: str) -> list[_Section]:
    sections: list[_Section] = []
    heading_path: list[str] = []
    paragraphs: list[str] = []

    def flush() -> None:
        if paragraphs:
            sections.append(_Section(tuple(heading_path), tuple(paragraphs)))
            paragraphs.clear()

    for paragraph in _paragraphs(content):
        heading = _heading(paragraph)
        if heading is None:
            paragraphs.append(paragraph)
            continue

        flush()
        level, title = heading
        del heading_path[level - 1 :]
        while len(heading_path) < level - 1:
            heading_path.append("Untitled")
        heading_path.append(title)

        lines = [line.strip() for line in paragraph.splitlines() if line.strip()]
        if len(lines) > 1:
            paragraphs.append("\n".join(lines[1:]))

    flush()
    return sections


def _natural_end(text: str, spans: list[tuple[int, int]], start: int, target: int) -> int:
    if target >= len(spans):
        return target
    minimum = min(target, start + max(int((target - start) * 0.6), 1))

    for index in range(target, minimum, -1):
        previous_end = spans[index - 1][1]
        next_start = spans[index][0] if index < len(spans) else len(text)
        if "\n" in text[previous_end:next_start]:
            return index
    for index in range(target, minimum, -1):
        token = text[spans[index - 1][0] : spans[index - 1][1]]
        if token and token[-1] in _BOUNDARY_PUNCTUATION:
            return index
    return target


def _token_windows(text: str, maximum: int, overlap: int) -> list[str]:
    spans = token_spans(text)
    if not spans:
        compact = text.strip()
        return [compact] if compact else []

    windows: list[str] = []
    start = 0
    while start < len(spans):
        target = min(start + maximum, len(spans))
        end = _natural_end(text, spans, start, target)
        if end <= start:
            end = target
        window = text[spans[start][0] : spans[end - 1][1]].strip()
        if window:
            windows.append(window)
        if end == len(spans):
            break
        start = max(end - overlap, start + 1)
    return windows


def _section_header(path: tuple[str, ...]) -> str:
    return f"Section: {' > '.join(path)}" if path else ""


def _with_header(header: str, body: str) -> str:
    return f"{header}\n\n{body}" if header else body


def _bounded_sections(
    sections: list[_Section],
    config: ChunkingConfig,
) -> list[_BoundedSection]:
    bounded: list[_BoundedSection] = []
    header_limit = min(max(config.child_max_tokens // 4, 4), 64)
    for section_index, section in enumerate(sections, start=1):
        full_header = _section_header(section.heading_path)
        header_windows = _token_windows(full_header, header_limit, 0)
        header = header_windows[0] if header_windows else ""
        # Leave a small safety margin because a sliced long URL can retokenize at
        # a different offset when it is joined to its repeated section header.
        body_budget = max(config.parent_max_tokens - count_tokens(header) - 2, 1)
        body = "\n\n".join(section.paragraphs)
        for part in _token_windows(body, body_budget, 0):
            bounded.append(_BoundedSection(section_index, section.heading_path, header, part))
    return bounded


def _render_bounded_section(section: _BoundedSection) -> str:
    return _with_header(section.header, section.body)


def _parent_groups(
    sections: list[_BoundedSection],
    maximum_tokens: int,
) -> list[list[_BoundedSection]]:
    groups: list[list[_BoundedSection]] = []
    current: list[_BoundedSection] = []
    current_tokens = 0
    for section in sections:
        section_tokens = count_tokens(_render_bounded_section(section))
        if current and current_tokens + section_tokens > maximum_tokens:
            groups.append(current)
            current = []
            current_tokens = 0
        current.append(section)
        current_tokens += section_tokens
    if current:
        groups.append(current)
    return groups


def _section_titles(sections: list[_BoundedSection]) -> str:
    paths = [" > ".join(section.heading_path) for section in sections if section.heading_path]
    return " | ".join(dict.fromkeys(paths))


def _structured_chunk_document(document: DocumentRecord, config: ChunkingConfig) -> list[Chunk]:
    chunks: list[Chunk] = []
    sections = _structured_sections(document.content)
    if not sections:
        sections = [_Section((), tuple(_paragraphs(document.content)))]
    bounded_sections = _bounded_sections(sections, config)
    parent_groups = _parent_groups(bounded_sections, config.parent_max_tokens)

    for parent_position, parent_sections in enumerate(parent_groups):
        parent_content = "\n\n".join(
            _render_bounded_section(section) for section in parent_sections
        )
        parent_id = f"{document.document_id}:{document.version}:parent:{parent_position}"
        child_groups: list[list[_BoundedSection]] = []
        current: list[_BoundedSection] = []
        current_tokens = 0

        for section in parent_sections:
            rendered = _render_bounded_section(section)
            rendered_tokens = count_tokens(rendered)
            if rendered_tokens > config.child_max_tokens:
                if current:
                    child_groups.append(current)
                    current = []
                    current_tokens = 0
                body_budget = max(
                    config.child_max_tokens - count_tokens(section.header) - 2,
                    1,
                )
                overlap = min(
                    config.child_overlap_tokens,
                    max(body_budget - 1, 0),
                )
                child_groups.extend(
                    [
                        [
                            _BoundedSection(
                                section.section_index,
                                section.heading_path,
                                section.header,
                                body,
                            )
                        ]
                        for body in _token_windows(section.body, body_budget, overlap)
                    ]
                )
                continue

            if current and current_tokens + rendered_tokens > config.child_max_tokens:
                child_groups.append(current)
                current = []
                current_tokens = 0
            current.append(section)
            current_tokens += rendered_tokens
        if current:
            child_groups.append(current)

        for local_child_position, child_sections in enumerate(child_groups, start=1):
            content = "\n\n".join(
                _render_bounded_section(section) for section in child_sections
            )
            token_count = count_tokens(content)
            if token_count > config.child_max_tokens:
                raise RuntimeError(
                    "structured chunk exceeded its strict token contract: "
                    f"{token_count} > {config.child_max_tokens}"
                )
            section_title = _section_titles(child_sections)
            anchor_digest = hashlib.sha256(section_title.encode("utf-8")).hexdigest()[:10]
            position = len(chunks)
            chunks.append(
                Chunk(
                    chunk_id=f"{document.document_id}:{document.version}:{position}",
                    document_id=document.document_id,
                    title=document.title,
                    content=content,
                    position=position,
                    anchor=(
                        f"section:{child_sections[0].section_index}:{anchor_digest}:"
                        f"p{parent_position + 1}:c{local_child_position}"
                    ),
                    allowed_roles=frozenset(document.allowed_roles),
                    version=document.version,
                    status=document.status,
                    business_class=document.business_class,
                    parent_id=parent_id,
                    parent_content=parent_content,
                    section_title=section_title,
                    chunking_version=config.version,
                    token_count=token_count,
                )
            )
    return chunks


def _legacy_chunk_document(
    document: DocumentRecord,
    max_characters: int,
    overlap_characters: int,
) -> list[Chunk]:
    if max_characters < 1:
        raise ValueError("max_characters must be positive")
    if not 0 <= overlap_characters < max_characters:
        raise ValueError("overlap_characters must be between 0 and max_characters")

    chunks: list[str] = []
    buffer = ""
    for paragraph in _paragraphs(document.content):
        candidate = f"{buffer}\n\n{paragraph}".strip() if buffer else paragraph
        if len(candidate) <= max_characters:
            buffer = candidate
            continue
        if buffer:
            chunks.append(buffer)
            buffer = f"{buffer[-overlap_characters:]}\n\n{paragraph}".strip()
        else:
            start = 0
            while start < len(paragraph):
                end = start + max_characters
                chunks.append(paragraph[start:end])
                start = max(end - overlap_characters, start + 1)
    if buffer:
        chunks.append(buffer)

    return [
        Chunk(
            chunk_id=f"{document.document_id}:{document.version}:{position}",
            document_id=document.document_id,
            title=document.title,
            content=content,
            position=position,
            anchor=f"section:{position + 1}",
            allowed_roles=frozenset(document.allowed_roles),
            version=document.version,
            status=document.status,
            business_class=document.business_class,
            chunking_version=LEGACY_CHUNKING_VERSION,
            token_count=count_tokens(content),
        )
        for position, content in enumerate(chunks)
    ]


def chunk_document(
    document: DocumentRecord,
    *,
    config: ChunkingConfig | None = None,
    max_characters: int = 900,
    overlap_characters: int = 100,
) -> list[Chunk]:
    """Build retrieval chunks; structured parent-child is the new default.

    ``max_characters`` and ``overlap_characters`` remain available for reproducible
    legacy-index ablations and are used only when ``config.strategy == 'legacy'``.
    """

    resolved = config or ChunkingConfig()
    if resolved.strategy == "legacy":
        return _legacy_chunk_document(document, max_characters, overlap_characters)
    return _structured_chunk_document(document, resolved)
