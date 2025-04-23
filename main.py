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

app = Flask(__name__)

@app.route("/health")
def health_check():
    return "OK", 200

user_states = {}

@client.on(events.NewMessage(pattern='/extract'))
async def start_extract(event):
    user_id = event.sender_id
    user_states[user_id] = {'step': 'first'}
    await event.reply("Please send me the Link to the first message (containing the first poll or any message before the polls)\nExample: https://t.me/channel/123")

@client.on(events.NewMessage)
async def handle_links(event):
    user_id = event.sender_id
    if user_id not in user_states:
        return

    text = event.raw_text.strip()
    if not text.startswith("https://t.me/"):
        return

    state = user_states[user_id]

    if state['step'] == 'first':
        state['first_url'] = text
        state['step'] = 'last'
        await event.reply("Got it! Now, please send me the link to the last message after the poll.")
    elif state['step'] == 'last':
        state['last_url'] = text
        await event.reply("Processing, please wait...")
        try:
            first_parts = state['first_url'].split('/')
            last_parts = state['last_url'].split('/')

            if len(first_parts) < 5 or len(last_parts) < 5:
                await event.reply("Invalid links. Please send full message links.")
                return

            channel_username = first_parts[3]
            first_msg_id = int(first_parts[4])
            last_msg_id = int(last_parts[4])

            channel = await client.get_entity(channel_username)

            polls = []
            count = 0
            async for message in client.iter_messages(channel, min_id=first_msg_id, max_id=last_msg_id):
                poll_obj = None
                if message.poll:
                    poll_obj = message.poll
                elif message.media and hasattr(message.media, 'poll'):
                    poll_obj = message.media.poll

                if poll_obj:
                    q = poll_obj.question
                    a_list = [a.text for a in poll_obj.answers]
                    correct = next((a.text for a in poll_obj.answers if a.is_correct), None)
                    polls.append((q, a_list, correct))

                count += 1
                if count % 10 == 0:
                    await event.reply(f"Checked {count} messages... Found {len(polls)} valid polls so far.")

            if not polls:
                await event.reply("No valid polls found between these messages.")
                return

            txt = ""
            for i, (q, a_list, correct) in enumerate(polls, 1):
                txt += f"Q{i}. {q}\n"
                for a in a_list:
                    mark = "✅" if a == correct else "⬜"
                    txt += f"  {mark} {a}\n"
                txt += "\n"

            with open("poll_output.txt", "w", encoding="utf-8") as f:
                f.write(txt)

            await event.reply(file="poll_output.txt")

        except Exception as e:
            await event.reply(f"Error while extracting polls: {e}")
        finally:
            user_states.pop(user_id, None)

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
