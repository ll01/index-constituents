from pathlib import Path

from mediacloud.matcher import SeriesIndex
from mediacloud.organizer import organize


def make(p: Path, name: str) -> Path:
    f = p / name
    f.write_bytes(b"fake video data")
    return f


def test_organize_builds_clean_tree(tmp_path):
    src = tmp_path / "downloads"
    src.mkdir()
    make(src, "[SubsPlease] Jujutsu Kaisen - 25 (1080p) [ABCD].mkv")
    make(src, "Jujutsu.Kaisen.S02E01.1080p.WEB.x264-GRP.mkv")
    make(src, "Spirited.Away.2001.1080p.BluRay.mkv")
    make(src, "notes.txt")  # ignored

    library = tmp_path / "library"
    report = organize([src], library, SeriesIndex())

    assert len(report.linked) == 3
    assert (library / "Jujutsu Kaisen" / "Season 01" / "Jujutsu Kaisen - S01E025.mkv").exists()
    assert (library / "Jujutsu Kaisen" / "Season 02" / "Jujutsu Kaisen - S02E001.mkv").exists()
    assert (library / "Movies" / "Spirited Away (2001).mkv").exists()
    # Hardlink: same inode, no extra space, original keeps seeding.
    src_file = src / "Jujutsu.Kaisen.S02E01.1080p.WEB.x264-GRP.mkv"
    dest_file = library / "Jujutsu Kaisen" / "Season 02" / "Jujutsu Kaisen - S02E001.mkv"
    assert src_file.stat().st_ino == dest_file.stat().st_ino


def test_organize_idempotent(tmp_path):
    src = tmp_path / "downloads"
    src.mkdir()
    make(src, "Show.S01E01.mkv")
    library = tmp_path / "library"

    first = organize([src], library, SeriesIndex())
    second = organize([src], library, SeriesIndex())
    assert len(first.linked) == 1
    assert len(second.linked) == 0
    assert len(second.skipped) == 1


def test_dry_run_touches_nothing(tmp_path):
    src = tmp_path / "downloads"
    src.mkdir()
    make(src, "Show.S01E01.mkv")
    library = tmp_path / "library"

    report = organize([src], library, SeriesIndex(), dry_run=True)
    assert len(report.planned) == 1
    assert not library.exists()
