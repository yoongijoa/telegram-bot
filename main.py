import os
import json
import requests
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
# 가격 조회
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
            return float(data[0]["trade_price"])

        elif exchange == "bithumb":
            r = requests.get(
                f"https://api.bithumb.com/public/ticker/{coin}_KRW",
                timeout=3
            )
            data = r.json()
            if data.get("status") != "0000":
                return None
            return float(data["data"]["closing_price"])
        else:
            return None
    except:
        return None

def get_upbit_all():
    try:
        markets = requests.get("https://api.upbit.com/v1/market/all", timeout=3).json()
        krw = [m['market'] for m in markets if m['market'].startswith("KRW-")]
        tickers = requests.get(
            "https://api.upbit.com/v1/ticker",
            params={"markets": ",".join(krw)}, timeout=5
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
        r = requests.get("https://api.bithumb.com/public/ticker/ALL_KRW", timeout=5)
        data = r.json()
        if data.get("status") != "0000":
            return {}
        raw = data['data']
        prices = {}
        for coin in raw:
            if coin == "date":
                continue
            price = float(raw[coin]['closing_price'])
            if price > 0:
                prices[coin] = price
        return prices
    except:
        return {}

def get_upbit_wallet_status():
    try:
        r = requests.get("https://api.upbit.com/v1/status/wallet", timeout=3)
        data = r.json()
        result = {}
        for d in data:
            result[d.get("currency")] = d.get("wallet_state")
        return result
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
        "/night\n"
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
    upbit_wallet = get_upbit_wallet_status()

    if not upbit or not bithumb:
        await update.message.reply_text("가격 조회 실패")
        return

    results = []
    for coin in upbit:
        if coin not in bithumb:
            continue
        if bithumb[coin] <= 0:
            continue
        gap = (upbit[coin] - bithumb[coin]) / bithumb[coin] * 100
        if abs(gap) < threshold:
            continue
        wallet_state = upbit_wallet.get(coin, "unknown")
        wallet_text = {
            "working": "🟢 정상",
            "withdraw_only": "🟡 출금만",
            "deposit_only": "🟡 입금만",
            "paused": "🔴 입출금중단"
        }.get(wallet_state, "⚪ 확인불가")
        results.append((coin, round(gap, 3), wallet_text))

    if not results:
        await update.message.reply_text("조건 만족 코인 없음")
        return

    results.sort(key=lambda x: abs(x[1]), reverse=True)
    msg = "📊 업비트 ↔ 빗썸 괴리율 (업비트 입출금상태)\n\n"
    for coin, g, wallet in results[:20]:
        msg += f"{coin} : {g}%  {wallet}\n"
    await update.message.reply_text(msg)

# --- /set ---
async def set_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 4:
        await update.message.reply_text("사용법: /set 업비트 빗썸 COIN 금액")
        return
    source = context.args[0]
    target = context.args[1]
    coin = context.args[2].upper()
    try:
        amount = float(context.args[3])
    except:
        await update.message.reply_text("금액은 숫자로 입력해야 합니다.")
        return

    alarms = load_alarms()
    alarms.append({
        "source": source,
        "target": target,
        "coin": coin,
        "amount": amount
    })
    save_alarms(alarms)
    await update.message.reply_text(f"✅ 알람 등록 완료: {source} → {target} {coin} {amount}")

# --- /list ---
async def list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    alarms = load_alarms()
    if not alarms:
        await update.message.reply_text("등록된 알람이 없습니다.")
        return
    msg = "📋 등록된 알람 목록\n"
    for i, a in enumerate(alarms, start=1):
        msg += f"{i}. {a['source']} → {a['target']} {a['coin']} {a['amount']}\n"
    await update.message.reply_text(msg)

# --- /delete ---
async def delete_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("삭제할 번호를 입력해주세요. 예: /delete 1")
        return
    try:
        idx = int(context.args[0]) - 1
        alarms = load_alarms()
        if 0 <= idx < len(alarms):
            removed = alarms.pop(idx)
            save_alarms(alarms)
            await update.message.reply_text(f"✅ 삭제 완료: {removed['coin']}")
        else:
            await update.message.reply_text("번호가 잘못되었습니다.")
    except:
        await update.message.reply_text("숫자만 입력해주세요.")

# --- /night ---
async def night_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = load_night()
    state["enabled"] = not state.get("enabled", False)
    save_night(state)
    status = "켜짐" if state["enabled"] else "꺼짐"
    await update.message.reply_text(f"🌙 밤 모드 {status}")

#################################
# 실행
#################################
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("gap", gap_cmd))
    app.add_handler(CommandHandler("set", set_cmd))
    app.add_handler(CommandHandler("list", list_cmd))
    app.add_handler(CommandHandler("delete", delete_cmd))
    app.add_handler(CommandHandler("night", night_cmd))

    app.run_polling()

if __name__ == "__main__":
    main()
