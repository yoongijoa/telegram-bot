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
