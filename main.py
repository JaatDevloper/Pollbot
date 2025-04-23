from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.sync import TelegramClient
from telethon.tl.types import Message, MessageMediaPoll
from telethon.tl.types import InputPeerChannel
import asyncio
import os

# Define your API credentials and string session
api_id = '28624690'  # Replace with your API ID
api_hash = '67e6593b5a9b5ab20b11ccef6700af5b'  # Replace with your API Hash
phone = '+919351504990'  # Replace with your phone number

# You can use your string session here or load it from an environment variable
string_session = os.getenv('1BVtsOKEBu0M0NiU2jKhDl1XFCRgj6MxCBfeYIW8VDHP-LX_BR-bTDOWByKUfiiw9Y-EjjhXCaZ0zcZjRxlirhR6nPKxpC1st_PW4kAZbMp6TLvgUXMOkVSd5rzz-vWxOZcd6WsdLxWjs9-lhi-xfWgL23p2iLGXyZi-BW17o3X38C3K-sHavdR1ggmV598L6x6bXnclPcQNmCDIBQF7KakTF0-k-Em33zsy4N-rUhb2egQO4k98F6DYTnnHQVwgJnlpLPFJdZ8g9-LDmqgUEmRsoXoUVx_Hf0lB7ykIpzlXUOeabteip8OsiSaFPIPj2f90wVCIxnfmXm1LMF70N9Z3HGVUa2g0=')  # Set this environment variable for production
# Or load it from a file if you're saving it
# with open('string_session.txt', 'r') as f:
#     string_session = f.read().strip()

if not string_session:
    raise ValueError("String session is required. Please generate it.")

# Initialize the Telegram Client using StringSession
client = TelegramClient(StringSession(string_session), api_id, api_hash)

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

# Running the client
async def main():
    await client.start()
    print("Userbot is running...")

if __name__ == '__main__':
    client.loop.run_until_complete(main())
