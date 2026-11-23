#!/usr/bin/env python3
import json
import math
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from pattern_monitor import fetch_export_listings, fetch_pattern_listings, pattern_label

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.json")
LIS_SKINS_FEED = "https://lis-skins.com/market_export_json/csgo.json"
CBR_RATE_URL = "https://www.cbr-xml-daily.ru/daily_json.js"
PREV_CHECK_DROP_THRESHOLD = 0.05  # 5% drop since the previous check (rises are not alerted on)
MIN_HISTORY_AGE_FOR_MIN_ALERT = timedelta(hours=24)  # new items haven't set a meaningful low yet
MAX_HISTORY_POINTS = 8064  # ~4 weeks at 5-minute intervals
TALON_FADE_SLUG = "talon-knife-fade-fn"
PATTERN_SLUGS = (TALON_FADE_SLUG, "karambit-doppler-phase-1-fn")
PATTERN_TOP_COUNT = 5
PATTERN_PREMIUM_RUB = 1500
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


def pattern_listing_text(lot, label):
    wear = lot.get("item_float")
    float_text = f" · float {wear:.8f}" if wear is not None else ""
    return f"<b>{label} #{lot['item_paint_seed']}</b> · ${lot['price']:.2f}{float_text} · лот {lot['id']}"


def talon_pattern_notes(listings):
    matches = {}
    for lot in listings:
        seed = lot["item_paint_seed"]
        label = pattern_label(TALON_FADE_SLUG, seed)
        if label and seed not in matches:
            matches[seed] = pattern_listing_text(lot, label)
    reference = matches.pop(412, None)
    notes = list(matches.values())
    if reference:
        notes.insert(0, reference)
    return ["В продаже на LIS-SKINS:", *notes] if notes else []


def compact_offer(lot):
    return {field: lot.get(field) for field in ("id", "price", "item_paint_seed", "item_float")}


def fetch_pattern_snapshot(previous):
    names = [ITEMS[slug] for slug in PATTERN_SLUGS]
    tracked_seeds = {
        slug: [seed for seed in range(1001) if pattern_label(slug, seed) is not None]
        for slug in PATTERN_SLUGS
    }
    started = time.monotonic()
    api_key = os.environ.get("LIS_SKINS_API_KEY")
    if api_key:
        listings = fetch_pattern_listings(api_key, names)
        etag = None
    else:
        cached_etag = previous.get("etag") if previous.get("tracked_seeds") == tracked_seeds else None
        listings, etag = fetch_export_listings(names, cached_etag)

    if listings is None:
        print("LIS-SKINS listing export is unchanged")
        return previous

    top_offers = {
        slug: [compact_offer(lot) for lot in listings[ITEMS[slug]][:PATTERN_TOP_COUNT]]
        for slug in PATTERN_SLUGS
    }
    pattern_offers = {
        slug: [
            {"rank": rank, **compact_offer(lot)}
            for rank, lot in enumerate(listings[ITEMS[slug]], 1)
            if pattern_label(slug, lot["item_paint_seed"]) is not None
        ]
        for slug in PATTERN_SLUGS
    }
    for slug, offers in top_offers.items():
        ranks = ", ".join(
            f"#{rank} ${lot['price']:.2f} seed {lot['item_paint_seed']}"
            for rank, lot in enumerate(offers, 1)
        )
        print(f"LIS-SKINS {ITEMS[slug]}: {ranks or 'no offers'}")
    print(f"LIS-SKINS listing check took {time.monotonic() - started:.1f}s")
    return {
        "etag": etag,
        "tracked_seeds": tracked_seeds,
        "top_offers": top_offers,
        "pattern_offers": pattern_offers,
        "talon_notes": talon_pattern_notes(listings[ITEMS[TALON_FADE_SLUG]]),
    }


def notify_pattern_matches(data, snapshot, usd_rate):
    notified = data.setdefault("notified_top_patterns", {})
    rub_per_dollar = Decimal(str(usd_rate)) if usd_rate is not None else None
    for slug, offers in snapshot["pattern_offers"].items():
        if not offers:
            notified[slug] = []
            continue

        name = ITEMS[slug]
        floor = Decimal(str(snapshot["top_offers"][slug][0]["price"]))
        previous = set(notified.get(slug, []))
        delivered = set()
        pending = []
        for lot in offers:
            lot_id = lot["id"]
            rank = lot["rank"]
            premium = (
                (Decimal(str(lot["price"])) - floor) * rub_per_dollar
                if rub_per_dollar is not None else None
            )
            if rank > PATTERN_TOP_COUNT and (premium is None or premium > PATTERN_PREMIUM_RUB):
                if premium is None and lot_id in previous:
                    delivered.add(lot_id)
                continue
            if lot_id in previous:
                delivered.add(lot_id)
                continue

            label = pattern_label(slug, lot["item_paint_seed"])
            premium_text = f" · ≈ +{premium:.0f} ₽ к минимуму" if premium is not None else ""
            line = f"#{rank} по цене · {pattern_listing_text(lot, label)}{premium_text}"
            pending.append((lot_id, line))

        url = data["items"].get(slug, {}).get("url") or ""
        title = "🦋 <b>Butterfly Watch: подходящий паттерн</b>"
        for start in range(0, len(pending), PATTERN_ALERT_BATCH_SIZE):
            batch = pending[start:start + PATTERN_ALERT_BATCH_SIZE]
            lines = [line for _, line in batch]
            message = "\n".join([title, f"<b>{name}</b>", *lines, url])
            if send_telegram(message):
                delivered.update(lot_id for lot_id, _ in batch)
                print(f"Sent pattern alert for {name} ({len(batch)} lots)")
        notified[slug] = sorted(delivered)


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
        pattern_snapshot = fetch_pattern_snapshot(data.get("pattern_snapshot", {}))
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

    alerts = []

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

        prev_min = min((h["price"] for h in history), default=None)
        prev_price = history[-1]["price"] if history else None
        first_ts = history[0]["t"] if history else None

        history.append({"t": now, "price": price})
        trim(history)

        reasons = []

        history_age = (
            now_dt - datetime.fromisoformat(first_ts.replace("Z", "+00:00"))
            if first_ts else timedelta(0)
        )
        if (
            prev_min is not None and price < prev_min
            and history_age >= MIN_HISTORY_AGE_FOR_MIN_ALERT
        ):
            drop_pct = (1 - price / prev_min) * 100
            reasons.append(f"\U0001F4C9 новый исторический минимум: ниже прошлого на {drop_pct:.1f}% (было ${prev_min:.2f})")

        if prev_price is not None and prev_price > 0:
            change_pct = (price - prev_price) / prev_price * 100
            if change_pct <= -PREV_CHECK_DROP_THRESHOLD * 100:
                reasons.append(f"\U0001F53B падение за одну проверку: {change_pct:.1f}% (было ${prev_price:.2f})")

        if check_csmarketcap:
            item_slug, wear_slug = csmarketcap_slug(match_name)
            csmc_url = f"{CSMARKETCAP_BASE}/{item_slug}/{wear_slug}"
            was_cheapest = item_data.get("csmarketcap", {}).get("lis_cheapest", False)
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
                    if is_cheapest and not was_cheapest:
                        reasons.append(
                            f"\U0001F3C6 lis-skins сейчас дешевле всех маркетплейсов "
                            f"(следующий — ${min_price:.2f} на {min_market})"
                        )
                else:
                    print(f"WARNING: no csmarketcap offers for {match_name}", file=sys.stderr)
            except Exception as e:
                print(f"WARNING: csmarketcap check failed for {match_name}: {e}", file=sys.stderr)
            time.sleep(CSMARKETCAP_REQUEST_DELAY)

        if reasons and slug in PATTERN_SLUGS:
            if slug == TALON_FADE_SLUG and pattern_snapshot is not None:
                reasons.extend(pattern_snapshot["talon_notes"])
            alerts.append(
                f"<b>{match_name}</b>\n"
                f"Цена: <b>${price:.2f}</b>\n"
                + "\n".join(reasons) + "\n"
                f"{entry.get('url', '')}"
            )

    if pattern_snapshot is not None:
        data["pattern_snapshot"] = pattern_snapshot
        last_rate = rate_history[-1]["rate"] if rate_history else None
        notify_pattern_matches(data, pattern_snapshot, last_rate)

    data["last_updated"] = now
    save_data(data)

    if alerts:
        message = "\U0001F98B <b>Butterfly Watch: изменение цены!</b>\n\n" + "\n\n".join(alerts)
        if send_telegram(message):
            print(f"Sent {len(alerts)} alert(s)")
    else:
        print("No price drops detected")


if __name__ == "__main__":
    main()
