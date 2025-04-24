import asyncio
import logging
import os
import json
import string
import random
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from flask import Flask
from threading import Thread

# Flask app for health checks
app = Flask(__name__)

@app.route("/health")
def health_check():
    return "OK", 200

# Logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Bot token
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN")

# Databases
QUIZ_DB = {}
if os.path.exists("quizzes.json"):
    with open("quizzes.json", "r", encoding="utf-8") as f:
        QUIZ_DB = json.load(f)

user_states = {}

# Helper to save DB
async def save_quizzes():
    with open("quizzes.json", "w", encoding="utf-8") as f:
        json.dump(QUIZ_DB, f, ensure_ascii=False, indent=2)

# Generate unique Quiz ID
def generate_quiz_id():
    return ''.join(random.choices(string.digits, k=5))

# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Welcome! Use /quiz to save polls as a quiz or /play <id> to play a quiz.")

# /quiz start
async def quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_states[user_id] = {"step": "awaiting_first"}
    await update.message.reply_text("Send me the FIRST poll message URL:")

# /play command
async def play_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /play <quiz_id>")
        return
    quiz_id = args[0]
    if quiz_id not in QUIZ_DB:
        await update.message.reply_text("Quiz ID not found.")
        return

    polls = QUIZ_DB[quiz_id]
    for poll in polls:
        question = poll['question']
        options = poll['options']
        correct_id = poll['correct']

        await update.message.bot.send_poll(
            chat_id=update.effective_chat.id,
            question=question,
            options=options,
            type='quiz',
            correct_option_id=correct_id,
            is_anonymous=False
        )
        await asyncio.sleep(1.5)

# Handle messages
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    if user_id not in user_states:
        return

    state = user_states[user_id]

    if state["step"] == "awaiting_first" and "https://t.me/" in text:
        state["first_url"] = text.strip()
        state["step"] = "awaiting_last"
        await update.message.reply_text("Now send me the LAST poll message URL:")

    elif state["step"] == "awaiting_last" and "https://t.me/" in text:
        state["last_url"] = text.strip()
        await update.message.reply_text("Saving polls and creating quiz, please wait...")

        try:
            first_url = state["first_url"]
            last_url = state["last_url"]

            parts1 = first_url.split('/')
            parts2 = last_url.split('/')
            chat = parts1[3]
            first_id = int(parts1[4])
            last_id = int(parts2[4])
            chat_id = f"@{chat}" if not chat.startswith('-100') else chat

            all_ids = list(range(first_id, last_id + 1))
            collected_polls = []
            for msg_id in all_ids:
                try:
                    message = await context.bot.forward_message(
                        chat_id=update.effective_user.id,
                        from_chat_id=chat_id,
                        message_id=msg_id
                    )
                    if message.poll:
                        poll = message.poll
                        question = poll.question
                        options = [o.text for o in poll.options]
                        correct_id = poll.correct_option_id or 0
                        collected_polls.append({
                            "question": question,
                            "options": options,
                            "correct": correct_id
                        })
                except Exception as e:
                    logger.warning(f"Could not fetch message {msg_id}: {e}")
                    continue

            if collected_polls:
                quiz_id = generate_quiz_id()
                QUIZ_DB[quiz_id] = collected_polls
                await save_quizzes()
                await update.message.reply_text(f"Saved {len(collected_polls)} polls as quiz with ID {quiz_id}.")
                
                # Start playing the quiz automatically after saving the polls
                await play_quiz(update, quiz_id)

            else:
                await update.message.reply_text("No polls were found in the given range.")
        except Exception as e:
            logger.error(f"Quiz creation error: {e}", exc_info=True)
            await update.message.reply_text("Failed to process. Please check the links and try again.")

        del user_states[user_id]

# Play quiz automatically after saving polls
async def play_quiz(update: Update, quiz_id: str):
    if quiz_id not in QUIZ_DB:
        await update.message.reply_text("Quiz ID not found.")
        return

    polls = QUIZ_DB[quiz_id]
    results = {'correct_answers': 0, 'total_questions': len(polls)}

    for poll in polls:
        question = poll['question']
        options = poll['options']
        correct_id = poll['correct']

        # Send poll to the user
        await update.message.bot.send_poll(
            chat_id=update.effective_chat.id,
            question=question,
            options=options,
            type='quiz',
            correct_option_id=correct_id,
            is_anonymous=False
        )

        # Wait 15 seconds before sending the next poll
        await asyncio.sleep(15)

    # After sending all polls, send the results
    await update.message.reply_text(f"Quiz finished! Here are your results:\n"
                                   f"Total Questions: {results['total_questions']}\n"
                                   f"Correct Answers: {results['correct_answers']}\n"
                                   f"Score: {int((results['correct_answers'] / results['total_questions']) * 100)}%")

# Main setup
def main():
    Thread(target=lambda: app.run(host="0.0.0.0", port=8080)).start()

    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("quiz", quiz_command))
    application.add_handler(CommandHandler("play", play_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    logger.info("Bot is running...")
    application.run_polling()

if __name__ == '__main__':
    main()
    
