import os
import json
import requests
import asyncio
from datetime import datetime, timedelta
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
# 🇰🇷 한국시간 기준 밤 체크
#################################

def is_night_time():
    kst = datetime.utcnow() + timedelta(hours=9)
    h = kst.hour
    return h >= NIGHT_START or h < NIGHT_END

#################################
# ✅ 안전한 가격 조회 (0원 완전 차단)
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

            # 🔥 status 체크
            if data.get("status") != "0000":
                return None

            price = float(data["data"]["closing_price"])

        else:
            return None

        # 🔥 0원 또는 음수 차단
        if price <= 0:
            return None

        return price

    except:
        return None

#################################
# 📊 업비트 vs 빗썸 전체 조회
#################################

def get_upbit_all():
    try:
        markets = requests.get(
            "https://api.upbit.com/v1/market/all",
            timeout=3
        ).json()

        krw = [m['market'] for m in markets if m['market'].startswith("KRW-")]

        tickers = requests.get(
            "https://api.upbit.com/v1/ticker",
            params={"markets": ",".join(krw)},
            timeout=5
        ).json()

        prices = {}
        for d in tickers:
            price = float(d['trade_price'])
            if price > 0:
                prices[d['market'].replace("KRW-", "")] = price

        return prices

    except:
        return {}

def get_bithumb_all():
    try:
        r = requests.get(
            "https://api.bithumb.com/public/ticker/ALL_KRW",
            timeout=5
        )
        data = r.json()

        if data.get("status") != "0000":
            return {}

        raw = data['data']

        prices = {}
        for coin in raw:
            if coin == "date":
                continue

            price = float(raw[coin]['closing_price'])

            if price > 0:  # 🔥 0원 차단
                prices[coin] = price

        return prices

    except:
        return {}

#################################
# 명령어
#################################

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📌 사용법\n"
        "/set 업비트 빗썸 ETH 1000\n"
        "/list\n"
        "/delete 번호\n"
        "/night 밤모드 ON/OFF\n"
        "/gap 0.5"
    )

async def gap_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("사용법: /gap 0.5")
        return

    try:
        threshold = float(context.args[0])
    except:
        await update.message.reply_text("숫자만 입력해줘.")
        return

    await update.message.reply_text("📊 전체 코인 비교중...")

    upbit = get_upbit_all()
    bithumb = get_bithumb_all()

    if not upbit or not bithumb:
        await update.message.reply_text("가격 조회 실패")
        return

    results = []

    for coin in upbit:
        if coin in bithumb:
            if bithumb[coin] <= 0:
                continue

            gap = (upbit[coin] - bithumb[coin]) / bithumb[coin] * 100

            if abs(gap) >= threshold:
                results.append((coin, round(gap, 3)))

    if not results:
        await update.message.reply_text("조건 만족 코인 없음")
        return

    results.sort(key=lambda x: abs(x[1]), reverse=True)

    msg = "📊 업비트 ↔ 빗썸 괴리율\n"
    for coin, g in results[:20]:
        msg += f"{coin} : {g}%\n"

    await update.message.reply_text(msg)

#################################
# 🔔 알람 체크 루프
#################################

async def check_alarms(app):
    alarms = load_alarms()
    night_data = load_night()
    now_night = is_night_time()

    for a in alarms:
        key = f"{a['chat_id']}_{a['coin']}_{a['ex_high']}_{a['ex_low']}"
        state = ALERT_STATE.get(key, {"count": 0, "max_gap": 0})

        high = get_price(a["ex_high"], a["coin"])
        low = get_price(a["ex_low"], a["coin"])

        # 🔥 가격 이상 차단
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

        buy_fee = low * FEE_RATE.get(a["ex_low"], 0)
        sell_fee = high * FEE_RATE.get(a["ex_high"], 0)
        net_profit = gap - buy_fee - sell_fee

        await app.bot.send_message(
            chat_id=a["chat_id"],
            text=(
                f"🚨 차익 발생 [{a['coin']}]\n"
                f"{a['kr_high']} : {high:,.0f}원\n"
                f"{a['kr_low']} : {low:,.0f}원\n"
                f"📈 가격차 : {gap:,.0f}원\n"
                f"💸 순이익 : {net_profit:,.0f}원"
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
    app.add_handler(CommandHandler("gap", gap_cmd))

    async def start(app):
        asyncio.create_task(alarm_loop(app))

    app.post_init = start
    app.run_polling()

if __name__ == "__main__":
    main()
