"""Private document storage. Local disk for development, any S3-compatible bucket in production.

Files are never served from a public path: only the authorised /api/documents endpoint reads them.
"""
from pathlib import Path

from app.config import settings


class LocalStorage:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, name: str, data: bytes, content_type: str) -> None:
        (self.root / name).write_bytes(data)

    def get(self, name: str) -> bytes:
        path = (self.root / name).resolve()
        if self.root.resolve() not in path.parents:  # defence against path tricks
            raise FileNotFoundError(name)
        return path.read_bytes()


class S3Storage:
    """Any S3-compatible store: AWS S3, Cloudflare R2, or Supabase Storage
    (endpoint https://<project-ref>.supabase.co/storage/v1/s3, path-style addressing)."""

    def __init__(self):
        import boto3
        from botocore.config import Config
        self.bucket = settings.s3_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url or None,
            region_name=settings.s3_region,
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key,
            config=Config(signature_version="s3v4",
                          s3={"addressing_style": "path" if settings.s3_endpoint_url else "auto"}),
        )

    def put(self, name: str, data: bytes, content_type: str) -> None:
        extra = {"ServerSideEncryption": "AES256"} if settings.s3_server_side_encryption else {}
        self.client.put_object(Bucket=self.bucket, Key=f"documents/{name}", Body=data,
                               ContentType=content_type, **extra)

    def get(self, name: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=f"documents/{name}")["Body"].read()


_storage = None


def storage():
    global _storage
    if _storage is None:
        _storage = S3Storage() if settings.storage_backend == "s3" else LocalStorage(settings.storage_dir)
    return _storage
