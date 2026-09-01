"""Safe extraction and ingestion for Markdown, text, and PDF documents."""

from __future__ import annotations

from io import BytesIO
from pathlib import PurePath
from uuid import uuid4

from pypdf import PdfReader

from api.models import TrustLevel
from api.security import redact_text, scan_prompt_injection
from retrieval.chunking import chunk_document
from retrieval.hybrid import HybridIndex
from retrieval.models import DocumentRecord

ALLOWED_SUFFIXES = {".md", ".markdown", ".txt", ".pdf"}


class IngestionError(ValueError):
    """Raised when an uploaded document violates an ingestion contract."""


def extract_text(filename: str, payload: bytes) -> str:
    """Extract text from an allowlisted file type without executing embedded content."""

    suffix = PurePath(filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise IngestionError(f"unsupported document type: {suffix or 'none'}")
    if suffix == ".pdf":
        try:
            reader = PdfReader(BytesIO(payload))
            return "\n\n".join(page.extract_text() or "" for page in reader.pages).strip()
        except Exception as exc:
            raise IngestionError("unable to parse PDF") from exc
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise IngestionError("text documents must use UTF-8") from exc


def ingest_bytes(
    index: HybridIndex,
    *,
    filename: str,
    payload: bytes,
    service: str,
    environment: str | None,
    version: str,
    trust_level: TrustLevel,
) -> tuple[DocumentRecord, int, bool]:
    """Extract, chunk, scan, and index a document with provenance metadata."""

    text = extract_text(filename, payload)
    if not text.strip():
        raise IngestionError("document contains no extractable text")
    scan = scan_prompt_injection(text)
    safe_text, _ = redact_text(text)
    document = DocumentRecord(
        id=f"DOC-{uuid4().hex[:12].upper()}",
        source=PurePath(filename).name,
        version=version,
        service=service,
        environment=environment,
        trust_level=trust_level,
        content=safe_text,
    )
    chunks = chunk_document(document)
    index.add(chunks)
    flagged = scan.flagged
    return document, len(chunks), flagged
