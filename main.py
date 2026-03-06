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
GAP_AUTO_FILE = "gap_auto.json"   # ✅ 추가: 자동 gap 알람 설정 저장

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

# ✅ 추가: 자동 gap 알람 설정 저장/불러오기
def load_gap_auto():
    try:
        with open(GAP_AUTO_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_gap_auto(data):
    with open(GAP_AUTO_FILE, "w", encoding="utf-8") as f:
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
        msgs.append("⛔️ 업비트 입출금 중단")
    elif upbit_state == "withdraw_only":
        msgs.append("⚠️ 업비트 입금불가")
    elif upbit_state == "deposit_only":
        msgs.append("⚠️ 업비트 출금불가")

    if b_dep is not None and b_wd is not None:
        if b_dep == 0 and b_wd == 0:
            msgs.append("⛔️ 빗썸 입출금 중단")
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
        "/gap 0.5\n"
        "/gap on 1 10  ← 1% 이상, 10분마다 자동 알람\n"
        "/gap on 1 30  ← 1% 이상, 30분마다 자동 알람\n"
        "/gap on 1     ← 분 생략시 기본 30분\n"
        "/gap off      ← 자동 알람 중단"
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
    b_dep, b_wd = get_bithumb_wallet_status(coin)

    if b_dep is None:
        bithumb_wallet = "❓ 알 수 없음"
    elif b_dep == 1 and b_wd == 1:
        bithumb_wallet = "✅ 정상"
    elif b_dep == 0 and b_wd == 0:
        bithumb_wallet = "⛔️ 입출금 중단"
    elif b_dep == 0:
        bithumb_wallet = "⚠️ 입금불가"
    elif b_wd == 0:
        bithumb_wallet = "⚠️ 출금불가"
    else:
        bithumb_wallet = "❓ 알 수 없음"

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
        f"빗썸 입출금 : {bithumb_wallet}"
    )

    await update.message.reply_text(msg)


async def gap_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ✅ /gap on 1 [분] 처리  예) /gap on 1 10  /gap on 1 30
    if context.args and context.args[0].lower() == "on":
        if len(context.args) < 2:
            await update.message.reply_text("사용법: /gap on [퍼센트] [분]\n예) /gap on 1 10  (1% 이상, 10분마다)")
            return
        try:
            threshold = float(context.args[1])
        except:
            await update.message.reply_text("퍼센트는 숫자로 입력해줘.\n예) /gap on 1 10")
            return

        # 분 인수 파싱 (없으면 기본 30분)
        interval_min = 30
        if len(context.args) >= 3:
            raw = context.args[2].replace("분", "").strip()
            try:
                interval_min = int(raw)
                if interval_min < 1:
                    raise ValueError
            except:
                await update.message.reply_text("분은 1 이상 정수로 입력해줘.\n예) /gap on 1 10")
                return

        data = load_gap_auto()
        cid = str(update.effective_chat.id)
        data[cid] = {
            "threshold": threshold,
            "interval_min": interval_min,
            "enabled": True,
            "next_run": 0   # 즉시 첫 실행 허용하려면 0, 아니면 time.time() + interval_min*60
        }
        save_gap_auto(data)

        await update.message.reply_text(
            f"✅ 자동 gap 알람 ON\n"
            f"조건 : {threshold}% 이상 & 빗썸 입출금 정상\n"
            f"주기 : {interval_min}분마다"
        )
        return

    # ✅ /gap off 처리
    if context.args and context.args[0].lower() == "off":
        data = load_gap_auto()
        cid = str(update.effective_chat.id)
        if cid in data:
            data[cid]["enabled"] = False
            save_gap_auto(data)
        await update.message.reply_text("🔕 자동 gap 알람 OFF")
        return

    # 기존 /gap 0.5 (수동 1회 조회)
    if not context.args:
        await update.message.reply_text("사용법: /gap 0.5")
        return

    try:
        threshold = float(context.args[0])
    except:
        await update.message.reply_text("숫자만 입력해줘.")
        return

    await _send_gap_result(update.effective_chat.id, threshold, update.message)


# ✅ 공통 gap 조회 함수 (수동 + 자동 모두 사용)
async def _send_gap_result(chat_id, threshold, reply_to=None):
    async def send(text):
        if reply_to:
            await reply_to.reply_text(text)
        else:
            # 자동 알람 전송 시 app 인스턴스를 전역에서 접근
            await _APP.bot.send_message(chat_id=chat_id, text=text)

    await send("📊 전체 코인 비교중...")

    upbit = get_upbit_all()
    bithumb = get_bithumb_all()

    if not upbit or not bithumb:
        await send("가격 조회 실패")
        return

    results = []
    for coin in upbit:
        if coin in bithumb and bithumb[coin] > 0:
            gap = (upbit[coin] - bithumb[coin]) / bithumb[coin] * 100
            if abs(gap) >= threshold:
                results.append((coin, round(gap, 3)))

    if not results:
        await send(f"📊 {threshold}% 이상 괴리 코인 없음")
        return

    results.sort(key=lambda x: abs(x[1]), reverse=True)
    top = results[:20]

    await send("🔒 빗썸 입출금 상태 조회중...")

    lines = []
    for coin, g in top:
        b_dep, b_wd = get_bithumb_wallet_status(coin)

        if b_dep is None:
            b_icon = "❓"
            is_open = False
        elif b_dep == 1 and b_wd == 1:
            b_icon = "✅"
            is_open = True
        elif b_dep == 0 and b_wd == 0:
            b_icon = "⛔️"
            is_open = False
        else:
            b_icon = "⚠️"
            is_open = False

        # ✅ 자동 알람 모드는 빗썸 정상인 것만 포함
        if reply_to is None and not is_open:
            continue

        lines.append(f"{coin} : {g:+.3f}% | 빗{b_icon}")

    if not lines:
        # 자동 알람일 때 조건 맞는 코인이 없으면 조용히 스킵
        if reply_to is None:
            return
        await send("조건 만족 코인 없음 (빗썸 입출금 정상 기준)")
        return

    chunk_size = 10
    for i in range(0, len(lines), chunk_size):
        chunk = lines[i:i + chunk_size]
        header = f"📊 업비트↔빗썸 괴리율 ({threshold}%↑, 빗썸정상만)\n" if i == 0 else ""
        await send(header + "\n".join(chunk))


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

        try:
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
        except Exception as e:
            print(f"[알람 전송 실패] {a['coin']} → {e}")

async def alarm_loop(app):
    while True:
        try:
            await check_alarms(app)
        except Exception as e:
            print(f"[알람 루프 오류] {e}")
        await asyncio.sleep(CHECK_INTERVAL)


import time as _time

# ✅ 자동 gap 알람 루프 - 유저별 간격 지원
async def gap_auto_loop():
    while True:
        await asyncio.sleep(60)  # 1분마다 체크
        try:
            now = _time.time()
            data = load_gap_auto()
            changed = False

            for cid, cfg in data.items():
                if not cfg.get("enabled", False):
                    continue

                next_run = cfg.get("next_run", 0)
                if now < next_run:
                    continue  # 아직 시간 안 됨

                interval_sec = cfg.get("interval_min", 30) * 60
                threshold = cfg.get("threshold", 1.0)

                # 다음 실행 시간 업데이트
                cfg["next_run"] = now + interval_sec
                changed = True

                try:
                    await _send_gap_result(int(cid), threshold, reply_to=None)
                except Exception as e:
                    print(f"[gap 자동 알람 오류] chat_id={cid} → {e}")

            if changed:
                save_gap_auto(data)

        except Exception as e:
            print(f"[gap 자동 루프 오류] {e}")


#################################
# 전역 app 참조 (자동 알람 전송용)
#################################
_APP = None

#################################
# main
#################################

def main():
    global _APP

    app = (
        ApplicationBuilder()
        .token(TOKEN)
        .connect_timeout(30)
        .read_timeout(30)
        .write_timeout(30)
        .pool_timeout(30)
        .build()
    )

    _APP = app

    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("set", set_alarm))
    app.add_handler(CommandHandler("list", list_alarm))
    app.add_handler(CommandHandler("delete", delete_alarm))
    app.add_handler(CommandHandler("night", night_toggle))
    app.add_handler(CommandHandler("gap", gap_cmd))
    app.add_handler(CommandHandler("status", status_cmd))

    async def start(app):
        asyncio.create_task(alarm_loop(app))
        asyncio.create_task(gap_auto_loop())   # ✅ 자동 gap 루프 시작

    app.post_init = start
    app.run_polling()

if __name__ == "__main__":
    main()
