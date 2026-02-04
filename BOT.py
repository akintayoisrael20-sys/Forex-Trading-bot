import requests
import pandas as pd
from datetime import datetime, timedelta
import pytz
import time

# ================= CONFIG =================
API_KEY = "21ff5b8011e64671a8fb8f504db74f1f"
BOT_TOKEN = "8520706083:AAEHWKKhnuuPDlY2FvNDz8os9Se-MetSYhY"
CHAT_ID = "-1003767859681"  # LIFE&PEACE FOREX SIGNAL group

PAIRS = ["EUR/USD", "GBP/USD", "USD/CHF"]

TIMEZONE = pytz.timezone("Africa/Lagos")
INTERVAL_H4 = "4h"
INTERVAL_H1 = "1h"
INTERVAL_M5 = "5min"

# ================= RISK =================
default_lot = 0.01

pip_value = {
    "EUR/USD": 0.0001,
    "GBP/USD": 0.0001,
    "USD/CHF": 0.0001,
}

# ================= ATR SETTINGS =================
ATR_SETTINGS = {
    "EUR/USD": {"sl": 1.2, "tp": 2.5},
    "GBP/USD": {"sl": 1.3, "tp": 2.8},
    "USD/CHF": {"sl": 1.2, "tp": 2.4},
}

# ================= TELEGRAM =================
def send_telegram(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": msg})

# ================= DATA =================
def fetch_data(symbol, interval):
    r = requests.get(
        "https://api.twelvedata.com/time_series",
        params={
            "symbol": symbol,
            "interval": interval,
            "apikey": API_KEY,
            "outputsize": 150
        }
    ).json()

    if "values" not in r:
        return None

    df = pd.DataFrame(r["values"]).iloc[::-1]
    df[["open", "high", "low", "close"]] = df[
        ["open", "high", "low", "close"]
    ].astype(float)

    return df.reset_index(drop=True)

# ================= INDICATORS =================
def indicators(df):
    df["ema50"] = df["close"].ewm(span=50).mean()
    ema12 = df["close"].ewm(span=12).mean()
    ema26 = df["close"].ewm(span=26).mean()
    df["macd"] = ema12 - ema26
    df["signal"] = df["macd"].ewm(span=9).mean()
    df["atr"] = (df["high"] - df["low"]).rolling(14).mean()
    return df

# ================= CONFIRMATIONS =================
def recent_macd_cross(p2, p1, c, side):
    if side == "BUY":
        return (
            (p1["macd"] > p1["signal"] and p2["macd"] <= p2["signal"]) or
            (c["macd"] > c["signal"] and p1["macd"] <= p1["signal"])
        )
    else:
        return (
            (p1["macd"] < p1["signal"] and p2["macd"] >= p2["signal"]) or
            (c["macd"] < c["signal"] and p1["macd"] >= p1["signal"])
        )

def strong_close(c, side):
    body = abs(c["close"] - c["open"])
    rng = c["high"] - c["low"]
    if rng == 0:
        return False
    return body / rng >= 0.6 and (
        c["close"] > c["open"] if side == "BUY" else c["close"] < c["open"]
    )

# ================= NEWS FILTER =================
def news_filter():
    try:
        upcoming_news_time = datetime.now(TIMEZONE) + timedelta(minutes=40)
        now = datetime.now(TIMEZONE)
        minutes_until_news = (upcoming_news_time - now).total_seconds() / 60
        return not (-30 <= minutes_until_news <= 30)
    except:
        return True

# ================= SIGNAL =================
def check_signal(h4, h1, m5, pair):
    if not news_filter():
        return None

    # --- H4 TREND ---
    h4_candle = h4.iloc[-2]
    h4_trend = "BUY" if h4_candle["close"] > h4_candle["ema50"] else "SELL"

    # --- H1 TREND ---
    h1_candle = h1.iloc[-2]
    h1_trend = "BUY" if h1_candle["close"] > h1_candle["ema50"] else "SELL"

    # --- TREND FILTER ---
    if h4_trend != h1_trend:
        return None

    trend = h1_trend  # confirmed trend

    # --- M5 ENTRY ---
    p2 = m5.iloc[-4]
    p1 = m5.iloc[-3]
    c  = m5.iloc[-2]

    if not recent_macd_cross(p2, p1, c, trend):
        return None

    if not strong_close(c, trend):
        return None

    atr = c["atr"]
    if atr <= 0 or pd.isna(atr):
        return None

    atr_sl = ATR_SETTINGS[pair]["sl"]
    atr_tp = ATR_SETTINGS[pair]["tp"]

    price = c["close"]

    sl = price - atr * atr_sl if trend == "BUY" else price + atr * atr_sl
    tp = price + atr * atr_tp if trend == "BUY" else price - atr * atr_tp

    sl_pips = round(abs(price - sl) / pip_value[pair], 1)
    tp_pips = round(abs(tp - price) / pip_value[pair], 1)

    confidence = int(
        min(max((abs(c["close"] - c["open"]) / atr) * 100, 50), 90)
    )

    return {
        "pair": pair,
        "signal": trend,
        "price": price,
        "sl": sl,
        "tp": tp,
        "lot": default_lot,
        "confidence": confidence,
        "sl_pips": sl_pips,
        "tp_pips": tp_pips,
        "time": datetime.now(TIMEZONE).strftime("%H:%M")
    }

# ================= LOOP =================
def main():
    print("🚀 BOT RUNNING — H4 + H1 TREND FILTER ACTIVE")
    last_checked = None

    while True:
        now = datetime.now(TIMEZONE)

        if now.minute % 5 == 0 and now.minute != last_checked:
            last_checked = now.minute

            for pair in PAIRS:
                h4 = fetch_data(pair, INTERVAL_H4)
                h1 = fetch_data(pair, INTERVAL_H1)
                m5 = fetch_data(pair, INTERVAL_M5)

                if h4 is None or h1 is None or m5 is None:
                    continue

                h4 = indicators(h4)
                h1 = indicators(h1)
                m5 = indicators(m5)

                result = check_signal(h4, h1, m5, pair)

                if result:
                    msg = (
                        "🔴 High Probability Trade Alert\n"
                        f"Pair: {result['pair']}\n"
                        f"Signal: {result['signal']}\n"
                        f"Entry: {result['price']}\n"
                        f"SL: {result['sl']} ({result['sl_pips']} pips)\n"
                        f"TP: {result['tp']} ({result['tp_pips']} pips)\n"
                        f"Lot: {result['lot']}\n"
                        f"Confidence: {result['confidence']}%\n"
                        f"Time: {result['time']} (Africa/Lagos)"
                    )
                    send_telegram(msg)

        time.sleep(15)

if __name__ == "__main__":
    main()
