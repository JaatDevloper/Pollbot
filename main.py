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

# Initialize the TelegramClient using StringSession
client = TelegramClient(StringSession(string_session), api_id, api_hash)

# Initialize Flask to serve the health check endpoint
app = Flask(__name__)

@app.route("/health")
def health_check():
    return "OK", 200  # Simple health check response

# Global variables to store the URLs
first_poll_url = None
last_poll_url = None

# Handle the /extract command to start the poll extraction process
@client.on(events.NewMessage(pattern='/extract'))
async def start_extract(event):
    await event.reply("Please send me the Link to the first message (containing the first poll or any message before the polls)\nExample: https://t.me/channel/123")

# Handle the first URL
@client.on(events.NewMessage)
async def handle_first_url(event):
    global first_poll_url
    if first_poll_url is None:  # Only process the first URL once
        first_poll_url = event.text
        await event.reply("Got it! Now, please send me the link to the last message after the poll.")

# Handle the last URL
@client.on(events.NewMessage)
async def handle_last_url(event):
    global last_poll_url
    if first_poll_url and last_poll_url is None:  # Only process the last URL once
        last_poll_url = event.text
        await event.reply("Processing, please wait...")

        # Get the message IDs from the URLs (format: https://t.me/channel/message_id)
        first_message_id = int(first_poll_url.split('/')[-1])
        last_message_id = int(last_poll_url.split('/')[-1])

        # Fetch messages between the first and last IDs
        await extract_polls(first_message_id, last_message_id, event)

# Function to extract polls from messages
async def extract_polls(first_message_id, last_message_id, event):
    global first_poll_url, last_poll_url

    # Replace with your actual channel name or ID
    channel = await client.get_entity('your_channel_name_or_id')

    valid_polls = []
    progress = 0
    total_messages = last_message_id - first_message_id + 1

    # Loop through messages between the first and last message IDs
    async for message in client.iter_messages(channel, min_id=first_message_id, max_id=last_message_id):
        if message.poll:
            question = message.poll.question
            answers = [answer.text for answer in message.poll.answers]
            correct_answer = None

            # Identify the correct answer (e.g., check for an option marked as correct)
            for answer in message.poll.answers:
                if answer.is_correct:
                    correct_answer = answer.text
                    break

            # Add to valid polls list
            valid_polls.append((question, answers, correct_answer))

        progress += 1
        # Show progress
        await event.reply(f"Processing message: {progress}/{total_messages} ({(progress / total_messages) * 100:.1f}%)\nFound {len(valid_polls)} valid polls so far...")

    # Generate and send the .txt file with the results
    await generate_txt(valid_polls, event)

    # Reset URLs after the process
    first_poll_url = None
    last_poll_url = None

# Function to generate the .txt file with poll results
async def generate_txt(valid_polls, event):
    # Create the content for the .txt file
    text = ""
    for idx, (question, answers, correct_answer) in enumerate(valid_polls, 1):
        text += f"Q{idx}. {question}\n"
        for ans in answers:
            if ans == correct_answer:
                text += f"  ✅ {ans}\n"
            else:
                text += f"  ⬜ {ans}\n"
        text += "\n"

    # Save the results to a text file
    with open('quiz_results.txt', 'w', encoding='utf-8') as file:
        file.write(text)

    # Send the .txt file back to the user
    await event.reply(file=open('quiz_results.txt', 'rb'))

# Example command to confirm the bot is working
@client.on(events.NewMessage(pattern='/start'))
async def start(event):
    await event.reply("Userbot is active and working!")

# Running the client
async def main():
    # Start Flask in a separate thread to handle health checks
    from threading import Thread
    def run_flask():
        app.run(host="0.0.0.0", port=8080)

    flask_thread = Thread(target=run_flask)
    flask_thread.start()

    # Start the Telegram client
    await client.start()
    print("Client started successfully.")
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
