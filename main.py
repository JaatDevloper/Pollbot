import asyncio
import logging
import re
import json
from telethon import events
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import MessageMediaPoll
from telethon.tl.custom import Message

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Your credentials
api_id = 27488818
api_hash = '321fb972c3c3aee2dbdca1deeab39050'
string_session = '1BVtsOKEBu1n1e48GEEoqRlPzUUy1CloJ4rwmCDOAfcyXvjPKoxgDTLfoypsaQxMKqqcXRTZ7Z7gACuECJuX8GnpAtiVMNTRQKMphB7j-Un7nILgKZ_EfYd1uwBMXN3WU1rPHsenQRxuhWsXcIx9T7hU2hF_za2l2saJhsj5N5WuvfazFBdX01sXV3y6PbCCYW4eSxBFhrcqR7cHoAoJWNlphdk7jygTHlltDbAt2aJzBKn_JBJgStE08OG5sFjkYQvnrMEJV7dpFjwPzW3akWHWGdFqdwNqDEz4yn6gnWP3wDZRsWOMy8r9FCmFpcx5V28g3d8L07XdkWtSHgDYoN9aK9kU1a9A='

client = TelegramClient(StringSession(string_session), api_id, api_hash)

quizzes = {}

# Command handler
@client.on(events.NewMessage(pattern=r'^/quiz (https://t\.me/.+?) (https://t\.me/.+?)$'))
async def quiz_handler(event):
    first_url, last_url = event.pattern_match.group(1), event.pattern_match.group(2)
    await event.reply("Extracting quiz questions, please wait...")

    try:
        quiz_id = await extract_and_save_quiz(first_url, last_url)
        await event.reply(f"Quiz saved with ID: {quiz_id}. Use /play {quiz_id} to replay it.")
    except Exception as e:
        await event.reply(f"Failed to extract quiz: {e}")

@client.on(events.NewMessage(pattern=r'^/play (\d+)$'))
async def play_handler(event):
    quiz_id = event.pattern_match.group(1)
    if quiz_id not in quizzes:
        await event.reply("Invalid quiz ID.")
        return

    for q in quizzes[quiz_id]:
        await client.send_message(
            entity=event.chat_id,
            message="Quiz:",
            buttons=None,
            file=None,
            parse_mode='html'
        )
        await client.send_message(
            entity=event.chat_id,
            message=f"🧠 {q['question']}\nOptions:\n" +
                    "\n".join([f"{idx+1}. {opt}" + (" ✅" if idx == q['correct_option_id'] else "")
                               for idx, opt in enumerate(q['options'])])
        )

async def extract_and_save_quiz(first_url, last_url):
    match1 = re.search(r'/(\d+)$', first_url)
    match2 = re.search(r'/(\d+)$', last_url)
    if not match1 or not match2:
        raise ValueError("Invalid URLs.")

    first_id = int(match1.group(1))
    last_id = int(match2.group(1))
    if first_id > last_id:
        first_id, last_id = last_id, first_id

    entity = await client.get_entity('quizbot')
    messages = await client.get_messages(entity, ids=range(first_id, last_id + 1))

    quiz = []
    for msg in messages:
        if isinstance(msg, Message) and isinstance(msg.media, MessageMediaPoll):
            poll = msg.media.poll
            correct_id = next((i for i, opt in enumerate(poll.options) if getattr(opt, 'correct', False)), None)
            quiz.append({
                "question": poll.question,
                "options": [opt.text for opt in poll.options],
                "correct_option_id": correct_id
            })

    quiz_id = str(len(quizzes) + 1)
    quizzes[quiz_id] = quiz
    return quiz_id

async def main():
    await client.start()
    print("Userbot is running...")
    await client.run_until_disconnected()

if __name__ == '__main__':
    from telethon import events
    asyncio.run(main())
    
