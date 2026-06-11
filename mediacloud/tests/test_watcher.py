import os

from mediacloud.matcher import SeriesIndex
from mediacloud.organizer import organize, seed_from_library
from mediacloud.watcher import FolderWatcher


def test_growing_file_not_reported_until_stable(tmp_path):
    src = tmp_path / "downloads"
    src.mkdir()
    f = src / "Show.S01E01.mkv"
    watcher = FolderWatcher(sources=[src])

    f.write_bytes(b"a" * 100)
    assert watcher.scan() == set()  # first sighting, not yet stable

    f.write_bytes(b"a" * 200)  # still downloading
    os.utime(f, (1000, 1000))
    assert watcher.scan() == set()  # changed since last scan

    assert watcher.scan() == {f}  # identical across two scans: settled
    assert watcher.scan() == set()  # reported only once


def test_deleted_then_readded_file_starts_fresh(tmp_path):
    src = tmp_path / "downloads"
    src.mkdir()
    f = src / "Show.S01E01.mkv"
    watcher = FolderWatcher(sources=[src])

    f.write_bytes(b"a")
    watcher.scan()
    assert watcher.scan() == {f}

    f.unlink()
    assert watcher.scan() == set()

    f.write_bytes(b"b")
    watcher.scan()
    assert watcher.scan() == {f}  # re-added file is reported again


def test_non_video_files_ignored(tmp_path):
    src = tmp_path / "downloads"
    src.mkdir()
    (src / "Show.S01E01.mkv.part").write_bytes(b"a")
    (src / "notes.txt").write_bytes(b"a")
    watcher = FolderWatcher(sources=[src])
    watcher.scan()
    assert watcher.scan() == set()


def test_organize_only_filter(tmp_path):
    src = tmp_path / "downloads"
    src.mkdir()
    a = src / "Show.S01E01.mkv"
    b = src / "Show.S01E02.mkv"
    a.write_bytes(b"a")
    b.write_bytes(b"b")
    library = tmp_path / "library"

    report = organize([src], library, SeriesIndex(), only={a})
    assert len(report.linked) == 1
    assert report.linked[0].source == a


def test_library_folders_pin_canonical_names(tmp_path):
    library = tmp_path / "library"
    (library / "Jujutsu Kaisen" / "Season 01").mkdir(parents=True)

    index = SeriesIndex()
    seed_from_library(library, index)
    # A shorter variant would normally replace the canonical; a pinned
    # library folder must win instead.
    assert index.resolve("Jujutsu") == "Jujutsu Kaisen"

    src = tmp_path / "downloads"
    src.mkdir()
    (src / "[Grp] Jujutsu - 26 (1080p).mkv").write_bytes(b"a")
    organize([src], library, SeriesIndex())
    dest = library / "Jujutsu Kaisen" / "Season 01" / "Jujutsu Kaisen - S01E026.mkv"
    assert dest.exists()
    assert not (library / "Jujutsu").exists()
