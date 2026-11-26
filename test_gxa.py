import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

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

    async def test_subscribe_new_pin_once_then_turn_off(self):
        self.pin(100)
        await self.command("on")
        await main.check_gxa(self.app)
        self.bot.send_message.assert_not_awaited()
        self.pin(101)
        await main.check_gxa(self.app)
        await main.check_gxa(self.app)
        self.pin(100)
        await main.check_gxa(self.app)
        self.bot.send_message.assert_awaited_once()
        sent = self.bot.send_message.await_args.kwargs
        self.assertEqual(sent["chat_id"], 17)
        self.assertIn("공지 사진", sent["text"])
        self.assertIn("https://t.me/GXACommunity/101", sent["text"])
        await self.command("off")
        self.pin(103)
        await main.check_gxa(self.app)
        self.bot.send_message.assert_awaited_once()

    async def test_failed_delivery_retried_before_next_pin(self):
        self.pin(100)
        await self.command("on")
        self.pin(101)
        self.bot.send_message.side_effect = [NetworkError("offline"), None, None]
        await main.check_gxa(self.app)
        self.pin(102)
        await main.check_gxa(self.app)
        calls = self.bot.send_message.await_args_list
        self.assertEqual([c.kwargs["text"].split("/")[-1] for c in calls], ["101", "101", "102"])

    async def test_group_chat_cannot_subscribe(self):
        self.update.effective_chat.type = "supergroup"
        await self.command("on")
        self.bot.get_chat.assert_not_awaited()
        await main.check_gxa(self.app)
        self.bot.send_message.assert_not_awaited()

    async def test_no_visible_pin_does_not_claim_subscription(self):
        self.bot.get_chat.return_value = SimpleNamespace(pinned_message=None)
        await self.command("on")
        self.assertIn("고정 공지를 읽지 못", self.update.message.reply_text.await_args.args[0])
        self.assertEqual(main._load_json(main.GXA_FILE, {}), {})

    async def test_personal_pin_goes_only_to_connected_owner(self):
        self.assertTrue(hasattr(main, "personal_account"))
        reader = SimpleNamespace(owner_id=17, latest_pin=AsyncMock(return_value=
            SimpleNamespace(message_id=42, text="새 공지", caption=None)))
        main._save_json(main.GXA_FILE, {"17": {"latest": 41, "pending": []},
                                        "18": {"latest": 41, "pending": []}})
        self.pin(41)
        with patch.object(main, "personal_account", return_value=reader), patch.object(main, "activate_personal_account"):
            await main.check_gxa(self.app)
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
