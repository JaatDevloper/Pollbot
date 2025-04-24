from telethon import TelegramClient, events
from telethon.sessions import StringSession
import os
import asyncio
from flask import Flask
import json

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

# Helper function to safely get attributes
def safe_get_attr(obj, attr, default=None):
    if hasattr(obj, attr):
        return getattr(obj, attr)
    return default

# Helper function to safely convert to string for debug info
def safe_str(obj):
    if obj is None:
        return "None"
    try:
        return str(obj)
    except:
        return "Unconvertible"

async def extract_polls(chat, first_id, last_id, event):
    entity = await client.get_entity(chat)
    valid_polls = []
    total_messages = last_id - first_id + 1
    progress = 0
    debug_info = []

    async for msg in client.iter_messages(entity, min_id=first_id, max_id=last_id):
        progress += 1
        if msg.media and hasattr(msg.media, 'poll'):
            poll = msg.media.poll
            question = poll.question
            answers = []
            correct_indices = []
            
            # Debug information
            poll_debug = {
                "question": question,
                "poll_type": safe_get_attr(poll, 'poll_type', 'unknown'),
                "quiz": safe_get_attr(poll, 'quiz', False),
                "answers": []
            }
            
            # Get all possible answer data
            for i, ans in enumerate(poll.answers):
                answers.append(ans.text)
                poll_debug["answers"].append({
                    "text": ans.text,
                    "has_correct_attr": hasattr(ans, 'correct'),
                    "correct_value": safe_get_attr(ans, 'correct', None),
                    "option": safe_get_attr(ans, 'option', None)
                })
                
                # Try different methods to detect correct answers
                is_correct = False
                
                # Method 1: Direct 'correct' attribute
                if hasattr(ans, 'correct') and ans.correct:
                    is_correct = True
                    poll_debug["answers"][i]["marked_by"] = "direct_correct_attr"
                
                # Method 2: getattr with default
                elif getattr(ans, 'correct', False):
                    is_correct = True
                    poll_debug["answers"][i]["marked_by"] = "getattr_correct"
                
                if is_correct:
                    correct_indices.append(i)
            
            # Debug poll results if available
            if hasattr(poll, 'results'):
                poll_debug["has_results"] = True
                poll_debug["results"] = {
                    "has_correct_options": hasattr(poll.results, 'correct_options'),
                    "correct_options": safe_str(safe_get_attr(poll.results, 'correct_options')),
                    "has_correct_option": hasattr(poll.results, 'correct_option'),
                    "correct_option": safe_str(safe_get_attr(poll.results, 'correct_option')),
                    "has_solution": hasattr(poll.results, 'solution'),
                    "solution": safe_str(safe_get_attr(poll.results, 'solution'))
                }
                
                # Method 3: Check poll.results.correct_options
                if hasattr(poll.results, 'correct_options') and poll.results.correct_options:
                    for i in poll.results.correct_options:
                        if isinstance(i, int) and 0 <= i < len(answers) and i not in correct_indices:
                            correct_indices.append(i)
                            poll_debug["answers"][i]["marked_by"] = "correct_options"
                
                # Method 4: Check poll.results.correct_option
                if hasattr(poll.results, 'correct_option') and poll.results.correct_option is not None:
                    i = poll.results.correct_option
                    if isinstance(i, int) and 0 <= i < len(answers) and i not in correct_indices:
                        correct_indices.append(i)
                        poll_debug["answers"][i]["marked_by"] = "correct_option"
                
                # Method 5: Check for solution in poll results
                if hasattr(poll.results, 'solution') and poll.results.solution:
                    poll_debug["found_solution"] = True
                    for i, ans in enumerate(answers):
                        # Check if solution contains or matches the answer
                        if (poll.results.solution in ans or ans in poll.results.solution) and i not in correct_indices:
                            correct_indices.append(i)
                            poll_debug["answers"][i]["marked_by"] = "solution_match"
            
            # Method 6: Check if this is a quiz and has correct_answers
            if hasattr(msg, 'quiz') and hasattr(msg.quiz, 'correct_answers'):
                poll_debug["has_quiz_correct_answers"] = True
                poll_debug["quiz_correct_answers"] = safe_str(msg.quiz.correct_answers)
                
                for correct_answer in msg.quiz.correct_answers:
                    for i, ans in enumerate(answers):
                        if ans == correct_answer and i not in correct_indices:
                            correct_indices.append(i)
                            poll_debug["answers"][i]["marked_by"] = "quiz_correct_answers"
            
            # Additional check: If we have a quiz but no correct answers detected yet,
            # try to infer from answer options if they contain indicators like "*", "✓", "✅"
            if safe_get_attr(poll, 'quiz', False) and not correct_indices:
                for i, ans in enumerate(answers):
                    # Check for common correct answer indicators
                    if any(marker in ans for marker in ["*", "✓", "✅", "√", "correct", "right"]):
                        correct_indices.append(i)
                        poll_debug["answers"][i]["marked_by"] = "text_marker_inference"
            
            # Save which answers were determined to be correct
            poll_debug["correct_indices"] = correct_indices
            
            # Save debug info for this poll
            debug_info.append(poll_debug)
            
            valid_polls.append((question, answers, correct_indices))

        if progress % 10 == 0:
            await event.reply(f"Progress: {progress}/{total_messages} messages scanned...")

    # Save debug info to a file
    with open("poll_debug.json", "w", encoding="utf-8") as f:
        json.dump(debug_info, f, indent=2, ensure_ascii=False)
    
    await event.reply("Debug information saved to poll_debug.json")
    
    await generate_txt(valid_polls, event)

async def generate_txt(polls, event):
    output = ""
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

    with open("quiz_results.txt", "w", encoding="utf-8") as f:
        f.write(output)

    await event.reply("Here is your extracted quiz:", file="quiz_results.txt")

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
