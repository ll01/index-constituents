"""Parse messy release/torrent filenames and fuzzy-group them into series.

Stdlib only. Handles names like:
    [SubsPlease] Jujutsu Kaisen - 25 (1080p) [ABCD1234].mkv
    Jujutsu.Kaisen.S02E01.1080p.WEB.x264-GROUP.mkv
    [ASW] Jujutsu Kaisen 2nd Season - 03 [1080p HEVC].mkv
    Jujutsu Kaisen 1x05 HEVC.mp4
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

VIDEO_EXTS = {
    ".mkv", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".ts", ".mpg", ".mpeg",
}

# Tokens that are release metadata, not part of a title.
RELEASE_TAGS = {
    "480p", "720p", "1080p", "2160p", "4k", "8k", "uhd", "hd", "sd",
    "x264", "x265", "h264", "h265", "h.264", "h.265", "hevc", "avc", "av1", "xvid", "divx",
    "aac", "ac3", "eac3", "dts", "flac", "opus", "mp3", "dd5", "ddp5", "atmos", "truehd",
    "web", "webrip", "web-dl", "webdl", "bluray", "blu-ray", "bdrip", "brrip", "dvdrip",
    "hdtv", "hdrip", "remux", "hdr", "hdr10", "dv", "dolby", "vision", "sdr",
    "10bit", "8bit", "hi10p", "dual", "audio", "multi", "sub", "subbed", "dubbed", "dub",
    "uncensored", "remastered", "extended", "proper", "repack", "internal", "complete",
    "batch", "season", "amzn", "nf", "dsnp", "hulu", "cr", "funi",
}

_BRACKETS_RE = re.compile(r"\[[^\]]*\]|\([^)]*\)|\{[^}]*\}")
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
_ORDINAL_SEASON_RE = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)\s+season\b", re.IGNORECASE)
_SEASON_WORD_RE = re.compile(r"\bseason\s+(\d{1,2})\b", re.IGNORECASE)

# Episode markers, in priority order. Each returns (season or None, episode).
_EP_PATTERNS = [
    # S01E02, s1e2, S01E02-E03 (take first episode)
    re.compile(r"\bS(\d{1,2})\s?E(\d{1,3})\b", re.IGNORECASE),
    # 1x02
    re.compile(r"\b(\d{1,2})x(\d{2,3})\b", re.IGNORECASE),
    # Episode 5 / Ep 5 / Ep.5 / E05
    re.compile(r"\b(?:episode|ep\.?|e)\s?()(\d{1,3})\b", re.IGNORECASE),
    # anime style: "Title - 05" (separator dash then bare number at/near the end)
    re.compile(r"\s-\s()(\d{1,3})(?:\s|$)"),
]


@dataclass
class ParsedMedia:
    raw_name: str
    title: str
    season: int | None = None
    episode: int | None = None
    year: int | None = None

    @property
    def is_episode(self) -> bool:
        return self.episode is not None


def is_video(filename: str) -> bool:
    return filename[filename.rfind("."):].lower() in VIDEO_EXTS if "." in filename else False


def _clean_title(text: str) -> str:
    words = []
    for word in text.split():
        if word.lower().strip(".-") in RELEASE_TAGS:
            break  # release tags mark the end of the title
        words.append(word)
    title = " ".join(words).strip(" -.")
    # Title-case fully-lower or fully-upper titles, leave mixed case alone.
    if title and (title.islower() or title.isupper()):
        title = title.title()
    return title


def parse(filename: str) -> ParsedMedia:
    """Best-effort parse of a single release filename."""
    stem = filename.rsplit("/", 1)[-1]
    if "." in stem and stem[stem.rfind("."):].lower() in VIDEO_EXTS:
        stem = stem[: stem.rfind(".")]

    raw = stem
    # Bracketed chunks are group names / hashes / quality tags: drop them.
    stem = _BRACKETS_RE.sub(" ", stem)
    # Dots and underscores are word separators in scene names.
    if "." in stem or "_" in stem:
        stem = re.sub(r"[._]+", " ", stem)
    stem = re.sub(r"\s+", " ", stem).strip()

    season: int | None = None
    episode: int | None = None

    # "2nd Season" / "Season 2" anywhere in the name sets the season.
    m = _ORDINAL_SEASON_RE.search(stem) or _SEASON_WORD_RE.search(stem)
    if m:
        season = int(m.group(1))
        stem = (stem[: m.start()] + " " + stem[m.end():]).strip()

    title_end = len(stem)
    for pattern in _EP_PATTERNS:
        m = pattern.search(stem)
        if m:
            if m.group(1):
                season = int(m.group(1))
            episode = int(m.group(2))
            title_end = m.start()
            break

    year = None
    m = _YEAR_RE.search(stem[:title_end])
    if m:
        year = int(m.group(0))
        title_end = min(title_end, m.start())

    title = _clean_title(stem[:title_end])
    if not title:  # everything got stripped; fall back to the raw stem
        title = _clean_title(_BRACKETS_RE.sub(" ", raw)) or raw
    # Dual titles ("Frieren - Sousou no Frieren"): keep the first form.
    if " - " in title:
        first = title.split(" - ")[0].strip()
        if first:
            title = first

    if episode is not None and season is None:
        season = 1

    return ParsedMedia(raw_name=filename, title=title, season=season, episode=episode, year=year)


def _normalize(title: str) -> str:
    t = title.lower()
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    t = re.sub(r"^(the|a|an)\s+", "", t)
    return re.sub(r"\s+", " ", t).strip()


def similarity(a: str, b: str) -> float:
    """0..1 similarity between two titles, tolerant of extra subtitle tokens."""
    na, nb = _normalize(a), _normalize(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    ta, tb = set(na.split()), set(nb.split())
    # One title's tokens contained in the other: "Jujutsu Kaisen" vs
    # "Jujutsu Kaisen Shibuya Incident" should land in the same series.
    if ta <= tb or tb <= ta:
        return 0.95
    return difflib.SequenceMatcher(None, na, nb).ratio()


@dataclass
class SeriesIndex:
    """Groups slightly-different titles under one canonical series name."""

    threshold: float = 0.82
    aliases: dict[str, str] = field(default_factory=dict)
    _canonical: list[str] = field(default_factory=list)
    _pinned: set[str] = field(default_factory=set)

    def seed(self, names: list[str]) -> None:
        """Register existing library folder names as pinned canonicals, so new
        files keep landing in established folders across runs."""
        for name in names:
            self._pinned.add(self._register(name))

    def resolve(self, title: str) -> str:
        for alias, target in self.aliases.items():
            if _normalize(alias) == _normalize(title):
                return self._register(target)
        best, best_score = None, 0.0
        for known in self._canonical:
            score = similarity(title, known)
            if score > best_score:
                best, best_score = known, score
        if best is not None and best_score >= self.threshold:
            # Prefer the shorter name as canonical ("Jujutsu Kaisen" over
            # "Jujutsu Kaisen Shibuya Incident Arc") — unless the existing
            # name is pinned to a real library folder.
            if best not in self._pinned and len(_normalize(title)) < len(_normalize(best)):
                self._canonical[self._canonical.index(best)] = title
                return title
            return best
        return self._register(title)

    def _register(self, title: str) -> str:
        for known in self._canonical:
            if _normalize(known) == _normalize(title):
                return known
        self._canonical.append(title)
        return title
