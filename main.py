import os
import json
import requests
import asyncio
import jwt
import uuid
import time as _time
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

ALARM_FILE = "/app/data/alarms.json"
NIGHT_FILE = "/app/data/night_mode.json"
GAP_AUTO_FILE = "/app/data/gap_auto.json"

CHECK_INTERVAL = 5
COOLDOWN_SEC = 300  # 5분 쿨다운

NIGHT_START = 23
NIGHT_END = 7

EXCHANGE_MAP = {
    "업비트": "upbit",
    "빗썸": "bithumb",
}

# 거래 수수료 (매매)
FEE_RATE = {
    "upbit": 0.0005,
    "bithumb": 0.0004
}

# 빗썸 출금 수수료
# None = 출금 수량의 1%
# 숫자 = 고정 수수료 (해당 코인 단위)
BITHUMB_WITHDRAW_FEE = {
    "BTC":   0.0002,
    "ETH":   0.005,
    "ETC":   0.005,
    "XRP":   0.4,
    "BCH":   0.0005,
    "QTUM":  0.009,
    "ADA":   0.45,
    "LINK":  0.03488447,
    "ENJ":   None,          # 1%
    "VET":   10,
    "THETA": None,          # 1%
    "ZRX":   None,          # 1%
    "SNT":   None,          # 1%
    "BAT":   None,          # 1%
    "WAVES": None,          # 1%
    "KNC":   None,          # 1%
    "GLM":   None,          # 1%
    "ZIL":   None,          # 1%
    "WAXP":  None,          # 1%
    "POWR":  None,          # 1%
    "STEEM": None,          # 1%
    "ICX":   None,          # 1% (출금 수량의 1%)
    "TRX":   0.9,
    "ELF":   None,          # 1%
    "MTL":   None,          # 1%
    "IOST":  None,          # 1%
    "ORBS":  36.60227272,
    "TFUEL": None,          # 1%
    "ANKR":  None,          # 1%
    "CRO":   None,          # 1%
    "CHR":   None,          # 1%
    "MBL":   None,          # 1%
    "WIN":   None,          # 무료 (Tron)
    "COS":   None,          # 1%
    "EL":    540,
    "HIVE":  None,          # 1%
    "BORA":  None,          # 1%
    "ARPA":  None,          # 1%
    "CTC":   1.98174733,
    "CKB":   None,          # 1%
    "AERGO": None,          # 1%
    "UNI":   0.09047752,
    "YFI":   None,          # 1%
    "UMA":   None,          # 1%
    "AAVE":  None,          # 1%
    "COMP":  None,          # 1%
    "RSR":   None,          # 1%
    "NMR":   None,          # 1%
    "RLC":   None,          # 1%
    "UOS":   None,          # 1%
    "SAND":  3.67,
    "BEL":   None,          # 1%
    "OBSR":  None,          # 1%
    "GRT":   None,          # 1%
    "BIOT":  None,          # 1%
    "SNX":   None,          # 1%
    "OXT":   None,          # 1%
    "AQT":   None,          # 1%
    "WIKEN": 80,
    "CTSI":  None,          # 1%
    "MANA":  None,          # 1%
    "LPT":   None,          # 1%
    "SRT":   0.5,
    "SUSHI": None,          # 1%
    "NSBT":  0.03,
    "PUNDIX":None,          # 1%
    "CELR":  None,          # 1%
    "ALICE": None,          # 1%
    "OGN":   None,          # 1%
    "COTI":  None,          # 1%
    "CAKE":  None,          # 1%
    "BNT":   None,          # 1%
    "XVS":   None,          # 1%
    "SWAP":  None,          # 1%
    "CHZ":   1,
    "AXS":   None,          # 1%
    "DAO":   None,          # 1%
    "SIX":   None,          # 1%
    "USDS":  1,
    "SHIB":  52516.3043,
    "POL":   0.009,
    "WOO":   None,          # 1%
    "ACH":   None,          # 1%
    "ANC":   5.4,
    "XLM":   0.005,
    "ONT":   None,          # 1%
    "META":  None,          # 1%
    "KAIA":  0.5,
    "ONG":   None,          # 1%
    "ALGO":  0.09,
    "JST":   None,          # 1%
    "XTZ":   None,          # 1%
    "MLK":   None,          # 1%
    "DOT":   0.075,
    "ATOM":  0.01,
    "DOGE":  8,
    "KSM":   None,          # 1%
    "CTK":   None,          # 1%
    "BNB":   0.001,
    "XEC":   500,
    "SOL":   0.009,
    "EGLD":  None,          # 1%
    "MASK":  None,          # 1%
    "C98":   None,          # 1%
    "MED":   None,          # 1%
    "SGB":   0.005,
    "1INCH": None,          # 1%
    "CRV":   None,          # 1%
    "BOBA":  None,          # 1%
    "RPG":   0.5,
    "DYDX":  None,          # 1%
    "MINA":  None,          # 1%
    "JOE":   None,          # 1%
    "GALA":  None,          # 1%
    "ENS":   0.05,
    "PURSE": 750,
    "BTT":   None,          # 무료 (Tron)
    "JASMY": None,          # 1%
    "REQ":   None,          # 1%
    "CSPR":  None,          # 1%
    "SOLO":  0.1,
    "AVAX":  0.01,
    "TDROP": None,          # 1%
    "HBAR":  0.01,
    "FANC":  None,          # 1%
    "MAY":   None,          # 1%
    "WITCH": 50,
    "REI":   None,          # 1%
    "T":     None,          # 1%
    "AQUA":  0.01,
    "MBX":   None,          # 1%
    "GMT":   None,          # 1%
    "TAVA":  None,          # 1%
    "D":     None,          # 1%
    "APE":   None,          # 1%
    "WNCG":  None,          # 1%
    "XCN":   None,          # 1%
    "LUNA2": 0.1,
    "TALK":  140,
    "AZIT":  None,          # 1%
    "ETHW":  0.01,
    "FLR":   None,          # 1%
    "SFP":   None,          # 1%
    "FITFI": 20,
    "STAT":  None,          # 1%
    "LM":    None,          # 1%
    "GRND":  None,          # 1%
    "APT":   None,          # 1%
    "BLUR":  None,          # 1%
    "HOOK":  None,          # 1%
    "OP":    None,          # 1%
    "ROA":   None,          # 1%
    "GMX":   None,          # 1%
    "STX":   2,
    "XPLA":  None,          # 1%
    "ARB":   0.2,
    "INJ":   None,          # 1%
    "HFT":   None,          # 1%
    "RPL":   None,          # 1%
    "IMX":   None,          # 1%
    "CFX":   None,          # 1%
    "ACS":   None,          # 1%
    "FRAX":  None,          # 1%
    "CELO":  None,          # 1%
    "LDO":   None,          # 1%
    "S":     None,          # 1%
    "FET":   1,
    "SUI":   0.009,
    "NCT":   None,          # 1%
    "FLOKI": None,          # 1%
    "ID":    None,          # 1%
    "RENDER":None,          # 1%
    "OSMO":  None,          # 1%
    "FIL":   None,          # 1%
    "ILV":   None,          # 1%
    "MAV":   None,          # 1%
    "HVH":   100,
    "RSS3":  None,          # 1%
    "AUDIO": None,          # 1%
    "AGI":   60,
    "ASTR":  None,          # 1%
    "WLD":   0.05,          # Optimism 기준
    "FLUX":  None,          # 1%
    "AGLD":  None,          # 1%
    "AR":    None,          # 1%
    "RVN":   None,          # 1%
    "EDU":   None,          # 1%
    "SEI":   0.04,
    "WAXL":  None,          # 1%
    "MOC":   None,          # 1%
    "PEPE":  92913.4615,
    "CYBER": None,          # 1%
    "ARKM":  None,          # 1%
    "PYR":   None,          # 1%
    "IOTX":  None,          # 1%
    "HIGH":  None,          # 1%
    "PENDLE":None,          # 1%
    "BICO":  None,          # 1%
    "STORJ": None,          # 1%
    "API3":  None,          # 1%
    "ZTX":   10,
    "MNT":   None,          # 1%
    "GTC":   None,          # 1%
    "METIS": None,          # 1%
    "TIA":   None,          # 1%
    "ICP":   None,          # 1%
    "SPURS": 0.1,
    "NEO":   None,          # 1%
    "GAS":   None,          # 1%
    "BIGTIME":None,         # 1%
    "ZETA":  None,          # 1%
    "ARK":   None,          # 1%
    "YGG":   None,          # 1%
    "HUNT":  None,          # 1%
    "KAVA":  None,          # 1%
    "MAGIC": None,          # 1%
    "AUCTION":None,         # 1%
    "USDT":  None,          # Tron: 무료, ETH: 4
    "USDC":  1,
    "RAD":   None,          # 1%
    "LSK":   None,          # 1%
    "TT":    None,          # 1%
    "ACE":   None,          # 1%
    "SKL":   None,          # 1%
    "IQ":    None,          # 1%
    "PYTH":  None,          # 1%
    "MANTA": None,          # 1%
    "AKT":   None,          # 1%
    "BEAM":  None,          # 1%
    "PHA":   None,          # 1%
    "JTO":   None,          # 1%
    "JUP":   None,          # 1%
    "STRK":  0.01,          # Starknet 기준
    "SC":    None,          # 1%
    "TRAC":  None,          # 1%
    "BONK":  15000,
    "TOKAMAK":None,         # 1%
    "AIOZ":  None,          # 1%
    "ZK":    None,          # 1%
    "ONDO":  1.26247713,
    "ALT":   None,          # 1%
    "TAO":   0.01,
    "NEAR":  0.02,
    "RON":   None,          # 1%
    "STRAX": None,          # 1%
    "XAI":   None,          # 1%
    "W":     None,          # 1%
    "POLYX": None,          # 1%
    "CORE":  None,          # 1%
    "BB":    None,          # 1%
    "POKT":  None,          # 1%
    "REZ":   None,          # 1%
    "ENA":   2,
    "MOCA":  None,          # 1%
    "ETHFI": None,          # 1%
    "MEW":   None,          # 1%
    "ZRO":   None,          # 1%
    "IO":    None,          # 1%
    "KLY":   0.01,
    "BLAST": None,          # 1%
    "TAIKO": None,          # 1%
    "BRETT": 1,
    "ATH":   None,          # 1%
    "PCI":   12.5,
    "AVAIL": None,          # 1%
    "TON":   None,          # 1%
    "G":     None,          # 1%
    "LISTA": None,          # 1%
    "PEAQ":  None,          # 1%
    "EIGEN": None,          # 1%
    "CFG":   None,          # 1%
    "XION":  None,          # 1%
    "ORDER": None,          # 1%
    "MERL":  None,          # 1%
    "SCR":   None,          # 1%
    "SWELL": None,          # 1%
    "PEPPER":100000,
    "SKY":   None,          # 1%
    "PONKE": None,          # 1%
    "MVL":   None,          # 1%
    "CARV":  None,          # 1%
    "PUFFER":None,          # 1%
    "SUNDOG":None,          # 1%
    "TURBO": None,          # 1%
    "RAY":   None,          # 1%
    "SAFE":  None,          # 1%
    "VIRTUAL":0.1,
    "DRIFT": 1,
    "MOVE":  None,          # 1%
    "F":     None,          # 1%
    "DEEP":  None,          # 1%
    "MORPHO":None,          # 1%
    "MOODENG":None,         # 1%
    "DBR":   None,          # 1%
    "GOAT":  1.6,
    "NIL":   None,          # 1%
    "ME":    None,          # 1%
    "INIT":  None,          # 1%
    "ZRC":   None,          # 1%
    "IOTA":  None,          # 1%
    "MONKY": 26800,
    "PENGU": 5,
    "ACX":   None,          # 1%
    "AERO":  None,          # 1%
    "THE":   None,          # 1%
    "AMP":   None,          # 1%
    "VANA":  None,          # 1%
    "XYO":   None,          # 1%
    "A8":    None,          # 1%
    "SONIC": None,          # 1%
    "WIF":   None,          # 1%
    "CPOOL": None,          # 1%
    "IP":    0.0005,
    "DKA":   None,          # 1%
    "SOLV":  9,
    "BLUE":  None,          # 1%
    "QKC":   None,          # 1%
    "HP":    None,          # 1%
    "GAME2": None,          # 1%
    "ERA":   None,          # 1%
    "ARDR":  None,          # 1%
    "BOUNTY":None,          # 1%
    "SHELL": None,          # 1%
    "BERA":  None,          # 1%
    "BIO":   None,          # 1%
    "PLUME": None,          # 1%
    "OBT":   None,          # 1%
    "TRUMP": 0.04,
    "KERNEL":3.43390191,
    "COOKIE":None,          # 1%
    "GNO":   None,          # 1%
    "VTHO":  None,          # 1%
    "ANIME": None,          # 1%
    "RED":   None,          # 1%
    "LAYER": None,          # 1%
    "GPS":   None,          # 1%
    "WCT":   None,          # 1%
    "FLOCK": None,          # 1%
    "KAITO": None,          # 1%
    "BMT":   None,          # 1%
    "C":     None,          # 1%
    "SOON":  1.5,
    "PAXG":  None,          # 1%
    "XAUT":  None,          # 1%
    "AVL":   None,          # 1%
    "B3":    None,          # 1%
    "COW":   None,          # 1%
    "WAL":   None,          # 1%
    "BABY":  None,          # 1%
    "ES":    None,          # 1%
    "XTER":  None,          # 1%
    "NXPC":  None,          # 1%
    "0G":    None,          # 1%
    "GRASS": None,          # 1%
    "ORCA":  None,          # 1%
    "KMNO":  None,          # 1%
    "PUMPBTC":None,         # 1%
    "EPT":   None,          # 1%
    "HAEDAL":None,          # 1%
    "PARTI": None,          # 1%
    "SXT":   None,          # 1%
    "PROMPT":None,          # 1%
    "SIGN":  None,          # 1%
    "BTR":   None,          # 1%
    "SAHARA":None,          # 1%
    "SNS":   487,
    "HEMI":  None,          # 1%
    "H":     3.44860813,
    "HOME":  None,          # 1%
    "LA":    None,          # 1%
    "SOPH":  None,          # 1%
    "HYPER": None,          # 1%
    "PROVE": None,          # 1%
    "CUDIS": None,          # 1%
    "FORT":  None,          # 1%
    "TOSHI": None,          # 1%
    "HUMA":  None,          # 1%
    "SPK":   None,          # 1%
    "USD1":  0.35,          # BNB Chain 기준
    "BOB":   None,          # 1%
    "SYRUP": None,          # 1%
    "NEWT":  None,          # 1%
    "RESOLV":8,
    "ALLO":  None,          # 1%
    "DOOD":  None,          # 1%
    "TREE":  None,          # 1%
    "EUL":   None,          # 1%
    "AVNT":  None,          # 1%
    "OPEN":  None,          # 1%
    "PUMP":  None,          # 1%
    "IRYS":  None,          # 1%
    "DEXE":  None,          # 1%
    "SD":    None,          # 1%
    "BARD":  None,          # 1%
    "TOWNS": None,          # 1%
    "MIRA":  None,          # 1%
    "CAMP":  None,          # 1%
    "XAN":   None,          # 1%
    "THQ":   None,          # 1%
    "POPCAT":None,          # 1%
    "WLFI":  3.09910198,
    "2Z":    None,          # 1%
    "LINEA": None,          # 1%
    "SAPIEN":None,          # 1%
    "HOLO":  None,          # 1%
    "ZKC":   None,          # 1%
    "ASTER": None,          # 1%
    "XPL":   None,          # 1%
    "FF":    None,          # 1%
    "SOMI":  None,          # 1%
    "MON":   None,          # 1%
    "FLUID": None,          # 1%
    "SUPER": None,          # 1%
    "IN":    None,          # 1%
    "EDEN":  None,          # 1%
    "RECALL":None,          # 1%
    "USDE":  0.32535353,
    "ENSO":  None,          # 1%
    "YB":    None,          # 1%
    "STABLE":None,          # 1%
    "ZBT":   None,          # 1%
    "NOM":   70,
    "ZORA":  None,          # 1%
    "SENT":  None,          # 1%
    "MMT":   None,          # 1%
    "MET":   None,          # 1%
    "KITE":  None,          # 1%
    "TRUST": None,          # 1%
    "ARIAIP":0.05,
    "ESP":   None,          # 1%
    "PIEVERSE":None,        # 1%
    "CYS":   None,          # 1%
    "EDGE":  None,          # 1%
    "SPACE": 7.2,
    "WET":   None,          # 1%
    "BREV":  None,          # 1%
    "KAT":   None,          # 1%
    "ZKP":   None,          # 1%
    "ZAMA":  None,          # 1%
    "GWEI":  None,          # 1%
    "SKR":   None,          # 1%
    "LIT":   None,          # 1%
    "ELSA":  None,          # 1%
    "BIRB":  None,          # 1%
    "AZTEC": None,          # 1%
    "ROBO":  None,          # 1%
    "BLEND": None,          # 1%
    "MANTRA":0.05,
    "MEGA":  0.1,
    "VVV":   None,          # 1%
    "BASED": None,          # 1%
    "CHIP":  None,          # 1%
    "EDGEX": 0.5,
    "PRL":   None,          # 1%
    "PROS":  0.1,
}

# 업비트 출금 수수료 (주요 코인만, 나머지는 None으로 처리)
# 업비트는 공식 수수료 페이지 기준 (코인별 고정)
UPBIT_WITHDRAW_FEE = {
    "BTC":   0.0005,
    "ETH":   0.01,
    "XRP":   1.0,
    "ADA":   1.0,
    "SOL":   0.01,
    "DOGE":  10.0,
    "DOT":   0.1,
    "AVAX":  0.01,
    "LINK":  0.3,
    "ATOM":  0.01,
    "UNI":   0.3,
    "SAND":  10.0,
    "MANA":  20.0,
    "XLM":   0.01,
    "ALGO":  0.01,
    "BCH":   0.001,
    "ETC":   0.01,
    "SHIB":  100000,
    "MATIC": 1.0,
    "POL":   1.0,
    "TRX":   10.0,
    "BNB":   0.001,
    "SUI":   0.01,
    "SEI":   0.1,
    "NEAR":  0.1,
    "ARB":   1.0,
    "OP":    1.0,
    "PEPE":  200000,
    "BONK":  50000,
    "WIF":   1.0,
}

ALERT_STATE = {}

#################################
# 출금 수수료 계산 함수
#################################

def get_withdraw_fee(exchange, coin, price):
    """
    출금 수수료를 원화로 반환
    exchange: 'upbit' or 'bithumb' (송금하는 쪽, 즉 출금하는 거래소)
    coin: 코인 심볼
    price: 해당 거래소 현재가 (원화)
    """
    if exchange == "bithumb":
        fee = BITHUMB_WITHDRAW_FEE.get(coin)
        if fee is None:
            # 출금 수량의 1% → 코인 1개 기준 0.01개 수수료 → 원화로 price * 0.01
            return price * 0.01
        else:
            return fee * price  # 고정 수수료 (코인 단위) → 원화

    elif exchange == "upbit":
        fee = UPBIT_WITHDRAW_FEE.get(coin)
        if fee is None:
            return 0  # 업비트는 대부분 코인별 고정, 없으면 0으로 처리
        return fee * price

    return 0

#################################
# 가격 포맷 함수 (소수점 자동 조정)
#################################

def fmt(n):
    if n >= 100:
        return f"{n:,.0f}"
    elif n >= 1:
        return f"{n:,.2f}"
    else:
        return f"{n:,.4f}"

#################################
# 저장
#################################

def ensure_data_dir():
    os.makedirs("/app/data", exist_ok=True)

def load_alarms():
    try:
        with open(ALARM_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def save_alarms(data):
    ensure_data_dir()
    with open(ALARM_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_night():
    try:
        with open(NIGHT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_night(data):
    ensure_data_dir()
    with open(NIGHT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_gap_auto():
    try:
        with open(GAP_AUTO_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_gap_auto(data):
    ensure_data_dir()
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
        "/gap off      ← 자동 알람 중단\n"
        "/status ETH   ← 현재가 및 괴리율 조회"
    )

async def set_alarm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 4:
        await update.message.reply_text("❌ /set 업비트 빗썸 ETH 1000\n코인 심볼은 반드시 영문으로 입력해주세요\n예) ETH, BTC, XRP")
        return

    ex_high_kr, ex_low_kr, coin, diff = context.args
    coin = coin.upper()

    # 한글 포함 여부 체크
    if any('\uac00' <= c <= '\ud7a3' for c in coin):
        await update.message.reply_text(
            f"❌ 코인 심볼은 영문으로 입력해주세요\n"
            f"예) 이더리움 → ETH, 비트코인 → BTC, 리플 → XRP\n"
            f"/status ETH 처럼 먼저 조회해보세요"
        )
        return

    if ex_high_kr not in EXCHANGE_MAP or ex_low_kr not in EXCHANGE_MAP:
        await update.message.reply_text("거래소 이름 오류\n예) 업비트, 빗썸")
        return

    try:
        diff = float(diff)
    except:
        await update.message.reply_text("차익은 숫자로 입력")
        return

    # 저장 전 가격 조회 검증
    await update.message.reply_text(f"🔍 {coin} 조회 확인중...")

    high = get_price(EXCHANGE_MAP[ex_high_kr], coin)
    low = get_price(EXCHANGE_MAP[ex_low_kr], coin)

    if high is None:
        await update.message.reply_text(
            f"❌ {ex_high_kr}에서 {coin} 조회 실패\n"
            f"심볼을 영문으로 다시 확인해주세요\n"
            f"예) ETH, BTC, XRP"
        )
        return

    if low is None:
        await update.message.reply_text(
            f"❌ {ex_low_kr}에서 {coin} 조회 실패\n"
            f"해당 거래소에 상장되지 않은 코인일 수 있어요"
        )
        return

    # 유저 정보 수집
    user = update.effective_user
    username = f"@{user.username}" if user.username else user.full_name

    alarms = load_alarms()
    cid = update.effective_chat.id

    alarms.append({
        "chat_id": cid,
        "username": username,
        "ex_high": EXCHANGE_MAP[ex_high_kr],
        "ex_low": EXCHANGE_MAP[ex_low_kr],
        "kr_high": ex_high_kr,
        "kr_low": ex_low_kr,
        "coin": coin,
        "diff": diff
    })

    save_alarms(alarms)
    await update.message.reply_text(
        f"✅ 알람 저장 완료\n"
        f"{ex_high_kr} : {fmt(high)}원\n"
        f"{ex_low_kr} : {fmt(low)}원"
    )

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

        # 빗썸→업비트 방향 기준 수수료 계산 (출금은 빗썸에서)
        trade_fee = bithumb_price * FEE_RATE["bithumb"] + upbit_price * FEE_RATE["upbit"]
        wd_fee_krw = get_withdraw_fee("bithumb", coin, bithumb_price)
        net = upbit_price - bithumb_price - trade_fee - wd_fee_krw

        # 빗썸 출금 수수료 타입 표시
        bithumb_fee_raw = BITHUMB_WITHDRAW_FEE.get(coin)
        fee_type = "1%" if bithumb_fee_raw is None else f"고정 {bithumb_fee_raw}"

        gap_line = (
            f"📊 괴리율 : {gap_pct:+.3f}%\n"
            f"💸 순이익(빗→업) : {fmt(net)}원\n"
            f"🏦 빗썸 출금수수료 : {fee_type} ({fmt(wd_fee_krw)}원)"
        )
    else:
        gap_line = "📊 괴리율 : 조회 실패"

    msg = (
        f"📊 {coin} 현황\n"
        f"업비트 : {fmt(upbit_price) if upbit_price else '조회 실패'}원\n"
        f"빗썸 : {fmt(bithumb_price) if bithumb_price else '조회 실패'}원\n"
        f"{gap_line}\n"
        f"빗썸 입출금 : {bithumb_wallet}"
    )

    await update.message.reply_text(msg)


async def gap_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args and context.args[0].lower() == "on":
        if len(context.args) < 2:
            await update.message.reply_text("사용법: /gap on [퍼센트] [분]\n예) /gap on 1 10  (1% 이상, 10분마다)")
            return
        try:
            threshold = float(context.args[1])
        except:
            await update.message.reply_text("퍼센트는 숫자로 입력해줘.\n예) /gap on 1 10")
            return

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
            "next_run": 0
        }
        save_gap_auto(data)

        await update.message.reply_text(
            f"✅ 자동 gap 알람 ON\n"
            f"조건 : {threshold}% 이상 & 빗썸 입출금 정상\n"
            f"주기 : {interval_min}분마다"
        )
        return

    if context.args and context.args[0].lower() == "off":
        data = load_gap_auto()
        cid = str(update.effective_chat.id)
        if cid in data:
            data[cid]["enabled"] = False
            save_gap_auto(data)
        await update.message.reply_text("🔕 자동 gap 알람 OFF")
        return

    if not context.args:
        await update.message.reply_text("사용법: /gap 0.5")
        return

    try:
        threshold = float(context.args[0])
    except:
        await update.message.reply_text("숫자만 입력해줘.")
        return

    await _send_gap_result(update.effective_chat.id, threshold, update.message)


async def _send_gap_result(chat_id, threshold, reply_to=None):
    async def send(text):
        if reply_to:
            await reply_to.reply_text(text)
        else:
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
            gap_pct = (upbit[coin] - bithumb[coin]) / bithumb[coin] * 100
            if abs(gap_pct) >= threshold:
                results.append((coin, round(gap_pct, 3)))

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

        if reply_to is None and not is_open:
            continue

        # 빗썸→업비트 순이익 계산
        b_price = bithumb.get(coin, 0)
        u_price = upbit.get(coin, 0)

        if b_price > 0 and u_price > 0 and g > 0:
            trade_fee = b_price * FEE_RATE["bithumb"] + u_price * FEE_RATE["upbit"]
            wd_fee_krw = get_withdraw_fee("bithumb", coin, b_price)
            net = u_price - b_price - trade_fee - wd_fee_krw
            net_str = f" | 순익 {fmt(net)}원"
        else:
            net_str = ""

        lines.append(f"{coin} : {g:+.3f}% | 빗{b_icon}{net_str}")

    if not lines:
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
# 👥 사용자 목록 조회 (관리자용)
#################################

async def users_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    alarms = load_alarms()
    if not alarms:
        await update.message.reply_text("등록된 알람 없음")
        return

    from collections import defaultdict
    user_map = defaultdict(list)
    for a in alarms:
        name = a.get("username", f"ID:{a['chat_id']}")
        label = f"{a['kr_high']}→{a['kr_low']} {a['coin']} {a['diff']}원"
        user_map[name].append(label)

    msg = "👥 알람 사용자 목록\n\n"
    for name, items in user_map.items():
        msg += f"👤 {name}\n"
        for item in items:
            msg += f"  • {item}\n"
        msg += "\n"

    await update.message.reply_text(msg)


#################################
# 🔔 알람 체크 루프 (2번 울리고 쿨다운)
#################################

async def check_alarms(app):
    alarms = load_alarms()
    night_data = load_night()
    now_night = is_night_time()
    now = _time.time()

    for a in alarms:
        key = f"{a['chat_id']}_{a['coin']}_{a['ex_high']}_{a['ex_low']}"
        state = ALERT_STATE.get(key, {"last_sent": 0, "active": False, "count": 0})

        high = get_price(a["ex_high"], a["coin"])
        low = get_price(a["ex_low"], a["coin"])

        if high is None or low is None:
            print(f"[가격 조회 실패] {a['coin']} high={high} low={low}")
            continue

        gap = round(high - low, 8)
        threshold = a["diff"]

        if night_data.get(str(a["chat_id"]), False) and now_night:
            threshold *= 2

        # 차익 사라지면 완전 리셋
        if gap < threshold:
            ALERT_STATE[key] = {"last_sent": 0, "active": False, "count": 0}
            continue

        count = state.get("count", 0)
        last_sent = state.get("last_sent", 0)

        # 2번 미만이면 바로 전송
        if count < 2:
            pass
        else:
            # 2번 울린 이후엔 쿨다운 체크
            if now - last_sent < COOLDOWN_SEC:
                continue
            # 쿨다운 끝나면 count 리셋 → 다시 2번 울림
            count = 0

        ALERT_STATE[key] = {"last_sent": now, "active": True, "count": count + 1}

        # 수수료 계산: 출금하는 쪽(ex_high)의 출금 수수료 적용
        trade_fee = low * FEE_RATE.get(a["ex_low"], 0) + high * FEE_RATE.get(a["ex_high"], 0)
        wd_fee_krw = get_withdraw_fee(a["ex_high"], a["coin"], high)
        net_profit = round(gap - trade_fee - wd_fee_krw, 2)

        # 빗썸 출금 수수료 타입 표시
        bithumb_fee_raw = BITHUMB_WITHDRAW_FEE.get(a["coin"])
        if a["ex_high"] == "bithumb":
            fee_info = f"출금수수료(빗) : {'1%' if bithumb_fee_raw is None else f'{bithumb_fee_raw} {a[\"coin\"]}'} ({fmt(wd_fee_krw)}원)"
        else:
            fee_info = f"출금수수료(업) : {fmt(wd_fee_krw)}원"

        try:
            await app.bot.send_message(
                chat_id=a["chat_id"],
                text=(
                    f"🚨 차익 발생 [{a['coin']}]\n"
                    f"{a['kr_high']} : {fmt(high)}원\n"
                    f"{a['kr_low']} : {fmt(low)}원\n"
                    f"📈 가격차 : {fmt(gap)}원\n"
                    f"💸 순이익 : {fmt(net_profit)}원\n"
                    f"📋 {fee_info}"
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


async def gap_auto_loop():
    while True:
        await asyncio.sleep(60)
        try:
            now = _time.time()
            data = load_gap_auto()
            changed = False

            for cid, cfg in data.items():
                if not cfg.get("enabled", False):
                    continue

                next_run = cfg.get("next_run", 0)
                if now < next_run:
                    continue

                interval_sec = cfg.get("interval_min", 30) * 60
                threshold = cfg.get("threshold", 1.0)

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

    ensure_data_dir()

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
    app.add_handler(CommandHandler("users", users_cmd))

    async def start(app):
        asyncio.create_task(alarm_loop(app))
        asyncio.create_task(gap_auto_loop())

    app.post_init = start
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
