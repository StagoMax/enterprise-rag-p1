import hashlib
import re

from enterprise_rag.models import Chunk, DocumentInput, DocumentRecord


def _paragraphs(content: str) -> list[str]:
    return [part.strip() for part in re.split(r"\n\s*\n", content) if part.strip()]


def build_document(document: DocumentInput) -> DocumentRecord:
    checksum = hashlib.sha256(document.content.encode("utf-8")).hexdigest()
    return DocumentRecord(**document.model_dump(), checksum=checksum)


def chunk_document(
    document: DocumentRecord,
    *,
    max_characters: int = 900,
    overlap_characters: int = 100,
) -> list[Chunk]:
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
        )
        for position, content in enumerate(chunks)
    ]

