import os
import re
import asyncio
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from flask import Flask

api_id = 27488818
api_hash = '321fb972c3c3aee2dbdca1deeab39050'

if os.path.exists("string_session.txt"):
    with open("string_session.txt", "r") as f:
        string_session = f.read().strip()
else:
    raise ValueError("string_session.txt not found or empty!")

client = TelegramClient(StringSession(string_session), api_id, api_hash)

app = Flask(__name__)

@app.route("/health")
def health_check():
    return "OK", 200

# Store user-specific states and URLs
user_sessions = {}

def extract_info(url):
    match = re.match(r'https://t.me/([^/]+)/(\d+)', url)
    if match:
        return match.group(1), int(match.group(2))
    else:
        raise ValueError("Invalid URL")

@client.on(events.NewMessage(pattern='/extract'))
async def extract_command(event):
    user_id = event.sender_id
    user_sessions[user_id] = {'step': 'awaiting_first'}
    await event.reply("Please send me the Link to the first message (containing the first poll or any message before the polls)\nExample: https://t.me/channel/123")

@client.on(events.NewMessage)
async def handle_links(event):
    user_id = event.sender_id
    text = event.raw_text.strip()

    if user_id not in user_sessions:
        return  # Ignore messages from users who haven't initiated

    session = user_sessions[user_id]

    if session['step'] == 'awaiting_first' and text.startswith('https://t.me/'):
        session['first_url'] = text
        session['step'] = 'awaiting_last'
        await event.reply("Got it! Now, please send me the link to the last message after the poll.")
        return

    if session['step'] == 'awaiting_last' and text.startswith('https://t.me/'):
        session['last_url'] = text
        session['step'] = 'processing'
        await event.reply("Processing, please wait...")

        try:
            first_channel, first_msg_id = extract_info(session['first_url'])
            last_channel, last_msg_id = extract_info(session['last_url'])

            if first_channel != last_channel:
                await event.reply("Error: First and last links must be from the same channel.")
                user_sessions.pop(user_id)
                return

            channel = await client.get_entity(first_channel)
            polls = []
            total = last_msg_id - first_msg_id + 1
            count = 0

            async for message in client.iter_messages(channel, min_id=first_msg_id, max_id=last_msg_id):
                if message.poll:
                    q = message.poll.question
                    a_list = [a.text for a in message.poll.answers]
                    correct = next((a.text for a in message.poll.answers if a.is_correct), None)
                    polls.append((q, a_list, correct))
                count += 1

            await generate_txt(polls, event)
        except Exception as e:
            await event.reply(f"Error while extracting polls: {str(e)}")
        finally:
            user_sessions.pop(user_id)

async def generate_txt(polls, event):
    content = ""
    for i, (q, a_list, correct) in enumerate(polls, 1):
        content += f"Q{i}. {q}\n"
        for a in a_list:
            prefix = "✅" if a == correct else "⬜"
            content += f"  {prefix} {a}\n"
        content += "\n"

    with open("quiz_results.txt", "w", encoding="utf-8") as f:
        f.write(content)

    await event.reply(file=open("quiz_results.txt", "rb"))

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
