"""Sync the library to any S3-compatible bucket and mint presigned URLs.

Works with AWS S3, MinIO, Cloudflare R2, Backblaze B2 — anything with an S3
API. Credentials come from the standard AWS chain (env vars, ~/.aws, etc.).
boto3 is imported lazily so the rest of the tool runs without it installed.
"""

from __future__ import annotations

import html
import re
from pathlib import Path

_VIDEO_RE = re.compile(r"\.(mkv|mp4|avi|mov|wmv|flv|webm|m4v|ts|mpg|mpeg)$", re.IGNORECASE)


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

    def sync_down(self, library: Path, dry_run: bool = False) -> tuple[list[str], int]:
        """Download objects that are missing locally or differ in size.
        Never deletes local files. Returns (downloaded_keys, skipped_count)."""
        library = library.expanduser()
        downloaded: list[str] = []
        skipped = 0
        for key, size in self.remote_objects().items():
            rel = key[len(self.prefix):]
            if not rel:
                continue
            dest = library / rel
            if dest.exists() and dest.stat().st_size == size:
                skipped += 1
                continue
            if not dry_run:
                dest.parent.mkdir(parents=True, exist_ok=True)
                self.client.download_file(self.bucket, key, str(dest))
            downloaded.append(key)
        return downloaded, skipped

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

    def publish(self, expires_hours: int = 144) -> str:
        """Build a static HTML index of presigned video links and upload it.

        Returns the presigned URL for the index page itself.
        expires_hours: lifetime for all links (default 144h = 6 days; AWS max is 7 days).
        """
        expires_sec = expires_hours * 3600
        keys = sorted(k for k in self.remote_objects() if _VIDEO_RE.search(k))

        # Group keys by first two path components after prefix (Series/Season or Movies).
        from collections import defaultdict
        groups: dict[str, list[str]] = defaultdict(list)
        for key in keys:
            rel = key[len(self.prefix):]
            parts = rel.split("/")
            group = "/".join(parts[:2]) if len(parts) > 2 else parts[0]
            groups[group].append(key)

        rows: list[str] = []
        for group in sorted(groups):
            rows.append(f"<h2>{html.escape(group)}</h2><ul>")
            for key in sorted(groups[group]):
                name = html.escape(key.rsplit("/", 1)[-1])
                url = self.presign(key, expires_seconds=expires_sec)
                rows.append(f'<li><a href="{url}">{name}</a></li>')
            rows.append("</ul>")

        body = (
            "<!DOCTYPE html><html><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>MediaCloud</title>"
            "<style>body{font-family:sans-serif;margin:1.5em;background:#111;color:#eee}"
            "h2{color:#aaa;border-bottom:1px solid #333;padding-bottom:.3em}"
            "a{color:#7ec8ff;text-decoration:none;font-size:1em;line-height:2em}"
            "li{list-style:none}ul{padding:0 0 0 1em}</style></head>"
            f"<body><h1>MediaCloud</h1>{''.join(rows)}</body></html>"
        )

        index_key = self.prefix + "_index.html"
        import io
        self.client.upload_fileobj(
            io.BytesIO(body.encode()),
            self.bucket,
            index_key,
            ExtraArgs={"ContentType": "text/html; charset=utf-8"},
        )
        return self.presign(index_key, expires_seconds=expires_sec)
