#!/usr/bin/env python3
"""
Regenerates data.json for the Switch Icons site from the titledb project
(https://github.com/blawar/titledb, MIT licensed).

Usage:
    python3 build_data.py [--region US.en]

Pulls the latest region JSON straight from titledb's GitHub repo, filters it
down to base games (title IDs ending in "000") that have an icon and aren't
demos, dedupes by title ID, and writes a compact data.json in the format
app.js expects: {"cats": [...], "games": [[id, name, iconHash, publisher,
[categoryIndices], releaseDate], ...]}
"""
import json
import sys
import urllib.request
import argparse

ICON_PREFIX = "https://img-eshop.cdn.nintendo.net/i/"
ICON_SUFFIX = ".jpg"


def fetch_titledb(region):
    url = f"https://raw.githubusercontent.com/blawar/titledb/master/{region}.json"
    print(f"Fetching {url} ...")
    with urllib.request.urlopen(url, timeout=60) as resp:
        return json.load(resp)


def build(data):
    seen = {}
    for k, v in data.items():
        icon = v.get("iconUrl")
        if not icon or not icon.startswith(ICON_PREFIX) or not icon.endswith(ICON_SUFFIX):
            continue
        tid = v.get("id") or k
        if not (isinstance(tid, str) and tid.upper().endswith("000")):
            continue
        if v.get("isDemo"):
            continue
        if tid in seen:
            continue
        seen[tid] = {
            "id": tid,
            "name": v.get("name") or "Untitled",
            "icon": icon[len(ICON_PREFIX):-len(ICON_SUFFIX)],
            "pub": v.get("publisher") or "",
            "cat": v.get("category") or [],
            "date": v.get("releaseDate") or 0,
        }

    games = list(seen.values())
    games.sort(key=lambda g: g["name"].lower())

    cats = sorted({c for g in games for c in g["cat"]})
    cat_idx = {c: i for i, c in enumerate(cats)}

    compact = [
        [g["id"], g["name"], g["icon"], g["pub"], [cat_idx[c] for c in g["cat"]], g["date"]]
        for g in games
    ]
    return {"cats": cats, "games": compact}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", default="US.en", help="titledb region file, e.g. US.en, JP.ja, GB.en")
    ap.add_argument("--out", default="data.json")
    args = ap.parse_args()

    raw = fetch_titledb(args.region)
    out = build(raw)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"), ensure_ascii=False)

    print(f"Wrote {len(out['games'])} games across {len(out['cats'])} categories to {args.out}")


if __name__ == "__main__":
    main()
