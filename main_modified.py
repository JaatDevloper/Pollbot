from telethon import TelegramClient, events
from telethon.sessions import StringSession
import os
import asyncio
from flask import Flask

api_id = 27488818
api_hash = '321fb972c3c3aee2dbdca1deeab39050'

if os.path.exists("string_session.txt"):
    with open("string_session.txt", "r") as f:
        string_session = f.read().strip()
else:
    raise ValueError("string_session.txt not found or empty!")

if not string_session:
    raise ValueError("String session is empty!")

client = TelegramClient(StringSession(string_session), api_id, api_hash)

app = Flask(__name__)

@app.route("/health")
def health_check():
    return "OK", 200

user_states = {}

@client.on(events.NewMessage(pattern='/extract'))
async def start_extract(event):
    user_id = event.sender_id
    user_states[user_id] = {"step": "awaiting_first"}
    await event.reply("Please send me the Link to the first message (containing the first poll or any message before the polls)\nExample: https://t.me/channel/123")

@client.on(events.NewMessage)
async def handle_url(event):
    user_id = event.sender_id
    if user_id not in user_states:
        return

    state = user_states[user_id]
    if state["step"] == "awaiting_first" and "https://t.me/" in event.raw_text:
        user_states[user_id]["first_url"] = event.raw_text.strip()
        user_states[user_id]["step"] = "awaiting_last"
        await event.reply("Got it! Now, please send me the link to the last message after the poll.")
    elif state["step"] == "awaiting_last" and "https://t.me/" in event.raw_text:
        user_states[user_id]["last_url"] = event.raw_text.strip()
        await event.reply("Processing, please wait...")

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

            await extract_polls(chat, first_id, last_id, event)
        except Exception as e:
            await event.reply(f"Error while extracting polls: {e}")

        del user_states[user_id]

async def extract_polls(chat, first_id, last_id, event):
    entity = await client.get_entity(chat)
    valid_polls = []
    total_messages = last_id - first_id + 1
    progress = 0

    async for msg in client.iter_messages(entity, min_id=first_id, max_id=last_id):
        progress += 1
        if msg.media and hasattr(msg.media, 'poll'):
            poll = msg.media.poll
            question = poll.question
            answers = []
            correct_indices = []
            
            # Get all possible answer data
            for i, ans in enumerate(poll.answers):
                answers.append(ans.text)
                
                # Check multiple ways an answer might be marked as correct
                if hasattr(ans, 'correct') and ans.correct:
                    correct_indices.append(i)
                elif getattr(ans, 'correct', False):
                    correct_indices.append(i)
                
            # If poll results are available, check them too
            if hasattr(poll, 'results'):
                if hasattr(poll.results, 'correct_options'):
                    for i in poll.results.correct_options:
                        if i not in correct_indices:
                            correct_indices.append(i)
                elif hasattr(poll.results, 'correct_option') and poll.results.correct_option is not None:
                    if poll.results.correct_option not in correct_indices:
                        correct_indices.append(poll.results.correct_option)
                
            # As a backup, also check quiz results directly
            if hasattr(msg, 'quiz') and hasattr(msg.quiz, 'correct_answers'):
                for correct_answer in msg.quiz.correct_answers:
                    for i, ans in enumerate(answers):
                        if ans == correct_answer and i not in correct_indices:
                            correct_indices.append(i)
            
            valid_polls.append((question, answers, correct_indices))

        if progress % 10 == 0:
            await event.reply(f"Progress: {progress}/{total_messages} messages scanned...")

    await generate_txt(valid_polls, event)

async def generate_txt(polls, event):
    output = ""
    for idx, (question, answers, correct_indices) in enumerate(polls, 1):
        output += f"{question}\n"
        
        # Create answer options with proper letter labels
        for i, ans in enumerate(answers):
            letter = chr(97 + i)  # Convert 0, 1, 2... to a, b, c...
            mark = " ✅" if i in correct_indices else ""
            output += f"({letter}) {ans}{mark}\n"
        
        output += "\n"

    with open("quiz_results.txt", "w", encoding="utf-8") as f:
        f.write(output)

    await event.reply("Here is your extracted quiz:", file="quiz_results.txt")

@client.on(events.NewMessage(pattern='/start'))
async def start(event):
    await event.reply("Userbot is active and working!")

async def main():
    from threading import Thread
    def run_flask():
        app.run(host="0.0.0.0", port=5000)  # Changed port to 5000 to match workflow
    Thread(target=run_flask).start()
    await client.start()
    print("Client started successfully.")
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())