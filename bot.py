
from google import genai
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes


# from google import genai
# from telegram import Update
# from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

# GEMINI_API_KEY = "YOUR_KEY"
# TELEGRAM_TOKEN = "YOUR_TOKEN"

client = genai.Client(api_key=GEMINI_API_KEY)

async def send_long_message(update, text):
    max_length = 4000
    for i in range(0, len(text), max_length):
        await update.message.reply_text(text[i:i+max_length])

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    try:
        user_text = update.message.text

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=user_text
        )

        await send_long_message(update, response.text)

    except Exception as e:
        print(e)
        await update.message.reply_text("Error occurred.")

app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

app.run_polling()