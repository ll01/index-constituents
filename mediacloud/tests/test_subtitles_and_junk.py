from pathlib import Path

import pytest

from mediacloud.matcher import is_junk, is_subtitle, parse, subtitle_lang_ext
from mediacloud.organizer import SeriesIndex, organize


# --- subtitle detection and parsing ---

@pytest.mark.parametrize("name,expected", [
    ("Show.S01E01.en.srt", True),
    ("Show.S01E01.srt", True),
    ("[Grp] Jujutsu Kaisen - 25 (1080p).ass", True),
    ("Show.S01E01.mkv", False),
    ("notes.txt", False),
])
def test_is_subtitle(name, expected):
    assert is_subtitle(name) == expected


@pytest.mark.parametrize("name,lang,ext", [
    ("Show.S01E01.en.srt", ".en", ".srt"),
    ("Show.S01E01.jpn.ass", ".jpn", ".ass"),
    ("Show.S01E01.srt", "", ".srt"),
    ("[Grp] Show - 05 (1080p).ass", "", ".ass"),
])
def test_subtitle_lang_ext(name, lang, ext):
    assert subtitle_lang_ext(name) == (lang, ext)


@pytest.mark.parametrize("name,season,episode", [
    ("[SubsPlease] Jujutsu Kaisen - 25 (1080p).en.srt", 1, 25),
    ("[Yameii] Jujutsu Kaisen - S02E01 [English Dub].srt", 2, 1),
    ("Jujutsu.Kaisen.S03E10.v2.ass", 3, 10),
])
def test_parse_subtitle_filenames(name, season, episode):
    m = parse(name)
    assert m.title == "Jujutsu Kaisen"
    assert (m.season, m.episode) == (season, episode)


# --- junk filtering ---

@pytest.mark.parametrize("path,expected", [
    (Path("downloads/sample.mkv"), True),
    (Path("downloads/ShowTitle - NCOP.mkv"), True),
    (Path("downloads/Show NCED2.mkv"), True),  # "NCED" with a number after
    (Path("downloads/Creditless OP.mkv"), True),
    (Path("downloads/Extras/featurette.mkv"), True),
    (Path("downloads/[Grp] Jujutsu Kaisen - S03E10 (1080p).mkv"), False),
    (Path("downloads/Jujutsu Kaisen 0 (2021).mkv"), False),
])
def test_is_junk(path, expected):
    assert is_junk(path) == expected


# --- organizer handles subtitles and ignores junk ---

def make(p: Path, name: str) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    f = p / name
    f.write_bytes(b"data")
    return f


def test_subtitle_colocated_with_video(tmp_path):
    src = tmp_path / "downloads"
    make(src, "[SubsPlease] Jujutsu Kaisen - S02E01 (1080p) [A1B2].mkv")
    make(src, "[SubsPlease] Jujutsu Kaisen - S02E01 (1080p) [A1B2].en.srt")
    make(src, "[SubsPlease] Jujutsu Kaisen - S02E01 (1080p) [A1B2].jpn.ass")
    library = tmp_path / "library"

    organize([src], library, SeriesIndex())
    season = library / "Jujutsu Kaisen" / "Season 02"
    assert (season / "Jujutsu Kaisen - S02E001.mkv").exists()
    assert (season / "Jujutsu Kaisen - S02E001.en.srt").exists()
    assert (season / "Jujutsu Kaisen - S02E001.jpn.ass").exists()


def test_junk_files_not_organized(tmp_path):
    src = tmp_path / "downloads"
    make(src, "[Grp] Jujutsu Kaisen - S03E10 (1080p).mkv")
    make(src, "sample.mkv")
    make(src, "Jujutsu Kaisen NCOP.mkv")
    (src / "Extras").mkdir(exist_ok=True)
    make(src / "Extras", "featurette.mkv")
    library = tmp_path / "library"

    report = organize([src], library, SeriesIndex())
    assert len(report.linked) == 1
    assert report.linked[0].source.name == "[Grp] Jujutsu Kaisen - S03E10 (1080p).mkv"


def test_publish_generates_html_and_returns_url(tmp_path):
    pytest.importorskip("boto3")
    moto = pytest.importorskip("moto")
    import boto3
    from mediacloud.s3sync import S3Sync

    import os
    os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
    os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
    os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")

    with moto.mock_aws():
        boto3.client("s3").create_bucket(Bucket="media")
        s3 = S3Sync(bucket="media", prefix="library")

        lib = tmp_path / "library"
        ep = lib / "Jujutsu Kaisen" / "Season 01"
        ep.mkdir(parents=True)
        (ep / "Jujutsu Kaisen - S01E025.mkv").write_bytes(b"x" * 100)
        s3.sync_up(lib)

        url = s3.publish(expires_hours=24)
        assert "X-Amz-Signature" in url or "Signature" in url

        # The index HTML must be in the bucket and link to the episode.
        index_key = "library/_index.html"
        obj = boto3.client("s3").get_object(Bucket="media", Key=index_key)
        content = obj["Body"].read().decode()
        assert "Jujutsu Kaisen" in content
        assert "S01E025" in content
