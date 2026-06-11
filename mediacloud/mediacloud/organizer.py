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

from .matcher import SeriesIndex, is_junk, is_subtitle, is_video, parse, season_hint, subtitle_lang_ext

_UNSAFE_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _safe(name: str) -> str:
    return _UNSAFE_RE.sub("", name).strip(" .") or "Unknown"


@dataclass
class PlannedFile:
    source: Path
    dest: Path
    series: str | None  # None for movies / unmatched
    version: int = 1


@dataclass
class Report:
    linked: list[PlannedFile] = field(default_factory=list)
    copied: list[PlannedFile] = field(default_factory=list)
    upgraded: list[PlannedFile] = field(default_factory=list)  # v2 replaced a v1
    skipped: list[PlannedFile] = field(default_factory=list)  # dest already exists
    planned: list[PlannedFile] = field(default_factory=list)  # dry-run only


def _same_content(a: Path, b: Path) -> bool:
    """True if the two paths are the same file (hardlink) or a faithful copy
    (copy2 preserves size and mtime)."""
    try:
        if a.samefile(b):
            return True
        sa, sb = a.stat(), b.stat()
        return sa.st_size == sb.st_size and sa.st_mtime == sb.st_mtime
    except OSError:
        return False


def seed_from_library(library: Path, index: SeriesIndex) -> None:
    """Pin existing series folders so new files keep matching them."""
    library = library.expanduser()
    if library.is_dir():
        index.seed(sorted(
            p.name for p in library.iterdir() if p.is_dir() and p.name != "Movies"
        ))


def plan(sources: list[Path], library: Path, index: SeriesIndex,
         only: set[Path] | None = None) -> list[PlannedFile]:
    found: list[Path] = []
    for src_dir in sources:
        src_dir = src_dir.expanduser()
        if not src_dir.is_dir():
            continue
        found.extend(
            p for p in sorted(src_dir.rglob("*"))
            if p.is_file()
            and (is_video(p.name) or is_subtitle(p.name))
            and not is_junk(p)
            and (only is None or p in only)
        )

    parsed = [(path, parse(path.name)) for path in found]
    # First pass settles canonical series names (a later, shorter variant can
    # replace an earlier long one); second pass assigns stable destinations.
    for _, media in parsed:
        if media.is_episode:
            index.resolve(media.title)

    out: list[PlannedFile] = []
    for path, media in parsed:
        # Subtitle files keep their language tag + real extension (.en.srt).
        if is_subtitle(path.name):
            lang, sub_ext = subtitle_lang_ext(path.name)
            file_ext = lang + sub_ext
        else:
            file_ext = path.suffix.lower()

        if media.is_episode:
            series = index.resolve(media.title)
            season = media.season or 1
            if not media.explicit_season:
                season = season_hint(path.parent.name) or season
            dest = (
                library
                / _safe(series)
                / f"Season {season:02d}"
                / f"{_safe(series)} - S{season:02d}E{media.episode:03d}{file_ext}"
            )
            out.append(PlannedFile(source=path, dest=dest, series=series,
                                   version=media.version))
        else:
            title = media.title + (f" ({media.year})" if media.year else "")
            dest = library / "Movies" / f"{_safe(title)}{file_ext}"
            out.append(PlannedFile(source=path, dest=dest, series=None,
                                   version=media.version))
    return out


def organize(sources: list[Path], library: Path, index: SeriesIndex,
             dry_run: bool = False, only: set[Path] | None = None) -> Report:
    library = library.expanduser()
    seed_from_library(library, index)
    report = Report()
    for item in plan(sources, library, index, only=only):
        upgrade = False
        if item.dest.exists():
            # A v2+ release replaces whatever is there — unless that is
            # already this very file (keeps re-runs idempotent).
            upgrade = item.version > 1 and not _same_content(item.source, item.dest)
            if not upgrade:
                report.skipped.append(item)
                continue
        if dry_run:
            report.planned.append(item)
            continue
        item.dest.parent.mkdir(parents=True, exist_ok=True)
        if upgrade:
            item.dest.unlink()
        try:
            os.link(item.source, item.dest)
        except OSError:  # cross-device or filesystem without hardlink support
            shutil.copy2(item.source, item.dest)
            report.upgraded.append(item) if upgrade else report.copied.append(item)
            continue
        report.upgraded.append(item) if upgrade else report.linked.append(item)
    return report
