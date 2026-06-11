"""Watch source folders by polling, client-agnostic.

No inotify, no torrent-client hooks: any program may drop files in. A file is
only considered ready once its size and mtime have been identical across
consecutive scans, so half-written downloads are never picked up.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .matcher import is_junk, is_subtitle, is_video


@dataclass
class FolderWatcher:
    sources: list[Path]
    # File must look identical across this many consecutive scans.
    stable_scans: int = 2
    _history: dict[Path, tuple[int, float]] = field(default_factory=dict)
    _stable: dict[Path, int] = field(default_factory=dict)
    _reported: set[Path] = field(default_factory=set)

    def scan(self) -> set[Path]:
        """One polling tick. Returns files newly settled since the last tick."""
        current: dict[Path, tuple[int, float]] = {}
        for src in self.sources:
            src = src.expanduser()
            if not src.is_dir():
                continue
            for path in src.rglob("*"):
                if not (path.is_file() and (is_video(path.name) or is_subtitle(path.name))):
                    continue
                if is_junk(path):
                    continue
                try:
                    st = path.stat()
                except OSError:  # vanished mid-scan
                    continue
                current[path] = (st.st_size, st.st_mtime)

        ready: set[Path] = set()
        for path, sig in current.items():
            if path in self._reported:
                continue
            if self._history.get(path) == sig:
                self._stable[path] = self._stable.get(path, 1) + 1
            else:
                self._stable[path] = 1
            if self._stable[path] >= self.stable_scans:
                ready.add(path)
                self._reported.add(path)

        # Forget files that disappeared so re-added ones start fresh.
        gone = set(self._history) - set(current)
        for path in gone:
            self._stable.pop(path, None)
            self._reported.discard(path)

        self._history = current
        return ready
