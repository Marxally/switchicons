#!/usr/bin/env python3
"""
Regenerates data.json for the Switch Icons site from two sources:

1. titledb (https://github.com/blawar/titledb, MIT licensed) — the primary
   source, covering ~18,800 original Nintendo Switch base games. Its data
   comes from dumped/cracked game files, which is why it's extremely
   thorough for Switch 1 but has almost nothing for Switch 2 (only ~26
   titles as of writing) — Switch 2 isn't meaningfully crackable yet, so
   there's very little for that community to have dumped and cataloged.

2. Nintendo.com's own game-search backend (an Algolia index that powers
   the search/filter UI on nintendo.com) — used here specifically to
   backfill Switch 2 titles, since it's driven by Nintendo's official
   catalog rather than dumped files and has the full ~350+ Switch 2
   library. Endpoint/fields confirmed against the open-source
   nintendo-switch-eshop library (github.com/lmmfranco/nintendo-switch-eshop).

Titles found in both sources are deduped by normalized name, preferring
titledb's richer metadata when a title appears in both.

Usage:
    python3 build_data.py [--region US.en] [--skip-switch2]
"""
import json
import re
import sys
import urllib.request
import urllib.parse
import argparse

ICON_PREFIX = "https://img-eshop.cdn.nintendo.net/i/"
ICON_SUFFIX = ".jpg"

ALGOLIA_APP_ID = "U3B6GR4UA3"
ALGOLIA_API_KEY = "c4da8be7fd29f0f5bfa42920b0a99dc7"
ALGOLIA_URL = f"https://{ALGOLIA_APP_ID}-dsn.algolia.net/1/indexes/*/queries"
ALGOLIA_INDEX = "ncom_game_en_us_title_asc"


def fetch_titledb(region):
    url = f"https://raw.githubusercontent.com/blawar/titledb/master/{region}.json"
    print(f"Fetching {url} ...")
    with urllib.request.urlopen(url, timeout=60) as resp:
        return json.load(resp)


def normalize_name(name):
    """Strip trademark symbols/punctuation so the same game from two
    differently-formatted sources (or with/without (TM)) matches for dedup."""
    s = (name or "").lower()
    s = re.sub(r"[™®©]", "", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return s.strip()


def parse_release_date(display):
    """Nintendo.com's releaseDateDisplay is usually ISO (YYYY-MM-DD) but is
    sometimes fuzzy text like 'Early 2026' — return 0 for anything we can't
    confidently parse rather than guess."""
    if not display:
        return 0
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", str(display))
    if m:
        return int(m.group(1) + m.group(2) + m.group(3))
    return 0


def fetch_nintendo_platform(platform_label, hits_per_page=1000):
    """Queries Nintendo's own site-search index for a given platform label
    (e.g. "Nintendo Switch 2"). Returns the raw list of hit dicts."""
    params = urllib.parse.urlencode({
        "hitsPerPage": hits_per_page,
        "page": 0,
        "analytics": "false",
        "facetFilters": json.dumps([[f"platform:{platform_label}"]]),
    })
    body = json.dumps({"requests": [{"indexName": ALGOLIA_INDEX, "params": params}]}).encode("utf-8")
    req = urllib.request.Request(
        ALGOLIA_URL,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Algolia-API-Key": ALGOLIA_API_KEY,
            "X-Algolia-Application-Id": ALGOLIA_APP_ID,
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.load(resp)
    hits = []
    for result in payload.get("results", []):
        hits.extend(result.get("hits", []))
    return hits


def switch2_supplement(existing_names):
    """Best-effort fetch of Switch 2 titles from Nintendo.com to backfill
    what titledb is missing. Returns [] on any failure rather than breaking
    the whole build — this is a supplement, not the primary source."""
    try:
        hits = fetch_nintendo_platform("Nintendo Switch 2")
        print(f"Nintendo.com search returned {len(hits)} Switch 2 hits")
    except Exception as e:
        print(f"WARNING: Switch 2 supplement fetch failed, skipping it ({e})", file=sys.stderr)
        return []

    out = []
    skipped_no_icon = 0
    skipped_dupe = 0
    for h in hits:
        icon = h.get("boxart")
        if not icon:
            skipped_no_icon += 1
            continue
        name = h.get("title") or "Untitled"
        norm = normalize_name(name)
        if norm in existing_names:
            skipped_dupe += 1
            continue
        existing_names.add(norm)  # guard against dupes within this same source too
        publishers = h.get("publishers") or []
        out.append({
            "id": "NCOM-" + (h.get("nsuid") or h.get("objectID") or norm),
            "name": name,
            "icon": icon,  # full URL, not a hash — app.js handles both forms
            "pub": ", ".join(publishers) if publishers else "",
            "cat": h.get("genres") or [],
            "date": parse_release_date(h.get("releaseDateDisplay")),
        })
    print(f"Switch 2 supplement: added {len(out)}, skipped {skipped_dupe} dupes of titledb entries, {skipped_no_icon} with no boxart")
    return out


def build(data, include_switch2=True):
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
    print(f"titledb: {len(games)} base games")

    if include_switch2:
        existing_names = {normalize_name(g["name"]) for g in games}
        games.extend(switch2_supplement(existing_names))

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
    ap.add_argument("--skip-switch2", action="store_true", help="Skip the Nintendo.com Switch 2 supplement")
    args = ap.parse_args()

    raw = fetch_titledb(args.region)
    out = build(raw, include_switch2=not args.skip_switch2)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"), ensure_ascii=False)

    print(f"Wrote {len(out['games'])} games across {len(out['cats'])} categories to {args.out}")


if __name__ == "__main__":
    main()
