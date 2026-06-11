import io

import pytest

from mediacloud import server
from mediacloud.server import save_uploads


def multipart_body(boundary: str, files: dict[str, bytes]) -> bytes:
    out = b""
    for name, data in files.items():
        out += (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="files"; filename="{name}"\r\n'
            f"Content-Type: application/octet-stream\r\n\r\n"
        ).encode() + data + b"\r\n"
    return out + f"--{boundary}--\r\n".encode()


def run(body: bytes, boundary: str, inbox) -> list[str]:
    return save_uploads(
        io.BytesIO(body), len(body), f"multipart/form-data; boundary={boundary}", inbox
    )


def test_two_files_saved_byte_exact(tmp_path):
    files = {
        "Show.S03E01.mkv": b"\x00\x01binary\r\ndata\xff" * 100,
        "Show.S03E02.mkv": b"other contents",
    }
    saved = run(multipart_body("BOUND123", files), "BOUND123", tmp_path)
    assert sorted(saved) == sorted(files)
    for name, data in files.items():
        assert (tmp_path / name).read_bytes() == data


def test_boundary_straddles_read_chunks(tmp_path, monkeypatch):
    # Tiny chunks force the boundary to split across reads.
    monkeypatch.setattr(server, "_CHUNK", 7)
    data = b"x" * 1000 + b"\r\n--almost-a-boundary" + b"y" * 1000
    saved = run(multipart_body("realBOUNDARY", {"ep.mkv": data}), "realBOUNDARY", tmp_path)
    assert saved == ["ep.mkv"]
    assert (tmp_path / "ep.mkv").read_bytes() == data


def test_filename_path_components_stripped(tmp_path):
    body = multipart_body("B1", {"../../evil.mkv": b"data"})
    saved = run(body, "B1", tmp_path)
    assert saved == ["evil.mkv"]
    assert (tmp_path / "evil.mkv").read_bytes() == b"data"
    assert not (tmp_path.parent / "evil.mkv").exists()


def test_existing_file_not_clobbered(tmp_path):
    (tmp_path / "ep.mkv").write_bytes(b"original")
    saved = run(multipart_body("B1", {"ep.mkv": b"new"}), "B1", tmp_path)
    assert saved == ["ep (1).mkv"]
    assert (tmp_path / "ep.mkv").read_bytes() == b"original"
    assert (tmp_path / "ep (1).mkv").read_bytes() == b"new"


@pytest.mark.parametrize("body,ctype", [
    (b"", "multipart/form-data; boundary=B1"),
    (b"not multipart at all", "multipart/form-data; boundary=B1"),
    (b"data", "multipart/form-data"),  # no boundary param
])
def test_malformed_bodies_save_nothing(tmp_path, body, ctype):
    assert save_uploads(io.BytesIO(body), len(body), ctype, tmp_path) == []
    assert list(tmp_path.iterdir()) == []
