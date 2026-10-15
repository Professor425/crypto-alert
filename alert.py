""" Dr.SamScience Crypto Alert: runs every 5 minutes on GitHub Actions. Sends a Telegram message when BTC or SOL moves THRESHOLD% from its last alert price, plus a BUY WATCH / SELL WATCH / WAIT signal based on RSI and trend. Signals are prompts to review the market, not financial advice. Never trades. """
import json
import os
import time
import requests

THRESHOLD = 5.0
STATE_FILE = "state.json"
TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
COIN_IDS = {"BTC": "bitcoin", "SOL": "solana"}


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


def history(sym):
    """About 14 days of hourly prices."""
    d = fetch(
        f"https://api.coingecko.com/api/v3/coins/{COIN_IDS[sym]}/market_chart",
        {"vs_currency": "usd", "days": 14},
    )
    return [p[1] for p in d["prices"]]


def rsi(closes, n=14):
    gains, losses = [], []
    for a, b in zip(closes, closes[1:]):
        d = b - a
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    ag = sum(gains[:n]) / n
    al = sum(losses[:n]) / n
    for g, l in zip(gains[n:], losses[n:]):
        ag = (ag * (n - 1) + g) / n
        al = (al * (n - 1) + l) / n
    return 100.0 if al == 0 else 100 - 100 / (1 + ag / al)


def signal(sym, change, usd):
    try:
        closes = history(sym)
        r = rsi(closes)
        avg50 = sum(closes[-50:]) / len(closes[-50:])
    except Exception:
        return "Signal: unavailable right now. Check the chart yourself."

    trend = "above" if usd >= avg50 else "below"
    if r <= 30:
        verdict = "ðŸŸ¢ BUY WATCH: oversold after the drop. A possible buying zone, but it can still fall further."
    elif r >= 70:
        verdict = "ðŸ”´ SELL / TAKE-PROFIT WATCH: overbought after the rise. Consider locking in some profit."
    elif change == 0:
        verdict = "ðŸŸ¡ WAIT: no strong buy or sell signal right now."
    elif change < 0:
        verdict = "ðŸŸ¡ WAIT: it fell but is not oversold yet. It may keep falling."
    else:
        verdict = "ðŸŸ¡ WAIT / HOLD: it rose but is not overbought yet."

    return (
        f"{verdict}\n"
        f"RSI: {r:.0f} (below 30 oversold, above 70 overbought)\n"
        f"Trend: price is {trend} its 50-hour average\n"
        f"Example stop-loss if you buy now: ${usd * 0.95:,.2f} (5% below)"
    )


def telegram(text):
    requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": text},
        timeout=15,
    ).raise_for_status()


def money(usd, ngn):
    s = f"${usd:,.2f}"
    return s + (f" (about â‚¦{ngn:,.0f})" if ngn else "")


def main():
    state = {}
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            state = json.load(f)

    prices = get_prices()

    # Manual run from the GitHub "Run workflow" button sends a test message
    if os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch":
        lines = [f"{s}: {money(*p)}\n{signal(s, 0, p[0])}" for s, p in prices.items()]
        telegram("âœ… Dr.SamScience Crypto Alert is working.\n\n" + "\n\n".join(lines) +
                 f"\n\nYou'll also be alerted on {THRESHOLD:.0f}% moves, with the same buy/sell watch signal.")

    for sym, (usd, ngn) in prices.items():
        base = state.get(sym)
        if base is None:
            state[sym] = usd
            continue
        change = (usd - base) / base * 100
        if abs(change) >= THRESHOLD:
            up = change > 0
            telegram(
                f"{'ðŸŸ¢' if up else 'ðŸ”´'} {sym} {'ROSE' if up else 'FELL'} {abs(change):.1f}%\n"
                f"Now: {money(usd, ngn)}\n"
                f"Last alert price: ${base:,.2f}\n\n"
                f"{signal(sym, change, usd)}\n\n"
                f"Signals are prompts, not advice. Review the chart and your plan first.\n"
                f"- Dr.SamScience Crypto Alert"
            )
            state[sym] = usd

    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


if __name__ == "__main__":
    main()
