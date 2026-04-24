"""Abstract EntityStore — one contract every backend implements."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Optional, Tuple


# MIME -> (extension, content_table, payload column, kind-hint)
# Identical map as vfs-webdav uses; kept central so every service agrees.
MIME_IO = {
    "application/json":  (".json", "content_json",     "data",     "json"),
    "application/yaml":  (".yaml", "content_yaml",     "raw_text", "text"),
    "application/xml":   (".xml",  "content_xml",      "raw_text", "text"),
    "text/html":         (".html", "content_html",     "body",     "text"),
    "text/markdown":     (".md",   "content_markdown", "body",     "text"),
    "text/plain":        (".txt",  "content_markdown", "body",     "text"),
    "image/png":         (".png",  "content_binary",   "bytes",    "bytes"),
    "image/jpeg":        (".jpg",  "content_binary",   "bytes",    "bytes"),
    "application/pdf":   (".pdf",  "content_binary",   "bytes",    "bytes"),
    "application/octet-stream": (".bin", "content_binary", "bytes", "bytes"),
}

EXT_TO_MIME = {}
for _mime, (_ext, *_rest) in MIME_IO.items():
    EXT_TO_MIME.setdefault(_ext, _mime)


@dataclass
class EntityRef:
    external_id: str
    entity_type: str
    mime: str
    updated_at: Optional[datetime] = None
    version: int = 0
    size: int = 0


class EntityStore(ABC):
    """Minimal uniform contract for protocol gateways and connectors."""

    # ---- discovery -----------------------------------------------------------
    @abstractmethod
    def list_types(self) -> Iterable[Tuple[str, str, str]]:
        """Yield (entity_type, mime, extension) for each folder/mailbox."""

    @abstractmethod
    def list_entities(self, entity_type: str) -> Iterable[EntityRef]:
        """Yield entity refs belonging to an entity_type."""

    # ---- single-entity I/O ---------------------------------------------------
    @abstractmethod
    def read(self, external_id: str) -> Optional[Tuple[bytes, str, Optional[datetime]]]:
        """Return (body, mime, updated_at) or None if not found."""

    @abstractmethod
    def write(self, external_id: str, entity_type: str, mime: str, body: bytes,
              source: str = "gateway") -> None:
        """Upsert an entity + its content row."""

    @abstractmethod
    def delete(self, external_id: str) -> None:
        ...

    # ---- optional ------------------------------------------------------------
    def close(self) -> None:
        return None
