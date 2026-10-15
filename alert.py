"""
Dr.SamScience Crypto Alert: runs every 5 minutes on GitHub Actions.
Sends a Telegram message when BTC or SOL moves 5% from its last alert price.
Alerts only. Never trades.
"""
import json
import os
import time
import requests

THRESHOLD = 5.0
STATE_FILE = "state.json"
TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]


def fetch(url, params=None, tries=3):
    for i in range(tries):
        try:
            r = requests.get(url, params=params, timeout=15)
            r.raise_for_status()
            return r.json()
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(3 * (i + 1))


def get_prices():
    """Returns {symbol: (usd, ngn_or_None)}. CoinGecko first, Coinbase as backup."""
    try:
        d = fetch(
            "https://api.coingecko.com/api/v3/simple/price",
            {"ids": "bitcoin,solana", "vs_currencies": "usd,ngn"},
        )
        return {
            "BTC": (d["bitcoin"]["usd"], d["bitcoin"].get("ngn")),
            "SOL": (d["solana"]["usd"], d["solana"].get("ngn")),
        }
    except Exception:
        out = {}
        for sym in ("BTC", "SOL"):
            d = fetch(f"https://api.coinbase.com/v2/prices/{sym}-USD/spot")
            out[sym] = (float(d["data"]["amount"]), None)
        return out


def telegram(text):
    requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": text},
        timeout=15,
    ).raise_for_status()


def money(usd, ngn):
    s = f"${usd:,.2f}"
    return s + (f" (about ₦{ngn:,.0f})" if ngn else "")


def main():
    state = {}
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            state = json.load(f)

    prices = get_prices()

    # Manual run from the GitHub "Run workflow" button sends a test message
    if os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch":
        lines = [f"{s}: {money(*p)}" for s, p in prices.items()]
        telegram("✅ Dr.SamScience Crypto Alert is working.\n" + "\n".join(lines) +
                 f"\nYou'll be alerted on {THRESHOLD:.0f}% moves.")

    for sym, (usd, ngn) in prices.items():
        base = state.get(sym)
        if base is None:
            state[sym] = usd
            continue
        change = (usd - base) / base * 100
        if abs(change) >= THRESHOLD:
            up = change > 0
            telegram(
                f"{'🟢' if up else '🔴'} {sym} {'ROSE' if up else 'FELL'} {abs(change):.1f}%\n"
                f"Now: {money(usd, ngn)}\n"
                f"Last alert price: ${base:,.2f}\n"
                f"Action: Review your trading plan before deciding.\n"
                f"- Dr.SamScience Crypto Alert"
            )
            state[sym] = usd  # next alert is 5% from this new price

    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


if __name__ == "__main__":
    main()
