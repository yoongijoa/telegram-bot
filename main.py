import time
import os
from telegram import Bot

TOKEN = os.getenv("TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

bot = Bot(token=TOKEN)

while True:
    bot.send_message(chat_id=CHAT_ID, text="Railway 알람봇 정상 작동중 🚀")
    time.sleep(60)