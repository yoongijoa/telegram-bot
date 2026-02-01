import os
import json
import requests
from datetime import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler

#################################
# 환경변수
#################################

TOKEN = os.getenv("BOT_TOKEN")
ALARM_FILE = "alarms.json"
CHECK_INTERVAL = 15   # 안정값

#################################
# 거래소 맵
#################################

EXCHANGE_MAP = {
    "업비트": "upbit",
    "빗썸": "bithumb",
    "코인원": "coinone",
    "코빗": "korbit",
    "고팍스": "gopax",
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
                a.setdefault("night_mode", False)
            return alarms
    except:
        return []

def save_alarms(alarms):
    with open(ALARM_FILE, "w", encoding="utf-8") as f:
        json.dump(alarms, f, ensure_ascii=False, indent=2)

#################################
# 가격 조회 (timeout 필수)
#################################

def get_price(exchange, coin):
    try:
        if exchange == "upbit":
            r = requests.get(
                f"https://api.upbit.com/v1/ticker?markets=KRW-{coin}",
                timeout=3
            ).json()
            return float(r[0]["trade_price"])

        if exchange == "bithumb":
            r = requests.get(
                f"https://api.bithumb.com/public/ticker/{coin}_KRW",
                timeout=3
            ).json()
            return float(r["data"]["closing_price"])

        if exchange == "coinone":
            r = requests.get(
                f"https://api.coinone.co.kr/ticker/?currency={coin.lower()}",
                timeout=3
            ).json()
            return float(r["last"])

        if exchange == "korbit":
            r = requests.get(
                f"https://api.korbit.co.kr/v1/ticker/detailed?currency_pair={coin.lower()}_krw",
                timeout=3
            ).json()
            return float(r["last"])

        if exchange == "gopax":
            r = requests.get(
                f"https://api.gopax.co.kr/trading-pairs/{coin}-KRW/ticker",
                timeout=3
            ).json()
            return float(r["price"])
    except:
        return None

#################################
# 밤모드 판단
#################################

def is_night():
    hour = datetime.now().hour
    return hour >= 0 and hour < 7   # 00:00 ~ 07:00

#################################
# 알람 체크
#################################

async def check_alarms(app):
    alarms = load_alarms()

    for a in alarms:
        high
