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

# Bot token from BotFather - you'll need to replace this with your actual token
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("No bot token found. Set the TELEGRAM_BOT_TOKEN environment variable.")

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
    """Save the correct answers database to disk."""
    try:
        with open("answer_database.json", "w", encoding="utf-8") as f:
            json.dump(CORRECT_ANSWERS_DB, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Error saving answer database: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /start is issued."""
    await update.message.reply_text(
        "👋 Hello! I'm a Poll Extractor Bot.\n\n"
        "I can extract polls from Telegram channels and mark the correct answers.\n\n"
        "Use /extract to start the extraction process."
    )

async def extract_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process the /extract command to start poll extraction."""
    user_id = update.effective_user.id
    user_states[user_id] = {"step": "awaiting_first"}
    await update.message.reply_text(
        "Please send me the link to the first message (containing the first poll or any message before the polls)\n"
        "Example: https://t.me/channel/123"
    )

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming messages."""
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
            
            # Extract channel and message IDs
            parts1 = first_url.split('/')
            parts2 = last_url.split('/')
            
            if len(parts1) < 5 or len(parts2) < 5:
                raise ValueError("Invalid URLs")
            
            chat = parts1[3]
            first_id = int(parts1[4])
            last_id = int(parts2[4])
            
            # Process the extraction
            await extract_polls(context.bot, chat, first_id, last_id, update, context)
        
        except Exception as e:
            logger.error(f"Error processing: {e}", exc_info=True)
            await update.message.reply_text(f"Error while processing: {e}")
        
        # Clean up user state
        del user_states[user_id]

async def extract_polls(bot: Bot, chat: str, first_id: int, last_id: int, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Extract polls from the specified message range."""
    valid_polls = []
    
    # Get chat_id (can be username or channel ID)
    chat_id = chat
    if not chat.startswith('@') and not chat.startswith('-100'):
        chat_id = f'@{chat}'
    
    # Collect all messages in range
    await update.message.reply_text("Collecting messages...")
    
    # For regular bots, we need to request each message individually
    # Since there's no iter_messages equivalent in python-telegram-bot
    all_ids = list(range(first_id, last_id + 1))
    poll_count = 0
    progress_count = 0
    
    for msg_id in all_ids:
        progress_count += 1
        try:
            # Forward message to get access to it
            # This is because bot API has limitations on getting messages directly
            message = None
            
            try:
                # Try to get message directly (works if bot has proper permissions)
                message = await bot.get_chat_message(chat_id=chat_id, message_id=msg_id)
            except Exception:
                # If direct access fails, try alternative methods
                # For channels where the bot is admin, we can sometimes forward messages
                try:
                    # Create a temporary chat with the bot user
                    temp_chat_id = update.effective_user.id
                    forwarded = await bot.forward_message(
                        chat_id=temp_chat_id,
                        from_chat_id=chat_id,
                        message_id=msg_id
                    )
                    message = forwarded
                except Exception as e:
                    # If forwarding fails, log and continue
                    logger.warning(f"Couldn't access message {msg_id}: {e}")
                    continue
            
            # Check if message contains a poll
            if hasattr(message, 'poll') and message.poll:
                poll = message.poll
                question = poll.question
                answers = [option.text for option in poll.options]
                correct_indices = []
                
                # For quiz polls, Bot API provides correct_option_id directly
                if hasattr(poll, 'type') and poll.type == 'quiz':
                    if hasattr(poll, 'correct_option_id') and poll.correct_option_id is not None:
                        correct_indices.append(poll.correct_option_id)
                
                # Store the correct answer in the database for future reference
                if correct_indices:
                    CORRECT_ANSWERS_DB[question] = correct_indices
                # If no correct answer found but we have it in database, use that
                elif question in CORRECT_ANSWERS_DB:
                    correct_indices = CORRECT_ANSWERS_DB[question]
                
                valid_polls.append((question, answers, correct_indices))
                poll_count += 1
            
            # Show progress periodically
            if progress_count % 10 == 0:
                await update.message.reply_text(f"Processed {progress_count}/{len(all_ids)} messages, found {poll_count} polls...")
        
        except Exception as e:
            # Skip messages that can't be retrieved or processed
            logger.warning(f"Error processing message {msg_id}: {e}")
            continue
    
    # Save updated database
    await save_correct_answers()
    
    await update.message.reply_text(f"Found {poll_count} polls. Generating output...")
    await generate_txt(valid_polls, update, context)

async def generate_txt(polls, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate a text file with the extracted polls."""
    output = ""
    correct_count = 0
    
    for question, answers, correct_indices in polls:
        output += f"{question}\n"
        
        for i, ans in enumerate(answers):
            # Check if answer already has a label
            if ans.strip().startswith('(') and len(ans) > 3 and ans[1].isalpha() and ans[2] == ')':
                # It already has a label
                mark = " ✅" if i in correct_indices else ""
                output += f"{ans}{mark}\n"
            else:
                # Add a label
                letter = chr(97 + i)  # a, b, c, etc.
                mark = " ✅" if i in correct_indices else ""
                output += f"({letter}) {ans}{mark}\n"
        
        output += "\n"
        
        if correct_indices:
            correct_count += 1
    
    # Save the output to a file
    with open("quiz_results.txt", "w", encoding="utf-8") as f:
        f.write(output)
    
    # Send the file
    await update.message.reply_document(document=open("quiz_results.txt", "rb"))
    
    if correct_count > 0:
        await update.message.reply_text(f"Successfully marked {correct_count} polls with correct answers ✅")
    else:
        await update.message.reply_text("No correct answers were found in these polls.")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log errors caused by updates."""
    logger.error("Exception while handling an update:", exc_info=context.error)
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "Sorry, an error occurred while processing your request."
        )

def main():
    """Start the bot."""
    # Start Flask in a separate thread
    from threading import Thread
    def run_flask():
        app.run(host="0.0.0.0", port=8080)
    Thread(target=run_flask).start()
    
    # Create the Application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("extract", extract_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    
    # Register error handler
    application.add_error_handler(error_handler)
    
    # Run the bot
    logger.info("Starting bot")
    application.run_polling()

if __name__ == "__main__":
    main()