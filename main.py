from telethon import TelegramClient, events
from telethon.sessions import StringSession
import os
import asyncio
from flask import Flask

# Define your API credentials
api_id = 27488818
api_hash = '321fb972c3c3aee2dbdca1deeab39050'

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

# User state
user_states = {}

@client.on(events.NewMessage(pattern='/extract'))
async def extract_start(event):
    user_id = event.sender_id
    user_states[user_id] = {"step": "awaiting_first_url"}
    await event.reply(
        "Please send me the Link to the first message (containing the first poll or any message before the polls)\nExample: https://t.me/channel/123"
    )

@client.on(events.NewMessage)
async def handle_links(event):
    user_id = event.sender_id
    if user_id not in user_states:
        return

    state = user_states[user_id]
    text = event.raw_text.strip()

    # Get current step
    if state["step"] == "awaiting_first_url":
        state["first_url"] = text
        state["step"] = "awaiting_last_url"
        await event.reply("Got it! Now, please send me the link to the last message after the poll.")
    elif state["step"] == "awaiting_last_url":
        state["last_url"] = text
        state["step"] = "processing"
        await event.reply("Processing, please wait...")

        try:
            first_parts = state["first_url"].split('/')
            last_parts = state["last_url"].split('/')

            if len(first_parts) < 5 or len(last_parts) < 5:
                raise ValueError("Invalid URL format")

            chat = first_parts[3]
            first_msg_id = int(first_parts[4])
            last_msg_id = int(last_parts[4])

            entity = await client.get_entity(chat)

            polls = []
            total = last_msg_id - first_msg_id + 1
            count = 0

            async for message in client.iter_messages(entity, min_id=first_msg_id - 1, max_id=last_msg_id + 1):
                count += 1

                poll_obj = getattr(message, 'poll', None)
                if not poll_obj and message.media and hasattr(message.media, 'poll'):
                    poll_obj = message.media.poll

                if poll_obj and hasattr(poll_obj, 'question') and hasattr(poll_obj, 'answers'):
                    q = poll_obj.question
                    a_list = [a.text for a in poll_obj.answers]
                    correct = next((a.text for a in poll_obj.answers if getattr(a, 'correct', False) or getattr(a, 'is_correct', False)), None)
                    polls.append((q, a_list, correct))

                if count % 10 == 0:
                    await event.reply(f"Checked {count}/{total} messages... Found {len(polls)} valid polls.")

            if not polls:
                await event.reply("No valid polls found between the provided messages.")
            else:
                text_result = ""
                for i, (q, options, correct) in enumerate(polls, 1):
                    text_result += f"Q{i}. {q}\n"
                    for opt in options:
                        prefix = "✅" if opt == correct else "⬜"
                        text_result += f"  {prefix} {opt}\n"
                    text_result += "\n"

                with open("poll_results.txt", "w", encoding='utf-8') as f:
                    f.write(text_result)

                await event.reply(file="poll_results.txt")

        except Exception as e:
            await event.reply(f"Error while extracting polls: {e}")

        user_states.pop(user_id)

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
