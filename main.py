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
        "/delete 번호"
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
        "trigger_count": 0
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
        msg += f"{i+1}. {a['kr_high']} → {a['kr_low']} {a['coin']} {a['diff']}원\n"

    await update.message.reply_text(msg)

async def delete_alarm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    alarms = load_alarms()
    chat_id = update.effective_chat.id

    try:
        idx = int(context.args[0]) - 1
        my = [a for a in alarms if a["chat_id"] == chat_id]
        alarms.remove(my[idx])
        save_alarms(alarms)
        await update.message.reply_text("🗑 삭제 완료")
    except:
        await update.message.reply_text("❌ 번호 오류")

#################################
# 알람 체크
#################################

async def alarm_checker(context: ContextTypes.DEFAULT_TYPE):
    alarms = load_alarms()
    changed = False

    now_hour = datetime.now().hour
    is_night = 0 <= now_hour < 7   # 🌙 밤 12시~7시

    for a in alarms:
        p1 = get_price(a["ex_high"], a["coin"])
        p2 = get_price(a["ex_low"], a["coin"])

        if not p1 or not p2:
            continue

        gap = p1 - p2

        # 🌙 밤에는 기준 2배 적용
        target_diff = a["diff"] * 2 if is_night else a["diff"]

        if gap >= target_diff and a["trigger_count"] < 5:
            fee = (
                p1 * FEE_RATE[a["ex_high"]] +
                p2 * FEE_RATE[a["ex_low"]]
            )
            net = gap - fee

            await context.bot.send_message(
                a["chat_id"],
                f"🚨 {a['coin']} 가격차 발생\n"
                f"{a['kr_high']}: {p1:,.0f}\n"
                f"{a['kr_low']}: {p2:,.0f}\n"
                f"차이: {gap:,.0f}\n"
                f"기준: {target_diff:,.0f}\n"
                f"수수료: {fee:,.0f}\n"
                f"순이익: {net:,.0f}"
            )

            a["trigger_count"] += 1
            changed = True

        # 차이 줄어들면 리셋 (스팸 방지)
        if gap < target_diff and a["trigger_count"] > 0:
            a["trigger_count"] = 0
            changed = True

    if changed:
        save_alarms(alarms)


#################################
# 실행
#################################

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("set", set_alarm))
    app.add_handler(CommandHandler("list", list_alarm))
    app.add_handler(CommandHandler("delete", delete_alarm))

    app.job_queue.run_repeating(alarm_checker, interval=CHECK_INTERVAL, first=5)

    print("🚀 아비트라지 알람봇 실행중")
    app.run_polling()

if __name__ == "__main__":
    main()

