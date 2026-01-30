import os
import json
import requests
from telegram.ext import Application, CommandHandler, ContextTypes

#################################
# 환경변수 (Railway Variables)
#################################

TOKEN = os.environ["BOT_TOKEN"]

ALARM_FILE = "alarms.json"
CHECK_INTERVAL = 5

#################################
# 거래소 설정
#################################

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
    "coinone": 0.0004,
    "korbit": 0.0004,
    "gopax": 0.0004,
}

#################################
# 알람 저장
#################################

def load_alarms():
    try:
        with open(ALARM_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
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
                timeout=5).json()[0]["trade_price"])

        if exchange == "bithumb":
            return float(requests.get(
                f"https://api.bithumb.com/public/ticker/{coin}_KRW",
                timeout=5).json()["data"]["closing_price"])

        if exchange == "coinone":
            return float(requests.get(
                f"https://api.coinone.co.kr/ticker/?currency={coin.lower()}",
                timeout=5).json()["last"])

        if exchange == "korbit":
            return float(requests.get(
                f"https://api.korbit.co.kr/v1/ticker/detailed?currency_pair={coin.lower()}_krw",
                timeout=5).json()["last"])

        if exchange == "gopax":
            return float(requests.get(
                f"https://api.gopax.co.kr/trading-pairs/{coin}-KRW/ticker",
                timeout=5).json()["price"])
    except:
        return None

#################################
# 명령어
#################################

async def help_cmd(update, context):
    await update.message.reply_text(
        "📌 사용법\n"
        "/set 업비트 빗썸 ETH 1000\n"
        "/list\n"
        "/delete 번호"
    )

async def set_alarm(update, context):
    if len(context.args) != 4:
        await update.message.reply_text("❌ /set 업비트 빗썸 ETH 1000")
        return

    ex1, ex2, coin, diff = context.args
    coin = coin.upper()

    if ex1 not in EXCHANGE_MAP or ex2 not in EXCHANGE_MAP:
        await update.message.reply_text("❌ 거래소 오류")
        return

    try:
        diff = float(diff)
    except:
        await update.message.reply_text("❌ 숫자만 입력")
        return

    alarms = load_alarms()
    alarms.append({
        "chat_id": update.effective_chat.id,
        "ex_high": EXCHANGE_MAP[ex1],
        "ex_low": EXCHANGE_MAP[ex2],
        "kr_high": ex1,
        "kr_low": ex2,
        "coin": coin,
        "diff": diff,
        "trigger_count": 0
    })

    save_alarms(alarms)
    await update.message.reply_text("✅ 알람 등록 완료")

async def list_alarm(update, context):
    alarms = load_alarms()
    my = [a for a in alarms if a["chat_id"] == update.effective_chat.id]

    if not my:
        await update.message.reply_text("알람 없음")
        return

    msg = "📋 내 알람 목록\n"
    for i, a in enumerate(my):
        msg += f"{i+1}. {a['kr_high']} → {a['kr_low']} {a['coin']} {a['diff']}원\n"

    await update.message.reply_text(msg)

async def delete_alarm(update, context):
    alarms = load_alarms()
    my = [a for a in alarms if a["chat_id"] == update.effective_chat.id]

    try:
        idx = int(context.args[0]) - 1
        alarms.remove(my[idx])
        save_alarms(alarms)
        await update.message.reply_text("🗑 삭제 완료")
    except:
        await update.message.reply_text("❌ /delete 번호")

#################################
# 알람 체크 루프
#################################

async def alarm_checker(context):
    alarms = load_alarms()
    changed = False

    for a in alarms:
        p1 = get_price(a["ex_high"], a["coin"])
        p2 = get_price(a["ex_low"], a["coin"])
        if not p1 or not p2:
            continue

        gap = p1 - p2

        if gap >= a["diff"] and a["trigger_count"] < 5:
            fee = p1 * FEE_RATE[a["ex_high"]] + p2 * FEE_RATE[a["ex_low"]]
            net = gap - fee

            await context.bot.send_message(
                a["chat_id"],
                f"🚨 {a['coin']} 차익 발생\n"
                f"{a['kr_high']}: {p1:,.0f}\n"
                f"{a['kr_low']}: {p2:,.0f}\n"
                f"차이: {gap:,.0f}원\n"
                f"수수료: {fee:,.0f}\n"
                f"순이익: {net:,.0f}"
            )

            a["trigger_count"] += 1
            changed = True

        if gap < a["diff"]:
            if a["trigger_count"] != 0:
                a["trigger_count"] = 0
                changed = True

    if changed:
        save_alarms(alarms)

#################################
# 실행
#################################

def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("set", set_alarm))
    app.add_handler(CommandHandler("list", list_alarm))
    app.add_handler(CommandHandler("delete", delete_alarm))

    app.job_queue.run_repeating(alarm_checker, interval=CHECK_INTERVAL, first=5)

    print("🚀 Railway 알람봇 실행중")
    app.run_polling()

if __name__ == "__main__":
    main()
