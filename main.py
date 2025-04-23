import os
import re
from telethon import TelegramClient, events
from urllib.parse import urlparse

# Environment variables or replace with your actual values
api_id = int(os.getenv("27488818"))
api_hash = os.getenv("321fb972c3c3aee2dbdca1deeab39050")
session = os.getenv("1BVtsOKEBu1n1e48GEEoqRlPzUUy1CloJ4rwmCDOAfcyXvjPKoxgDTLfoypsaQxMKqqcXRTZ7Z7gACuECJuX8GnpAtiVMNTRQKMphB7j-Un7nILgKZ_EfYd1uwBMXN3WU1rPHsenQRxuhWsXcIx9T7hU2hF_za2l2saJhsj5N5WuvfazFBdX01sXV3y6PbCCYW4eSxBFhrcqR7cHoAoJWNlphdk7jygTHlltDbAt2aJzBKn_JBJgStE08OG5sFjkYQvnrMEJV7dpFjwPzW3akWHWGdFqdwNqDEz4yn6gnWP3wDZRsWOMy8r9FCmFpcx5V28g3d8L07XdkWtSHgDYoN9aK9kU1a9A=")

client = TelegramClient("userbot", api_id, api_hash, session=session)

# Track each user's step
user_state = {}

def extract_ids_from_url(url):
    parts = urlparse(url)
    path_parts = parts.path.strip("/").split("/")
    if len(path_parts) != 2:
        return None, None
    return path_parts[0], int(path_parts[1])

@client.on(events.NewMessage(pattern='/extract'))
async def handle_extract_command(event):
    user_id = event.sender_id
    user_state[user_id] = {'step': 'awaiting_first_url'}
    await event.respond("Please send me the **link to the first message** (poll or any message before it).\nExample: https://t.me/channel/123")

@client.on(events.NewMessage)
async def handle_url_messages(event):
    user_id = event.sender_id
    if user_id not in user_state:
        return

    msg = event.raw_text.strip()
    state = user_state[user_id]

    if state['step'] == 'awaiting_first_url':
        if "https://t.me/" in msg:
            state['first_url'] = msg
            state['step'] = 'awaiting_last_url'
            await event.respond("Got it!\nNow send me the **link to the last poll message**.\nExample: https://t.me/channel/456")
        else:
            await event.respond("Please send a valid first poll URL (starting with https://t.me/...)")

    elif state['step'] == 'awaiting_last_url':
        if "https://t.me/" in msg:
            first_url = state['first_url']
            last_url = msg
            del user_state[user_id]  # clear state

            await event.respond("Extracting polls between messages...")

            try:
                await extract_polls_between(client, event, first_url, last_url)
            except Exception as e:
                await event.respond(f"An error occurred: {e}")
        else:
            await event.respond("Please send a valid last poll URL (starting with https://t.me/...)")

async def extract_polls_between(client, event, first_url, last_url):
    first_chat, first_msg_id = extract_ids_from_url(first_url)
    last_chat, last_msg_id = extract_ids_from_url(last_url)

    if first_chat != last_chat:
        await event.respond("Both URLs must be from the same channel or chat.")
        return

    all_polls = []
    async for message in client.iter_messages(first_chat, min_id=first_msg_id - 1, max_id=last_msg_id + 1):
        if message.poll:
            question = message.poll.question
            options = message.poll.answers
            correct_option = next((opt for opt in options if opt.correct), None)
            text = f"{question}\n"
            for opt in options:
                mark = "✅" if opt.correct else ""
                text += f"- {opt.text} {mark}\n"
            all_polls.append(text)

    if not all_polls:
        await event.respond("No polls found between those messages.")
        return

    content = "\n\n".join(reversed(all_polls))  # reverse to maintain order
    filename = "quiz_extract.txt"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(content)

    await client.send_file(event.chat_id, filename, caption="Here is your extracted quiz.")
    os.remove(filename)

print("Userbot is running...")
client.start()
client.run_until_disconnected()
