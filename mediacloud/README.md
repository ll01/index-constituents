# mediacloud

Your own personal media cloud. Point it at the folders where your downloads
land, and it:

1. **Fuzzy-matches messy release names** — `[SubsPlease] Jujutsu Kaisen - 25 (1080p).mkv`,
   `Jujutsu.Kaisen.S02E01.WEB.x264-GRP.mkv` and `[ASW] Jujutsu Kaisen 2nd Season - 03.mkv`
   all land in the same `Jujutsu Kaisen/` folder, sorted by season.
2. **Organizes via hardlinks** — zero extra disk space, originals untouched
   (torrents keep seeding).
3. **Serves the library over local Wi-Fi** — with HTTP Range support, so VLC on
   your phone can stream *and seek*. Works fully offline (laptop hotspot on a
   plane is enough).
4. **Syncs to any S3-compatible bucket** — AWS, MinIO, Cloudflare R2, Backblaze
   B2 — and mints presigned download URLs you can open in *any* app on your
   phone, saving the file wherever you want.

No MTP, no companion app, no vendor lock-in. Python 3.11+, standard library
only (boto3 needed just for the S3 commands).

## Install

```bash
cd mediacloud
pip install .          # or: pip install '.[s3]' for the S3 commands
```

## Setup

```bash
mediacloud init        # writes mediacloud.toml
```

Edit it:

```toml
[library]
root = "~/MediaCloud/Library"
sources = ["~/Downloads", "D:/Torrents"]

[s3]
bucket = "my-media"
endpoint_url = ""      # empty for AWS; set for MinIO/R2/B2
prefix = "library"
```

S3 credentials come from the standard AWS chain (`AWS_ACCESS_KEY_ID` /
`AWS_SECRET_ACCESS_KEY` env vars or `~/.aws/credentials`).

## Use

```bash
mediacloud organize --dry-run   # preview how files will be sorted
mediacloud organize             # hardlink into the clean library tree
mediacloud watch                # keep organizing new files as they arrive
mediacloud status               # what's in the library

mediacloud serve                # stream over local Wi-Fi (port 8080)
mediacloud sync                 # upload library to S3 (skips unchanged files)
mediacloud pull                 # restore the library from S3 (new/replaced drive)
mediacloud url jujutsu e025     # presigned download link for that episode

mediacloud install [--serve]    # autostart watch (and serve) at login
mediacloud uninstall            # remove the autostart entries
```

`install` uses the OS's native scheduler: systemd user units on Linux,
launchd agents on macOS, Task Scheduler on Windows. `--dry-run` shows
exactly what would be written.

With `pip install zeroconf`, `serve` also announces itself over mDNS: VLC's
*Local Network* browser finds it by name, and most platforms can open
`http://mediacloud.local:8080/` directly (note: many Android *browsers* can't
resolve `.local` names — VLC discovery works there, or use the IP).

## The two transfer modes

**Direct wireless (offline, fast):** run `mediacloud serve`, connect the phone
to the same Wi-Fi — or to your laptop's hotspot if there's no network at all —
and open the printed `http://<ip>:8080/` in VLC (*Browse → URL*) or any
browser. Stream in place or download. Downloads land in the phone's normal
`Download/` folder, visible in the Files app, playable by any player.

**Phone → PC:** the same page has a *Send to PC* button. It opens the Android
file picker; selected files stream straight into the PC's inbox folder
(defaults to your first source folder, so `mediacloud watch` organizes them
automatically). Uploads stream to disk, so multi-GB episodes are fine. No app
needed on the phone — the browser is the app. Note that `localhost` on the
phone means the phone itself: always use the PC's LAN IP that `serve` prints.

**Via S3 (anywhere):** `mediacloud sync` from home, then from anywhere run
`mediacloud url <search terms>` and open the link on your phone. Because it's
a plain HTTPS link, your phone's browser/download manager controls where the
file saves — use whatever player you like afterwards.

## What gets organized, and where

- **Non-video files** (documents, archives, subtitles...) are ignored entirely.
- **Videos with an episode marker** (`S02E01`, `1x05`, `Show - 25`, `2nd
  Season`) go to `Series/Season XX/`. If the filename has no season but its
  folder does (`jjk s03/`), the folder's season is used.
- **Videos without an episode marker** (standalone films, `Jujutsu Kaisen 0`)
  go to `Movies/`, with the year if one is present.
- **Duplicates** (`... - Copy.mkv`, re-downloads from another release group)
  parse to the same episode, map to the same library path, and are skipped.
- **Versioned re-releases** (`... S03E10 v2 ...`) *replace* the existing
  episode in the library instead of being skipped — release groups ship a v2
  precisely because the v1 was broken.

## Watch mode

`mediacloud watch` polls the source folders (default every 15s, `--interval`
to change) and is **client-agnostic**: it doesn't care whether files come from
a torrent client, a browser, or `scp`. A file is only organized once its size
and mtime have stopped changing across consecutive scans, so half-written
downloads are never picked up. It does a full catch-up scan on startup, and
existing library folders are pinned so series keep landing in the same place
across restarts.

## Backups: use the right tool alongside this one

mediacloud is a media library, not a backup system — media is re-downloadable,
so a plain one-way mirror to S3 (`sync` up, `pull` to restore onto a new
drive; nothing is ever deleted remotely) is the right durability level, and it
keeps files streamable and presign-able.

For irreplaceable files (documents, photos), use **restic** next to it,
pointed at the same bucket under a different prefix:

```bash
restic -r s3:s3.amazonaws.com/my-media/backup init
restic -r s3:s3.amazonaws.com/my-media/backup backup ~/Documents
```

That gives you client-side encryption, deduplicated snapshots, and
point-in-time restore — protection a mirror can't provide, because a mirror
faithfully syncs your mistakes. For an extra local copy of the media library
on an external drive, plain `rsync -a Library/ /mnt/external/Library/` is all
you need.

## Fuzzy matching knobs

```toml
[matcher]
threshold = 0.82            # 0..1, higher = stricter title matching
[matcher.aliases]
"JJK" = "Jujutsu Kaisen"    # force-map a name to a canonical series
```

## Tests

```bash
pip install pytest moto boto3
python -m pytest tests/
```
