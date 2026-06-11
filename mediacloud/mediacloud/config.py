"""TOML config loading. Looks for ./mediacloud.toml, then ~/.config/mediacloud/config.toml."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_PATHS = [
    Path("mediacloud.toml"),
    Path("~/.config/mediacloud/config.toml").expanduser(),
]

EXAMPLE = """\
# MediaCloud configuration

[library]
# Where the clean, organized library lives.
root = "~/MediaCloud/Library"
# Folders to scan for incoming video files (torrents, downloads...).
sources = [
    "~/Downloads",
]

[matcher]
# 0..1 — how similar two parsed titles must be to count as the same series.
threshold = 0.82
# Force specific names to map to a canonical series.
[matcher.aliases]
# "JJK" = "Jujutsu Kaisen"

[s3]
# Bucket on any S3-compatible service (AWS, MinIO, R2, B2...).
bucket = ""
# Leave empty for AWS; set for MinIO/R2/B2, e.g. "http://192.168.1.10:9000"
endpoint_url = ""
region = ""
# Key prefix inside the bucket.
prefix = "library"
# Lifetime of presigned links in hours (AWS/R2/B2 cap is 7 days = 168h).
publish_expires = 144
# Credentials are read from the standard AWS chain:
#   AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY env vars, or ~/.aws/credentials

[serve]
port = 8080
# Where files uploaded from the phone land. Defaults to the first
# [library] source, so `mediacloud watch` organizes them automatically.
inbox = ""
"""


@dataclass
class Config:
    library_root: Path = Path("~/MediaCloud/Library")
    sources: list[Path] = field(default_factory=list)
    threshold: float = 0.82
    aliases: dict[str, str] = field(default_factory=dict)
    s3_bucket: str = ""
    s3_endpoint: str = ""
    s3_region: str = ""
    s3_prefix: str = "library"
    serve_port: int = 8080
    serve_inbox: str = ""
    publish_expires: int = 144  # hours; 144h = 6 days (AWS S3 cap is 7 days)
    path: Path | None = None

    @property
    def inbox(self) -> Path | None:
        if self.serve_inbox:
            return Path(self.serve_inbox)
        return self.sources[0] if self.sources else None


def load(explicit: Path | None = None) -> Config:
    candidates = [explicit] if explicit else DEFAULT_PATHS
    for candidate in candidates:
        if candidate and candidate.exists():
            data = tomllib.loads(candidate.read_text())
            lib = data.get("library", {})
            matcher = data.get("matcher", {})
            s3 = data.get("s3", {})
            return Config(
                library_root=Path(lib.get("root", "~/MediaCloud/Library")),
                sources=[Path(s) for s in lib.get("sources", [])],
                threshold=float(matcher.get("threshold", 0.82)),
                aliases=dict(matcher.get("aliases", {})),
                s3_bucket=s3.get("bucket", ""),
                s3_endpoint=s3.get("endpoint_url", ""),
                s3_region=s3.get("region", ""),
                s3_prefix=s3.get("prefix", "library"),
                serve_port=int(data.get("serve", {}).get("port", 8080)),
                serve_inbox=data.get("serve", {}).get("inbox", ""),
                publish_expires=int(data.get("s3", {}).get("publish_expires", 144)),
                path=candidate,
            )
    if explicit:
        raise SystemExit(f"Config file not found: {explicit}")
    raise SystemExit(
        "No config found. Run `mediacloud init` to create mediacloud.toml, then edit it."
    )


def write_example(dest: Path = Path("mediacloud.toml")) -> Path:
    if dest.exists():
        raise SystemExit(f"{dest} already exists; not overwriting.")
    dest.write_text(EXAMPLE)
    return dest
