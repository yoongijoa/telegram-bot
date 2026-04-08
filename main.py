import os
import json
import requests
import asyncio
import jwt
import uuid
import time as _time
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

#################################
# 환경변수
#################################

TOKEN = os.getenv("BOT_TOKEN")
UPBIT_ACCESS = os.getenv("UPBIT_ACCESS")
UPBIT_SECRET = os.getenv("UPBIT_SECRET")

ALARM_FILE = "/app/data/alarms.json"
NIGHT_FILE = "/app/data/night_mode.json"
GAP_AUTO_FILE = "/app/data/gap_auto.json"

CHECK_INTERVAL = 5
COOLDOWN_SEC = 300

NIGHT_START = 23
NIGHT_END = 7

EXCHANGE_MAP = {
    "업비트": "upbit",
    "빗썸": "bithumb",
}

FEE_RATE = {
    "upbit": 0.0005,
    "bithumb": 0.0004
}

ALERT_STATE = {}

#################################
# 유틸
#################################

def fmt(n):
    if n is None:
        return "조회 실패"
    if n >= 100:
        return f"{n:,.0f}"
    elif n >= 1:
        return f"{n:,.2f}"
    else:
        return f"{n:,.4f}"

def ensure_data_dir():
    os.makedirs("/app/data", exist_ok=True)

def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return default

def save_json(path, data):
    ensure_data_dir()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

#################################
# 시간
#################################

def is_night_time():
    kst = datetime.utcnow() + timedelta(hours=9)
    h = kst.hour
    return h >= NIGHT_START or h < NIGHT_END

#################################
# 가격 조회
#################################

def safe_get(url, params=None):
    try:
        return requests.get(url, params=params, timeout=3).json()
    except:
        return None

def get_price(exchange, coin):
    try:
        if exchange == "upbit":
            data = safe_get("https://api.upbit.com/v1/ticker", {"markets": f"KRW-{coin}"})
            return float(data[0]["trade_price"])

        elif exchange == "bithumb":
            data = safe_get(f"https://api.bithumb.com/public/ticker/{coin}_KRW")
            if data["status"] != "0000":
                return None
            return float(data["data"]["closing_price"])

    except:
        return None

#################################
# 전체 가격
#################################

def get_upbit_all():
    try:
        markets = safe_get("https://api.upbit.com/v1/market/all")
        krw = [m['market'] for m in markets if m['market'].startswith("KRW-")]

        tickers = safe_get("https://api.upbit.com/v1/ticker", {"markets": ",".join(krw)})

        return {d['market'].replace("KRW-", ""): float(d['trade_price']) for d in tickers}
    except:
        return {}

def get_bithumb_all():
    try:
        data = safe_get("https://api.bithumb.com/public/ticker/ALL_KRW")
        if data["status"] != "0000":
            return {}
        return {k: float(v["closing_price"]) for k, v in data["data"].items() if k != "date"}
    except:
        return {}

#################################
# 입출금
#################################

def get_bithumb_wallet_status(coin):
    try:
        data = safe_get(f"https://api.bithumb.com/public/assetsstatus/{coin}")
        if data["status"] != "0000":
            return None, None
        d = data["data"]
        return int(d["deposit_status"]), int(d["withdrawal_status"])
    except:
        return None, None

#################################
# 명령어
#################################

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    coin = context.args[0].upper()

    up = get_price("upbit", coin)
    bt = get_price("bithumb", coin)

    if up and bt:
        gap = (up - bt) / bt * 100
        gap_txt = f"{gap:+.3f}%"
    else:
        gap_txt = "조회 실패"

    await update.message.reply_text(
        f"{coin}\n업비트 {fmt(up)}\n빗썸 {fmt(bt)}\n괴리율 {gap_txt}"
    )

#################################
# GAP
#################################

async def gap_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    threshold = float(context.args[0])
    await send_gap(update.effective_chat.id, threshold, update)

async def send_gap(chat_id, threshold, update=None):
    up = get_upbit_all()
    bt = get_bithumb_all()

    result = []

    for coin in up:
        if coin in bt:
            gap = (up[coin] - bt[coin]) / bt[coin] * 100
            if abs(gap) >= threshold:
                result.append((coin, gap))

    result.sort(key=lambda x: abs(x[1]), reverse=True)

    msg = "\n".join([f"{c} {g:+.2f}%" for c, g in result[:20]])

    if update:
        await update.message.reply_text(msg or "없음")
    else:
        await _APP.bot.send_message(chat_id=chat_id, text=msg or "없음")

#################################
# 알람 루프
#################################

async def check_alarms(app):
    alarms = load_json(ALARM_FILE, [])

    for a in alarms:
        high = get_price(a["ex_high"], a["coin"])
        low = get_price(a["ex_low"], a["coin"])

        if not high or not low:
            continue

        gap = high - low

        if gap >= a["diff"]:
            await app.bot.send_message(
                chat_id=a["chat_id"],
                text=f"{a['coin']} 차익 발생 {fmt(gap)}원"
            )

async def alarm_loop(app):
    while True:
        await check_alarms(app)
        await asyncio.sleep(CHECK_INTERVAL)

#################################
# main
#################################

_APP = None

def main():
    global _APP

    ensure_data_dir()

    app = ApplicationBuilder().token(TOKEN).build()
    _APP = app

    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("gap", gap_cmd))

    async def start(app):
        asyncio.create_task(alarm_loop(app))

    app.post_init = start
    app.run_polling()

if __name__ == "__main__":
    main()
