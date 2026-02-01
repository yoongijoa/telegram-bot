import os
import json
import requests
import asyncio
from datetime import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

#################################
# 환경변수
#################################

TOKEN = os.getenv("BOT_TOKEN")

ALARM_FILE = "alarms.json"
NIGHT_FILE = "night_mode.json"

CHECK_INTERVAL = 5

NIGHT_START = 23
NIGHT_END = 7

EXCHANGE_MAP = {
    "업비트": "upbit",
    "빗썸": "bithumb",
    "코인원": "coinone",
    "코빗": "korbit",
    "고팍스": "gopax",
}

FEE_RATE = {
    "upbit": 0.0005,
    "bithumb": 0.0004
}

#################################
# 저장
#################################

def load_alarms():
    try:
        with open(ALARM_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def save_alarms(data):
    with open(ALARM_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_night():
    try:
        with open(NIGHT_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_night(data):
    with open(NIGHT_FILE, "w") as f:
        json.dump(data, f)

#################################
# 밤 시간 체크
#################################

def is_night_time():
    h = datetime.now().hour
    return h >= NIGHT_START or h < NIGHT_END

#################################
# 가격 조회
#################################

def get_price(exchange, coin):
    try:
        if exchange == "upbit":
            return float(requests.get(
                f"https://api.upbit.com/v1/ticker?markets=KRW-{coin}",
                timeout=3
            ).json()[0]["trade_price"])

        if exchange == "bithumb":
            return float(requests.get(
                f"https://api.bithumb.com/public/ticker/{coin}_KRW",
                timeout=3
            ).json()["data"]["closing_price"])
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
        "/night  밤모드 ON/OFF\n\n"
        "※ 같은 조건으로 다시 입력하면 자동 수정됨"
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
    cid = update.effective_chat.id

    # ✅ 기존 같은 알람 있으면 제거 (자동 덮어쓰기 핵심)
    alarms = [
        a for a in alarms
        if not (
            a["chat_id"] == cid and
            a["ex_high"] == EXCHANGE_MAP[ex_high_kr] and
            a["ex_low"] == EXCHANGE_MAP[ex_low_kr] and
            a["coin"] == coin
        )
    ]

    alarms.append({
        "chat_id": cid,
        "ex_high": EXCHANGE_MAP[ex_high_kr],
        "ex_low": EXCHANGE_MAP[ex_low_kr],
        "kr_high": ex_high_kr,
        "kr_low": ex_low_kr,
        "coin": coin,
        "diff": diff
    })

    save_alarms(alarms)

    await update.message.reply_text("✅ 기존 알람 자동 수정 완료")

async def list_alarm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    alarms = load_alarms()
    my = [a for a in alarms if a["chat_id"] == update.effective_chat.id]

    night = load_night().get(str(update.effective_chat.id), False)
    night_txt = "🌙ON" if night else "OFF"

    if not my:
        await update.message.reply_text("알람 없음")
        return

    msg = f"📌 내 알람 (밤모드:{night_txt})\n"
    for i, a in enumerate(my):
        msg += f"{i+1}. {a['kr_high']} → {a['kr_low']} {a['coin']} {a['diff']}원\n"

    await update.message.reply_text(msg)

async def delete_alarm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    alarms = load_alarms()
    my = [a for a in alarms if a["chat_id"] == update.effective_chat.id]

    if not context.args:
        return

    idx = int(context.args[0]) - 1
    if idx < 0 or idx >= len(my):
        return

    alarms.remove(my[idx])
    save_alarms(alarms)
    await update.message.reply_text("🗑 삭제 완료")

async def night_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_night()
    cid = str(update.effective_chat.id)

    data[cid] = not data.get(cid, False)
    save_night(data)

    state = "🌙 ON" if data[cid] else "☀️ OFF"
    await update.message.reply_text(f"밤모드 {state}")

#################################
# 알람 체크
#################################

async def check_alarms(app):
    alarms = load_alarms()
    night_data = load_night()
    now_night = is_night_time()

    for a in alarms:
        chat_id = str(a["chat_id"])
        night_on = night_data.get(chat_id, False)

        high = get_price(a["ex_high"], a["coin"])
        low = get_price(a["ex_low"], a["coin"])

        if not high or not low:
            continue

        gap = high - low
        threshold = a["diff"]

        if night_on and now_night:
            threshold *= 2

        if gap < threshold:
            continue

        buy_fee = low * FEE_RATE.get(a["ex_low"], 0)
        sell_fee = high * FEE_RATE.get(a["ex_high"], 0)

        net_profit = gap - buy_fee - sell_fee

        try:
           await app.bot.send_message(
    chat_id=a["chat_id"],
    text=(
        f"🚨 차익 발생! [{a['coin']}]\n"
        f"{a['kr_high']} : {high:,.0f}원\n"
        f"{a['kr_low']} : {low:,.0f}원\n"
        f"📈 가격차 : {gap:,.0f}원\n"
        f"💸 수수료 제외 순이익 : {net_profit:,.0f}원"
    )
)

        except:
            pass

#################################
# 루프
#################################

async def alarm_loop(app):
    while True:
        await check_alarms(app)
        await asyncio.sleep(CHECK_INTERVAL)

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("set", set_alarm))
    app.add_handler(CommandHandler("list", list_alarm))
    app.add_handler(CommandHandler("delete", delete_alarm))
    app.add_handler(CommandHandler("night", night_toggle))

    async def start(app):
        asyncio.create_task(alarm_loop(app))

    app.post_init = start
    app.run_polling()

if __name__ == "__main__":
    main()

