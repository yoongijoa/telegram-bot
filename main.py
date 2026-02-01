import os
import json
import requests
from datetime import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

#################################
# 환경변수
#################################

TOKEN = os.getenv("BOT_TOKEN")
ALARM_FILE = "alarms.json"
CHECK_INTERVAL = 5

EXCHANGE_MAP = {
    "업비트": "upbit",
    "빗썸": "bithumb",
    "코인원": "coinone",
    "코빗": "korbit",
    "고팍스": "gopax",
}

FEE_RATE = {
    "upbit": 0.0005,
    "bithumb": 0.0004,
    "coinone": 0.0005,
    "korbit": 0.0005,
    "gopax": 0.0005,
}

#################################
# 알람 저장
#################################

def load_alarms():
    try:
        with open(ALARM_FILE, "r", encoding="utf-8") as f:
            alarms = json.load(f)
            for a in alarms:
                a.setdefault("trigger_count", 0)
                a.setdefault("night_mode", False)   # 🌙 밤모드 기본 OFF
            return alarms
    except:
        return []

def save_alarms(alarms):
    with open(ALARM_FILE, "w", encoding="utf-8") as f:
        json.dump(alarms, f, ensure_ascii=False, indent=2)

#################################
# 가격 조회
#################################

def get_price(exchange, coin):
    try:
        if exchange == "upbit":
            return float(requests.get(
                f"https://api.upbit.com/v1/ticker?markets=KRW-{coin}",
                timeout=5
            ).json()[0]["trade_price"])

        if exchange == "bithumb":
            return float(requests.get(
                f"https://api.bithumb.com/public/ticker/{coin}_KRW",
                timeout=5
            ).json()["data"]["closing_price"])

        if exchange == "coinone":
            return float(requests.get(
                f"https://api.coinone.co.kr/ticker/?currency={coin.lower()}",
                timeout=5
            ).json()["last"])

        if exchange == "korbit":
            return float(requests.get(
                f"https://api.korbit.co.kr/v1/ticker/detailed?currency_pair={coin.lower()}_krw",
                timeout=5
            ).json()["last"])

        if exchange == "gopax":
            return float(requests.get(
                f"https://api.gopax.co.kr/trading-pairs/{coin}-KRW/ticker",
                timeout=5
            ).json()["price"])
    except:
        return None

#################################
# 명령어
#################################

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📌 사용법\n"
        "/set 업비트 빗썸 ETH 1000\n"
        "/list\n"
        "/delete 번호\n"
        "/밤  → 밤모드 ON/OFF"
    )

async def set_alarm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 4:
        await update.message.reply_text("❌ /set 업비트 빗썸 ETH 1000")
        return

    ex_high_kr, ex_low_kr, coin, diff = context.args
    coin = coin.upper()

    if ex_high_kr not in EXCHANGE_MAP or ex_low_kr not in EXCHANGE_MAP:
        await update.message.reply_text("❌ 거래소 오류")
        return

    try:
        diff = float(diff)
    except:
        await update.message.reply_text("❌ 숫자 입력")
        return

    alarms = load_alarms()
    alarms.append({
        "chat_id": update.effective_chat.id,
        "ex_high": EXCHANGE_MAP[ex_high_kr],
        "ex_low": EXCHANGE_MAP[ex_low_kr],
        "kr_high": ex_high_kr,
        "kr_low": ex_low_kr,
        "coin": coin,
        "diff": diff,
        "trigger_count": 0,
        "night_mode": False
    })

    save_alarms(alarms)
    await update.message.reply_text("✅ 알람 등록 완료")

async def list_alarm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    alarms = load_alarms()
    my = [a for a in alarms if a["chat_id"] == update.effective_chat.id]

    if not my:
        await update.message.reply_text("알람 없음")
        return

    msg = "📌 내 알람\n"
    for i, a in enumerate(my):
        night = "🌙ON" if a["night_mode"] else "OFF"
        msg += f"{i+1}. {a['kr_high']} → {a['kr_low']} {a['coin']} {a['diff']}원 |_]()_]()
