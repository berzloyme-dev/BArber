from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = "8344001959:AAGYcesxI7MlfWwxGPlQ7Q1P8HxhUcWAhwQ"
SALTAROSH_ID = 9587055445  # sartaroshning Telegram ID'si

# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user.first_name

    keyboard = [
        [KeyboardButton(text="📲 Raqamni yuborish", request_contact=True)]
    ]
    markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

    await update.message.reply_text(
        f"Salom {user}! Sochingizni olish uchun ro‘yxatdan o‘ting.\n"
        f"Quyidagi tugmani bosing 👇",
        reply_markup=markup
    )

# Kontakt qabul qilish
async def contact_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.contact
    user = update.message.from_user

    name = user.first_name
    phone = contact.phone_number

    text = f"Yangi mijoz!\n👤 Ism: {name}\n📞 Raqam: {phone}"

    # Sartaroshga yuborish
    await context.bot.send_message(chat_id=SALTAROSH_ID, text=text)

    # Klentga tasdiq
    await update.message.reply_text(
        "Rahmat! Siz ro‘yxatga olindingiz ✅\n"
        "Sartarosh siz bilan tez orada bog‘lanadi."
    )

# main
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.CONTACT, contact_handler))

    print("Bot ishga tushdi...")
    app.run_polling()

if __name__ == "__main__":
    main()
