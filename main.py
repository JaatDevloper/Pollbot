from telethon import TelegramClient, events
from telethon.sessions import StringSession
import os
import asyncio
from flask import Flask

# API credentials
api_id = 27488818
api_hash = '321fb972c3c3aee2dbdca1deeab39050'

# Load string session
if os.path.exists("string_session.txt"):
    with open("string_session.txt", "r") as f:
        string_session = f.read().strip()
else:
    raise ValueError("string_session.txt not found or empty! Please create it and paste your string session inside.")

if not string_session:
    raise ValueError("String session is empty!")

# Init client
client = TelegramClient(StringSession(string_session), api_id, api_hash)

# Flask app for health checks
app = Flask(__name__)

@app.route("/health")
def health_check():
    return "OK", 200

# User state
user_states = {}

# /start command
@client.on(events.NewMessage(pattern='/start'))
async def start(event):
    await event.reply("Userbot is active and working!")

# /extract command
@client.on(events.NewMessage(pattern='/extract'))
async def start_extract(event):
    user_id = event.sender_id
    user_states[user_id] = {'stage': 'awaiting_first_url'}
    await event.reply("Please send me the Link to the first message (containing the first poll or any message before the polls)\nExample: https://t.me/channel/123")

# Poll URL handling
@client.on(events.NewMessage(incoming=True))
async def handle_links(event):
    user_id = event.sender_id
    text = event.raw_text.strip()

    # Ignore if it's a command
    if text.startswith('/'):
        return

    # If user is not in flow
    if user_id not in user_states:
        return

    state = user_states[user_id]

    if state['stage'] == 'awaiting_first_url':
        state['first_url'] = text
        state['stage'] = 'awaiting_last_url'
        await event.reply("Got it! Now, please send me the link to the last message after the poll.")
    elif state['stage'] == 'awaiting_last_url':
        state['last_url'] = text
        await event.reply("Processing, please wait...")

        try:
            first_message_id = int(state['first_url'].split('/')[-1])
            last_message_id = int(state['last_url'].split('/')[-1])
            channel_username = state['first_url'].split('/')[-2]

            await extract_polls(event, channel_username, first_message_id, last_message_id)

        except Exception as e:
            await event.reply(f"Error while extracting polls: {e}")

        del user_states[user_id]

# Extract polls
async def extract_polls(event, channel_username, first_id, last_id):
    channel = await client.get_entity(channel_username)
    valid_polls = []
    progress = 0
    total = last_id - first_id + 1

    async for message in client.iter_messages(channel, min_id=first_id - 1, max_id=last_id + 1):
        if message.poll:
            question = message.poll.question
            answers = [a.text for a in message.poll.answers]
            correct_answer = next((a.text for a in message.poll.answers if getattr(a, 'correct', False)), None)

            valid_polls.append((question, answers, correct_answer))

        progress += 1
        if progress % 10 == 0:
            await event.reply(f"Processed {progress}/{total} messages... Found {len(valid_polls)} polls.")

    await generate_txt(valid_polls, event)

# Generate .txt file
async def generate_txt(polls, event):
    text = ""
    for idx, (question, answers, correct) in enumerate(polls, 1):
        text += f"Q{idx}. {question}\n"
        for ans in answers:
            mark = '✅' if ans == correct else '⬜'
            text += f"  {mark} {ans}\n"
        text += "\n"

    with open('quiz_results.txt', 'w', encoding='utf-8') as f:
        f.write(text)

    await event.reply(file=open('quiz_results.txt', 'rb'))

# Start app
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
