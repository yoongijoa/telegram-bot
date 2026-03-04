import os
import json
import requests
import asyncio
import jwt
import uuid
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

#################################
# 환경변수
#################################

TOKEN = os.getenv("BOT_TOKEN")
UPBIT_ACCESS = os.getenv("UPBIT_ACCESS")
UPBIT_SECRET = os.getenv("UPBIT_SECRET")
FIXIE_URL = os.getenv("FIXIE_URL")
PROXIES = {"http": FIXIE_URL, "https": FIXIE_URL} if FIXIE_URL else {}

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

session = requests.Session()

#################################
# 저장
#################################

def load_json(file, default):
    try:
        with open(file, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return default

def save_json(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

#################################
# 🇰🇷 한국시간 기준 밤 체크
#################################

def is_night_time():
    kst = datetime.utcnow() + timedelta(hours=9)
    h = kst.hour
    return h >= NIGHT_START or h < NIGHT_END

#################################
# 안전한 가격 조회
#################################

def safe_float(value):
    try:
        v = float(value)
        return v if v > 0 else None
    except:
        return None

def get_price(exchange, coin):
    try:
        if exchange == "upbit":
            r = session.get(
                f"https://api.upbit.com/v1/ticker?markets=KRW-{coin}",
                timeout=2
            )
            data = r.json()
            if not data:
                return None
            return safe_float(data[0]["trade_price"])

        elif exchange == "bithumb":
            r = session.get(
                f"https://api.bithumb.com/public/ticker/{coin}_KRW",
                timeout=2
            )
            data = r.json()
            if data.get("status") != "0000":
                return None
            return safe_float(data["data"]["closing_price"])

    except:
        return None

#################################
# 전체 시세
#################################

def get_upbit_all():
    try:
        markets = session.get(
            "https://api.upbit.com/v1/market/all",
            timeout=3
        ).json()

        krw = [m['market'] for m in markets if m['market'].startswith("KRW-")]

        tickers = session.get(
            "https://api.upbit.com/v1/ticker",
            params={"markets": ",".join(krw)},
            timeout=4
        ).json()

        return {
            d['market'].replace("KRW-", ""): float(d['trade_price'])
            for d in tickers if float(d['trade_price']) > 0
        }
    except:
        return {}

def get_bithumb_all():
    try:
        r = session.get(
            "https://api.bithumb.com/public/ticker/ALL_KRW",
            timeout=4
        )
        data = r.json()

        if data.get("status") != "0000":
            return {}

        raw = data['data']
        return {
            coin: float(raw[coin]['closing_price'])
            for coin in raw
            if coin != "date" and float(raw[coin]['closing_price']) > 0
        }
    except:
        return {}

#################################
# 🔒 입출금 상태
#################################

def get_upbit_wallet_status(coin):
    try:
        payload = {
            "access_key": UPBIT_ACCESS,
            "nonce": str(uuid.uuid4())
        }
        token = jwt.encode(payload, UPBIT_SECRET, algorithm="HS256")
        headers = {"Authorization": f"Bearer {token}"}

        r = session.get(
            "https://api.upbit.com/v1/status/wallet",
            headers=headers,
            proxies=PROXIES,
            timeout=3
        )
        for item in r.json():
            if item["currency"] == coin:
                return item["wallet_state"]
        return "unknown"
    except:
        return "unknown"

def get_bithumb_wallet_status(coin):
    try:
        r = session.get(
            f"https://api.bithumb.com/public/assetsstatus/{coin}",
            timeout=2
        )
        data = r.json()
        if data["status"] == "0000":
            d = data["data"]
            return int(d["deposit_status"]), int(d["withdrawal_status"])
        return None, None
    except:
        return None, None

#################################
# 명령어
#################################

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("사용법: /status ETH")
        return

    coin = context.args[0].upper()
    await update.message.reply_text(f"🔍 {coin} 조회중...")

    upbit_price = get_price("upbit", coin)
    bithumb_price = get_price("bithumb", coin)

    upbit_wallet = get_upbit_wallet_status(coin)
    b_dep, b_wd = get_bithumb_wallet_status(coin)

    # 빗썸 상태
    if b_dep is None:
        bithumb_wallet = "❓ 알 수 없음"
    elif b_dep == 1 and b_wd == 1:
        bithumb_wallet = "✅ 정상"
    elif b_dep == 0 and b_wd == 0:
        bithumb_wallet = "⛔ 입출금 중단"
    elif b_dep == 0:
        bithumb_wallet = "⚠️ 입금불가"
    elif b_wd == 0:
        bithumb_wallet = "⚠️ 출금불가"
    else:
        bithumb_wallet = "❓ 알 수 없음"

    # 업비트 상태
    if upbit_wallet == "working":
        upbit_wallet_msg = "✅ 정상"
    elif upbit_wallet == "paused":
        upbit_wallet_msg = "⛔ 입출금 중단"
    elif upbit_wallet == "withdraw_only":
        upbit_wallet_msg = "⚠️ 입금불가"
    elif upbit_wallet == "deposit_only":
        upbit_wallet_msg = "⚠️ 출금불가"
    else:
        upbit_wallet_msg = "❓ 알 수 없음"

    # 괴리율
    if upbit_price and bithumb_price:
        gap_pct = (upbit_price - bithumb_price) / bithumb_price * 100
        gap_line = f"{gap_pct:+.3f}%"
    else:
        gap_line = "조회 실패"

    msg = (
        f"📊 {coin} 현황\n"
        f"업비트 : {f'{upbit_price:,.0f}원' if upbit_price else '조회 실패'}\n"
        f"빗썸 : {f'{bithumb_price:,.0f}원' if bithumb_price else '조회 실패'}\n"
        f"괴리율 : {gap_line}\n"
        f"업비트 입출금 : {upbit_wallet_msg}\n"
        f"빗썸 입출금 : {bithumb_wallet}"
    )

    await update.message.reply_text(msg)

#################################
# 알람 루프
#################################

async def check_alarms(app):
    alarms = load_json(ALARM_FILE, [])
    night_data = load_json(NIGHT_FILE, {})
    now_night = is_night_time()

    for a in alarms:
        key = f"{a['chat_id']}_{a['coin']}_{a['ex_high']}_{a['ex_low']}"
        state = ALERT_STATE.get(key, {"count": 0, "max_gap": 0})

        high = get_price(a["ex_high"], a["coin"])
        low = get_price(a["ex_low"], a["coin"])

        if not high or not low:
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
            state["max_gap"] = gap
        elif gap > state["max_gap"]:
            send = True
            state["max_gap"] = gap

        ALERT_STATE[key] = state

        if not send:
            continue

        buy_fee = low * FEE_RATE[a["ex_low"]]
        sell_fee = high * FEE_RATE[a["ex_high"]]
        net_profit = gap - buy_fee - sell_fee

        await app.bot.send_message(
            chat_id=a["chat_id"],
            text=(
                f"🚨 차익 발생 [{a['coin']}]\n"
                f"{a['kr_high']} : {high:,.0f}원\n"
                f"{a['kr_low']} : {low:,.0f}원\n"
                f"가격차 : {gap:,.0f}원\n"
                f"예상 순이익 : {net_profit:,.0f}원"
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

    app.add_handler(CommandHandler("status", status_cmd))

    async def start(app):
        asyncio.create_task(alarm_loop(app))

    app.post_init = start
    app.run_polling()

if __name__ == "__main__":
    main()
