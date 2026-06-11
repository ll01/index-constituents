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
# Folders to scan for incoming video files (torrents, downloads, OneDrive...).
sources = [
    "~/Downloads",
]

[matcher]
# 0..1 — how similar two parsed titles must be to count as the same series.
threshold = 0.82
# Force specific names to map to a canonical series.
[matcher.aliases]
# "JJK" = "Jujutsu Kaisen"

# ── S3 is entirely optional ──────────────────────────────────────────────────
# If you already have OneDrive/Google Drive/Dropbox, just add your sync folder
# to [library] sources above instead — no S3 setup needed.
# Only fill this in if you want S3-specific features: presigned URLs, publish,
# sync/pull commands. Works with AWS, Cloudflare R2, Backblaze B2, MinIO.
# [s3]
# bucket = "my-media"
# endpoint_url = ""   # leave empty for AWS; R2: "https://<id>.r2.cloudflarestorage.com"
# region = ""
# prefix = "library"
# publish_expires = 144   # presigned link lifetime in hours (max 168 = 7 days)
# Credentials: AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY env vars, or ~/.aws/credentials
# ─────────────────────────────────────────────────────────────────────────────

[serve]
port = 8080
# Where files uploaded from the phone land. Defaults to the first source folder.
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
    publish_expires: int = 144
    path: Path | None = None

    @property
    def has_s3(self) -> bool:
        return bool(self.s3_bucket)

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
