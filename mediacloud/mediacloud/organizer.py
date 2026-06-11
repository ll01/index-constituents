"""Scan source folders and hardlink videos into a clean library tree.

Hardlinks mean zero extra disk space and the original files keep seeding;
falls back to copying when source and library are on different filesystems.
"""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .matcher import SeriesIndex, is_video, parse

_UNSAFE_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _safe(name: str) -> str:
    return _UNSAFE_RE.sub("", name).strip(" .") or "Unknown"


@dataclass
class PlannedFile:
    source: Path
    dest: Path
    series: str | None  # None for movies / unmatched


@dataclass
class Report:
    linked: list[PlannedFile] = field(default_factory=list)
    copied: list[PlannedFile] = field(default_factory=list)
    skipped: list[PlannedFile] = field(default_factory=list)  # dest already exists
    planned: list[PlannedFile] = field(default_factory=list)  # dry-run only


def plan(sources: list[Path], library: Path, index: SeriesIndex) -> list[PlannedFile]:
    found: list[Path] = []
    for src_dir in sources:
        src_dir = src_dir.expanduser()
        if not src_dir.is_dir():
            continue
        found.extend(
            p for p in sorted(src_dir.rglob("*")) if p.is_file() and is_video(p.name)
        )

    parsed = [(path, parse(path.name)) for path in found]
    # First pass settles canonical series names (a later, shorter variant can
    # replace an earlier long one); second pass assigns stable destinations.
    for _, media in parsed:
        if media.is_episode:
            index.resolve(media.title)

    out: list[PlannedFile] = []
    for path, media in parsed:
        ext = path.suffix.lower()
        if media.is_episode:
            series = index.resolve(media.title)
            season = media.season or 1
            dest = (
                library
                / _safe(series)
                / f"Season {season:02d}"
                / f"{_safe(series)} - S{season:02d}E{media.episode:03d}{ext}"
            )
            out.append(PlannedFile(source=path, dest=dest, series=series))
        else:
            title = media.title + (f" ({media.year})" if media.year else "")
            dest = library / "Movies" / f"{_safe(title)}{ext}"
            out.append(PlannedFile(source=path, dest=dest, series=None))
    return out


def organize(sources: list[Path], library: Path, index: SeriesIndex, dry_run: bool = False) -> Report:
    library = library.expanduser()
    report = Report()
    for item in plan(sources, library, index):
        if item.dest.exists():
            report.skipped.append(item)
            continue
        if dry_run:
            report.planned.append(item)
            continue
        item.dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(item.source, item.dest)
            report.linked.append(item)
        except OSError:  # cross-device or filesystem without hardlink support
            shutil.copy2(item.source, item.dest)
            report.copied.append(item)
    return report
