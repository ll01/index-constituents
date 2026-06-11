"""Sync the library to any S3-compatible bucket and mint presigned URLs.

Works with AWS S3, MinIO, Cloudflare R2, Backblaze B2 — anything with an S3
API. Credentials come from the standard AWS chain (env vars, ~/.aws, etc.).
boto3 is imported lazily so the rest of the tool runs without it installed.
"""

from __future__ import annotations

from pathlib import Path


class S3Sync:
    def __init__(self, bucket: str, prefix: str = "", endpoint_url: str | None = None,
                 region: str | None = None):
        try:
            import boto3
        except ImportError as e:
            raise SystemExit(
                "boto3 is required for S3 commands: pip install boto3"
            ) from e
        self.bucket = bucket
        self.prefix = prefix.strip("/") + "/" if prefix.strip("/") else ""
        self.client = boto3.client(
            "s3", endpoint_url=endpoint_url or None, region_name=region or None
        )

    def remote_objects(self) -> dict[str, int]:
        """Map of key -> size for everything under our prefix."""
        out: dict[str, int] = {}
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=self.prefix):
            for obj in page.get("Contents", []):
                out[obj["Key"]] = obj["Size"]
        return out

    def _key_for(self, library: Path, path: Path) -> str:
        return self.prefix + path.relative_to(library).as_posix()

    def sync_up(self, library: Path, dry_run: bool = False) -> tuple[list[str], int]:
        """Upload files that are missing remotely or differ in size.

        Returns (uploaded_keys, skipped_count).
        """
        library = library.expanduser()
        remote = self.remote_objects()
        uploaded: list[str] = []
        skipped = 0
        for path in sorted(library.rglob("*")):
            if not path.is_file():
                continue
            key = self._key_for(library, path)
            if remote.get(key) == path.stat().st_size:
                skipped += 1
                continue
            if not dry_run:
                self.client.upload_file(str(path), self.bucket, key)
            uploaded.append(key)
        return uploaded, skipped

    def presign(self, key: str, expires_seconds: int = 86400) -> str:
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_seconds,
        )

    def find_keys(self, terms: list[str]) -> list[str]:
        """Remote keys whose path contains every search term (case-insensitive)."""
        lowered = [t.lower() for t in terms]
        return [k for k in self.remote_objects() if all(t in k.lower() for t in lowered)]
