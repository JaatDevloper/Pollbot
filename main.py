from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import PollAnswer
from telethon.tl.functions.messages import GetPollResultsRequest
import os
import asyncio
from flask import Flask

api_id = 27488818
api_hash = '321fb972c3c3aee2dbdca1deeab39050'

if os.path.exists("string_session.txt"):
    with open("string_session.txt", "r") as f:
        string_session = f.read().strip()
else:
    raise ValueError("string_session.txt not found or empty!")

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
    user_states[user_id] = {"step": "awaiting_first"}
    await event.reply("Please send me the Link to the first message (containing the first poll or any message before the polls)\nExample: https://t.me/channel/123")

@client.on(events.NewMessage)
async def handle_url(event):
    user_id = event.sender_id
    if user_id not in user_states:
        return

    state = user_states[user_id]
    if state["step"] == "awaiting_first" and "https://t.me/" in event.raw_text:
        user_states[user_id]["first_url"] = event.raw_text.strip()
        user_states[user_id]["step"] = "awaiting_last"
        await event.reply("Got it! Now, please send me the link to the last message after the poll.")
    elif state["step"] == "awaiting_last" and "https://t.me/" in event.raw_text:
        user_states[user_id]["last_url"] = event.raw_text.strip()
        await event.reply("Processing, please wait...")

        try:
            first_url = user_states[user_id]["first_url"]
            last_url = user_states[user_id]["last_url"]

            parts1 = first_url.split('/')
            parts2 = last_url.split('/')
            if len(parts1) < 5 or len(parts2) < 5:
                raise ValueError("Invalid URLs")

            chat = parts1[3]
            first_id = int(parts1[4])
            last_id = int(parts2[4])

            await extract_polls(chat, first_id, last_id, event)
        except Exception as e:
            await event.reply(f"Error while extracting polls: {e}")

        del user_states[user_id]

async def extract_polls(chat, first_id, last_id, event):
    entity = await client.get_entity(chat)
    valid_polls = []
    total_messages = last_id - first_id + 1
    progress = 0
    debug_info = []

    await event.reply("Extracting quiz polls...")
    
    async for msg in client.iter_messages(entity, min_id=first_id, max_id=last_id):
        progress += 1
        
        if msg.media and hasattr(msg.media, 'poll'):
            poll = msg.media.poll
            question = poll.question
            answers = []
            correct_indices = []
            
            # Get all answers
            for i, ans in enumerate(poll.answers):
                answers.append(ans.text)
            
            # First check - is this a quiz poll?
            is_quiz = False
            if hasattr(poll, 'quiz') and poll.quiz:
                is_quiz = True
                # For quiz polls, we need to get the correct answer
                # This requires additional API call
                debug_info.append(f"Found quiz poll: {question}")
                
                try:
                    # Try to vote in the poll to get the correct answer
                    # We'll vote for the first option
                    if len(poll.answers) > 0:
                        poll_answer = PollAnswer(
                            poll.poll.id,
                            b'0'  # Vote for first option
                        )
                        
                        # Get poll results to find correct answer
                        results = await client(GetPollResultsRequest(
                            peer=entity,
                            msg_id=msg.id
                        ))
                        
                        # Extract correct option from results
                        if hasattr(results, 'poll') and hasattr(results.poll, 'answers'):
                            for i, ans_result in enumerate(results.poll.answers):
                                if hasattr(ans_result, 'correct') and ans_result.correct:
                                    correct_indices.append(i)
                                    debug_info.append(f"  - Correct answer: {answers[i]}")
                except Exception as e:
                    debug_info.append(f"  - Error getting quiz results: {str(e)}")
            
            # Use additional methods to detect correct answers
            if not correct_indices:
                # Check if quiz attribute exists on the poll object
                if hasattr(poll, 'quiz') and poll.quiz:
                    # Check if solution is available
                    if hasattr(poll.quiz, 'solution'):
                        debug_info.append(f"  - Quiz has solution: {poll.quiz.solution}")
                    
                    # Check for correct_answer or correct_answers
                    if hasattr(poll.quiz, 'correct_answer'):
                        idx = poll.quiz.correct_answer
                        if 0 <= idx < len(answers):
                            correct_indices.append(idx)
                            debug_info.append(f"  - Found correct_answer: {idx}")
                    
                    if hasattr(poll.quiz, 'correct_answers'):
                        for idx in poll.quiz.correct_answers:
                            if 0 <= idx < len(answers):
                                if idx not in correct_indices:
                                    correct_indices.append(idx)
                                debug_info.append(f"  - Found in correct_answers: {idx}")
            
            # Special handling for Telegram Bot Quiz polls
            if "Anonymous Quiz" in str(msg.message) or "Anonymous Poll" in str(msg.message):
                debug_info.append("  - This is a Telegram Bot Quiz")
                
                # Try to find corresponding results messages
                # Look at 5 messages after this one for possible answer information
                after_messages = []
                async for after_msg in client.iter_messages(entity, min_id=msg.id, limit=5):
                    if after_msg.id != msg.id:
                        after_messages.append(after_msg)
                
                # Check these messages for quiz answer information
                for after_msg in after_messages:
                    if after_msg.message and "correct answer" in after_msg.message.lower():
                        debug_info.append(f"  - Found answer info: {after_msg.message}")
                        
                        # Try to extract which answer is correct from the message
                        msg_text = after_msg.message.lower()
                        for i, ans in enumerate(answers):
                            if ans.lower() in msg_text and "correct" in msg_text:
                                correct_indices.append(i)
                                debug_info.append(f"  - Matched answer {i} as correct")
            
            # Last resort for quiz polls - try to access poll.results directly
            if not correct_indices and hasattr(poll, 'results'):
                if hasattr(poll.results, 'correct_option'):
                    idx = poll.results.correct_option
                    if 0 <= idx < len(answers):
                        correct_indices.append(idx)
                        debug_info.append(f"  - Found correct_option in results: {idx}")
                
                if hasattr(poll.results, 'correct_options'):
                    for idx in poll.results.correct_options:
                        if 0 <= idx < len(answers) and idx not in correct_indices:
                            correct_indices.append(idx)
                            debug_info.append(f"  - Found in correct_options: {idx}")
            
            # Save poll with any correct answers we've found
            valid_polls.append((question, answers, correct_indices))

        if progress % 10 == 0:
            await event.reply(f"Progress: {progress}/{total_messages} messages scanned...")

    # Save debug info
    with open("quiz_debug.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(debug_info))
    
    # Check if we need to try one more approach
    polls_with_correct_answers = sum(1 for _, _, c in valid_polls if c)
    if polls_with_correct_answers == 0 and valid_polls:
        await event.reply("No correct answers detected in quiz format. Trying message-based detection...")
        
        # Try to use message context to find correct answers
        updated_polls = await analyze_message_context(entity, valid_polls, first_id, last_id)
        await generate_txt(updated_polls, event)
    else:
        await generate_txt(valid_polls, event)

async def analyze_message_context(entity, polls, first_id, last_id):
    # Get all messages in range
    all_messages = []
    async for msg in client.iter_messages(entity, min_id=first_id, max_id=last_id):
        if hasattr(msg, 'message') and msg.message:
            all_messages.append((msg.id, msg.message))
    
    # Sort by message ID
    all_messages.sort(key=lambda x: x[0])
    
    # For each poll, try to find answer in nearby messages
    updated_polls = []
    for i, (question, answers, _) in enumerate(polls):
        correct_indices = []
        
        # Generate letter-based versions of answers (a, b, c, d)
        letter_answers = {}
        for j, ans in enumerate(answers):
            letter = chr(97 + j).upper()  # A, B, C, D
            letter_answers[letter] = j
        
        # Search for answer patterns in messages near this poll
        # Find message index that might contain this poll
        poll_msg_idx = -1
        for j, (_, msg_text) in enumerate(all_messages):
            if question in msg_text:
                poll_msg_idx = j
                break
        
        if poll_msg_idx >= 0:
            # Look at 5 messages after this one
            for j in range(poll_msg_idx+1, min(poll_msg_idx+6, len(all_messages))):
                msg_text = all_messages[j][1].lower()
                
                # Check for correct answer patterns
                if "correct" in msg_text or "answer" in msg_text or "right" in msg_text:
                    # Try to find letter pattern
                    for letter in "ABCD":
                        if f"answer {letter}" in msg_text or f"correct {letter}" in msg_text or f"{letter} is correct" in msg_text:
                            if letter in letter_answers:
                                correct_indices.append(letter_answers[letter])
                
                # Also check for answer text directly
                for j, ans in enumerate(answers):
                    if ans.lower() in msg_text and ("correct" in msg_text or "right" in msg_text):
                        correct_indices.append(j)
        
        updated_polls.append((question, answers, correct_indices))
    
    return updated_polls

async def generate_txt(polls, event):
    output = ""
    correct_count = 0
    
    for idx, (question, answers, correct_indices) in enumerate(polls, 1):
        output += f"{question}\n"
        
        for i, ans in enumerate(answers):
            # Check if the answer already starts with (a), (b), etc.
            if ans.strip().startswith('(') and len(ans) > 3 and ans[1].isalpha() and ans[2] == ')':
                # It already has a label, just add the check mark if needed
                mark = " ✅" if i in correct_indices else ""
                output += f"{ans}{mark}\n"
            else:
                # Need to add the label
                letter = chr(97 + i)  # Convert 0, 1, 2... to a, b, c...
                mark = " ✅" if i in correct_indices else ""
                output += f"({letter}) {ans}{mark}\n"
        
        output += "\n"
        if correct_indices:
            correct_count += 1

    with open("quiz_results.txt", "w", encoding="utf-8") as f:
        f.write(output)

    await event.reply("Here is your extracted quiz:", file="quiz_results.txt")
    
    if correct_count > 0:
        await event.reply(f"Successfully detected and marked correct answers in {correct_count} polls.")
    else:
        await event.reply("Warning: No correct answers were detected in any polls. The channel may not be using quiz polls with embedded correct answers.")

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
