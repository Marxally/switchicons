#!/usr/bin/env python3
"""
Regenerates data.json for the Switch Icons site from two sources:

1. titledb (https://github.com/blawar/titledb, MIT licensed) — the primary
   source, covering ~18,800 original Nintendo Switch base games. Its data
   comes from dumped/cracked game files, which is why it's extremely
   thorough for Switch 1 but has almost nothing for Switch 2 — Switch 2
   isn't meaningfully crackable yet, so there's very little for that
   community to have dumped and cataloged.

2. Nintendo.com's own live product-search backend (an Algolia index called
   "store_all_products_en_us" that powers search on nintendo.com today) —
   used here specifically to backfill Switch 2 titles, since it's driven by
   Nintendo's official catalog rather than dumped files. An older sibling
   index ("ncom_game_en_us") was tried first but turned out to be a stale,
   abandoned snapshot from before Switch 2 existed (confirmed by its total
   size and by direct title searches returning nothing relevant) — kept
   here only as a last-resort fallback. Endpoint/fields confirmed against
   the actively maintained fork of nintendo-switch-eshop
   (github.com/favna/nintendo-switch-eshop).

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

# Current, actively-maintained index (as of this writing) that backs
# nintendo.com's live product search. Uses Algolia's plain single-index
# /query REST endpoint — body is just the search params as JSON directly.
NEW_INDEX_NAME = "store_all_products_en_us"
NEW_INDEX_KEY = "a29c6927638bfd8cee23993e51e721c9"
NEW_INDEX_URL = f"https://{ALGOLIA_APP_ID}-dsn.algolia.net/1/indexes/{NEW_INDEX_NAME}/query"

# Older index/endpoint, confirmed stale (frozen pre-Switch-2, ~9k entries)
# but kept as a fallback attempt in case the new index ever changes shape.
OLD_INDEX_NAME = "ncom_game_en_us"
OLD_INDEX_KEY = "6efbfb0f8f80defc44895018caf77504"
OLD_INDEX_URL = f"https://{ALGOLIA_APP_ID}-dsn.algolia.net/1/indexes/{OLD_INDEX_NAME}/query"


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


def _index_query(url, api_key, body_dict, timeout=60):
    """POST to an Algolia single-index /query endpoint. Body is sent as
    plain JSON (this newer-style endpoint doesn't use the urlencoded
    'params' string wrapper the older multi-query endpoint needs)."""
    body = json.dumps(body_dict).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Algolia-API-Key": api_key,
            "X-Algolia-Application-Id": ALGOLIA_APP_ID,
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def discover_switch2_facet(url, api_key, facet_names=("platformCode", "platform", "corePlatforms")):
    """Ask Algolia for the full breakdown of candidate platform-ish facets
    (empty query = match everything) rather than guessing Nintendo's exact
    label for Switch 2. Returns (facet_name, value) or (None, None)."""
    result = _index_query(url, api_key, {
        "query": "",
        "hitsPerPage": 0,
        "facets": list(facet_names),
    })
    total = result.get("nbHits", 0)
    facets = result.get("facets", {})
    print(f"[{url}] nbHits={total} facets={ {k: v for k, v in facets.items()} }")

    for facet_name in facet_names:
        values = facets.get(facet_name, {})
        candidates = [k for k in values if "switch" in k.lower() and "2" in k]
        if candidates:
            best = max(candidates, key=lambda k: values[k])
            print(f"Using facet {facet_name!r} = {best!r} ({values[best]} hits) on {url}")
            return facet_name, best

    print(f"No Switch-2-shaped facet value found at {url}")
    return None, None


def fetch_by_facet(url, api_key, facet_name, value, hits_per_page=1000, max_pages=5):
    """Paginates through all hits matching a facet filter (up to max_pages
    safety cap)."""
    all_hits = []
    for page in range(max_pages):
        result = _index_query(url, api_key, {
            "query": "",
            "hitsPerPage": hits_per_page,
            "page": page,
            "facetFilters": [[f"{facet_name}:{value}"]],
        })
        hits = result.get("hits", [])
        all_hits.extend(hits)
        if page >= result.get("nbPages", 1) - 1 or not hits:
            break
    return all_hits


def pick_icon_field(hit):
    """The 'store_all_products' index doesn't necessarily use 'boxart' the
    way the old games-only index did (it covers hardware/merch too). Try
    known field names first, then fall back to scanning every field for
    anything that looks like a real image URL (starts with http, has an
    image extension) — maximizes the chance of finding it without needing
    another guess-and-check round trip."""
    for field in ("boxart", "productImage", "image", "thumbnailImage", "heroImage", "cardImage"):
        val = hit.get(field)
        if isinstance(val, str) and val.startswith("http"):
            return field, val

    image_exts = (".jpg", ".jpeg", ".png", ".webp")
    for key, val in hit.items():
        if isinstance(val, str) and val.startswith("http") and any(ext in val.lower() for ext in image_exts):
            return key, val

    return None, None


def switch2_supplement(existing_names):
    """Best-effort fetch of Switch 2 titles from Nintendo.com to backfill
    what titledb is missing. Returns [] on any failure (or if we can't
    confidently identify the right platform facet) rather than breaking
    the whole build — this is a supplement, not the primary source."""
    hits = []
    for url, key in ((NEW_INDEX_URL, NEW_INDEX_KEY), (OLD_INDEX_URL, OLD_INDEX_KEY)):
        try:
            facet_name, value = discover_switch2_facet(url, key)
            if not facet_name:
                continue
            hits = fetch_by_facet(url, key, facet_name, value)
            print(f"Fetched {len(hits)} hits for {facet_name}={value!r} from {url}")
            if hits:
                break
        except Exception as e:
            print(f"WARNING: query against {url} failed: {e}", file=sys.stderr)

    if not hits:
        print("Switch 2 supplement: no usable data found from any source, skipping")
        return []

    field_counts = {}
    for h in hits:
        field, _ = pick_icon_field(h)
        field_counts[field] = field_counts.get(field, 0) + 1
    print(f"Icon field usage across {len(hits)} hits: {field_counts}")
    if field_counts.get(None, 0) == len(hits):
        sample = hits[0]
        print("None of the known/guessed icon fields matched. Full keys on first hit:", sorted(sample.keys()))
        http_fields = {k: v for k, v in sample.items() if isinstance(v, str) and v.startswith("http")}
        print("All http(s)-looking string fields on first hit:", json.dumps(http_fields, indent=2))
        # These field names look image-related from the key list but didn't
        # pass the "starts with http" test — print their raw values (any
        # type) so we can see whether they're relative paths, slugs, or
        # nested objects that need different handling.
        for candidate in ("productImage", "productImageSquare", "productGallery", "eshopDetails", "editions"):
            if candidate in sample:
                print(f"Raw value of {candidate!r}: {json.dumps(sample[candidate], indent=2, default=str)[:1000]}")

    out = []
    skipped_no_icon = 0
    skipped_dupe = 0
    for h in hits:
        _, icon = pick_icon_field(h)
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
