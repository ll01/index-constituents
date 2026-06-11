"""mediacloud — your own personal media cloud.

    mediacloud init                 create a starter config file
    mediacloud organize [--dry-run] sort source folders into the library
    mediacloud watch [--interval N] keep organizing new files as they finish
    mediacloud serve [--port N]     stream the library over local Wi-Fi
    mediacloud sync [--dry-run]     upload the library to S3
    mediacloud pull [--dry-run]     restore the library from S3
    mediacloud url <search terms>   presigned S3 download link for a file
    mediacloud publish              upload a presigned HTML index to S3
    mediacloud status               library overview
"""

from __future__ import annotations

import argparse
from pathlib import Path

from . import config as config_mod
from .matcher import SeriesIndex
from .organizer import organize
from .server import serve


def _s3(cfg: config_mod.Config):
    if not cfg.s3_bucket:
        raise SystemExit("No [s3] bucket configured — edit your mediacloud.toml.")
    from .s3sync import S3Sync

    return S3Sync(
        bucket=cfg.s3_bucket,
        prefix=cfg.s3_prefix,
        endpoint_url=cfg.s3_endpoint or None,
        region=cfg.s3_region or None,
    )


def cmd_init(args: argparse.Namespace) -> None:
    dest = config_mod.write_example()
    print(f"Wrote {dest} — edit it, then run `mediacloud organize`.")


def cmd_organize(args: argparse.Namespace) -> None:
    cfg = config_mod.load(args.config)
    if not cfg.sources:
        raise SystemExit("No [library] sources configured — edit your mediacloud.toml.")
    index = SeriesIndex(threshold=cfg.threshold, aliases=cfg.aliases)
    report = organize(cfg.sources, cfg.library_root, index, dry_run=args.dry_run)
    for item in report.planned:
        print(f"  would link  {item.source.name}\n          ->  {item.dest}")
    for item in report.linked:
        print(f"  linked  {item.source.name}\n      ->  {item.dest}")
    for item in report.copied:
        print(f"  copied  {item.source.name}\n      ->  {item.dest}")
    for item in report.upgraded:
        print(f"  upgraded (v{item.version})  {item.source.name}\n      ->  {item.dest}")
    done = len(report.linked) + len(report.copied) + len(report.upgraded) + len(report.planned)
    print(f"{done} file(s) {'planned' if args.dry_run else 'organized'}, "
          f"{len(report.skipped)} already in library.")


def cmd_watch(args: argparse.Namespace) -> None:
    import time

    from .watcher import FolderWatcher

    cfg = config_mod.load(args.config)
    if not cfg.sources:
        raise SystemExit("No [library] sources configured — edit your mediacloud.toml.")
    index = SeriesIndex(threshold=cfg.threshold, aliases=cfg.aliases)

    # Catch-up pass for anything that arrived while we weren't running.
    report = organize(cfg.sources, cfg.library_root, index)
    done = len(report.linked) + len(report.copied)
    print(f"Startup scan: {done} file(s) organized, {len(report.skipped)} already in library.")
    print(f"Watching {len(cfg.sources)} folder(s) every {args.interval}s; Ctrl+C to stop.")

    watcher = FolderWatcher(sources=cfg.sources)
    try:
        while True:
            time.sleep(args.interval)
            ready = watcher.scan()
            if not ready:
                continue
            report = organize(cfg.sources, cfg.library_root, index, only=ready)
            for item in report.linked + report.copied + report.upgraded:
                print(f"  {item.source.name}\n    ->  {item.dest}")
    except KeyboardInterrupt:
        print("\nStopped.")


def cmd_serve(args: argparse.Namespace) -> None:
    cfg = config_mod.load(args.config)
    serve(cfg.library_root, port=args.port or cfg.serve_port, inbox=cfg.inbox)


def cmd_sync(args: argparse.Namespace) -> None:
    cfg = config_mod.load(args.config)
    s3 = _s3(cfg)
    uploaded, skipped = s3.sync_up(cfg.library_root.expanduser(), dry_run=args.dry_run)
    verb = "would upload" if args.dry_run else "uploaded"
    for key in uploaded:
        print(f"  {verb}  {key}")
    print(f"{len(uploaded)} file(s) {verb}, {skipped} already up to date.")


def cmd_pull(args: argparse.Namespace) -> None:
    cfg = config_mod.load(args.config)
    s3 = _s3(cfg)
    downloaded, skipped = s3.sync_down(cfg.library_root.expanduser(), dry_run=args.dry_run)
    verb = "would download" if args.dry_run else "downloaded"
    for key in downloaded:
        print(f"  {verb}  {key}")
    print(f"{len(downloaded)} file(s) {verb}, {skipped} already present locally.")


def cmd_url(args: argparse.Namespace) -> None:
    cfg = config_mod.load(args.config)
    s3 = _s3(cfg)
    keys = s3.find_keys(args.terms)
    if not keys:
        raise SystemExit(f"No remote file matches: {' '.join(args.terms)}")
    if len(keys) > 1 and not args.all:
        print(f"{len(keys)} matches (use --all for URLs for every match):")
        for key in sorted(keys):
            print(f"  {key}")
        return
    for key in sorted(keys):
        print(f"{key}\n  {s3.presign(key, expires_seconds=args.expires * 3600)}\n")


def cmd_publish(args: argparse.Namespace) -> None:
    cfg = config_mod.load(args.config)
    s3 = _s3(cfg)
    expires = args.expires or cfg.publish_expires
    url = s3.publish(expires_hours=expires)
    print(f"Index page ({expires}h link):\n  {url}")
    print("Bookmark this on your phone — it browses your whole library from anywhere.")


def _autostart_commands(args: argparse.Namespace) -> list[str]:
    return ["watch", "serve"] if args.serve else ["watch"]


def cmd_install(args: argparse.Namespace) -> None:
    from . import autostart

    cfg = config_mod.load(args.config)  # validates config exists before installing
    config_path = cfg.path.resolve() if cfg.path else None
    autostart.install(_autostart_commands(args), config_path, dry_run=args.dry_run)


def cmd_uninstall(args: argparse.Namespace) -> None:
    from . import autostart

    autostart.uninstall(["watch", "serve"])


def cmd_status(args: argparse.Namespace) -> None:
    cfg = config_mod.load(args.config)
    root = cfg.library_root.expanduser()
    if not root.is_dir():
        print(f"Library {root} does not exist yet — run `mediacloud organize`.")
        return
    total_files = total_bytes = 0
    for series_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        files = [f for f in series_dir.rglob("*") if f.is_file()]
        size = sum(f.stat().st_size for f in files)
        total_files += len(files)
        total_bytes += size
        print(f"  {series_dir.name}: {len(files)} file(s), {size / 1e9:.2f} GB")
    print(f"Total: {total_files} file(s), {total_bytes / 1e9:.2f} GB in {root}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="mediacloud", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--config", type=Path, help="path to mediacloud.toml")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="create a starter config file").set_defaults(func=cmd_init)

    p = sub.add_parser("organize", help="sort source folders into the library")
    p.add_argument("--dry-run", action="store_true", help="show the plan without linking")
    p.set_defaults(func=cmd_organize)

    p = sub.add_parser("watch", help="poll source folders and organize new files as they settle")
    p.add_argument("--interval", type=int, default=15, help="seconds between scans (default 15)")
    p.set_defaults(func=cmd_watch)

    p = sub.add_parser("serve", help="stream the library over local Wi-Fi")
    p.add_argument("--port", type=int, help="override the configured port")
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("sync", help="upload the library to S3")
    p.add_argument("--dry-run", action="store_true", help="show what would upload")
    p.set_defaults(func=cmd_sync)

    p = sub.add_parser("pull", help="restore the library from S3 (e.g. onto a new drive)")
    p.add_argument("--dry-run", action="store_true", help="show what would download")
    p.set_defaults(func=cmd_pull)

    p = sub.add_parser("url", help="presigned S3 download link for a file")
    p.add_argument("terms", nargs="+", help="search terms matched against remote paths")
    p.add_argument("--expires", type=int, default=24, help="link lifetime in hours (default 24)")
    p.add_argument("--all", action="store_true", help="print URLs for every match")
    p.set_defaults(func=cmd_url)

    p = sub.add_parser("publish", help="upload a presigned HTML index to S3 for phone browsing")
    p.add_argument("--expires", type=int, help="link lifetime in hours (default from config)")
    p.set_defaults(func=cmd_publish)

    p = sub.add_parser("install", help="autostart watch (and optionally serve) at login")
    p.add_argument("--serve", action="store_true", help="also autostart the LAN server")
    p.add_argument("--dry-run", action="store_true", help="show what would be installed")
    p.set_defaults(func=cmd_install)

    p = sub.add_parser("uninstall", help="remove the autostart entries")
    p.set_defaults(func=cmd_uninstall)

    sub.add_parser("status", help="library overview").set_defaults(func=cmd_status)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
