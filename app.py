import streamlit as st
import requests
import time
from datetime import datetime, timezone

# ==========================
# CONFIG
# ==========================
st.set_page_config(page_title="Funding Rate Arbitrage Scanner", layout="wide")

REFRESH_SECONDS = 60
ALERT_THRESHOLD = 0.10  # %

BINANCE_URL = "https://fapi.binance.com/fapi/v1/premiumIndex"
DELTA_URL = "https://api.india.delta.exchange/v2/tickers?contract_types=perpetual_futures"
BYBIT_URL = "https://api.bybit.com/v5/market/tickers?category=linear"

TELEGRAM_BOT_TOKEN = st.secrets.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = st.secrets.get("TELEGRAM_CHAT_ID", "")

# ==========================
# TELEGRAM
# ==========================
def send_telegram(msg):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"},
            timeout=10
        )
    except Exception:
        pass

# ==========================
# BINANCE
# ==========================
@st.cache_data(ttl=60)
def fetch_binance():
    res = requests.get(BINANCE_URL, timeout=10).json()
    rates, next_funding = {}, {}
    now = time.time()

    for r in res:
        sym = r.get("symbol")
        fr = r.get("lastFundingRate")
        nft = r.get("nextFundingTime")

        if not sym or fr in ("", None):
            continue

        try:
            rates[sym] = float(fr) * 100  # ✅ normalize
            next_funding[sym] = int((nft / 1000) - now) if nft else None
        except Exception:
            continue

    return rates, next_funding

# ==========================
# DELTA
# ==========================
@st.cache_data(ttl=60)
def fetch_delta():
    res = requests.get(DELTA_URL, timeout=10).json()
    data = res.get("result", [])

    rates, next_funding = {}, {}

    for r in data:
        sym = r.get("symbol")
        fr = r.get("funding_rate")
        nft = r.get("next_funding_realization")

        if not sym or fr is None:
            continue

        try:
            rates[sym] = float(fr)
            next_funding[sym] = int((nft / 1_000_000) - time.time()) if nft else None
        except Exception:
            continue

    return rates, next_funding

# ==========================
# BYBIT
# ==========================
@st.cache_data(ttl=60)
def fetch_bybit():
    res = requests.get(BYBIT_URL, timeout=10).json()
    data = res.get("result", {}).get("list", [])

    rates, next_funding = {}, {}
    now = time.time()

    for r in data:
        sym = r.get("symbol")
        fr = r.get("fundingRate")
        nft = r.get("nextFundingTime")

        if not sym or fr in ("", None):
            continue

        try:
            rates[sym] = float(fr) * 100  # ✅ normalize
            next_funding[sym] = int((nft / 1000) - now) if nft else None
        except Exception:
            continue

    return rates, next_funding

# ==========================
# UTILS
# ==========================
def countdown(sec):
    if not sec or sec <= 0:
        return "N/A"
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    return f"{h:02d}:{m:02d}:{s:02d}"

# ==========================
# UI
# ==========================
st.title("📊 Funding Rate Arbitrage Dashboard")
st.caption("Binance ↔ Delta ↔ Bybit (Live Snapshot)")

container = st.empty()

while True:
    with container.container():
        b_rates, b_next = fetch_binance()
        d_rates, d_next = fetch_delta()
        y_rates, y_next = fetch_bybit()

        rows = []

        for d_sym, d_rate in d_rates.items():
            b_sym = d_sym.replace("USD", "USDT")

            for ex_name, rates, nxt in [
                ("Binance", b_rates, b_next),
                ("Bybit", y_rates, y_next),
            ]:
                if b_sym not in rates:
                    continue

                ex_rate = rates[b_sym]
                diff = d_rate - ex_rate

                strategy = (
                    "SHORT Delta, LONG " + ex_name
                    if diff > 0
                    else "LONG Delta, SHORT " + ex_name
                )

                next_sec = min(
                    filter(None, [
                        d_next.get(d_sym),
                        nxt.get(b_sym)
                    ]),
                    default=None
                )

                rows.append({
                    "Symbol": b_sym,
                    "Exchange": ex_name,
                    "Delta Rate (%)": round(d_rate, 4),
                    f"{ex_name} Rate (%)": round(ex_rate, 4),
                    "Difference (%)": round(diff, 4),
                    "Next Funding": countdown(next_sec),
                    "Strategy": strategy
                })

                if abs(diff) >= ALERT_THRESHOLD:
                    send_telegram(
                        f"🚨 <b>Funding Arbitrage</b>\n"
                        f"{b_sym}\n"
                        f"Delta: {d_rate:.4f}%\n"
                        f"{ex_name}: {ex_rate:.4f}%\n"
                        f"Diff: {diff:.4f}%\n"
                        f"<b>{strategy}</b>"
                    )

        st.metric("Total Opportunities", len(rows))
        st.dataframe(rows, use_container_width=True)

        st.caption(
            f"Last refresh: {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')} "
            f"| Auto refresh every {REFRESH_SECONDS}s"
        )

    time.sleep(REFRESH_SECONDS)
