import io
import uuid
from typing import BinaryIO

from app.config import settings


class StorageError(Exception):
    pass


def _get_client():
    try:
        from minio import Minio
    except Exception as e:  # pragma: no cover
        raise StorageError("minio client is not installed") from e
    return Minio(
        settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_SECURE,
    )


def ensure_bucket() -> None:
    client = _get_client()
    bucket = settings.MINIO_BUCKET
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)


def upload_pdf(data: bytes, filename: str) -> str:
    """Upload PDF bytes to MinIO and return the object key."""
    ensure_bucket()
    client = _get_client()
    key = f"documents/{uuid.uuid4()}-{filename}"
    stream = io.BytesIO(data)
    client.put_object(
        settings.MINIO_BUCKET,
        key,
        stream,
        length=len(data),
        content_type="application/pdf",
    )
    return key


def download_pdf(key: str) -> bytes:
    client = _get_client()
    resp = client.get_object(settings.MINIO_BUCKET, key)
    try:
        return resp.read()
    finally:
        resp.close()
        resp.release_conn()
