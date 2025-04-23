from telethon import TelegramClient, events
from telethon.sessions import StringSession
import os
import asyncio
from flask import Flask

# Define your API credentials
api_id = 27488818  # Replace with your API ID
api_hash = '321fb972c3c3aee2dbdca1deeab39050'  # Replace with your API Hash

# Load string session from the string_session.txt file
if os.path.exists("string_session.txt"):
    with open("string_session.txt", "r") as f:
        string_session = f.read().strip()
else:
    raise ValueError("string_session.txt not found or empty! Please create it and paste your string session inside.")

if not string_session:
    raise ValueError("String session is empty!")

client = TelegramClient(StringSession(string_session), api_id, api_hash)

# Flask app for health check
app = Flask(__name__)

@app.route("/health")
def health_check():
    return "OK", 200

# State tracking
user_states = {}

@client.on(events.NewMessage(pattern='/extract'))
async def extract_command(event):
    user_id = event.sender_id
    user_states[user_id] = {'stage': 'awaiting_first_url'}
    await event.reply("Please send me the Link to the first message (containing the first poll or any message before the polls)\nExample: https://t.me/channel/123")

@client.on(events.NewMessage)
async def handle_poll_links(event):
    user_id = event.sender_id
    text = event.raw_text.strip()

    if user_id not in user_states:
        return

    if text.startswith("/"):
        return

    state = user_states[user_id]

    if state['stage'] == 'awaiting_first_url':
        if 'https://t.me/' not in text:
            await event.reply("Please send a valid Telegram message link.")
            return
        state['first_url'] = text
        state['stage'] = 'awaiting_last_url'
        await event.reply("Got it! Now, please send me the link to the last message after the poll.")

    elif state['stage'] == 'awaiting_last_url':
        if 'https://t.me/' not in text:
            await event.reply("Please send a valid Telegram message link.")
            return
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

# Extract polls between two message IDs
async def extract_polls(event, channel_username, first_message_id, last_message_id):
    try:
        channel = await client.get_entity(channel_username)

        valid_polls = []
        total = last_message_id - first_message_id + 1
        count = 0

        async for message in client.iter_messages(channel, min_id=first_message_id, max_id=last_message_id):
            if message.poll:
                question = message.poll.question
                answers = [a.text for a in message.poll.answers]
                correct_answer = None
                for ans in message.poll.answers:
                    if getattr(ans, 'correct', False):
                        correct_answer = ans.text
                        break
                valid_polls.append((question, answers, correct_answer))

            count += 1
            if count % 10 == 0 or count == total:
                await event.reply(f"Processed {count}/{total} messages...\nFound {len(valid_polls)} valid polls so far.")

        await generate_txt(valid_polls, event)

    except Exception as e:
        await event.reply(f"Error while extracting polls: {e}")

# Generate a .txt file with results
async def generate_txt(valid_polls, event):
    text = ""
    for idx, (question, answers, correct_answer) in enumerate(valid_polls, 1):
        text += f"Q{idx}. {question}\n"
        for ans in answers:
            prefix = "✅" if ans == correct_answer else "⬜"
            text += f"  {prefix} {ans}\n"
        text += "\n"

    with open('quiz_results.txt', 'w', encoding='utf-8') as file:
        file.write(text)

    await event.reply(file=open('quiz_results.txt', 'rb'))

@client.on(events.NewMessage(pattern='/start'))
async def start(event):
    await event.reply("Userbot is active and working!")

# Main runner
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
