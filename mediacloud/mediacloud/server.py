"""Direct-wireless mode: serve the library over HTTP on the local network.

Supports HTTP Range requests so VLC / mpv on the phone can seek while
streaming. Works with no internet at all — e.g. a laptop hotspot on a plane.
"""

from __future__ import annotations

import html
import socket
import urllib.parse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .matcher import is_video


class RangeRequestHandler(SimpleHTTPRequestHandler):
    """SimpleHTTPRequestHandler plus single-range byte serving (RFC 7233)."""

    protocol_version = "HTTP/1.1"

    def send_head(self):
        path = Path(self.translate_path(self.path))
        range_header = self.headers.get("Range")
        if not (range_header and path.is_file()):
            return super().send_head()

        try:
            unit, _, spec = range_header.partition("=")
            start_s, _, end_s = spec.partition("-")
            if unit.strip() != "bytes":
                raise ValueError
            size = path.stat().st_size
            start = int(start_s) if start_s else size - int(end_s)
            end = min(int(end_s), size - 1) if start_s and end_s else size - 1
            if start < 0 or start > end:
                raise ValueError
        except (ValueError, OSError):
            self.send_error(416, "Requested Range Not Satisfiable")
            return None

        f = open(path, "rb")
        f.seek(start)
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(str(path)))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        self._range_remaining = end - start + 1
        return f

    def copyfile(self, source, outputfile):
        remaining = getattr(self, "_range_remaining", None)
        if remaining is None:
            return super().copyfile(source, outputfile)
        self._range_remaining = None
        while remaining > 0:
            chunk = source.read(min(64 * 1024, remaining))
            if not chunk:
                break
            outputfile.write(chunk)
            remaining -= len(chunk)

    def list_directory(self, path):
        # Friendlier index page than the stock one, video files first.
        try:
            entries = sorted(Path(path).iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        except OSError:
            self.send_error(404)
            return None
        rows = []
        for entry in entries:
            name = entry.name + ("/" if entry.is_dir() else "")
            href = urllib.parse.quote(name)
            icon = "📁" if entry.is_dir() else ("🎬" if is_video(entry.name) else "📄")
            rows.append(f'<li>{icon} <a href="{href}">{html.escape(name)}</a></li>')
        shown = html.escape(urllib.parse.unquote(self.path))
        body = (
            "<!DOCTYPE html><html><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>MediaCloud {shown}</title>"
            "<style>body{font-family:sans-serif;margin:1.5em;background:#111;color:#eee}"
            "a{color:#7ec8ff;text-decoration:none;font-size:1.1em;line-height:2em}"
            "li{list-style:none}ul{padding:0}</style></head>"
            f"<body><h2>MediaCloud {shown}</h2><ul>{''.join(rows)}</ul></body></html>"
        ).encode("utf-8", "surrogateescape")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        import io

        return io.BytesIO(body)

    def log_message(self, fmt, *args):  # quieter logs
        print(f"  {self.client_address[0]} {fmt % args}")


def lan_addresses() -> list[str]:
    """Best-effort list of non-loopback IPv4 addresses on this machine."""
    addrs: set[str] = set()
    try:
        # UDP "connect" never sends packets; it just picks the outbound iface.
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            addrs.add(s.getsockname()[0])
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            addrs.add(info[4][0])
    except OSError:
        pass
    return sorted(a for a in addrs if not a.startswith("127."))


def serve(library: Path, port: int = 8080) -> None:
    library = library.expanduser()
    handler = partial(RangeRequestHandler, directory=str(library))
    server = ThreadingHTTPServer(("0.0.0.0", port), handler)
    print(f"Serving {library} on:")
    ips = lan_addresses() or ["<this machine's IP>"]
    for ip in ips:
        print(f"  http://{ip}:{port}/")
    print("Open one of these in VLC or a browser on your phone (same Wi-Fi/hotspot).")
    print("Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
