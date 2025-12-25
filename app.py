import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime, timezone

# ==================================================
# CONFIG
# ==================================================
BINANCE_URL = "https://fapi.binance.com/fapi/v1/premiumIndex"
DELTA_URL = "https://api.india.delta.exchange/v2/tickers?contract_types=perpetual_futures"
BYBIT_URL = "https://api.bybit.com/v5/market/tickers?category=linear"

HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0"
}

DEFAULT_THRESHOLD = 0.2  # %


# ===================== TELEGRAM ====================
ENABLE_TELEGRAM = True   # 🔴 turn OFF if not needed
TELEGRAM_TOKEN = "8564253749:AAE6jcZeKBvL54g662-cJ-kgoWi046YJ0Z0"
TELEGRAM_CHAT_ID = "1086680348"

ALERT_BEFORE_MIN = 15  # minutes before funding

# ==================================================
# HELPERS
# ==================================================
def funding_countdown(ts_ms):
    next_funding = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
    now = datetime.now(timezone.utc)
    delta = next_funding - now

    if delta.total_seconds() <= 0:
        return "Funding now"

    h = int(delta.total_seconds() // 3600)
    m = int((delta.total_seconds() % 3600) // 60)
    return f"{h}h {m}m"


def minutes_to_funding(ts_ms):
    next_funding = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
    now = datetime.now(timezone.utc)
    return int((next_funding - now).total_seconds() / 60)


def send_telegram(msg):
    if not ENABLE_TELEGRAM:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": msg,
        "parse_mode": "HTML"
    }
    try:
        requests.post(url, json=payload, timeout=5)
    except:
        pass


# ✅ TELEGRAM TEST BUTTON (PLACE HERE)
if st.button("📩 Test Telegram"):
    send_telegram("✅ Telegram connected. Funding scanner alerts are live.")
    st.success("Test message sent — check Telegram")
# ==================================================
# DATA FETCHERS
# ==================================================
@st.cache_data(ttl=300)
def fetch_binance():
    res = requests.get(BINANCE_URL, headers=HEADERS).json()
    rates, times = {}, {}

    for r in res:
        rates[r["symbol"]] = float(r["lastFundingRate"]) * 100
        times[r["symbol"]] = int(r["nextFundingTime"])

    return rates, times


@st.cache_data(ttl=300)
def fetch_delta():
    res = requests.get(DELTA_URL, headers=HEADERS).json()["result"]
    rates = {}
    for r in res:
        if r.get("funding_rate") is not None:
            rates[r["symbol"]] = float(r["funding_rate"])
    return rates


@st.cache_data(ttl=300)
def fetch_bybit():
    res = requests.get(BYBIT_URL, headers=HEADERS).json()
    rates, times = {}, {}

    for r in res["result"]["list"]:
        fr = r.get("fundingRate")
        if not fr:
            continue
        try:
            rates[r["symbol"]] = float(fr) * 100
        except:
            continue

        nft = r.get("nextFundingTime")
        if nft:
            times[r["symbol"]] = int(nft)

    return rates, times

# ==================================================
# UI
# ==================================================
st.set_page_config(page_title="Funding Arbitrage Scanner", layout="wide")
st.title("📊 Funding Rate Arbitrage Scanner")

auto_refresh = st.checkbox("🔄 Auto-refresh every 60s", value=True)

threshold = st.slider(
    "Minimum Funding Difference (%)",
    0.05, 5.0, DEFAULT_THRESHOLD, 0.05
)

# ==================================================
# MAIN LOGIC
# ==================================================
binance_rates, binance_next = fetch_binance()
delta_rates = fetch_delta()
bybit_rates, bybit_next = fetch_bybit()

rows = []

symbols = set(binance_rates) | set(bybit_rates)

alerted = st.session_state.setdefault("alerted", set())

for sym in symbols:
    b = binance_rates.get(sym)
    y = bybit_rates.get(sym)
    d = delta_rates.get(sym.replace("USDT", "USD"))

    rates = {"Binance": b, "Bybit": y, "Delta": d}
    valid = {k: v for k, v in rates.items() if v is not None}

    if len(valid) < 2:
        continue

    best = None
    for e1, r1 in valid.items():
        for e2, r2 in valid.items():
            if e1 == e2:
                continue
            diff = abs(r1 - r2)
            if diff >= threshold and (best is None or diff > best[2]):
                best = (e1, e2, diff)

    if not best:
        continue

    e1, e2, diff = best

    long_ex, short_ex = (e1, e2) if valid[e1] < valid[e2] else (e2, e1)

    ts = binance_next.get(sym) or bybit_next.get(sym)
    countdown = funding_countdown(ts) if ts else "N/A"

    # ================= TELEGRAM ALERT =================
    if ts:
        mins = minutes_to_funding(ts)
        alert_key = f"{sym}-{ts}"

        if mins <= ALERT_BEFORE_MIN and alert_key not in alerted:
            msg = (
                f"🚨 <b>Funding Arbitrage Alert</b>\n\n"
                f"<b>{sym}</b>\n"
                f"LONG <b>{long_ex}</b>\n"
                f"SHORT <b>{short_ex}</b>\n"
                f"Diff: <b>{diff:.2f}%</b>\n"
                f"Funding in <b>{mins} min</b>"
            )
            send_telegram(msg)
            alerted.add(alert_key)

    rows.append({
        "Symbol": sym,
        "Binance (%)": b,
        "Bybit (%)": y,
        "Delta (%)": d,
        "Difference (%)": round(diff, 4),
        "Strategy": f"LONG {long_ex}, SHORT {short_ex}",
        "Next Funding": countdown
    })

# ==================================================
# DISPLAY
# ==================================================
st.subheader("📈 Arbitrage Opportunities")

if rows:
    df = pd.DataFrame(rows).sort_values("Difference (%)", ascending=False)
    st.dataframe(df, use_container_width=True)
else:
    st.warning("No strong arbitrage opportunities.")

st.caption(datetime.now(timezone.utc).strftime("Updated %d %b %Y %H:%M:%S UTC"))

# ==================================================
# AUTO REFRESH
# ==================================================
if auto_refresh:
    time.sleep(60)
    st.experimental_rerun()
