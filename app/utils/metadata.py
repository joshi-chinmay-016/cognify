"""Metadata management utility for Cognify.

Tracks file synchronization state, modification timestamps,
and processing metadata to prevent redundant downloads and reprocessing.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class FileMetadata:
    """Metadata for an ingested file."""

    file_id: str
    filename: str
    file_type: str  # 'docx', 'xlsx', etc.
    modified_time: str
    local_path: str
    size_bytes: int = 0
    worksheets: list[str] = field(default_factory=list)
    chunk_count: int = 0
    processed_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FileMetadata:
        return cls(
            file_id=data.get("file_id", ""),
            filename=data.get("filename", ""),
            file_type=data.get("file_type", ""),
            modified_time=data.get("modified_time", ""),
            local_path=data.get("local_path", ""),
            size_bytes=data.get("size_bytes", 0),
            worksheets=data.get("worksheets", []),
            chunk_count=data.get("chunk_count", 0),
            processed_at=data.get("processed_at", ""),
        )


class MetadataRegistry:
    """Persistent registry of file metadata."""

    def __init__(self, registry_file: Path):
        self.registry_file = registry_file
        self.records: dict[str, FileMetadata] = {}
        self.load()

    def load(self) -> None:
        """Load metadata from persistent JSON storage."""
        if self.registry_file.exists():
            try:
                with open(self.registry_file, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                    self.records = {
                        fid: FileMetadata.from_dict(meta)
                        for fid, meta in raw.items()
                    }
                logger.debug("Loaded %d metadata records from %s", len(self.records), self.registry_file)
            except Exception as e:
                logger.warning("Failed to load metadata registry from %s: %s", self.registry_file, e)
                self.records = {}
        else:
            self.records = {}

    def save(self) -> None:
        """Persist metadata to JSON file."""
        try:
            self.registry_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.registry_file, "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self.records.items()}, f, indent=2)
            logger.debug("Saved %d metadata records to %s", len(self.records), self.registry_file)
        except Exception as e:
            logger.error("Failed to save metadata registry to %s: %s", self.registry_file, e)

    def get(self, file_id: str) -> FileMetadata | None:
        return self.records.get(file_id)

    def set(self, metadata: FileMetadata) -> None:
        self.records[metadata.file_id] = metadata
        self.save()

    def remove(self, file_id: str) -> None:
        if file_id in self.records:
            del self.records[file_id]
            self.save()

    def list_all(self) -> list[FileMetadata]:
        return list(self.records.values())

    def clear(self) -> None:
        self.records.clear()
        self.save()
