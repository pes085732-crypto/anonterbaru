from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters
)

from config import BOT_TOKEN
from database import create_user

MAIN_MENU = ReplyKeyboardMarkup(
    [
        ["🚀 Find Partner"],
        ["⚙ Settings", "⭐ VIP"],
        ["❓ Help"]
    ],
    resize_keyboard=True
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    create_user(user.id)

    await update.message.reply_text(
        "👋 Welcome to Anonymous Chat Bot!\n\n"
        "Tekan tombol di bawah untuk mulai.",
        reply_markup=MAIN_MENU
    )

async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "🚀 Find Partner":
        await update.message.reply_text(
            "🔎 Mencari partner...\n(Fitur pairing belum aktif — tahap berikutnya)"
        )

    elif text == "⚙ Settings":
        await update.message.reply_text("Menu setting akan dibuat di tahap selanjutnya.")

    elif text == "⭐ VIP":
        await update.message.reply_text("Fitur VIP coming soon.")

    else:
        await update.message.reply_text("Gunakan tombol menu ya.")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu_handler))

    print("BOT RUNNING...")
    app.run_polling()

if __name__ == "__main__":
    main()
