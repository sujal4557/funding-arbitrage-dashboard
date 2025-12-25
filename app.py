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
ENABLE_TELEGRAM = True
TELEGRAM_TOKEN = "8564253749:AAE6jcZeKBvL54g662-cJ-kgoWi046YJ0Z0"
TELEGRAM_CHAT_ID = "1086680348"
ALERT_BEFORE_MIN = 15

# ==================================================
# HELPERS
# ==================================================
def funding_countdown(ts_ms):
    if not ts_ms:
        return "N/A"
    next_funding = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
    now = datetime.now(timezone.utc)
    delta = next_funding - now
    if delta.total_seconds() <= 0:
        return "Funding now"
    h = int(delta.total_seconds() // 3600)
    m = int((delta.total_seconds() % 3600) // 60)
    return f"{h}h {m}m"

def minutes_to_funding(ts_ms):
    if not ts_ms:
        return 9999
    next_funding = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
    now = datetime.now(timezone.utc)
    return int((next_funding - now).total_seconds() / 60)

def send_telegram(msg):
    if not ENABLE_TELEGRAM:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"},
            timeout=5
        )
    except:
        pass

# ==================================================
# DATA FETCHERS (CLOUD SAFE)
# ==================================================
@st.cache_data(ttl=120)
def fetch_binance():
    rates, times = {}, {}
    try:
        res = requests.get(BINANCE_URL, headers=HEADERS, timeout=10).json()
        for r in res:
            sym = r.get("symbol")
            fr = r.get("lastFundingRate")
            if sym and fr:
                rates[sym] = float(fr) * 100  # normalize
                times[sym] = int(r.get("nextFundingTime", 0))
    except:
        pass
    return rates, times

@st.cache_data(ttl=120)
def fetch_delta():
    rates = {}
    try:
        res = requests.get(DELTA_URL, headers=HEADERS, timeout=10).json().get("result", [])
        for r in res:
            sym = r.get("symbol")
            fr = r.get("funding_rate")
            if sym and fr is not None:
                rates[sym] = float(fr)
    except:
        pass
    return rates

@st.cache_data(ttl=120)
def fetch_bybit():
    rates, times = {}, {}
    try:
        resp = requests.get(BYBIT_URL, headers=HEADERS, timeout=10)
        if resp.status_code != 200:
            return rates, times
        data = resp.json().get("result", {}).get("list", [])
        for r in data:
            sym = r.get("symbol")
            fr = r.get("fundingRate")
            nft = r.get("nextFundingTime")
            if sym and fr not in ("", None):
                rates[sym] = float(fr) * 100
                if nft:
                    times[sym] = int(nft)
    except:
        pass
    return rates, times

# ==================================================
# UI
# ==================================================
st.set_page_config(page_title="Funding Arbitrage Scanner", layout="wide")
st.title("📊 Funding Rate Arbitrage Dashboard")
st.caption("Binance ↔ Delta ↔ Bybit (Live Snapshot)")

if st.button("📩 Test Telegram"):
    send_telegram("✅ Telegram connected. Funding scanner alerts are live.")
    st.success("Telegram test message sent")

auto_refresh = st.checkbox("🔄 Auto-refresh every 60s", value=True)
threshold = st.slider("Minimum Funding Difference (%)", 0.05, 5.0, DEFAULT_THRESHOLD, 0.05)

# ==================================================
# MAIN LOGIC
# ==================================================
binance_rates, binance_next = fetch_binance()
delta_rates = fetch_delta()
bybit_rates, bybit_next = fetch_bybit()

rows = []
alerted = st.session_state.setdefault("alerted", set())

all_symbols = set(binance_rates) | set(bybit_rates)

for sym in all_symbols:
    b = binance_rates.get(sym)
    y = bybit_rates.get(sym)
    d = delta_rates.get(sym.replace("USDT", "USD"))

    available = {
        "Binance": b,
        "Bybit": y,
        "Delta": d
    }

    valid = {k: v for k, v in available.items() if v is not None}
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
    countdown = funding_countdown(ts)

    if ts:
        mins = minutes_to_funding(ts)
        key = f"{sym}-{ts}"
        if mins <= ALERT_BEFORE_MIN and key not in alerted:
            send_telegram(
                f"🚨 <b>Funding Arbitrage</b>\n\n"
                f"<b>{sym}</b>\n"
                f"LONG <b>{long_ex}</b>\n"
                f"SHORT <b>{short_ex}</b>\n"
                f"Diff: <b>{diff:.2f}%</b>\n"
                f"Funding in <b>{mins} min</b>"
            )
            alerted.add(key)

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
    st.metric("Total Opportunities", len(df))
    st.dataframe(df, use_container_width=True)
else:
    st.warning("No strong arbitrage opportunities right now.")

st.caption(datetime.now(timezone.utc).strftime("Last refresh: %H:%M:%S UTC"))

# ==================================================
# AUTO REFRESH
# ==================================================
if auto_refresh:
    time.sleep(60)
    st.experimental_rerun()
