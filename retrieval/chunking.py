"""Structure-aware text chunking for runbooks and postmortems."""

from __future__ import annotations

import re
from collections.abc import Iterable

from api.security import scan_prompt_injection
from retrieval.models import ChunkRecord, DocumentRecord

HEADING_RE = re.compile(r"^#{1,6}\s+(.+)$")


def _sections(text: str) -> Iterable[tuple[str, str]]:
    current_heading = "Document"
    buffer: list[str] = []
    in_code = False
    for raw_line in text.replace("\r\n", "\n").split("\n"):
        line = raw_line.rstrip()
        if line.strip().startswith("```"):
            in_code = not in_code
        heading = None if in_code else HEADING_RE.match(line)
        if heading:
            if any(item.strip() for item in buffer):
                yield current_heading, "\n".join(buffer).strip()
            current_heading = heading.group(1).strip()
            buffer = []
        else:
            buffer.append(line)
    if any(item.strip() for item in buffer):
        yield current_heading, "\n".join(buffer).strip()


def chunk_document(
    document: DocumentRecord,
    *,
    target_words: int = 420,
    overlap_words: int = 50,
) -> list[ChunkRecord]:
    """Split text on headings, then enforce bounded chunks with overlap."""

    if target_words < 50 or overlap_words < 0 or overlap_words >= target_words:
        raise ValueError("invalid chunk size or overlap")

    chunks: list[ChunkRecord] = []
    position = 0
    for section, body in _sections(document.content):
        words = body.split()
        if not words:
            continue
        cursor = 0
        while cursor < len(words):
            end = min(cursor + target_words, len(words))
            content = " ".join(words[cursor:end])
            scan = scan_prompt_injection(content)
            chunks.append(
                ChunkRecord(
                    id=f"{document.id}-C{position + 1:04d}",
                    document_id=document.id,
                    source=document.source,
                    version=document.version,
                    service=document.service,
                    environment=document.environment,
                    trust_level=document.trust_level,
                    section=section,
                    content=content,
                    position=position,
                    injection_flagged=scan.flagged,
                )
            )
            position += 1
            if end == len(words):
                break
            cursor = end - overlap_words
    return chunks
