"""
storage/router.py
FastAPI router exposing CRUD endpoints for the FileStore.

All routes are session-gated via the shared ``require_session`` dependency
imported from the parent application module.

Endpoints:
  POST   /api/storage/files                – insert (upload) a file
  GET    /api/storage/files                – list all files (metadata only)
  GET    /api/storage/files/{file_id}      – get a single file's metadata
  GET    /api/storage/files/{file_id}/download  – download raw content
  PATCH  /api/storage/files/{file_id}      – edit metadata
  PUT    /api/storage/files/{file_id}      – replace content (re-upload)
  DELETE /api/storage/files/{file_id}      – delete a file
  DELETE /api/storage/files                – clear all files
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Optional

from .store import FileStore


# ---------------------------------------------------------------------------
# Pydantic response / request models
# ---------------------------------------------------------------------------

class FileMetadata(BaseModel):
    file_id: str
    filename: str
    content_type: str
    size: int
    created_at: str
    updated_at: str
    description: Optional[str] = None
    tags: list[str] = []

    @classmethod
    def from_record(cls, record) -> "FileMetadata":
        return cls(**record.to_dict())


class MetadataUpdateRequest(BaseModel):
    filename: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[list[str]] = None
    content_type: Optional[str] = None


class FileListResponse(BaseModel):
    files: list[FileMetadata]
    total: int


class DeleteResponse(BaseModel):
    message: str
    file_id: Optional[str] = None
    deleted_count: Optional[int] = None


# ---------------------------------------------------------------------------
# Router factory
# ---------------------------------------------------------------------------

def create_router(store: FileStore, require_session) -> APIRouter:
    """
    Return a fully-wired :class:`~fastapi.APIRouter`.

    Parameters
    ----------
    store:
        The :class:`~storage.store.FileStore` instance to operate on.
    require_session:
        The session-guard dependency from the parent app. Passed in to
        avoid circular imports.
    """

    router = APIRouter(
        prefix="/api/storage",
        tags=["Storage"],
        dependencies=[Depends(require_session)],
    )

    # ------------------------------------------------------------------
    # INSERT – POST /api/storage/files
    # ------------------------------------------------------------------

    @router.post(
        "/files",
        response_model=FileMetadata,
        status_code=status.HTTP_201_CREATED,
        summary="Upload and store a new file",
    )
    async def insert_file(
        file: UploadFile = File(..., description="File to store"),
        description: Optional[str] = Form(None, description="Human-readable description"),
        tags: Optional[str] = Form(
            None,
            description="Comma-separated list of tags, e.g. 'report,2026'",
        ),
    ) -> FileMetadata:
        """Upload a file. Returns the stored file's metadata."""
        data = await file.read()
        tag_list = [t.strip() for t in tags.split(",")] if tags else []
        record = store.insert(
            data,
            filename=file.filename or "unnamed",
            content_type=file.content_type or "application/octet-stream",
            description=description,
            tags=tag_list,
        )
        return FileMetadata.from_record(record)

    # ------------------------------------------------------------------
    # LIST – GET /api/storage/files
    # ------------------------------------------------------------------

    @router.get(
        "/files",
        response_model=FileListResponse,
        summary="List all stored files (metadata only)",
    )
    def list_files() -> FileListResponse:
        """Returns metadata for every stored file, newest first."""
        records = store.list_all()
        return FileListResponse(
            files=[FileMetadata.from_record(r) for r in records],
            total=len(records),
        )

    # ------------------------------------------------------------------
    # GET METADATA – GET /api/storage/files/{file_id}
    # ------------------------------------------------------------------

    @router.get(
        "/files/{file_id}",
        response_model=FileMetadata,
        summary="Get a single file's metadata",
    )
    def get_file(file_id: str) -> FileMetadata:
        """Returns the metadata record for *file_id*."""
        record = store.get(file_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"File '{file_id}' not found.")
        return FileMetadata.from_record(record)

    # ------------------------------------------------------------------
    # DOWNLOAD – GET /api/storage/files/{file_id}/download
    # ------------------------------------------------------------------

    @router.get(
        "/files/{file_id}/download",
        summary="Download the raw content of a file",
        responses={200: {"content": {"application/octet-stream": {}}}},
    )
    def download_file(file_id: str) -> Response:
        """Streams the raw bytes of a stored file."""
        record = store.get(file_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"File '{file_id}' not found.")
        content = store.get_content(file_id)
        if content is None:
            raise HTTPException(
                status_code=500,
                detail="File metadata exists but content could not be read.",
            )
        return Response(
            content=content,
            media_type=record.content_type,
            headers={"Content-Disposition": f'attachment; filename="{record.filename}"'},
        )

    # ------------------------------------------------------------------
    # EDIT METADATA – PATCH /api/storage/files/{file_id}
    # ------------------------------------------------------------------

    @router.patch(
        "/files/{file_id}",
        response_model=FileMetadata,
        summary="Update a file's metadata",
    )
    def edit_metadata(file_id: str, body: MetadataUpdateRequest) -> FileMetadata:
        """
        Partially update mutable metadata fields (filename, description,
        tags, content_type). Pass only the fields you want to change.
        Renaming also renames the file on disk.
        """
        record = store.update_metadata(
            file_id,
            filename=body.filename,
            description=body.description,
            tags=body.tags,
            content_type=body.content_type,
        )
        if record is None:
            raise HTTPException(status_code=404, detail=f"File '{file_id}' not found.")
        return FileMetadata.from_record(record)

    # ------------------------------------------------------------------
    # REPLACE CONTENT – PUT /api/storage/files/{file_id}
    # ------------------------------------------------------------------

    @router.put(
        "/files/{file_id}",
        response_model=FileMetadata,
        summary="Replace the content of an existing file",
    )
    async def replace_content(
        file_id: str,
        file: UploadFile = File(..., description="New file content"),
    ) -> FileMetadata:
        """
        Replaces the stored bytes for *file_id* with the newly uploaded
        content. Metadata (filename, description, tags) is preserved
        unless the upload provides a different content-type.
        """
        record = store.get(file_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"File '{file_id}' not found.")
        data = await file.read()
        updated = store.replace_content(
            file_id,
            data,
            content_type=file.content_type or None,
        )
        return FileMetadata.from_record(updated)

    # ------------------------------------------------------------------
    # DELETE ONE – DELETE /api/storage/files/{file_id}
    # ------------------------------------------------------------------

    @router.delete(
        "/files/{file_id}",
        response_model=DeleteResponse,
        summary="Delete a single file",
    )
    def delete_file(file_id: str) -> DeleteResponse:
        """Removes the file and its metadata from the store."""
        ok = store.delete(file_id)
        if not ok:
            raise HTTPException(status_code=404, detail=f"File '{file_id}' not found.")
        return DeleteResponse(message="File deleted.", file_id=file_id)

    # ------------------------------------------------------------------
    # CLEAR ALL – DELETE /api/storage/files
    # ------------------------------------------------------------------

    @router.delete(
        "/files",
        response_model=DeleteResponse,
        summary="Delete all stored files",
    )
    def clear_files() -> DeleteResponse:
        """Removes every file from the store. Use with caution."""
        count = store.clear()
        return DeleteResponse(
            message=f"Cleared {count} file(s).",
            deleted_count=count,
        )

    return router
