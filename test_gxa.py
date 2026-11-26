import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from telegram.error import NetworkError
import main


class GxaAlerts(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        for setting in (patch.object(main, "GXA_FILE", str(Path(directory.name) / "gxa.json")),
                        patch.object(main, "ensure_data_dir")):
            setting.start()
            self.addCleanup(setting.stop)
        self.bot = SimpleNamespace(get_chat=AsyncMock(), send_message=AsyncMock())
        self.update = SimpleNamespace(effective_chat=SimpleNamespace(id=17, type="private"),
                                      message=SimpleNamespace(reply_text=AsyncMock()))
        self.app = SimpleNamespace(bot=self.bot)

    def pin(self, number):
        self.bot.get_chat.return_value = SimpleNamespace(
            pinned_message=SimpleNamespace(message_id=number, text=None, caption="공지 사진")
        )

    async def command(self, arg):
        await main.gxa_cmd(self.update, SimpleNamespace(bot=self.bot, args=[arg]))

    async def bot_event(self):
        message = SimpleNamespace(chat=SimpleNamespace(username="GXACommunity"),
                                  pinned_message=self.bot.get_chat.return_value.pinned_message)
        await main.public_gxa_event(SimpleNamespace(effective_message=message), self.app)
        await main.flush_gxa(self.app)

    async def test_subscribe_new_pin_once_then_turn_off(self):
        self.pin(100)
        await self.command("on")
        await self.bot_event()
        self.bot.send_message.assert_not_awaited()
        self.pin(101)
        await self.bot_event()
        await self.bot_event()
        self.pin(100)
        await self.bot_event()
        self.bot.send_message.assert_awaited_once()
        sent = self.bot.send_message.await_args.kwargs
        self.assertEqual(sent["chat_id"], 17)
        self.assertIn("공지 사진", sent["text"])
        self.assertIn("https://t.me/GXACommunity/101", sent["text"])
        await self.command("off")
        self.pin(103)
        await self.bot_event()
        self.bot.send_message.assert_awaited_once()

    async def test_failed_delivery_retried_before_next_pin(self):
        self.pin(100)
        await self.command("on")
        self.pin(101)
        self.bot.send_message.side_effect = [NetworkError("offline"), None, None]
        await self.bot_event()
        self.pin(102)
        await self.bot_event()
        calls = self.bot.send_message.await_args_list
        self.assertEqual([c.kwargs["text"].split("/")[-1] for c in calls], ["101", "101", "102"])

    async def test_group_chat_cannot_subscribe(self):
        self.update.effective_chat.type = "supergroup"
        await self.command("on")
        self.bot.get_chat.assert_not_awaited()
        await self.bot_event()
        self.bot.send_message.assert_not_awaited()

    async def test_no_visible_pin_does_not_claim_subscription(self):
        self.bot.get_chat.return_value = SimpleNamespace(pinned_message=None)
        await self.command("on")
        self.assertIn("고정 공지를 읽지 못", self.update.message.reply_text.await_args.args[0])
        self.assertEqual(main._load_json(main.GXA_FILE, {}), {})

    async def test_personal_pin_goes_only_to_connected_owner(self):
        reader = SimpleNamespace(owner_id=17)
        async def listen(subscribed, snapshot, update):
            self.assertTrue(subscribed())
            snapshot([main.gxa_account.Pin(41, "")])
            await update([main.gxa_account.Pin(42, "새 공지")], [])
            raise asyncio.CancelledError()
        reader.listen = listen
        main._save_json(main.GXA_FILE, {"17": {"latest": 41, "pending": []},
                                        "18": {"latest": 41, "pending": []}})
        self.pin(41)
        with patch.object(main, "personal_account", return_value=reader), patch.object(main, "activate_personal_account"):
            with self.assertRaises(asyncio.CancelledError):
                await main.gxa_loop(self.app)
        await main.flush_gxa(self.app)
        self.bot.get_chat.assert_not_awaited()
        self.bot.send_message.assert_awaited_once()
        self.assertEqual(self.bot.send_message.await_args.kwargs["chat_id"], 17)

    async def test_pair_activates_own_chat_once_and_preserves_off(self):
        reader = SimpleNamespace(owner_id=17, baseline=42)
        marker = Path(main.GXA_FILE).with_name("activated")
        with patch.object(main.gxa_account, "ACTIVATED", marker):
            main.activate_personal_account(reader)
            subscriptions = main._load_json(main.GXA_FILE, {})
            self.assertEqual(set(subscriptions), {"17"})
            self.assertEqual(subscriptions["17"]["latest"], 42)
            self.assertIn("GXACommunity/42", subscriptions["17"]["pending"][0])
            await self.command("off")
            main.activate_personal_account(reader)
            self.assertEqual(main._load_json(main.GXA_FILE, {}), {})

    def test_events_deduplicate_and_allow_old_posts_to_be_pinned_again(self):
        main._save_json(main.GXA_FILE, {"17": {"latest": 100, "pending": []}})
        def pin(number):
            return main.gxa_account.Pin(number, "공지")
        main.record_gxa_pins({"17"}, [pin(90), pin(100)], snapshot=True)
        main.record_gxa_pins({"17"}, [pin(80), pin(101)])
        main.record_gxa_pins({"17"}, [pin(80)])
        main.record_gxa_pins({"17"}, [], removed=[80])
        main.record_gxa_pins({"17"}, [pin(80)])
        main.record_gxa_pins({"17"}, [pin(80), pin(90), pin(100), pin(101), pin(102)], snapshot=True)
        state = main._load_json(main.GXA_FILE, {})["17"]
        self.assertEqual([m.split("/")[-1] for m in state["pending"]], ["80", "101", "80", "102"])

    def test_live_pin_before_initial_snapshot_does_not_replay_historical_pins(self):
        pin = main.gxa_account.Pin
        main._save_json(main.GXA_FILE, {"17": {"latest": 100, "pending": []}})
        main.record_gxa_pins({"17"}, [pin(105, "")])
        main.record_gxa_pins({"17"}, [pin(40, ""), pin(100, ""), pin(103, ""), pin(105, "")], snapshot=True)
        saved = main._load_json(main.GXA_FILE, {})["17"]
        self.assertEqual([m.split("/")[-1] for m in saved["pending"]], ["105", "103"])
        self.assertEqual(saved["pin_ids"], [40, 100, 103, 105])

    async def test_listener_handles_target_pin_and_service_messages(self):
        from telethon import types
        reader = object.__new__(main.gxa_account.PersonalAccount)
        reader.peer = types.InputPeerChannel(700, 42)
        reader.connect = AsyncMock()
        reader.pinned_posts = AsyncMock(return_value=[])
        reader.pin_marker = AsyncMock(return_value=(10, 0, None))
        connected = asyncio.Event()
        delivered = asyncio.Event()
        disconnected = asyncio.Event()
        reader.client = Mock(get_messages=AsyncMock(return_value=[SimpleNamespace(id=7, raw_text="공지")]),
                             disconnect=AsyncMock(), run_until_disconnected=disconnected.wait)
        async def update(pins, removed):
            if pins:
                self.assertEqual(pins[0].message_id, 7)
                delivered.set()
        listener = asyncio.create_task(reader.listen(lambda: True, lambda _: connected.set(), update))
        try:
            await asyncio.wait_for(connected.wait(), 2)
            receive, event_filter = reader.client.add_event_handler.call_args.args
            self.assertIn(types.UpdatePinnedChannelMessages, event_filter.types)
            self.assertIn(types.UpdateNewChannelMessage, event_filter.types)
            await receive(types.UpdatePinnedChannelMessages(555, [99], 1, 1, pinned=True))
            await receive(types.UpdatePinnedChannelMessages(700, [99], 2, 1, pinned=False))
            await asyncio.sleep(0)
            reader.client.get_messages.assert_not_awaited()
            await receive(types.UpdatePinnedChannelMessages(700, [7], 3, 1, pinned=True))
            await asyncio.wait_for(delivered.wait(), 2)
            reader.client.get_messages.assert_awaited_once_with(reader.peer, ids=[7])
            def service(channel):
                msg = types.MessageService(id=99, peer_id=types.PeerChannel(channel),
                                           action=types.MessageActionPinMessage(),
                                           reply_to=types.MessageReplyHeader(reply_to_msg_id=7))
                return types.UpdateNewChannelMessage(msg, pts=4, pts_count=1)
            delivered.clear()
            await receive(service(555))
            await receive(service(700))
            await asyncio.wait_for(delivered.wait(), 2)
            self.assertEqual(reader.client.get_messages.await_count, 2)
            reader.pinned_posts.assert_awaited_once()
        finally:
            disconnected.set()
            await asyncio.wait_for(listener, 2)

    async def test_missed_push_recovers_old_pin_without_restart_or_duplicate(self):
        from telethon import types
        reader = object.__new__(main.gxa_account.PersonalAccount)
        reader.peer = types.InputPeerChannel(700, 42)
        reader.connect = AsyncMock()
        disconnected = asyncio.Event()
        recovered = asyncio.Event()
        reader.client = Mock(disconnect=AsyncMock(), run_until_disconnected=disconnected.wait)
        from itertools import chain, repeat
        reader.pin_marker = AsyncMock(side_effect=chain([OSError(), (10, 2, 100), (10, 2, 100)],
                                                        repeat((12, 2, 100))))
        pin = main.gxa_account.Pin
        reader.pinned_posts = AsyncMock(side_effect=[[pin(70, ""), pin(100, "")],
                                                     [pin(60, "과거 글을 새로 고정"), pin(100, "")]])
        main._save_json(main.GXA_FILE, {"17": {"latest": 100, "pin_ids": [70, 100], "pending": []}})
        def snapshot(pins):
            main.record_gxa_pins({"17"}, pins, snapshot=True)
            if any(p.message_id == 60 for p in pins):
                recovered.set()
        with patch.object(main.gxa_account, "PIN_CHECK_SECONDS", 0.02, create=True):
            listener = asyncio.create_task(reader.listen(lambda: True, snapshot, AsyncMock()))
            try:
                await asyncio.wait_for(recovered.wait(), 1)
                main.record_gxa_pins({"17"}, [pin(60, "중복 실시간 이벤트")])
                await main.flush_gxa(self.app)
                self.bot.send_message.assert_awaited_once()
                self.assertIn("/60", self.bot.send_message.await_args.kwargs["text"])
                self.assertEqual(reader.pinned_posts.await_count, 2)
            finally:
                disconnected.set()
                await asyncio.wait_for(listener, 2)
