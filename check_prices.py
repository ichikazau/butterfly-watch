#!/usr/bin/env python3
import json
import math
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal
from html import escape

from pattern_monitor import PATTERN_CATALOG, fetch_export_listings, tracked_market_names

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.json")
LIS_SKINS_FEED = "https://lis-skins.com/market_export_json/csgo.json"
CBR_RATE_URL = "https://www.cbr-xml-daily.ru/daily_json.js"
MAX_HISTORY_POINTS = 8064  # ~4 weeks at 5-minute intervals
PATTERN_TOP_COUNT = 5
PATTERN_PREMIUM_RUB = 3000
PATTERN_MAX_PRICE_RUB = 20000
PATTERN_ALERT_BATCH_SIZE = 20

# csmarketcap.com aggregates the same item's price across ~20-30 marketplaces.
# Checking all 186 tracked items there is heavy on their server, so it only
# runs every CSMARKETCAP_CHECK_INTERVAL_MINUTES (gated in main()) rather than
# on every 3-minute check.
CSMARKETCAP_BASE = "https://csmarketcap.com/ru/item"
CSMARKETCAP_CHECK_INTERVAL_MINUTES = 15  # cron fires on :00,:03,:06,... — all multiples of 15 line up
CSMARKETCAP_REQUEST_DELAY = 0.3  # seconds between requests, be polite
WEAR_SLUGS = {
    "Factory New": "factory-new",
    "Minimal Wear": "minimal-wear",
    "Field-Tested": "field-tested",
    "Well-Worn": "well-worn",
    "Battle-Scarred": "battle-scarred",
}

# slug -> exact item name as it appears in the lis-skins JSON feed
ITEMS = {
    "butterfly-doppler-p1-fn": "★ Butterfly Knife | Doppler Phase 1 (Factory New)",
    "butterfly-doppler-p2-fn": "★ Butterfly Knife | Doppler Phase 2 (Factory New)",
    "butterfly-doppler-p4-fn": "★ Butterfly Knife | Doppler Phase 4 (Factory New)",
    "karambit-doppler-p2-fn": "★ Karambit | Doppler Phase 2 (Factory New)",
    "karambit-gamma-doppler-p1-fn": "★ Karambit | Gamma Doppler Phase 1 (Factory New)",
    "karambit-gamma-doppler-p2-fn": "★ Karambit | Gamma Doppler Phase 2 (Factory New)",
    "karambit-gamma-doppler-p3-fn": "★ Karambit | Gamma Doppler Phase 3 (Factory New)",
    "karambit-gamma-doppler-p4-fn": "★ Karambit | Gamma Doppler Phase 4 (Factory New)",
    # Butterfly Knife
    "slaughter-ft": "★ Butterfly Knife | Slaughter (Field-Tested)",
    "slaughter-mw": "★ Butterfly Knife | Slaughter (Minimal Wear)",
    "slaughter-fn": "★ Butterfly Knife | Slaughter (Factory New)",
    "autotronic-ft": "★ Butterfly Knife | Autotronic (Field-Tested)",
    "tiger-tooth-fn": "★ Butterfly Knife | Tiger Tooth (Factory New)",
    "gamma-doppler-p4-mw": "★ Butterfly Knife | Gamma Doppler Phase 4 (Minimal Wear)",
    "gamma-doppler-p4-fn": "★ Butterfly Knife | Gamma Doppler Phase 4 (Factory New)",
    "gamma-doppler-p2-mw": "★ Butterfly Knife | Gamma Doppler Phase 2 (Minimal Wear)",
    "gamma-doppler-p2-fn": "★ Butterfly Knife | Gamma Doppler Phase 2 (Factory New)",
    "gamma-doppler-p3-fn": "★ Butterfly Knife | Gamma Doppler Phase 3 (Factory New)",
    "gamma-doppler-p1-fn": "★ Butterfly Knife | Gamma Doppler Phase 1 (Factory New)",
    "doppler-p3-fn": "★ Butterfly Knife | Doppler Phase 3 (Factory New)",
    "fade-fn": "★ Butterfly Knife | Fade (Factory New)",
    # Karambit
    "karambit-doppler-phase-1-fn": "★ Karambit | Doppler Phase 1 (Factory New)",
    "karambit-doppler-phase-3-fn": "★ Karambit | Doppler Phase 3 (Factory New)",
    "karambit-doppler-phase-3-mw": "★ Karambit | Doppler Phase 3 (Minimal Wear)",
    "karambit-doppler-phase-4-fn": "★ Karambit | Doppler Phase 4 (Factory New)",
    "karambit-doppler-phase-4-mw": "★ Karambit | Doppler Phase 4 (Minimal Wear)",
    "karambit-marble-fade-fn": "★ Karambit | Marble Fade (Factory New)",
    "karambit-marble-fade-mw": "★ Karambit | Marble Fade (Minimal Wear)",
    "karambit-slaughter-fn": "★ Karambit | Slaughter (Factory New)",
    "karambit-slaughter-ft": "★ Karambit | Slaughter (Field-Tested)",
    "karambit-slaughter-mw": "★ Karambit | Slaughter (Minimal Wear)",
    "karambit-tiger-tooth-fn": "★ Karambit | Tiger Tooth (Factory New)",
    "karambit-tiger-tooth-mw": "★ Karambit | Tiger Tooth (Minimal Wear)",
    # Butterfly Knife | Freehand
    "butterfly-knife-freehand-fn": "★ Butterfly Knife | Freehand (Factory New)",
    "butterfly-knife-freehand-ft": "★ Butterfly Knife | Freehand (Field-Tested)",
    "butterfly-knife-freehand-mw": "★ Butterfly Knife | Freehand (Minimal Wear)",
    # Talon Knife
    "talon-knife-fade-fn": "★ Talon Knife | Fade (Factory New)",
    # AK-47 (selected skins, 3000-40000₽, FN/MW/FT, no StatTrak)
    "ak-47-aquamarine-revenge-fn": "AK-47 | Aquamarine Revenge (Factory New)",
    "ak-47-aquamarine-revenge-mw": "AK-47 | Aquamarine Revenge (Minimal Wear)",
    "ak-47-b-the-monster-fn": "AK-47 | B the Monster (Factory New)",
    "ak-47-b-the-monster-ft": "AK-47 | B the Monster (Field-Tested)",
    "ak-47-b-the-monster-mw": "AK-47 | B the Monster (Minimal Wear)",
    "ak-47-bloodsport-fn": "AK-47 | Bloodsport (Factory New)",
    "ak-47-bloodsport-ft": "AK-47 | Bloodsport (Field-Tested)",
    "ak-47-bloodsport-mw": "AK-47 | Bloodsport (Minimal Wear)",
    "ak-47-inheritance-fn": "AK-47 | Inheritance (Factory New)",
    "ak-47-inheritance-mw": "AK-47 | Inheritance (Minimal Wear)",
    "ak-47-neon-rider-fn": "AK-47 | Neon Rider (Factory New)",
    "ak-47-neon-rider-ft": "AK-47 | Neon Rider (Field-Tested)",
    "ak-47-neon-rider-mw": "AK-47 | Neon Rider (Minimal Wear)",
    "ak-47-point-disarray-fn": "AK-47 | Point Disarray (Factory New)",
    "ak-47-the-empress-fn": "AK-47 | The Empress (Factory New)",
    "ak-47-the-empress-ft": "AK-47 | The Empress (Field-Tested)",
    "ak-47-the-empress-mw": "AK-47 | The Empress (Minimal Wear)",
    "ak-47-vulcan-ft": "AK-47 | Vulcan (Field-Tested)",
    "ak-47-vulcan-mw": "AK-47 | Vulcan (Minimal Wear)",
}


def fetch_json(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "butterfly-watch/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def csmarketcap_slug(match_name):
    """'★ StatTrak™ Karambit | Doppler Phase 1 (Factory New)' ->
    ('stattrak-karambit-doppler-phase-1', 'factory-new')"""
    name = match_name.replace("★", "").strip()
    stattrak = name.startswith("StatTrak")
    name = name.replace("StatTrak™", "").strip()
    weapon, rest = name.split("|", 1)
    m = re.match(r"^(.*)\((.*)\)\s*$", rest.strip())
    skin, wear = m.group(1).strip(), m.group(2).strip()
    base = re.sub(r"[^a-z0-9]+", "-", f"{weapon.strip()} {skin}".lower()).strip("-")
    item_slug = ("stattrak-" if stattrak else "") + base
    return item_slug, WEAR_SLUGS.get(wear, wear.lower())


def _resolve_nuxt_ref(data, value, depth=0):
    """Nuxt's __NUXT_DATA__ payload dedupes strings/objects/arrays into one
    flat array and replaces repeated occurrences with an index into it."""
    if depth > 6:
        return value
    if isinstance(value, int) and 0 <= value < len(data):
        target = data[value]
        if isinstance(target, (dict, list, str)):
            return _resolve_nuxt_ref(data, target, depth + 1)
        return target
    if isinstance(value, dict):
        return {k: _resolve_nuxt_ref(data, v, depth + 1) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_nuxt_ref(data, v, depth + 1) for v in value]
    return value


def fetch_csmarketcap_offers(item_slug, wear_slug, timeout=20):
    """Returns {market_name: price_usd, ...} for one item page, or None if
    the page couldn't be parsed (item not listed there, layout change, etc.)."""
    url = f"{CSMARKETCAP_BASE}/{item_slug}/{wear_slug}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (butterfly-watch)"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        html = resp.read().decode("utf-8")

    m = re.search(r'<script[^>]*id="__NUXT_DATA__"[^>]*>', html)
    if not m:
        return None
    end = html.find("</script>", m.end())
    data = json.loads(html[m.end():end])

    root = next((v for v in data if isinstance(v, dict) and "markets_offers" in v), None)
    if root is None:
        return None
    offers = _resolve_nuxt_ref(data, root["markets_offers"])
    return {
        o["market_name"]: o["price"] / 1000
        for o in offers
        if isinstance(o, dict) and o.get("market_name") and o.get("price") is not None
    }


def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"items": {}, "usd_rub": {"history": []}, "last_updated": None}


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def trim(history):
    if len(history) > MAX_HISTORY_POINTS:
        del history[: len(history) - MAX_HISTORY_POINTS]


def send_telegram(text):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    recipients = list(dict.fromkeys(
        chat.strip() for value in (
            os.environ.get("TELEGRAM_CHAT_ID", ""),
            os.environ.get("TELEGRAM_EXTRA_CHAT_IDS", ""),
        ) for chat in value.split(",") if chat.strip()
    ))
    if not token or not recipients:
        print("Telegram secrets not set, skipping notification", file=sys.stderr)
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    delivered = False
    for number, chat_id in enumerate(recipients, 1):
        payload = json.dumps({
            "chat_id": chat_id, "text": text, "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }).encode("utf-8")
        req = urllib.request.Request(
            url, data=payload, headers={"Content-Type": "application/json"}, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read())
                if result.get("ok"):
                    delivered = True
                else:
                    print(f"Telegram recipient {number}: API rejected message", file=sys.stderr)
        except Exception as exc:
            print(f"Telegram recipient {number}: {type(exc).__name__}", file=sys.stderr)
    return delivered


def fetch_pattern_snapshot(previous, now):
    names = tracked_market_names()
    # JSON object keys are strings after reading the previous snapshot.
    catalog = {
        name: {str(seed): label for seed, label in seeds.items()}
        for name, seeds in PATTERN_CATALOG.items()
    }
    started = time.monotonic()
    cached_etag = previous.get("etag") if previous.get("catalog") == catalog else None
    listings, etag = fetch_export_listings(names, cached_etag)

    if listings is None:
        print("LIS-SKINS listing export is unchanged")
        return previous

    pattern_offers = {}
    for name, offers in listings.items():
        seeds = names[name]
        matches = [
            {**lot, "rank": rank, "label": seeds[lot["item_paint_seed"]]}
            for rank, lot in enumerate(offers, 1)
            if lot["item_paint_seed"] in seeds
        ]
        if matches:
            pattern_offers[name] = {"floor_price": offers[0]["price"], "lots": matches}

    market_variants = sum(bool(offers) for offers in listings.values())
    match_count = sum(len(group["lots"]) for group in pattern_offers.values())
    print(
        f"LIS-SKINS listing check took {time.monotonic() - started:.1f}s"
        f" ({market_variants} variants, {match_count} rare lots before price limits)"
    )
    return {
        "etag": etag,
        "checked_at": now,
        "catalog": catalog,
        "market_variants": market_variants,
        "pattern_offers": pattern_offers,
    }


def eligible_pattern_offers(group, rub_per_dollar):
    floor = Decimal(str(group["floor_price"]))
    for lot in group["lots"]:
        price = Decimal(str(lot["price"]))
        price_rub = price * rub_per_dollar
        premium = (price - floor) * rub_per_dollar
        if price_rub <= PATTERN_MAX_PRICE_RUB and (
            lot["rank"] <= PATTERN_TOP_COUNT or premium <= PATTERN_PREMIUM_RUB
        ):
            yield lot, price_rub, premium


def notify_pattern_matches(data, snapshot, usd_rate, market):
    if type(usd_rate) not in (float, int) or not math.isfinite(usd_rate) or usd_rate <= 0:
        print("Skipping pattern alerts without a valid USD/RUB rate", file=sys.stderr)
        return

    rub_per_dollar = Decimal(str(usd_rate))
    previous = data.get("notified_top_patterns", {})
    notified = {}
    for name, group in snapshot["pattern_offers"].items():
        active_ids = {lot["id"] for lot in group["lots"]}
        delivered = active_ids.intersection(previous.get(name, ()))
        pending = []
        for lot, price_rub, premium in eligible_pattern_offers(group, rub_per_dollar):
            if lot["id"] in delivered:
                continue

            line = (
                f"<b>{escape(lot['label'])} #{lot['item_paint_seed']}</b>"
                f" · ≈ {price_rub:,.0f} ₽ (${lot['price']:.2f})"
                f" · #{lot['rank']} по цене · +{premium:,.0f} ₽ к минимуму"
                f" · лот {lot['id']}"
            ).replace(",", " ")
            pending.append((lot["id"], line))

        url = market.get(name, {}).get("url")
        title = "🦋 <b>Butterfly Watch: подходящий паттерн</b>"
        for start in range(0, len(pending), PATTERN_ALERT_BATCH_SIZE):
            batch = pending[start:start + PATTERN_ALERT_BATCH_SIZE]
            lines = [line for _, line in batch]
            message = "\n".join([title, f"<b>{escape(name)}</b>", *lines])
            if url:
                message += f"\n{escape(url)}"
            if send_telegram(message):
                delivered.update(lot_id for lot_id, _ in batch)
                print(f"Sent pattern alert for {name} ({len(batch)} lots)")
        if delivered:
            notified[name] = sorted(delivered)
    data["notified_top_patterns"] = notified


def main():
    now_dt = datetime.now(timezone.utc)
    now = now_dt.isoformat(timespec="seconds").replace("+00:00", "Z")
    check_csmarketcap = now_dt.minute % CSMARKETCAP_CHECK_INTERVAL_MINUTES == 0

    data = load_data()
    data.setdefault("items", {})
    data["items"] = {slug: item for slug, item in data["items"].items() if slug in ITEMS}
    data.setdefault("usd_rub", {"history": []})

    try:
        feed = fetch_json(LIS_SKINS_FEED)
    except Exception as e:
        print(f"Failed to fetch lis-skins feed: {e}", file=sys.stderr)
        sys.exit(1)
    by_name = {entry["name"]: entry for entry in feed}

    pattern_snapshot = None
    try:
        pattern_snapshot = fetch_pattern_snapshot(data.get("pattern_snapshot", {}), now)
    except Exception as exc:
        print(f"WARNING: LIS-SKINS pattern check failed ({type(exc).__name__})", file=sys.stderr)

    try:
        cbr = fetch_json(CBR_RATE_URL)
        usd_rate = cbr["Valute"]["USD"]["Value"]
        if type(usd_rate) not in (int, float) or not math.isfinite(usd_rate) or usd_rate <= 0:
            raise ValueError("invalid USD/RUB rate")
    except Exception as e:
        print(f"Failed to fetch USD/RUB rate: {e}", file=sys.stderr)
        usd_rate = None

    rate_history = data["usd_rub"]["history"]
    if usd_rate is not None:
        rate_history.append({"t": now, "rate": usd_rate})
        trim(rate_history)

    for slug, match_name in ITEMS.items():
        entry = by_name.get(match_name)
        item_data = data["items"].setdefault(slug, {
            "name": match_name,
            "url": None,
            "history": [],
        })
        item_data["name"] = match_name

        if entry is None:
            print(f"WARNING: item not found in feed: {match_name}", file=sys.stderr)
            continue

        item_data["url"] = entry.get("url")
        price = entry["price"]
        history = item_data["history"]

        history.append({"t": now, "price": price})
        trim(history)

        if check_csmarketcap:
            item_slug, wear_slug = csmarketcap_slug(match_name)
            csmc_url = f"{CSMARKETCAP_BASE}/{item_slug}/{wear_slug}"
            try:
                offers = fetch_csmarketcap_offers(item_slug, wear_slug)
                others = {m: p for m, p in (offers or {}).items() if m != "lis-skins"}
                if others:
                    min_market, min_price = min(others.items(), key=lambda kv: kv[1])
                    is_cheapest = price < min_price
                    item_data["csmarketcap"] = {
                        "min_price": min_price,
                        "min_market": min_market,
                        "lis_cheapest": is_cheapest,
                        "url": csmc_url,
                        "checked_at": now,
                    }
                else:
                    print(f"WARNING: no csmarketcap offers for {match_name}", file=sys.stderr)
            except Exception as e:
                print(f"WARNING: csmarketcap check failed for {match_name}: {e}", file=sys.stderr)
            time.sleep(CSMARKETCAP_REQUEST_DELAY)

    if pattern_snapshot is not None:
        data["pattern_snapshot"] = pattern_snapshot
        last_rate = rate_history[-1]["rate"] if rate_history else None
        notify_pattern_matches(data, pattern_snapshot, last_rate, by_name)

    data["last_updated"] = now
    save_data(data)

if __name__ == "__main__":
    main()
