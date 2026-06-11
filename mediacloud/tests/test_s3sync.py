import pytest

boto3 = pytest.importorskip("boto3")
moto = pytest.importorskip("moto")

from mediacloud.s3sync import S3Sync  # noqa: E402


@pytest.fixture()
def bucket(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    with moto.mock_aws():
        boto3.client("s3").create_bucket(Bucket="media-test")
        yield "media-test"


def make_library(tmp_path):
    lib = tmp_path / "library"
    ep = lib / "Jujutsu Kaisen" / "Season 01"
    ep.mkdir(parents=True)
    (ep / "Jujutsu Kaisen - S01E025.mkv").write_bytes(b"x" * 1000)
    (lib / "Movies").mkdir()
    (lib / "Movies" / "Spirited Away (2001).mkv").write_bytes(b"y" * 2000)
    return lib


def test_sync_up_and_skip(bucket, tmp_path):
    lib = make_library(tmp_path)
    s3 = S3Sync(bucket=bucket, prefix="library")

    uploaded, skipped = s3.sync_up(lib)
    assert len(uploaded) == 2 and skipped == 0
    assert "library/Jujutsu Kaisen/Season 01/Jujutsu Kaisen - S01E025.mkv" in uploaded

    # Second run: nothing changed, nothing re-uploaded.
    uploaded, skipped = s3.sync_up(lib)
    assert uploaded == [] and skipped == 2

    # Changed size re-uploads.
    (lib / "Movies" / "Spirited Away (2001).mkv").write_bytes(b"y" * 3000)
    uploaded, skipped = s3.sync_up(lib)
    assert len(uploaded) == 1 and skipped == 1


def test_dry_run_uploads_nothing(bucket, tmp_path):
    lib = make_library(tmp_path)
    s3 = S3Sync(bucket=bucket, prefix="library")
    uploaded, _ = s3.sync_up(lib, dry_run=True)
    assert len(uploaded) == 2
    assert s3.remote_objects() == {}


def test_find_keys_and_presign(bucket, tmp_path):
    lib = make_library(tmp_path)
    s3 = S3Sync(bucket=bucket, prefix="library")
    s3.sync_up(lib)

    keys = s3.find_keys(["jujutsu", "e025"])
    assert keys == ["library/Jujutsu Kaisen/Season 01/Jujutsu Kaisen - S01E025.mkv"]
    url = s3.presign(keys[0], expires_seconds=3600)
    assert "X-Amz-Signature" in url or "Signature" in url
