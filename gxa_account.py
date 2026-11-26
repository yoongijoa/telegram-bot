"""Personal GXA reader. Run this module interactively in the Railway service console to pair."""
import asyncio
import getpass
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from telethon import TelegramClient, errors, events, types

GROUP = "GXACommunity"
DIRECTORY = Path("/app/data/gxa-account")
CONFIG = DIRECTORY / "account.json"
SESSION = DIRECTORY / "reader.session"
ACTIVATED = DIRECTORY / "activated"


@dataclass
class Pin:
    message_id: int
    text: str
    caption: str = ""


class PersonalAccount:
    def __init__(self, config):
        self.owner_id = config["owner_id"]
        self.baseline = config["baseline"]
        self.peer = types.InputPeerChannel(config["group_id"], config["group_hash"])
        self.client = make_client(config["api_id"], config["api_hash"], monitor=True)
        self.lock = asyncio.Lock()

    async def connect(self):
        async with self.lock:
            if not self.client.is_connected():
                await self.client.connect()
                owner = await self.client.get_me()
                if not owner or owner.id != self.owner_id:
                    await self.client.disconnect()
                    raise RuntimeError("GXA 계정 재연결이 필요합니다.")
    async def pinned_posts(self):
        await self.connect()
        return [Pin(post.id, post.raw_text or "") async for post in self.client.iter_messages(
            self.peer, filter=types.InputMessagesFilterPinned())]

    async def listen(self, subscribed, snapshot, update):
        queue = asyncio.Queue()

        async def receive(event):
            if event.channel_id == self.peer.channel_id and subscribed():
                queue.put_nowait(event)

        async def consume():
            if subscribed():
                snapshot(await self.pinned_posts())
            print("[GXA 공지] 고정 이벤트 수신 대기", flush=True)
            while True:
                event = await queue.get()
                if not subscribed():
                    continue
                if not event.pinned:
                    await update([], event.messages)
                    continue
                posts = await self.client.get_messages(self.peer, ids=event.messages)
                by_id = {p.id: p.raw_text or "" for p in posts if p}
                await update([Pin(n, by_id.get(n, "")) for n in event.messages], [])

        self.client.add_event_handler(receive, events.Raw(types.UpdatePinnedChannelMessages))
        tasks = []
        try:
            await self.connect()
            tasks = [asyncio.create_task(consume()), asyncio.ensure_future(self.client.run_until_disconnected())]
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        finally:
            self.client.remove_event_handler(receive)
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await self.client.disconnect()


def make_client(api_id, api_hash, *, monitor=False):
    client = TelegramClient(str(SESSION), api_id, api_hash, receive_updates=True,
                            auto_reconnect=not monitor, sequential_updates=monitor,
                            device_model="GXA Notice Monitor (Railway)", request_retries=2,
                            connection_retries=2)
    client.session.save_entities = False
    return client


async def pair():
    import qrcode

    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise SystemExit("Railway 서비스의 대화형 Console에서만 실행해 주세요.")
    if CONFIG.exists():
        raise SystemExit("이미 연결 설정이 있습니다. 봇에서 /gxa status 로 확인해 주세요.")

    os.umask(0o077)
    DIRECTORY.mkdir(mode=0o700, parents=True, exist_ok=True)
    api_id = int(input("Telegram App api_id: ").strip())
    api_hash = getpass.getpass("Telegram App api_hash (입력은 표시되지 않습니다): ").strip()
    if len(api_hash) != 32 or any(ch not in "0123456789abcdefABCDEF" for ch in api_hash):
        raise SystemExit("api_hash 형식을 확인한 뒤 다시 실행해 주세요.")
    client = make_client(api_id, api_hash)
    try:
        await client.connect()
        while not await client.is_user_authorized():
            login = await client.qr_login()
            qr = qrcode.QRCode(border=3)
            qr.add_data(login.url)
            qr.make(fit=True)
            print("휴대폰 텔레그램 → 설정 → 기기 → 데스크톱 기기 연결에서 QR을 스캔하세요.")
            qr.print_ascii(invert=True)
            try:
                await login.wait()
            except asyncio.TimeoutError:
                print("QR이 만료되어 새 코드를 표시합니다.")
            except errors.SessionPasswordNeededError:
                await client.sign_in(password=getpass.getpass("텔레그램 2단계 인증 비밀번호: "))
        owner = await client.get_me()
        group = await client.get_entity("@" + GROUP)
        pins = await client.get_messages(group, filter=types.InputMessagesFilterPinned(), limit=1)
        if not pins:
            raise SystemExit("이 계정에서 GXA 고정 공지를 확인하지 못했습니다.")
        config = dict(owner_id=owner.id, api_id=api_id, api_hash=api_hash, baseline=pins[0].id,
                      group_id=group.id, group_hash=group.access_hash)
    finally:
        await client.disconnect()

    temporary = CONFIG.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(config, stream)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, CONFIG)
    print("GXA 고정 공지를 확인했습니다. 가격 봇이 이 계정의 개인 대화로 연결 알림을 보냅니다.")


if __name__ == "__main__":
    asyncio.run(pair())
