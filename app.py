import streamlit as st
import requests
from datetime import datetime, timezone

st.set_page_config(page_title="Funding Debugger", layout="wide")
st.title("🧪 Funding API Debug Dashboard")

HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0"
}

BINANCE_URL = "https://fapi.binance.com/fapi/v1/premiumIndex"
DELTA_URL = "https://api.india.delta.exchange/v2/tickers?contract_types=perpetual_futures"
BYBIT_URL = "https://api.bybit.com/v5/market/tickers?category=linear"

# ================= BINANCE =================
st.subheader("1️⃣ Binance Test")
try:
    res = requests.get(BINANCE_URL, headers=HEADERS, timeout=10)
    st.write("Status:", res.status_code)
    data = res.json()
    st.write("Total symbols:", len(data))
    st.json(data[:3])
except Exception as e:
    st.error(f"Binance error: {e}")

# ================= DELTA =================
st.subheader("2️⃣ Delta Test")
try:
    res = requests.get(DELTA_URL, headers=HEADERS, timeout=10)
    st.write("Status:", res.status_code)
    data = res.json().get("result", [])
    st.write("Total symbols:", len(data))
    st.json(data[:3])
except Exception as e:
    st.error(f"Delta error: {e}")

# ================= BYBIT =================
st.subheader("3️⃣ Bybit Test")
try:
    res = requests.get(BYBIT_URL, headers=HEADERS, timeout=10)
    st.write("Status:", res.status_code)
    raw = res.json()
    lst = raw.get("result", {}).get("list", [])
    st.write("Total symbols:", len(lst))
    st.json(lst[:3])
except Exception as e:
    st.error(f"Bybit error: {e}")

st.caption(datetime.now(timezone.utc).strftime("Checked at %H:%M:%S UTC"))
