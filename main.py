from telegram.ext import Application, CommandHandler

TOKEN = "8410288468:AAEhGY-A-8Zu1iBR8zaKGKP4UTSxjRQSpWY"

async def start(update, context):
    await update.message.reply_text("Railway 봇 정상 작동중 🚀")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.run_polling()

if __name__ == "__main__":
    main()
