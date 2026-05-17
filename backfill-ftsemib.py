#!/usr/bin/env python3
# coding: utf-8

import argparse
import importlib.util
import pathlib
import time
from datetime import date, datetime

import requests


START_MONTH = date(2024, 3, 1)
WIKI_API_URL = "https://en.wikipedia.org/w/api.php"
WIKI_TITLE = "FTSE_MIB"
OUTPUT_BASENAME = "constituents-ftsemib"
HEADERS = {
    "User-Agent": "index-constituents-ftsemib-backfill/1.0 (https://github.com/yfiua/index-constituents)"
}


def load_get_constituents_module():
    module_path = pathlib.Path(__file__).resolve().parent / "get-constituents.py"
    spec = importlib.util.spec_from_file_location("get_constituents", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gc = load_get_constituents_module()


def iter_month_starts(start, end):
    current = date(start.year, start.month, 1)
    final = date(end.year, end.month, 1)

    while current <= final:
        yield current
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)


def get_wikipedia_oldid_url(month_start):
    target = datetime(month_start.year, month_start.month, month_start.day)
    params = {
        "action": "query",
        "prop": "revisions",
        "titles": WIKI_TITLE,
        "rvlimit": 1,
        "rvstart": target.strftime("%Y-%m-%dT00:00:00Z"),
        "rvdir": "older",
        "format": "json",
    }
    response = requests.get(WIKI_API_URL, params=params, headers=HEADERS, timeout=30)
    response.raise_for_status()

    pages = response.json().get("query", {}).get("pages", {})
    for page in pages.values():
        revisions = page.get("revisions", [])
        if revisions:
            oldid = revisions[0]["revid"]
            return f"https://en.wikipedia.org/w/index.php?title={WIKI_TITLE}&oldid={oldid}"

    raise RuntimeError(f"No Wikipedia revision found for {month_start:%Y-%m}")


def backfill_month(month_start, output_dir, overwrite=False):
    month_dir = pathlib.Path(output_dir) / f"{month_start:%Y}" / f"{month_start:%m}"
    csv_path = month_dir / f"{OUTPUT_BASENAME}.csv"
    json_path = month_dir / f"{OUTPUT_BASENAME}.json"

    if not overwrite and csv_path.exists() and json_path.exists():
        return "skipped"

    oldid_url = get_wikipedia_oldid_url(month_start)
    df = gc.get_constituents_from_wikipedia(oldid_url, suffix=".MI", headers=HEADERS)

    month_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(csv_path, index=False)
    df.to_json(json_path, orient="records")
    return "saved"


def parse_args():
    parser = argparse.ArgumentParser(description="Backfill FTSE MIB historical constituents.")
    parser.add_argument("--start", default="2024-03", help="Start month in YYYY-MM format.")
    parser.add_argument("--end", default=date.today().strftime("%Y-%m"), help="End month in YYYY-MM format.")
    parser.add_argument("--output", default="docs", help="Output directory.")
    parser.add_argument("--overwrite", action="store_true", help="Replace existing FTSE MIB files.")
    parser.add_argument("--sleep", type=float, default=0.5, help="Seconds to sleep between months.")
    return parser.parse_args()


def parse_month(value):
    return datetime.strptime(value, "%Y-%m").date().replace(day=1)


def main():
    args = parse_args()
    start = parse_month(args.start)
    end = parse_month(args.end)

    if start < START_MONTH:
        raise SystemExit(f"FTSE MIB backfill starts at {START_MONTH:%Y-%m}.")
    if end < start:
        raise SystemExit("--end must be the same as or later than --start.")

    status_counts = {"saved": 0, "skipped": 0}
    for month_start in iter_month_starts(start, end):
        status = backfill_month(month_start, pathlib.Path(args.output), overwrite=args.overwrite)
        status_counts[status] = status_counts.get(status, 0) + 1
        print(f"{month_start:%Y-%m}: {status}")
        if args.sleep:
            time.sleep(args.sleep)

    print(f"Saved {status_counts.get('saved', 0)} month(s), skipped {status_counts.get('skipped', 0)}.")


if __name__ == "__main__":
    main()
