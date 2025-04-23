import os
import asyncio
from urllib.parse import urlparse
from telethon import TelegramClient, events
from telethon.sessions import StringSession

# Load credentials from environment variables
api_id = int(os.getenv("API_ID", "27488818"))  # Replace default if needed
api_hash = os.getenv("API_HASH", "321fb972c3c3aee2dbdca1deeab39050")
string_session = os.getenv("1BVtsOKEBu1n1e48GEEoqRlPzUUy1CloJ4rwmCDOAfcyXvjPKoxgDTLfoypsaQxMKqqcXRTZ7Z7gACuECJuX8GnpAtiVMNTRQKMphB7j-Un7nILgKZ_EfYd1uwBMXN3WU1rPHsenQRxuhWsXcIx9T7hU2hF_za2l2saJhsj5N5WuvfazFBdX01sXV3y6PbCCYW4eSxBFhrcqR7cHoAoJWNlphdk7jygTHlltDbAt2aJzBKn_JBJgStE08OG5sFjkYQvnrMEJV7dpFjwPzW3akWHWGdFqdwNqDEz4yn6gnWP3wDZRsWOMy8r9FCmFpcx5V28g3d8L07XdkWtSHgDYoN9aK9kU1a9A=")

if not string_session:
    raise ValueError("String session is required. Please generate it and set as STRING_SESSION env variable.")

# Initialize Telegram client
client = TelegramClient(StringSession(string_session), api_id, api_hash)

# Global state
first_poll_url = None
last_poll_url = None

# Start /extract command
@client.on(events.NewMessage(pattern='/extract'))
async def start_extract(event):
    global first_poll_url, last_poll_url
    first_poll_url = None
    last_poll_url = None
    await event.reply("Please send me the link to the *first* poll message (or any message just before the poll starts).")

# Handle messages to capture URLs
@client.on(events.NewMessage)
async def handle_urls(event):
    global first_poll_url, last_poll_url

    if event.text.startswith("https://t.me/") or event.text.startswith("http://t.me/"):
        if not first_poll_url:
            first_poll_url = event.text
            await event.reply("Got the first message URL! Now send me the link to the *last* poll message.")
        elif not last_poll_url:
            last_poll_url = event.text
            await event.reply("Thanks! Extracting polls now...")

            try:
                await extract_polls(event)
            except Exception as e:
                await event.reply(f"Error: {str(e)}")

# Extract polls between first and last message
async def extract_polls(event):
    global first_poll_url, last_poll_url

    first_id = int(first_poll_url.split("/")[-1])
    last_id = int(last_poll_url.split("/")[-1])

    url_parts = urlparse(first_poll_url)
    channel_username = url_parts.path.strip("/").split("/")[0]
    channel = await client.get_entity(channel_username)

    valid_polls = []
    progress = 0
    total = last_id - first_id + 1

    async for message in client.iter_messages(channel, min_id=first_id, max_id=last_id):
        if message.poll:
            question = message.poll.question
            answers = [a.text for a in message.poll.answers]
            correct = next((a.text for a in message.poll.answers if a.is_correct), None)
            valid_polls.append((question, answers, correct))

        progress += 1
        if progress % 10 == 0:
            await event.reply(f"Processed {progress}/{total} messages. Found {len(valid_polls)} polls so far...")

    await generate_txt(valid_polls, event)
    first_poll_url = None
    last_poll_url = None

# Generate .txt result file
async def generate_txt(valid_polls, event):
    text = ""
    for idx, (q, options, correct) in enumerate(valid_polls, 1):
        text += f"Q{idx}. {q}\n"
        for opt in options:
            marker = "✅" if opt == correct else "⬜"
            text += f"  {marker} {opt}\n"
        text += "\n"

    with open("quiz_results.txt", "w", encoding="utf-8") as f:
        f.write(text)

    await event.reply("Here is your extracted quiz:", file="quiz_results.txt")

# Run client
async def main():
    await client.start()
    print("Userbot is running...")
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
