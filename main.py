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
            await update.message.reply_text(f"Error while processing: {e}")
        
        del user_states[user_id]

async def extract_polls(bot: Bot, chat: str, first_id: int, last_id: int, update: Update, context: ContextTypes.DEFAULT_TYPE):
    valid_polls = []
    
    chat_id = chat
    if not chat.startswith('@') and not chat.startswith('-100'):
        chat_id = f'@{chat}'
    
    await update.message.reply_text("Collecting messages...")
    
    all_ids = list(range(first_id, last_id + 1))
    poll_count = 0
    progress_count = 0
    
    for msg_id in all_ids:
        progress_count += 1
        try:
            message = None
            
            try:
                message = await bot.get_chat_message(chat_id=chat_id, message_id=msg_id)
            except Exception:
                try:
                    temp_chat_id = update.effective_user.id
                    forwarded = await bot.forward_message(
                        chat_id=temp_chat_id,
                        from_chat_id=chat_id,
                        message_id=msg_id
                    )
                    message = forwarded
                except Exception as e:
                    logger.warning(f"Couldn't access message {msg_id}: {e}")
                    continue
            
            if hasattr(message, 'poll') and message.poll:
                poll = message.poll
                question = poll.question
                answers = [option.text for option in poll.options]
                correct_indices = []
                
                if hasattr(poll, 'type') and poll.type == 'quiz':
                    if hasattr(poll, 'correct_option_id') and poll.correct_option_id is not None:
                        correct_indices.append(poll.correct_option_id)
                
                if correct_indices:
                    CORRECT_ANSWERS_DB[question] = correct_indices
                elif question in CORRECT_ANSWERS_DB:
                    correct_indices = CORRECT_ANSWERS_DB[question]
                
                valid_polls.append((question, answers, correct_indices))
                poll_count += 1
            
            if progress_count % 10 == 0:
                await update.message.reply_text(f"Processed {progress_count}/{len(all_ids)} messages, found {poll_count} polls...")
        
        except Exception as e:
            logger.warning(f"Error processing message {msg_id}: {e}")
            continue
    
    await save_correct_answers()
    
    await update.message.reply_text(f"Found {poll_count} polls. Generating output...")
    await generate_txt(valid_polls, update, context)

async def generate_txt(polls, update: Update, context: ContextTypes.DEFAULT_TYPE):
    output = ""
    correct_count = 0
    
    for question, answers, correct_indices in polls:
        output += f"{question}\n"
        
        for i, ans in enumerate(answers):
            if ans.strip().startswith('(') and len(ans) > 3 and ans[1].isalpha() and ans[2] == ')':
                mark = " ✅" if i in correct_indices else ""
                output += f"{ans}{mark}\n"
            else:
                letter = chr(97 + i)
                mark = " ✅" if i in correct_indices else ""
                output += f"({letter}) {ans}{mark}\n"
        
        output += "\n"
        
        if correct_indices:
            correct_count += 1
    
    with open("quiz_results.txt", "w", encoding="utf-8") as f:
        f.write(output)
    
    await update.message.reply_document(document=open("quiz_results.txt", "rb"))
    
    if correct_count > 0:
        await update.message.reply_text(f"Successfully marked {correct_count} polls with correct answers ✅")
    else:
        await update.message.reply_text("No correct answers were found in these polls.")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Exception while handling an update:", exc_info=context.error)
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "Sorry, an error occurred while processing your request."
        )

def main():
    from threading import Thread
    def run_flask():
        app.run(host="0.0.0.0", port=8080)
    Thread(target=run_flask).start()
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("extract", extract_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    
    application.add_error_handler(error_handler)
    
    logger.info("Starting bot")
    application.run_polling()

if __name__ == "__main__":
    main()
    
