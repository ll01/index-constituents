import pytest

from mediacloud.matcher import SeriesIndex, is_video, parse


@pytest.mark.parametrize(
    "name,title,season,episode",
    [
        ("[SubsPlease] Jujutsu Kaisen - 25 (1080p) [ABCD1234].mkv", "Jujutsu Kaisen", 1, 25),
        ("Jujutsu.Kaisen.S02E01.1080p.WEB.x264-GROUP.mkv", "Jujutsu Kaisen", 2, 1),
        ("[ASW] Jujutsu Kaisen 2nd Season - 03 [1080p HEVC].mkv", "Jujutsu Kaisen", 2, 3),
        ("Jujutsu Kaisen 1x05 HEVC.mp4", "Jujutsu Kaisen", 1, 5),
        ("jujutsu_kaisen_episode_12_720p.mkv", "Jujutsu Kaisen", 1, 12),
        ("Breaking.Bad.S05E14.Ozymandias.1080p.BluRay.x265.mkv", "Breaking Bad", 5, 14),
        ("The Office (US) - 3x07.avi", "The Office", 3, 7),
        ("[Erai-raws] Frieren - Sousou no Frieren - 17 [1080p][Multiple Subtitle].mkv",
         "Frieren", 1, 17),
        ("Chainsaw Man Season 1 - 08 [Dual Audio].mkv", "Chainsaw Man", 1, 8),
    ],
)
def test_parse_episodes(name, title, season, episode):
    media = parse(name)
    assert media.title == title
    assert media.season == season
    assert media.episode == episode


@pytest.mark.parametrize(
    "name,title,season,episode",
    [
        # Episode marker first, title after.
        ("s03e01 DW.mkv", "Dw", 3, 1),
        ("S01E05 Doctor Who.mkv", "Doctor Who", 1, 5),
    ],
)
def test_parse_title_after_marker(name, title, season, episode):
    media = parse(name)
    assert (media.title, media.season, media.episode) == (title, season, episode)


def test_marker_first_files_group_via_alias():
    index = SeriesIndex(aliases={"DW": "Doctor Who"})
    a = index.resolve(parse("s03e01 DW.mkv").title)
    b = index.resolve(parse("S01E05 Doctor Who.mkv").title)
    assert a == b == "Doctor Who"


def test_parse_movie():
    media = parse("Spirited.Away.2001.1080p.BluRay.x264.mkv")
    assert media.title == "Spirited Away"
    assert media.year == 2001
    assert not media.is_episode


def test_is_video():
    assert is_video("show.mkv")
    assert is_video("SHOW.MP4")
    assert not is_video("notes.txt")
    assert not is_video("noext")


class TestSeriesIndex:
    def test_groups_slightly_different_names(self):
        # The core "torrents from different groups land together" requirement.
        index = SeriesIndex()
        a = index.resolve(parse("[SubsPlease] Jujutsu Kaisen - 25 (1080p).mkv").title)
        b = index.resolve(parse("Jujutsu.Kaisen.S02E01.1080p.WEB.x264-GRP.mkv").title)
        c = index.resolve(parse("[ASW] Jujutsu Kaisen 2nd Season - 03 [1080p].mkv").title)
        assert a == b == c

    def test_subtitle_variants_merge(self):
        index = SeriesIndex()
        index.resolve("Frieren Beyond Journeys End")
        index.resolve("Frieren")
        # After both are seen, the shorter form wins as canonical for both.
        assert index.resolve("Frieren Beyond Journeys End") == "Frieren"
        assert index.resolve("Frieren") == "Frieren"

    def test_distinct_series_stay_apart(self):
        index = SeriesIndex()
        a = index.resolve("Jujutsu Kaisen")
        b = index.resolve("Chainsaw Man")
        c = index.resolve("Breaking Bad")
        assert len({a, b, c}) == 3

    def test_aliases(self):
        index = SeriesIndex(aliases={"JJK": "Jujutsu Kaisen"})
        assert index.resolve("JJK") == "Jujutsu Kaisen"
        assert index.resolve("Jujutsu Kaisen") == "Jujutsu Kaisen"

    def test_the_prefix_ignored(self):
        index = SeriesIndex()
        a = index.resolve("The Office")
        b = index.resolve("Office")
        assert a == b
