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
            answers = [ans.text for ans in poll.answers]
            correct_answer = None
            for ans in poll.answers:
                if getattr(ans, 'correct', False):
                    correct_answer = ans.text
                    break
            valid_polls.append((question, answers, correct_answer))

        if progress % 10 == 0:
            await event.reply(f"Progress: {progress}/{total_messages} messages scanned...")

    await generate_txt(valid_polls, event)

async def generate_txt(polls, event):
    output = ""
    for idx, (question, answers, correct) in enumerate(polls, 1):
        output += f"{question}\n"
        for ans in answers:
            mark = " ✅" if ans == correct else ""
            output += f"{ans}{mark}\n"
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
        app.run(host="0.0.0.0", port=8080)
    Thread(target=run_flask).start()
    await client.start()
    print("Client started successfully.")
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
