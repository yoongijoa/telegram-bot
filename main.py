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
        high = get_price(a["ex_high"], a["coin"])
        low = get_price(a["ex_low"], a["coin"])

        if not high or not low:
            continue

        diff_now = high - low
        target = a["diff"]

        # 🌙 밤모드면 기준 2배
        if a["night_mode"] and is_night():
            target *= 2

        if diff_now >= target:
            msg = (
                f"🚨 차익 기회!\n"
                f"{a['kr_high']} → {a['kr_low']} {a['coin']}\n"
                f"차이: {int(diff_now)}원"
            )
            await app.bot.send_message(a["chat_id"], msg)

#################################
# 명령어
#################################

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📌 사용법\n"
        "/set 업비트 빗썸 ETH 1000\n"
        "/list\n"
        "/delete 번호\n"
        "/night → 밤모드 ON/OFF"
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
        msg += f"{i+1}. {a['kr_high']} → {a['kr_low']} {a['coin']} {a['diff']}원 | 밤:{night}\n"

    await update.message.reply_text(msg)

async def night_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    alarms = load_alarms()

    for a in alarms:
        if a["chat_id"] == update.effective_chat.id:
            a["night_mode"] = not a["night_mode"]

    save_alarms(alarms)
    await update.message.reply_text("🌙 밤모드 토글 완료")

#################################
# 실행
#################################

async def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("set", set_alarm))
    app.add_handler(CommandHandler("list", list_alarm))
    app.add_handler(CommandHandler("night", night_mode))

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        check_alarms,
        "interval",
        seconds=CHECK_INTERVAL,
        args=[app],
        max_instances=1,
        coalesce=True
    )
    scheduler.start()

    await app.run_polling()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

