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


def test_folder_name_supplies_missing_season(tmp_path):
    src = tmp_path / "downloads"
    folder = src / "jjk s03"
    folder.mkdir(parents=True)
    make(folder, "[DubZoku] Jujutsu Kaisen - 05 [Dual-Audio].mkv")
    # Explicit season in the filename must beat the folder hint.
    make(folder, "Jujutsu.Kaisen.S02E01.mkv")
    library = tmp_path / "library"

    organize([src], library, SeriesIndex())
    assert (library / "Jujutsu Kaisen" / "Season 03" / "Jujutsu Kaisen - S03E005.mkv").exists()
    assert (library / "Jujutsu Kaisen" / "Season 02" / "Jujutsu Kaisen - S02E001.mkv").exists()


def test_v2_release_replaces_v1(tmp_path):
    src = tmp_path / "downloads"
    src.mkdir()
    v1 = src / "[Grp] Jujutsu Kaisen - S03E10 (1080p).mkv"
    v1.write_bytes(b"v1 with glitched subs")
    library = tmp_path / "library"
    organize([src], library, SeriesIndex())
    dest = library / "Jujutsu Kaisen" / "Season 03" / "Jujutsu Kaisen - S03E010.mkv"
    assert dest.read_bytes() == b"v1 with glitched subs"

    v2 = src / "[DubZoku] Jujutsu Kaisen - S03E10 v2 (WEB 1080p).mkv"
    v2.write_bytes(b"v2 fixed")
    report = organize([src], library, SeriesIndex())
    assert len(report.upgraded) == 1
    assert dest.read_bytes() == b"v2 fixed"
    assert dest.stat().st_ino == v2.stat().st_ino

    # Re-run: the v2 already in place is recognized, nothing churns.
    report = organize([src], library, SeriesIndex())
    assert report.upgraded == [] and len(report.skipped) == 2


def test_plain_duplicate_still_skipped(tmp_path):
    src = tmp_path / "downloads"
    src.mkdir()
    (src / "[Yameii] Jujutsu Kaisen - S02E01 [720p].mkv").write_bytes(b"original")
    (src / "[Yameii] Jujutsu Kaisen - S02E01 [720p] - Copy.mkv").write_bytes(b"copy")
    library = tmp_path / "library"
    report = organize([src], library, SeriesIndex())
    assert len(report.linked) == 1 and len(report.skipped) == 1


def test_dry_run_touches_nothing(tmp_path):
    src = tmp_path / "downloads"
    src.mkdir()
    make(src, "Show.S01E01.mkv")
    library = tmp_path / "library"

    report = organize([src], library, SeriesIndex(), dry_run=True)
    assert len(report.planned) == 1
    assert not library.exists()
