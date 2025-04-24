from telethon import TelegramClient, events
from telethon.sessions import StringSession
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
    poll_info = []

    async for msg in client.iter_messages(entity, min_id=first_id, max_id=last_id):
        progress += 1
        if msg.media and hasattr(msg.media, 'poll'):
            poll = msg.media.poll
            question = poll.question
            answers = []
            correct_indices = []
            
            # Create simplified answer objects for easier inspection
            poll_struct = {
                'question': question,
                'answers': [],
                'correct_indices': []
            }
            
            # A simple debug log
            debug_log = f"POLL: {question}\n"
            
            # Process answers
            for i, ans in enumerate(poll.answers):
                answers.append(ans.text)
                poll_struct['answers'].append(ans.text)
                
                debug_log += f"  Answer {i}: {ans.text}\n"
                
                # Check for correct attribute (Quiz poll)
                if hasattr(ans, 'correct'):
                    debug_log += f"    Has 'correct' attribute: {ans.correct}\n"
                    if ans.correct:
                        correct_indices.append(i)
                        poll_struct['correct_indices'].append(i)
            
            # Most important - check for solution attribute
            solution = ""
            solution_index = -1
            
            # Check if poll has solutions
            if hasattr(poll, 'results') and hasattr(poll.results, 'solution'):
                solution = str(poll.results.solution)
                debug_log += f"  Found solution: {solution}\n"
                poll_struct['solution'] = solution
            
            # If we have a solution, try to match it with an answer
            if solution:
                for i, ans in enumerate(answers):
                    if solution.lower() in ans.lower() or ans.lower() in solution.lower():
                        solution_index = i
                        correct_indices.append(i)
                        poll_struct['correct_indices'].append(i)
                        debug_log += f"  Matched solution to answer {i}\n"
                        break
            
            # Add direct answer matching for quiz-style answers
            # Look for answers with indicators like (*), ✅, etc.
            for i, ans in enumerate(answers):
                ans_lower = ans.lower()
                has_indicator = any(marker in ans for marker in 
                                   ["(*)", "✓", "✅", "*", "correct", "right answer", "√"])
                
                if has_indicator and i not in correct_indices:
                    correct_indices.append(i)
                    poll_struct['correct_indices'].append(i)
                    debug_log += f"  Inferred correct answer {i} from markers in text\n"
            
            # Force correct answer extraction from poll.questions.correct_answers
            if hasattr(poll, 'questions') and hasattr(poll.questions, 'correct_answers'):
                for answer_idx in poll.questions.correct_answers:
                    if answer_idx not in correct_indices and 0 <= answer_idx < len(answers):
                        correct_indices.append(answer_idx)
                        poll_struct['correct_indices'].append(answer_idx)
                        debug_log += f"  Found correct answer {answer_idx} in poll.questions.correct_answers\n"
            
            # For quiz polls, check .quiz.correct_answers
            if hasattr(msg, 'quiz') and hasattr(msg.quiz, 'correct_answers'):
                for correct_answer in msg.quiz.correct_answers:
                    for i, ans in enumerate(answers):
                        if ans == correct_answer and i not in correct_indices:
                            correct_indices.append(i)
                            poll_struct['correct_indices'].append(i)
                            debug_log += f"  Found correct answer {i} in quiz.correct_answers\n"
            
            # Fallback: if there's exactly one answer starting with (*) or similar, mark that
            star_answers = [i for i, ans in enumerate(answers) if ans.startswith("(*)")]
            if len(star_answers) == 1 and not correct_indices:
                i = star_answers[0]
                correct_indices.append(i)
                poll_struct['correct_indices'].append(i)
                debug_log += f"  Marked answer {i} as correct because it starts with (*)\n"
            
            # Last resort: Heuristic for detecting correct answers
            # In many formats, the correct answer often comes first
            if not correct_indices and len(answers) > 0:
                # Only guess in specific formats like numbered lists
                has_numbered_format = all(ans.startswith(str(j+1)+".") for j, ans in enumerate(answers))
                if has_numbered_format:
                    correct_indices.append(0)  # Mark first answer as correct
                    poll_struct['correct_indices'].append(0)
                    debug_log += "  No correct answer detected, marking first answer based on numbered format\n"
            
            # Get answers after all detection methods
            debug_log += f"  Final correct indices: {correct_indices}\n\n"
            
            # Save debug log
            with open("poll_debug.txt", "a", encoding="utf-8") as f:
                f.write(debug_log)
            
            # Save poll data
            poll_info.append(poll_struct)
            valid_polls.append((question, answers, correct_indices))

        if progress % 10 == 0:
            await event.reply(f"Progress: {progress}/{total_messages} messages scanned...")

    # Save poll info for debugging
    try:
        with open("polls_extracted.txt", "w", encoding="utf-8") as f:
            for p in poll_info:
                f.write(f"Question: {p['question']}\n")
                for i, ans in enumerate(p['answers']):
                    marker = "✅" if i in p['correct_indices'] else ""
                    f.write(f"  {i}. {ans} {marker}\n")
                f.write("\n")
        await event.reply("Debug info saved to polls_extracted.txt")
    except Exception as e:
        await event.reply(f"Error saving debug info: {e}")

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
    if correct_indices:
        await event.reply("Correct answers have been marked with ✅")
    else:
        await event.reply("Warning: No correct answers were detected in any polls.")

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
