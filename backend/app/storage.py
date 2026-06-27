from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import BinaryIO, Protocol

from backend.app.config import settings


class StorageBackend(Protocol):
    def save_upload(self, session_id: str, filename: str, file_obj: BinaryIO) -> str: ...
    def open(self, clip_ref: str) -> BinaryIO: ...
    def get_url(self, clip_ref: str) -> str | None: ...
    def delete(self, clip_ref: str) -> None: ...


class LocalBackend:
    def __init__(self) -> None:
        self._root = Path(settings.storage_local_dir)
        self._root.mkdir(parents=True, exist_ok=True)

    def save_upload(self, session_id: str, filename: str, file_obj: BinaryIO) -> str:
        ext = Path(filename).suffix
        clip_id = uuid.uuid4().hex
        rel = f"{session_id}/{clip_id}{ext}"
        dest = self._root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as f:
            shutil.copyfileobj(file_obj, f)
        return rel

    def open(self, clip_ref: str) -> BinaryIO:
        return open(self._root / clip_ref, "rb")

    def get_url(self, clip_ref: str) -> str | None:
        return None

    def delete(self, clip_ref: str) -> None:
        p = self._root / clip_ref
        if p.exists():
            p.unlink()


class S3Backend:
    def __init__(self) -> None:
        import boto3  # type: ignore[import-untyped]

        self._client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
        )
        self._bucket = settings.s3_bucket or ""

    def save_upload(self, session_id: str, filename: str, file_obj: BinaryIO) -> str:
        ext = Path(filename).suffix
        clip_id = uuid.uuid4().hex
        key = f"{session_id}/{clip_id}{ext}"
        self._client.upload_fileobj(file_obj, self._bucket, key)
        return key

    def open(self, clip_ref: str) -> BinaryIO:
        import io

        buf = io.BytesIO()
        self._client.download_fileobj(self._bucket, clip_ref, buf)
        buf.seek(0)
        return buf

    def get_url(self, clip_ref: str) -> str | None:
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": clip_ref},
            ExpiresIn=3600,
        )

    def delete(self, clip_ref: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=clip_ref)


def get_backend() -> StorageBackend:
    if settings.storage_backend == "s3":
        return S3Backend()
    return LocalBackend()
