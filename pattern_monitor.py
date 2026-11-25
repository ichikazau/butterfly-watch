import gzip
import math
import time
import urllib.error
import urllib.request

import ijson

LIS_SKINS_EXPORT = "https://lis-skins.com/market_export_json/api_csgo_full.json"
EXPORT_TRANSFER_TIMEOUT = 100
# Blue Gem picks combine collector guides with inspected playside coverage.
# https://steamcommunity.com/sharedfiles/filedetails/?id=3090086681
# https://skinrate.app/patterns/blue-gem
CASE_HARDENED_KNIVES = {
    "Bayonet": (555, 592),
    "Bowie Knife": (182, 398),
    "Classic Knife": (403, 585),
    "Falchion Knife": (494, 694),
    "Flip Knife": (670, 321),
    "Gut Knife": (567, 962),
    "Huntsman Knife": (618, 703),
    "Kukri Knife": (494, 770),
    "Navaja Knife": (398, 838),
    "Nomad Knife": (577, 456),
    "Paracord Knife": (403, 583),
    "Shadow Daggers": (56, 707),
    "Skeleton Knife": (403, 583),
    "Stiletto Knife": (182, 494),
    "Survival Knife": (403, 634),
    "Ursus Knife": (494, 618),
}
PATTERN_CATALOG = {
    **{
        f"★ {model} | Case Hardened": {seed: "Blue Gem" for seed in seeds}
        for model, seeds in CASE_HARDENED_KNIVES.items()
    },
    # https://skin.gallery/skin/navaja-knife-fade
    "★ Navaja Knife | Fade": {763: "100% Fade", 575: "99.99% Fade"},
    # https://steamcommunity.com/sharedfiles/filedetails/?id=3137163506
    "★ Gut Knife | Marble Fade": {412: "Fire & Ice 1st Max", 602: "Fire & Ice 2nd Max"},
    # https://steamcommunity.com/sharedfiles/filedetails/?id=2481147886
    "AK-47 | Case Hardened": {784: "Gold Gem", 219: "Gold Gem"},
    # https://steamcommunity.com/sharedfiles/filedetails/?id=2873225968
    "Five-SeveN | Case Hardened": {278: "Blue Gem", 670: "Blue Gem"},
    # https://cs2pattern-prices.com/weapons/mac-10/case-hardened/blue-gems-1
    "MAC-10 | Case Hardened": {95: "Blue Gem", 667: "Blue Gem"},
    # https://pricempire.com/guides/desert-eagle-heat-treated-guide
    "Desert Eagle | Heat Treated": {490: "Blue Gem", 148: "Blue Gem"},
    # https://skinrate.app/patterns/five-seven-heat-treated
    "Five-SeveN | Heat Treated": {904: "Blue Gem", 148: "Blue Gem"},
    # https://cs2pattern-prices.com/deep-dives/awp-paw-patterns
    "AWP | PAW": {420: "Stoner Cat", 41: "Golden Cat"},
    # https://steamcommunity.com/sharedfiles/filedetails/?id=3613249488
    "AWP | Electric Hive": {253: "Max Orange", 273: "Max Blue"},
    # https://cs2pattern-prices.com/deep-dives/m4a1-s-solitude-patterns
    "M4A1-S | Solitude": {12: "Golden Mountain", 379: "Golden Mountain"},
    # https://steamcommunity.com/sharedfiles/filedetails/?id=3474497759
    "XM1014 | Solitude": {95: "Golden Sun", 871: "Golden Sun"},
    # https://cs2pattern-prices.com/weapons/mac-10/snow-splash/max-white-1
    "MAC-10 | Snow Splash": {828: "Max White", 222: "Max White"},
    # https://steamcommunity.com/sharedfiles/filedetails/?id=3522993912
    "Galil AR | Sandstorm": {449: "Max White", 555: "Max White"},
    # https://steamcommunity.com/sharedfiles/filedetails/?id=2044221485
    "Five-SeveN | Kami": {909: "Редкий рисунок", 662: "Редкий рисунок"},
    # https://lis-skins.com/blog/the-ak-47-aphrodite-best-patterns-aphrodite-tier-list/
    "AK-47 | Aphrodite": {904: "Pink Gem", 948: "Pink Gem"},
    # https://steamcommunity.com/sharedfiles/filedetails/?id=3353615892
    "USP-S | Alpine Camo": {674: "Blue Gem", 490: "Blue Gem"},
    # https://steamcommunity.com/sharedfiles/filedetails/?id=2880283225
    "Glock-18 | Grinder": {916: "Full Black", 384: "Full Black"},
    # https://steamcommunity.com/sharedfiles/filedetails/?id=2844559383
    "Glock-18 | High Beam": {897: "Full Beam"},
    # https://steamcommunity.com/sharedfiles/filedetails/?id=3656899678
    "Glock-18 | Trace Lock": {679: "White Gem", 570: "White Gem"},
}

WEAR_NAMES = ("Factory New", "Minimal Wear", "Field-Tested", "Well-Worn", "Battle-Scarred")


def tracked_market_names():
    names = {}
    for base, seeds in PATTERN_CATALOG.items():
        if base.startswith("★ "):
            variants = (base, f"★ StatTrak™ {base[2:]}")
        else:
            variants = (base, f"StatTrak™ {base}", f"Souvenir {base}")
        for variant in variants:
            for wear in WEAR_NAMES:
                names[f"{variant} ({wear})"] = seeds
    return names


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
