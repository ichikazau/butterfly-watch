#!/usr/bin/env python3
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.json")
LIS_SKINS_FEED = "https://lis-skins.com/market_export_json/csgo.json"
CBR_RATE_URL = "https://www.cbr-xml-daily.ru/daily_json.js"
DROP_THRESHOLD = 0.05  # 5% below the historical minimum
LAST_CHECK_THRESHOLD = 0.07  # 7% move (either direction) since the previous check
MAX_HISTORY_POINTS = 8064  # ~4 weeks at 5-minute intervals

# slug -> exact item name as it appears in the lis-skins JSON feed
ITEMS = {
    # Butterfly Knife
    "slaughter-mw": "★ Butterfly Knife | Slaughter (Minimal Wear)",
    "slaughter-fn": "★ Butterfly Knife | Slaughter (Factory New)",
    "autotronic-ft": "★ Butterfly Knife | Autotronic (Field-Tested)",
    "tiger-tooth-fn": "★ Butterfly Knife | Tiger Tooth (Factory New)",
    "gamma-doppler-p4-mw": "★ Butterfly Knife | Gamma Doppler Phase 4 (Minimal Wear)",
    "gamma-doppler-p4-fn": "★ Butterfly Knife | Gamma Doppler Phase 4 (Factory New)",
    "gamma-doppler-p3-fn": "★ Butterfly Knife | Gamma Doppler Phase 3 (Factory New)",
    "gamma-doppler-p1-fn": "★ Butterfly Knife | Gamma Doppler Phase 1 (Factory New)",
    "doppler-p3-fn": "★ Butterfly Knife | Doppler Phase 3 (Factory New)",
    "fade-fn": "★ Butterfly Knife | Fade (Factory New)",
    # Skeleton Knife
    "skeleton-knife-doppler-phase-1-fn": "★ Skeleton Knife | Doppler Phase 1 (Factory New)",
    "skeleton-knife-doppler-phase-1-mw": "★ Skeleton Knife | Doppler Phase 1 (Minimal Wear)",
    "skeleton-knife-doppler-phase-2-fn": "★ Skeleton Knife | Doppler Phase 2 (Factory New)",
    "skeleton-knife-doppler-phase-2-mw": "★ Skeleton Knife | Doppler Phase 2 (Minimal Wear)",
    "skeleton-knife-doppler-phase-3-fn": "★ Skeleton Knife | Doppler Phase 3 (Factory New)",
    "skeleton-knife-doppler-phase-3-mw": "★ Skeleton Knife | Doppler Phase 3 (Minimal Wear)",
    "skeleton-knife-doppler-phase-4-fn": "★ Skeleton Knife | Doppler Phase 4 (Factory New)",
    "skeleton-knife-doppler-sapphire-fn": "★ Skeleton Knife | Doppler Sapphire (Factory New)",
    "skeleton-knife-fade-fn": "★ Skeleton Knife | Fade (Factory New)",
    "skeleton-knife-fade-mw": "★ Skeleton Knife | Fade (Minimal Wear)",
    "skeleton-knife-marble-fade-fn": "★ Skeleton Knife | Marble Fade (Factory New)",
    "skeleton-knife-marble-fade-mw": "★ Skeleton Knife | Marble Fade (Minimal Wear)",
    "skeleton-knife-slaughter-fn": "★ Skeleton Knife | Slaughter (Factory New)",
    "skeleton-knife-slaughter-ft": "★ Skeleton Knife | Slaughter (Field-Tested)",
    "skeleton-knife-slaughter-mw": "★ Skeleton Knife | Slaughter (Minimal Wear)",
    "skeleton-knife-tiger-tooth-fn": "★ Skeleton Knife | Tiger Tooth (Factory New)",
    "skeleton-knife-tiger-tooth-mw": "★ Skeleton Knife | Tiger Tooth (Minimal Wear)",
    "skeleton-knife-doppler-phase-1-st-fn": "★ StatTrak™ Skeleton Knife | Doppler Phase 1 (Factory New)",
    "skeleton-knife-doppler-phase-2-st-fn": "★ StatTrak™ Skeleton Knife | Doppler Phase 2 (Factory New)",
    "skeleton-knife-doppler-phase-3-st-fn": "★ StatTrak™ Skeleton Knife | Doppler Phase 3 (Factory New)",
    "skeleton-knife-doppler-phase-4-st-fn": "★ StatTrak™ Skeleton Knife | Doppler Phase 4 (Factory New)",
    "skeleton-knife-doppler-phase-4-st-mw": "★ StatTrak™ Skeleton Knife | Doppler Phase 4 (Minimal Wear)",
    "skeleton-knife-doppler-sapphire-st-fn": "★ StatTrak™ Skeleton Knife | Doppler Sapphire (Factory New)",
    "skeleton-knife-fade-st-fn": "★ StatTrak™ Skeleton Knife | Fade (Factory New)",
    "skeleton-knife-fade-st-mw": "★ StatTrak™ Skeleton Knife | Fade (Minimal Wear)",
    "skeleton-knife-marble-fade-st-fn": "★ StatTrak™ Skeleton Knife | Marble Fade (Factory New)",
    "skeleton-knife-marble-fade-st-mw": "★ StatTrak™ Skeleton Knife | Marble Fade (Minimal Wear)",
    "skeleton-knife-slaughter-st-fn": "★ StatTrak™ Skeleton Knife | Slaughter (Factory New)",
    "skeleton-knife-slaughter-st-ft": "★ StatTrak™ Skeleton Knife | Slaughter (Field-Tested)",
    "skeleton-knife-slaughter-st-mw": "★ StatTrak™ Skeleton Knife | Slaughter (Minimal Wear)",
    "skeleton-knife-tiger-tooth-st-fn": "★ StatTrak™ Skeleton Knife | Tiger Tooth (Factory New)",
    "skeleton-knife-tiger-tooth-st-mw": "★ StatTrak™ Skeleton Knife | Tiger Tooth (Minimal Wear)",
    # Stiletto Knife
    "stiletto-knife-doppler-phase-1-st-fn": "★ StatTrak™ Stiletto Knife | Doppler Phase 1 (Factory New)",
    "stiletto-knife-doppler-phase-2-st-fn": "★ StatTrak™ Stiletto Knife | Doppler Phase 2 (Factory New)",
    "stiletto-knife-doppler-phase-3-st-fn": "★ StatTrak™ Stiletto Knife | Doppler Phase 3 (Factory New)",
    "stiletto-knife-doppler-phase-3-st-mw": "★ StatTrak™ Stiletto Knife | Doppler Phase 3 (Minimal Wear)",
    "stiletto-knife-doppler-phase-4-st-fn": "★ StatTrak™ Stiletto Knife | Doppler Phase 4 (Factory New)",
    "stiletto-knife-doppler-sapphire-st-fn": "★ StatTrak™ Stiletto Knife | Doppler Sapphire (Factory New)",
    "stiletto-knife-fade-st-fn": "★ StatTrak™ Stiletto Knife | Fade (Factory New)",
    "stiletto-knife-fade-st-mw": "★ StatTrak™ Stiletto Knife | Fade (Minimal Wear)",
    "stiletto-knife-marble-fade-st-fn": "★ StatTrak™ Stiletto Knife | Marble Fade (Factory New)",
    "stiletto-knife-marble-fade-st-mw": "★ StatTrak™ Stiletto Knife | Marble Fade (Minimal Wear)",
    "stiletto-knife-slaughter-st-fn": "★ StatTrak™ Stiletto Knife | Slaughter (Factory New)",
    "stiletto-knife-slaughter-st-ft": "★ StatTrak™ Stiletto Knife | Slaughter (Field-Tested)",
    "stiletto-knife-slaughter-st-mw": "★ StatTrak™ Stiletto Knife | Slaughter (Minimal Wear)",
    "stiletto-knife-tiger-tooth-st-fn": "★ StatTrak™ Stiletto Knife | Tiger Tooth (Factory New)",
    "stiletto-knife-tiger-tooth-st-mw": "★ StatTrak™ Stiletto Knife | Tiger Tooth (Minimal Wear)",
    "stiletto-knife-doppler-phase-1-fn": "★ Stiletto Knife | Doppler Phase 1 (Factory New)",
    "stiletto-knife-doppler-phase-1-mw": "★ Stiletto Knife | Doppler Phase 1 (Minimal Wear)",
    "stiletto-knife-doppler-phase-2-fn": "★ Stiletto Knife | Doppler Phase 2 (Factory New)",
    "stiletto-knife-doppler-phase-2-mw": "★ Stiletto Knife | Doppler Phase 2 (Minimal Wear)",
    "stiletto-knife-doppler-phase-3-fn": "★ Stiletto Knife | Doppler Phase 3 (Factory New)",
    "stiletto-knife-doppler-phase-3-mw": "★ Stiletto Knife | Doppler Phase 3 (Minimal Wear)",
    "stiletto-knife-doppler-phase-4-fn": "★ Stiletto Knife | Doppler Phase 4 (Factory New)",
    "stiletto-knife-doppler-phase-4-mw": "★ Stiletto Knife | Doppler Phase 4 (Minimal Wear)",
    "stiletto-knife-doppler-sapphire-fn": "★ Stiletto Knife | Doppler Sapphire (Factory New)",
    "stiletto-knife-fade-fn": "★ Stiletto Knife | Fade (Factory New)",
    "stiletto-knife-fade-mw": "★ Stiletto Knife | Fade (Minimal Wear)",
    "stiletto-knife-marble-fade-fn": "★ Stiletto Knife | Marble Fade (Factory New)",
    "stiletto-knife-marble-fade-mw": "★ Stiletto Knife | Marble Fade (Minimal Wear)",
    "stiletto-knife-slaughter-fn": "★ Stiletto Knife | Slaughter (Factory New)",
    "stiletto-knife-slaughter-ft": "★ Stiletto Knife | Slaughter (Field-Tested)",
    "stiletto-knife-slaughter-mw": "★ Stiletto Knife | Slaughter (Minimal Wear)",
    "stiletto-knife-tiger-tooth-fn": "★ Stiletto Knife | Tiger Tooth (Factory New)",
    "stiletto-knife-tiger-tooth-mw": "★ Stiletto Knife | Tiger Tooth (Minimal Wear)",
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
    "karambit-doppler-phase-1-st-fn": "★ StatTrak™ Karambit | Doppler Phase 1 (Factory New)",
    "karambit-doppler-phase-3-st-fn": "★ StatTrak™ Karambit | Doppler Phase 3 (Factory New)",
    "karambit-marble-fade-st-fn": "★ StatTrak™ Karambit | Marble Fade (Factory New)",
    "karambit-slaughter-st-fn": "★ StatTrak™ Karambit | Slaughter (Factory New)",
    "karambit-slaughter-st-ft": "★ StatTrak™ Karambit | Slaughter (Field-Tested)",
    "karambit-slaughter-st-mw": "★ StatTrak™ Karambit | Slaughter (Minimal Wear)",
    "karambit-tiger-tooth-st-fn": "★ StatTrak™ Karambit | Tiger Tooth (Factory New)",
}


def fetch_json(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "butterfly-watch/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


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
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("Telegram secrets not set, skipping notification", file=sys.stderr)
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp.read()
    except Exception as e:
        print(f"Failed to send Telegram message: {e}", file=sys.stderr)


def main():
    now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    data = load_data()
    data.setdefault("items", {})
    data.setdefault("usd_rub", {"history": []})

    try:
        feed = fetch_json(LIS_SKINS_FEED)
    except Exception as e:
        print(f"Failed to fetch lis-skins feed: {e}", file=sys.stderr)
        sys.exit(1)
    by_name = {entry["name"]: entry for entry in feed}

    try:
        cbr = fetch_json(CBR_RATE_URL)
        usd_rate = cbr["Valute"]["USD"]["Value"]
    except Exception as e:
        print(f"Failed to fetch USD/RUB rate: {e}", file=sys.stderr)
        usd_rate = None

    if usd_rate is not None:
        rate_history = data["usd_rub"]["history"]
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

        history.append({"t": now, "price": price})
        trim(history)

        reasons = []

        if prev_min is not None and price <= prev_min * (1 - DROP_THRESHOLD):
            drop_pct = (1 - price / prev_min) * 100
            reasons.append(f"\U0001F4C9 ниже исторического минимума на {drop_pct:.1f}% (было ${prev_min:.2f})")

        if prev_price is not None and prev_price > 0:
            change_pct = (price - prev_price) / prev_price * 100
            if change_pct <= -LAST_CHECK_THRESHOLD * 100:
                reasons.append(f"\U0001F53B резкое падение за одну проверку: {change_pct:.1f}% (было ${prev_price:.2f})")
            elif change_pct >= LAST_CHECK_THRESHOLD * 100:
                reasons.append(f"\U0001F53A резкий рост за одну проверку: +{change_pct:.1f}% (было ${prev_price:.2f})")

        if reasons:
            alerts.append(
                f"<b>{match_name}</b>\n"
                f"Цена: <b>${price:.2f}</b>\n"
                + "\n".join(reasons) + "\n"
                f"{entry.get('url', '')}"
            )

    data["last_updated"] = now
    save_data(data)

    if alerts:
        message = "\U0001F98B <b>Butterfly Watch: изменение цены!</b>\n\n" + "\n\n".join(alerts)
        send_telegram(message)
        print(f"Sent {len(alerts)} alert(s)")
    else:
        print("No price drops detected")


if __name__ == "__main__":
    main()
