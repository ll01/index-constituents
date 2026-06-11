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
mediacloud url jujutsu e025     # presigned download link for that episode
```

## The two transfer modes

**Direct wireless (offline, fast):** run `mediacloud serve`, connect the phone
to the same Wi-Fi — or to your laptop's hotspot if there's no network at all —
and open the printed `http://<ip>:8080/` in VLC (*Browse → URL*) or any
browser. Stream in place or download.

**Via S3 (anywhere):** `mediacloud sync` from home, then from anywhere run
`mediacloud url <search terms>` and open the link on your phone. Because it's
a plain HTTPS link, your phone's browser/download manager controls where the
file saves — use whatever player you like afterwards.

## Watch mode

`mediacloud watch` polls the source folders (default every 15s, `--interval`
to change) and is **client-agnostic**: it doesn't care whether files come from
a torrent client, a browser, or `scp`. A file is only organized once its size
and mtime have stopped changing across consecutive scans, so half-written
downloads are never picked up. It does a full catch-up scan on startup, and
existing library folders are pinned so series keep landing in the same place
across restarts.

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
