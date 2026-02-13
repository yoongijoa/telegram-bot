import os
import json
import requests
import asyncio
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TOKEN = os.getenv("BOT_TOKEN")

ALARM_FILE = "alarms.json"
NIGHT_FILE = "night_mode.json"

CHECK_INTERVAL = 5
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
        with open(NIGHT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_night(data):
    with open(NIGHT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

#################################
# 시간
#################################

def is_night_time():
    kst = datetime.utcnow() + timedelta(hours=9)
    h = kst.hour
    return h >= NIGHT_START or h < NIGHT_END

#################################
# 안전한 가격 조회 (0원 방지)
#################################

def get_price(exchange, coin):
    try:
        if exchange == "upbit":
            r = requests.get(
                f"https://api.upbit.com/v1/ticker?markets=KRW-{coin}",
                timeout=3
            )
            data = r.json()
            if not data:
                return None
            price = float(data[0]["trade_price"])

        elif exchange == "bithumb":
            r = requests.get(
                f"https://api.bithumb.com/public/ticker/{coin}_KRW",
                timeout=3
            )
            data = r.json()
            if data.get("status") != "0000":
                return None
            price = float(data["data"]["closing_price"])

        else:
            return None

        if price <= 0:
            return None

        return price

    except:
        return None

#################################
# 명령어
#################################

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/set 업비트 빗썸 ETH 1000\n"
        "/list\n"
        "/delete 번호\n"
        "/night"
    )

async def set_alarm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 4:
        await update.message.reply_text("❌ /set 업비트 빗썸 ETH 1000")
        return

    ex_high_kr, ex_low_kr, coin, diff = context.args
    coin = coin.upper()

    if ex_high_kr not in EXCHANGE_MAP or ex_low_kr not in EXCHANGE_MAP:
        await update.message.reply_text("거래소 이름 오류")
        return

    try:
        diff = float(diff)
    except:
        await update.message.reply_text("차익은 숫자로 입력")
        return

    alarms = load_alarms()
    cid = update.effective_chat.id

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
    await update.message.reply_text("✅ 알람 저장 완료")

async def list_alarm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    alarms = load_alarms()
    cid = update.effective_chat.id

    my = [a for a in alarms if a["chat_id"] == cid]

    if not my:
        await update.message.reply_text("알람 없음")
        return

    msg = "📌 내 알람\n"
    for i, a in enumerate(my):
        msg += f"{i+1}. {a['kr_high']}→{a['kr_low']} {a['coin']} {a['diff']}원\n"

    await update.message.reply_text(msg)

async def delete_alarm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return

    alarms = load_alarms()
    cid = update.effective_chat.id
    my = [a for a in alarms if a["chat_id"] == cid]

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

    await update.message.reply_text(f"밤모드 {'ON' if data[cid] else 'OFF'}")

#################################
# 알람 체크
#################################

async def check_alarms(app):
    alarms = load_alarms()
    night_data = load_night()
    now_night = is_night_time()

    for a in alarms:
        key = f"{a['chat_id']}_{a['coin']}"
        state = ALERT_STATE.get(key, {"count": 0, "max_gap": 0})

        high = get_price(a["ex_high"], a["coin"])
        low = get_price(a["ex_low"], a["coin"])

        if high is None or low is None:
            continue

        gap = high - low
        threshold = a["diff"]

        if night_data.get(str(a["chat_id"]), False) and now_night:
            threshold *= 2

        if gap < threshold:
            ALERT_STATE[key] = {"count": 0, "max_gap": 0}
            continue

        send = False

        if state["count"] < 5:
            send = True
            state["count"] += 1
            state["max_gap"] = max(state["max_gap"], gap)
        else:
            if gap > state["max_gap"]:
                send = True
                state["max_gap"] = gap

        ALERT_STATE[key] = state

        if not send:
            continue

        await app.bot.send_message(
            chat_id=a["chat_id"],
            text=(
                f"🚨 차익 발생 [{a['coin']}]\n"
                f"{a['kr_high']} : {high:,.0f}원\n"
                f"{a['kr_low']} : {low:,.0f}원\n"
                f"가격차 : {gap:,.0f}원"
            )
        )

async def alarm_loop(app):
    while True:
        await check_alarms(app)
        await asyncio.sleep(CHECK_INTERVAL)

#################################
# 실행
#################################

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
