import gzip
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request

import ijson

LIS_SKINS_SEARCH = "https://api.lis-skins.com/v1/market/search"
LIS_SKINS_EXPORT = "https://lis-skins.com/market_export_json/api_csgo_full.json"
EXPORT_TRANSFER_TIMEOUT = 100
TALON_FADE_SEEDS = {
    16, 129, 146, 152, 241, 281, 292, 332, 344, 359, 393, 412,
    541, 602, 628, 649, 673, 688, 701, 743, 777, 792, 918, 994,
}
# https://pricempire.com/guides/karambit-doppler-phase-1-guide
KARAMBIT_TIER_ONE_SEEDS = {
    31, 49, 88, 98, 106, 113, 135, 190, 196, 217, 218, 220, 226,
    253, 262, 296, 311, 354, 384, 387, 409, 445, 530, 540, 547,
    552, 574, 594, 606, 610, 630, 717, 730, 746, 783, 812, 858,
    939, 972, 989, 998,
}
KARAMBIT_PINK_SEEDS = {129, 281, 602, 673, 908}


def _listing_fields(listing):
    listing_id = listing.get("id")
    price = listing.get("price")
    if type(listing_id) is not int or listing_id <= 0:
        raise ValueError("Invalid LIS-SKINS listing ID")
    if type(price) not in (int, float) or not math.isfinite(price) or price <= 0:
        raise ValueError("Invalid LIS-SKINS listing price")

    seed = listing.get("item_paint_seed")
    if type(seed) is not int or not 0 <= seed <= 1000:
        seed = None
    return listing_id, price, seed


def _sorted_listings(listings):
    return {
        name: sorted(by_id.values(), key=lambda listing: (listing["price"], listing["id"]))
        for name, by_id in listings.items()
    }


def fetch_pattern_listings(api_key, names):
    """Fetch exact LIS-SKINS listings in ascending price and ID order."""
    listings = {name: {} for name in names}
    if not listings:
        return {}

    query = [("game", "csgo"), *(("names[]", name) for name in listings)]
    cursor_params = []
    seen_cursors = set()

    while True:
        request = urllib.request.Request(
            f"{LIS_SKINS_SEARCH}?{urllib.parse.urlencode(query + cursor_params)}",
            headers={"Accept": "application/json", "User-Agent": "butterfly-watch/1.0"},
        )
        request.add_unredirected_header("Authorization", f"Bearer {api_key}")
        with urllib.request.urlopen(request, timeout=12) as response:
            page = json.load(response)

        if not isinstance(page, dict) or not isinstance(page.get("data"), list):
            raise ValueError("Invalid LIS-SKINS search response")
        meta = page.get("meta", {})
        if not isinstance(meta, dict):
            raise ValueError("Invalid LIS-SKINS search metadata")

        for listing in page["data"]:
            if not isinstance(listing, dict):
                raise ValueError("Invalid LIS-SKINS listing")
            name = listing.get("name")
            if name not in listings:
                continue

            listing_id, _, seed = _listing_fields(listing)
            listings[name][listing_id] = {
                **listing,
                "item_paint_seed": seed,
                "item_float": _listing_wear(listing.get("item_float")),
            }

        cursor = meta.get("next_cursor")
        if not cursor:
            break
        if cursor in seen_cursors:
            raise ValueError("Repeated LIS-SKINS search cursor")
        seen_cursors.add(cursor)
        cursor_params = [("cursor", cursor)]

    return _sorted_listings(listings)


class _TimedExportStream:
    def __init__(self, response, deadline):
        self.response = response
        self.deadline = deadline

    def read(self, size=-1):
        if time.monotonic() >= self.deadline:
            raise TimeoutError("LIS-SKINS export transfer exceeded its time budget")
        # Read at most one socket chunk so a slow response cannot hide inside a
        # large decompressor read for the entire transfer.
        return self.response.read1(size)


def _validated_export_events(stream):
    success = False
    has_items = False
    for prefix, event, value in ijson.parse(stream, use_float=True):
        if prefix == "status":
            if event != "string" or value != "success":
                raise ValueError("LIS-SKINS reported an unsuccessful export")
            success = True
        elif prefix == "items" and event == "start_array":
            has_items = True
        yield prefix, event, value
    if not success or not has_items:
        raise ValueError("Invalid LIS-SKINS export envelope")


def _listing_wear(value):
    if type(value) not in (int, float, str):
        return None
    try:
        wear = float(value)
    except (ValueError, OverflowError):
        return None
    return wear if 0 <= wear <= 1 else None


def fetch_export_listings(names, etag=None):
    """Stream the public export and retain only the requested listings.

    A 304 returns ``(None, etag)`` so callers can reuse their filtered snapshot.
    """
    listings = {name: {} for name in names}
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "User-Agent": "butterfly-watch/1.0",
    }
    if etag is not None:
        headers["If-None-Match"] = etag
    request = urllib.request.Request(LIS_SKINS_EXPORT, headers=headers)
    deadline = time.monotonic() + EXPORT_TRANSFER_TIMEOUT
    try:
        response = urllib.request.urlopen(request, timeout=15)
    except urllib.error.HTTPError as exc:
        if exc.code != 304:
            raise
        with exc:
            return None, exc.headers.get("ETag", etag)

    with response:
        if response.headers.get("Content-Encoding", "").lower() != "gzip":
            raise ValueError("LIS-SKINS export is missing gzip encoding")
        timed_stream = _TimedExportStream(response, deadline)
        with gzip.GzipFile(fileobj=timed_stream) as stream:
            for listing in ijson.items(_validated_export_events(stream), "items.item"):
                if not isinstance(listing, dict) or not isinstance(listing.get("name"), str):
                    raise ValueError("Invalid LIS-SKINS export listing")
                name = listing["name"]
                if name in listings:
                    listing_id, price, seed = _listing_fields(listing)
                    listings[name][listing_id] = {
                        "id": listing_id,
                        "price": price,
                        "item_paint_seed": seed,
                        "item_float": _listing_wear(listing.get("item_float")),
                    }
        return _sorted_listings(listings), response.headers.get("ETag")


def pattern_label(slug, seed):
    if slug == "talon-knife-fade-fn" and seed in TALON_FADE_SEEDS:
        return "ЭТАЛОННЫЙ СИД" if seed == 412 else "100% Fade"

    if slug == "karambit-doppler-phase-1-fn":
        if seed in KARAMBIT_PINK_SEEDS:
            return "Розовый паттерн"
        if seed in KARAMBIT_TIER_ONE_SEEDS:
            return "Fake Black Pearl (Tier 1)"
        if seed == 711:
            return "Fake Black Pearl"

    return None
