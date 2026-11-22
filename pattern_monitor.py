import json
import math
import urllib.parse
import urllib.request

LIS_SKINS_SEARCH = "https://api.lis-skins.com/v1/market/search"
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

            listing_id = listing.get("id")
            price = listing.get("price")
            if type(listing_id) is not int or listing_id <= 0:
                raise ValueError("Invalid LIS-SKINS listing ID")
            if type(price) not in (int, float) or not math.isfinite(price) or price <= 0:
                raise ValueError("Invalid LIS-SKINS listing price")

            seed = listing.get("item_paint_seed")
            if type(seed) is not int or not 0 <= seed <= 1000:
                seed = None
            listings[name][listing_id] = {**listing, "item_paint_seed": seed}

        cursor = meta.get("next_cursor")
        if not cursor:
            break
        if cursor in seen_cursors:
            raise ValueError("Repeated LIS-SKINS search cursor")
        seen_cursors.add(cursor)
        cursor_params = [("cursor", cursor)]

    return {
        name: sorted(by_id.values(), key=lambda listing: (listing["price"], listing["id"]))
        for name, by_id in listings.items()
    }


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
