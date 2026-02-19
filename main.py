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
# 안전한 가격 조회 (0원 차단 + status 체크)
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
# 📊 전체 코인 조회 (gap용)
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

            if price > 0:
                prices[coin] = price

        return prices

    except:
        return {}

#################################
# 🔒 입출금 상태 조회
#################################

def get_upbit_wallet_status(coin):
    try:
        payload = {
            "access_key": UPBIT_ACCESS,
            "nonce": str(uuid.uuid4())
        }
        token = jwt.encode(payload, UPBIT_SECRET, algorithm="HS256")
        headers = {"Authorization": f"Bearer {token}"}

        r = requests.get(
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
        r = requests.get(
            f"https://api.bithumb.com/public/assetsstatus/{coin}",
            timeout=3
        )
        data = r.json()
        if data["status"] == "0000":
            d = data["data"]
            return int(d["deposit_status"]), int(d["withdrawal_status"])
        return None, None
    except:
        return None, None

def build_status_msg(upbit_state, b_dep, b_wd):
    msgs = []

    if upbit_state == "paused":
        msgs.append("⛔ 업비트 입출금 중단")
    elif upbit_state == "withdraw_only":
        msgs.append("⚠️ 업비트 입금불가")
    elif upbit_state == "deposit_only":
        msgs.append("⚠️ 업비트 출금불가")

    if b_dep is not None and b_wd is not None:
        if b_dep == 0 and b_wd == 0:
            msgs.append("⛔ 빗썸 입출금 중단")
        elif b_dep == 0:
            msgs.append("⚠️ 빗썸 입금불가")
        elif b_wd == 0:
            msgs.append("⚠️ 빗썸 출금불가")

    return "\n".join(msgs) if msgs else "✅ 입출금 정상"

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

    night = load_night().get(str(cid), False)

    msg = f"📌 내 알람 (밤모드:{'ON' if night else 'OFF'})\n"
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

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("사용법: /status ETH")
        return

    coin = context.args[0].upper()

    await update.message.reply_text(f"🔍 {coin} 조회중...")

    upbit_price = get_price("upbit", coin)
    bithumb_price = get_price("bithumb", coin)
    upbit_state = get_upbit_wallet_status(coin)
    b_dep, b_wd = get_bithumb_wallet_status(coin)

    # 업비트 입출금 상태
    if upbit_state == "working":
        upbit_wallet = "✅ 정상"
    elif upbit_state == "paused":
        upbit_wallet = "⛔ 입출금 중단"
    elif upbit_state == "withdraw_only":
        upbit_wallet = "⚠️ 입금불가"
    elif upbit_state == "deposit_only":
        upbit_wallet = "⚠️ 출금불가"
    else:
        upbit_wallet = "❓ 알 수 없음"

    # 빗썸 입출금 상태
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

    # 괴리율
    if upbit_price and bithumb_price:
        gap_pct = (upbit_price - bithumb_price) / bithumb_price * 100
        gap_line = f"📊 괴리율 : {gap_pct:+.3f}%"
    else:
        gap_line = "📊 괴리율 : 조회 실패"

    msg = (
        f"📊 {coin} 현황\n"
        f"업비트 : {f'{upbit_price:,.0f}원' if upbit_price else '조회 실패'}\n"
        f"빗썸 : {f'{bithumb_price:,.0f}원' if bithumb_price else '조회 실패'}\n"
        f"{gap_line}\n"
        f"업비트 입출금 : {upbit_wallet}\n"
        f"빗썸 입출금 : {bithumb_wallet}"
    )

    await update.message.reply_text(msg)


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
        if coin in bithumb and bithumb[coin] > 0:
            gap = (upbit[coin] - bithumb[coin]) / bithumb[coin] * 100
            if abs(gap) >= threshold:
                results.append((coin, round(gap, 3)))

    if not results:
        await update.message.reply_text("조건 만족 코인 없음")
        return

    results.sort(key=lambda x: abs(x[1]), reverse=True)

    await update.message.reply_text("🔒 입출금 상태 조회중...")

    msg = "📊 업비트 ↔ 빗썸 괴리율\n"
    for coin, g in results[:20]:
        upbit_state = get_upbit_wallet_status(coin)
        b_dep, b_wd = get_bithumb_wallet_status(coin)

        if upbit_state == "working":
            u_icon = "✅"
        elif upbit_state == "paused":
            u_icon = "⛔"
        else:
            u_icon = "⚠️"

        if b_dep is None:
            b_icon = "❓"
        elif b_dep == 1 and b_wd == 1:
            b_icon = "✅"
        elif b_dep == 0 and b_wd == 0:
            b_icon = "⛔"
        else:
            b_icon = "⚠️"

        msg += f"{coin} : {g}% | 업{u_icon} 빗{b_icon}\n"

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
    app.add_handler(CommandHandler("status", status_cmd))

    async def start(app):
        asyncio.create_task(alarm_loop(app))

    app.post_init = start
    app.run_polling()

if __name__ == "__main__":
    main()
