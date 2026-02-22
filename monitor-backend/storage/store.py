"""
storage/store.py
Core storage system: FileRecord dataclass + FileStore class.

FileStore handles all disk I/O and tracks file metadata in memory.
The storage directory is created automatically on instantiation.
"""

from __future__ import annotations

import os
import shutil
import uuid
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# FileRecord – metadata for a single stored file
# ---------------------------------------------------------------------------

@dataclass
class FileRecord:
    """Immutable-ish value object that describes a stored file."""

    file_id: str
    filename: str           # original, user-supplied name
    content_type: str       # MIME type
    size: int               # bytes
    created_at: str         # ISO-8601 UTC
    updated_at: str         # ISO-8601 UTC
    description: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    # Internal: absolute path on disk (not exposed in API responses)
    _path: str = field(default="", repr=False)

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    def to_dict(self, *, include_path: bool = False) -> dict:
        """Return a JSON-serialisable dict (path excluded by default)."""
        d = asdict(self)
        d.pop("_path")
        if include_path:
            d["path"] = self._path
        return d

    @classmethod
    def _from_dict(cls, d: dict, path: str) -> "FileRecord":
        """Reconstruct from a previously serialised dict."""
        return cls(
            file_id=d["file_id"],
            filename=d["filename"],
            content_type=d["content_type"],
            size=d["size"],
            created_at=d["created_at"],
            updated_at=d["updated_at"],
            description=d.get("description"),
            tags=d.get("tags", []),
            _path=path,
        )


# ---------------------------------------------------------------------------
# FileStore – manages a directory of files + their in-memory metadata index
# ---------------------------------------------------------------------------

class FileStore:
    """
    Manages stored files and their metadata.

    All files are written to *storage_dir* under their UUID.
    Metadata is kept in an in-memory dict keyed by ``file_id``.

    Typical lifecycle::

        store = FileStore("/data/storage")
        record = store.insert(b"hello", "note.txt", "text/plain")
        content = store.get_content(record.file_id)
        store.update_metadata(record.file_id, description="my note")
        store.replace_content(record.file_id, b"updated content")
        store.delete(record.file_id)
    """

    def __init__(self, storage_dir: str) -> None:
        self._dir = os.path.abspath(storage_dir)
        os.makedirs(self._dir, exist_ok=True)
        # file_id -> FileRecord
        self._index: dict[str, FileRecord] = {}
        logger.info("FileStore initialised at %s", self._dir)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def storage_dir(self) -> str:
        return self._dir

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def insert(
        self,
        data: bytes,
        filename: str,
        content_type: str = "application/octet-stream",
        description: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> FileRecord:
        """Write *data* to disk and register its metadata.

        Returns the newly created :class:`FileRecord`.
        """
        file_id = str(uuid.uuid4())
        path = self._build_path(file_id, filename)

        with open(path, "wb") as fh:
            fh.write(data)

        now = _now_iso()
        record = FileRecord(
            file_id=file_id,
            filename=filename,
            content_type=content_type,
            size=len(data),
            created_at=now,
            updated_at=now,
            description=description,
            tags=tags or [],
            _path=path,
        )
        self._index[file_id] = record
        logger.info("Inserted file %s (%s, %d bytes)", file_id, filename, len(data))
        return record

    def get(self, file_id: str) -> Optional[FileRecord]:
        """Return the :class:`FileRecord` for *file_id*, or ``None``."""
        return self._index.get(file_id)

    def get_content(self, file_id: str) -> Optional[bytes]:
        """Return the raw bytes of the file, or ``None`` if not found."""
        record = self._index.get(file_id)
        if record is None:
            return None
        try:
            with open(record._path, "rb") as fh:
                return fh.read()
        except OSError as exc:
            logger.warning("Could not read file %s: %s", file_id, exc)
            return None

    def list_all(self) -> list[FileRecord]:
        """Return all :class:`FileRecord` objects, newest first."""
        return sorted(
            self._index.values(),
            key=lambda r: r.created_at,
            reverse=True,
        )

    def update_metadata(
        self,
        file_id: str,
        *,
        filename: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[list[str]] = None,
        content_type: Optional[str] = None,
    ) -> Optional[FileRecord]:
        """Update mutable metadata fields for an existing record.

        Returns the updated :class:`FileRecord`, or ``None`` if not found.
        Changing *filename* also renames the file on disk.
        """
        record = self._index.get(file_id)
        if record is None:
            return None

        new_path = record._path

        if filename is not None and filename != record.filename:
            new_path = self._build_path(file_id, filename)
            try:
                shutil.move(record._path, new_path)
            except OSError as exc:
                logger.warning("Could not rename file %s: %s", file_id, exc)
                new_path = record._path  # rollback path change
            else:
                record.filename = filename

        if description is not None:
            record.description = description
        if tags is not None:
            record.tags = tags
        if content_type is not None:
            record.content_type = content_type

        record._path = new_path
        record.updated_at = _now_iso()
        logger.info("Updated metadata for file %s", file_id)
        return record

    def replace_content(
        self,
        file_id: str,
        data: bytes,
        *,
        content_type: Optional[str] = None,
    ) -> Optional[FileRecord]:
        """Overwrite the on-disk content of an existing file.

        Metadata (filename, description, tags) is preserved.
        Returns the updated :class:`FileRecord`, or ``None`` if not found.
        """
        record = self._index.get(file_id)
        if record is None:
            return None

        with open(record._path, "wb") as fh:
            fh.write(data)

        record.size = len(data)
        record.updated_at = _now_iso()
        if content_type is not None:
            record.content_type = content_type

        logger.info("Replaced content of file %s (%d bytes)", file_id, len(data))
        return record

    def delete(self, file_id: str) -> bool:
        """Remove the file from disk and the metadata index.

        Returns ``True`` on success, ``False`` if the file was not found.
        """
        record = self._index.pop(file_id, None)
        if record is None:
            return False
        try:
            os.remove(record._path)
        except OSError as exc:
            logger.warning("Could not remove file %s from disk: %s", file_id, exc)
        logger.info("Deleted file %s (%s)", file_id, record.filename)
        return True

    def clear(self) -> int:
        """Delete all files managed by this store. Returns the count removed."""
        ids = list(self._index.keys())
        for fid in ids:
            self.delete(fid)
        return len(ids)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_path(self, file_id: str, filename: str) -> str:
        """Construct a safe disk path: <storage_dir>/<uuid>_<original_name>."""
        safe_name = os.path.basename(filename).replace(" ", "_")
        return os.path.join(self._dir, f"{file_id}_{safe_name}")


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
