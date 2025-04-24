import asyncio
import logging
import os
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from flask import Flask
import json

# Set up Flask for the health check
app = Flask(__name__)

@app.route("/health")
def health_check():
    return "OK", 200

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot token (hardcoded)
BOT_TOKEN = "7443584461:AAFyeaZs4YIujxe5bWu9sGzMEHgTAUd8kDs"

# Store user states
user_states = {}

# Store known correct answers in a database
CORRECT_ANSWERS_DB = {}
QUIZ_DB = {}

if os.path.exists("answer_database.json"):
    try:
        with open("answer_database.json", "r", encoding="utf-8") as f:
            CORRECT_ANSWERS_DB = json.load(f)
    except Exception as e:
        logger.error(f"Error loading answer database: {e}")

async def save_correct_answers():
    try:
        with open("answer_database.json", "w", encoding="utf-8") as f:
            json.dump(CORRECT_ANSWERS_DB, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Error saving answer database: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Hello! I'm a Poll Extractor Bot.\n\n"
        "I can extract polls from Telegram channels and mark the correct answers.\n\n"
        "Use /extract to start the extraction process."
    )

async def extract_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_states[user_id] = {"step": "awaiting_first"}
    await update.message.reply_text(
        "Please send me the link to the first message (containing the first poll or any message before the polls)\n"
        "Example: https://t.me/channel/123"
    )

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # ✅ Detect forwarded quiz poll and extract correct answer
    if update.message.forward_from_chat and update.message.text:
        lines = update.message.text.split('\n')
        question = lines[0].strip()
        options = []
        correct_indices = []

        for i, line in enumerate(lines[1:]):
            option = line.strip()
            if '✅' in option:
                correct_indices.append(i)
                option = option.replace('✅', '').strip()
            options.append(option)

        polls = [(question, options, correct_indices)]
        await generate_txt(polls, update, context)
        return

    # Normal extract flow
    if user_id not in user_states:
        return

    state = user_states[user_id]

    if state["step"] == "awaiting_first" and "https://t.me/" in update.message.text:
        user_states[user_id]["first_url"] = update.message.text.strip()
        user_states[user_id]["step"] = "awaiting_last"
        await update.message.reply_text("Got it! Now, please send me the link to the last message after the polls.")

    elif state["step"] == "awaiting_last" and "https://t.me/" in update.message.text:
        user_states[user_id]["last_url"] = update.message.text.strip()
        await update.message.reply_text("Processing, please wait...")

        try:
            first_url = user_states[user_id]["first_url"]
            last_url = user_states[user_id]["last_url"]

            parts1 = first_url.split('/')
            parts2 = last_url.split('/')

            if len(parts1) < 5 or len(parts2) < 5:
                raise ValueError("Invalid URLs")

            chat = parts1[3]
            first_id = int(parts1[4])
            last_id = int(parts2[4])

            await extract_polls(context.bot, chat, first_id, last_id, update, context)

        except Exception as e:
            logger.error(f"Error processing: {e}", exc_info=True)
            await update.message
          
