"""Direct-wireless mode: serve the library over HTTP on the local network.

Supports HTTP Range requests so VLC / mpv on the phone can seek while
streaming. Works with no internet at all — e.g. a laptop hotspot on a plane.
"""

from __future__ import annotations

import html
import re
import socket
import urllib.parse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .matcher import is_video

_CHUNK = 64 * 1024
_FILENAME_RE = re.compile(rb'filename="([^"]*)"')


def save_uploads(rfile, length: int, content_type: str, inbox: Path) -> list[str]:
    """Stream a multipart/form-data body to disk; memory use stays ~64 KB
    regardless of file size. Returns the saved filenames."""
    m = re.search(r'boundary="?([^";]+)"?', content_type)
    if not m or length <= 0:
        return []
    delim = b"\r\n--" + m.group(1).encode()
    remaining = length

    # Prefix with CRLF so the first boundary looks like every other one.
    buf = b"\r\n"

    def more() -> bool:
        nonlocal buf, remaining
        if remaining <= 0:
            return False
        chunk = rfile.read(min(_CHUNK, remaining))
        remaining -= len(chunk)
        buf += chunk
        return bool(chunk)

    saved: list[str] = []
    while delim not in buf and more():
        pass
    if delim not in buf:
        return []
    buf = buf[buf.index(delim) + len(delim):]

    while True:
        while len(buf) < 2 and more():
            pass
        if buf.startswith(b"--") or not buf:  # closing boundary
            break
        while b"\r\n\r\n" not in buf and more():
            pass
        head, _, buf = buf.partition(b"\r\n\r\n")
        fm = _FILENAME_RE.search(head)
        out = None
        if fm and fm.group(1):
            name = Path(fm.group(1).decode("utf-8", "replace")).name  # no path tricks
            dest, i = inbox / name, 1
            while dest.exists():
                dest = inbox / f"{Path(name).stem} ({i}){Path(name).suffix}"
                i += 1
            inbox.mkdir(parents=True, exist_ok=True)
            out = open(dest, "wb")
        try:
            while True:
                idx = buf.find(delim)
                if idx != -1:
                    if out:
                        out.write(buf[:idx])
                        saved.append(dest.name)
                    buf = buf[idx + len(delim):]
                    break
                # Flush all but a tail that could hold a partial boundary.
                keep = len(delim) - 1
                if len(buf) > keep:
                    if out:
                        out.write(buf[:-keep])
                    buf = buf[-keep:]
                if not more():  # truncated body
                    if out:
                        out.write(buf)
                        saved.append(dest.name)
                    buf = b""
                    break
        finally:
            if out:
                out.close()

    while remaining > 0:  # drain the epilogue so keep-alive stays usable
        chunk = rfile.read(min(_CHUNK, remaining))
        if not chunk:
            break
        remaining -= len(chunk)
    return saved


class RangeRequestHandler(SimpleHTTPRequestHandler):
    """SimpleHTTPRequestHandler plus single-range byte serving (RFC 7233)
    and phone-to-PC uploads via POST /upload."""

    protocol_version = "HTTP/1.1"

    def __init__(self, *args, inbox: Path | None = None, **kwargs):
        self.inbox = inbox  # before super().__init__: it handles the request
        super().__init__(*args, **kwargs)

    def do_POST(self):
        if urllib.parse.urlparse(self.path).path != "/upload" or self.inbox is None:
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length") or 0)
        ctype = self.headers.get("Content-Type", "")
        if not ctype.startswith("multipart/form-data"):
            self.send_error(400, "Expected multipart/form-data")
            return
        saved = save_uploads(self.rfile, length, ctype, self.inbox)
        print(f"  {self.client_address[0]} uploaded {len(saved)} file(s): {', '.join(saved)}")
        self.send_response(303)
        self.send_header("Location", "/")
        self.send_header("Content-Length", "0")
        self.end_headers()

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
        upload_form = ""
        if self.inbox is not None:
            upload_form = (
                "<form method='post' enctype='multipart/form-data' action='/upload' "
                "style='margin:1em 0;padding:0.8em;border:1px dashed #555;border-radius:8px'>"
                "<input type='file' name='files' multiple> "
                "<button style='padding:0.4em 1em'>Send to PC</button></form>"
            )
        body = (
            "<!DOCTYPE html><html><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>MediaCloud {shown}</title>"
            "<style>body{font-family:sans-serif;margin:1.5em;background:#111;color:#eee}"
            "a{color:#7ec8ff;text-decoration:none;font-size:1.1em;line-height:2em}"
            "li{list-style:none}ul{padding:0}</style></head>"
            f"<body><h2>MediaCloud {shown}</h2>{upload_form}<ul>{''.join(rows)}</ul></body></html>"
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


def _qr_text(url: str) -> str | None:
    """Render a QR code as Unicode block characters. Returns None if qrcode
    is not installed (the URL is still printed as plain text)."""
    try:
        import qrcode
        qr = qrcode.QRCode(border=1)
        qr.add_data(url)
        qr.make(fit=True)
        lines = []
        matrix = qr.get_matrix()
        # Two rows per terminal line using upper/lower half-block characters.
        for y in range(0, len(matrix) - 1, 2):
            row = ""
            for x in range(len(matrix[y])):
                top = matrix[y][x]
                bot = matrix[y + 1][x] if y + 1 < len(matrix) else False
                if top and bot:
                    row += "█"
                elif top:
                    row += "▀"
                elif bot:
                    row += "▄"
                else:
                    row += " "
            lines.append(row)
        return "\n".join(lines)
    except ImportError:
        return None


def advertise_mdns(port: int):
    """Announce as mediacloud.local via mDNS, if zeroconf is installed.
    Returns the Zeroconf handle (caller closes it), or None."""
    try:
        from zeroconf import ServiceInfo, Zeroconf
    except ImportError:
        print("Tip: `pip install zeroconf` to be reachable as http://mediacloud.local"
              f":{port}/ and discoverable in VLC's Local Network browser.")
        return None
    ips = lan_addresses()
    if not ips:
        return None
    zc = Zeroconf()
    info = ServiceInfo(
        "_http._tcp.local.",
        "MediaCloud._http._tcp.local.",
        addresses=[socket.inet_aton(ip) for ip in ips],
        port=port,
        server="mediacloud.local.",
        properties={"path": "/"},
    )
    zc.register_service(info)
    print(f"Advertised as http://mediacloud.local:{port}/ "
          "(works in VLC's Local Network browser; some Android browsers "
          "can't resolve .local names — use the IP there).")
    return zc


def serve(library: Path, port: int = 8080, inbox: Path | None = None) -> None:
    library = library.expanduser()
    if inbox is not None:
        inbox = inbox.expanduser()
    handler = partial(RangeRequestHandler, directory=str(library), inbox=inbox)
    server = ThreadingHTTPServer(("0.0.0.0", port), handler)
    print(f"Serving {library} on:")
    ips = lan_addresses() or ["<this machine's IP>"]
    for ip in ips:
        url = f"http://{ip}:{port}/"
        print(f"  {url}")
        qr = _qr_text(url)
        if qr:
            print(qr)
    if len(ips) > 1:
        print("(Multiple addresses shown — use the one matching your current network.)")
    print("Open the URL or scan the QR code in VLC (Browse → Network) or your phone browser.")
    if inbox is not None:
        print(f"Phone uploads land in {inbox}")
    zc = advertise_mdns(port)
    print("Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        if zc is not None:
            zc.close()
