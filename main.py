from telethon import TelegramClient, events
from telethon.sessions import StringSession
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
    quiz_count = 0
    
    # For logging poll details
    with open("poll_debug.txt", "w", encoding="utf-8") as f:
        f.write("Poll debug information:\n\n")

    async for msg in client.iter_messages(entity, min_id=first_id, max_id=last_id):
        progress += 1
        if msg.media and hasattr(msg.media, 'poll'):
            poll = msg.media.poll
            question = poll.question
            answers = [ans.text for ans in poll.answers]
            correct_indices = []
            quiz_detected = False
            
            # Debug info
            poll_info = f"Poll: {question}\n"
            poll_info += f"Poll type: {getattr(poll, 'poll_type', 'unknown')}\n"
            poll_info += f"Is quiz: {hasattr(poll, 'quiz')}\n"
            
            # Look for quiz information - multiple approaches
            # Method 1: Check if it's a quiz type poll
            if hasattr(poll, 'quiz') and poll.quiz:
                quiz_detected = True
                quiz_count += 1
                poll_info += "Quiz poll detected!\n"
                
                # Method 1.1: Direct correct_answer_id attribute
                if hasattr(poll.quiz, 'correct_answer_id'):
                    correct_idx = poll.quiz.correct_answer_id
                    if 0 <= correct_idx < len(answers):
                        correct_indices.append(correct_idx)
                        poll_info += f"Found correct_answer_id: {correct_idx}\n"
                
                # Method 1.2: correct_answers list
                elif hasattr(poll.quiz, 'correct_answers'):
                    for idx in poll.quiz.correct_answers:
                        if 0 <= idx < len(answers) and idx not in correct_indices:
                            correct_indices.append(idx)
                            poll_info += f"Found in correct_answers: {idx}\n"
                
                # Method 1.3: Try to access poll results and find solutions
                try:
                    if hasattr(poll, 'results'):
                        # Check for solution
                        if hasattr(poll.results, 'solution'):
                            poll_info += f"Found solution: {poll.results.solution}\n"
                            
                            # Try to match solution with an answer
                            solution = str(poll.results.solution).lower()
                            for i, ans in enumerate(answers):
                                if solution in ans.lower() or ans.lower() in solution:
                                    if i not in correct_indices:
                                        correct_indices.append(i)
                                        poll_info += f"Matched solution to answer {i}\n"
                        
                        # Check for correct_option
                        if hasattr(poll.results, 'correct_option'):
                            correct_idx = poll.results.correct_option
                            if 0 <= correct_idx < len(answers) and correct_idx not in correct_indices:
                                correct_indices.append(correct_idx)
                                poll_info += f"Found correct_option: {correct_idx}\n"
                        
                        # Check for correct_options list
                        if hasattr(poll.results, 'correct_options'):
                            for idx in poll.results.correct_options:
                                if 0 <= idx < len(answers) and idx not in correct_indices:
                                    correct_indices.append(idx)
                                    poll_info += f"Found in correct_options: {idx}\n"
                except Exception as e:
                    poll_info += f"Error accessing poll results: {str(e)}\n"
                
                # Method 1.4: Try to get poll results via API call
                if not correct_indices:
                    try:
                        # This is the method your friend's bot might be using!
                        results = await client(GetPollResultsRequest(
                            peer=entity,
                            msg_id=msg.id
                        ))
                        
                        poll_info += "Called GetPollResultsRequest API\n"
                        
                        if hasattr(results, 'poll'):
                            result_poll = results.poll
                            
                            # Check for correct_option in results
                            if hasattr(result_poll, 'correct_option'):
                                correct_idx = result_poll.correct_option
                                if 0 <= correct_idx < len(answers) and correct_idx not in correct_indices:
                                    correct_indices.append(correct_idx)
                                    poll_info += f"API returned correct_option: {correct_idx}\n"
                            
                            # Check each answer for 'correct' flag
                            for i, ans in enumerate(result_poll.answers):
                                if hasattr(ans, 'correct') and ans.correct:
                                    if i not in correct_indices:
                                        correct_indices.append(i)
                                        poll_info += f"API result marked answer {i} as correct\n"
                    except Exception as e:
                        poll_info += f"Error with GetPollResultsRequest: {str(e)}\n"
            
            # Method 2: Look for "correct" attribute on individual answers
            if not correct_indices:
                for i, ans in enumerate(poll.answers):
                    if hasattr(ans, 'correct') and ans.correct:
                        correct_indices.append(i)
                        poll_info += f"Answer {i} has correct=True attribute\n"
            
            # Method 3: Check if answers themselves contain indicators
            if not correct_indices:
                for i, ans in enumerate(answers):
                    ans_lower = ans.lower()
                    if any(marker in ans for marker in ["✓", "✅", "*", "(*)"]):
                        correct_indices.append(i)
                        poll_info += f"Found marker in answer {i}: {ans}\n"
            
            # Method 4: If "Anonymous Quiz" is mentioned, try to find marked answer
            if "Anonymous Quiz" in str(msg.message) and not correct_indices:
                poll_info += "Anonymous Quiz type detected\n"
                # This is often a bot-created quiz, look for special patterns
                for i, ans in enumerate(answers):
                    if "✓" in ans or "✅" in ans or "*)" in ans:
                        correct_indices.append(i)
                        poll_info += f"Found marker in anonymous quiz answer {i}: {ans}\n"
            
            # Write debug info for this poll
            with open("poll_debug.txt", "a", encoding="utf-8") as f:
                f.write(poll_info + "\n" + "-"*50 + "\n\n")
            
            # Add to valid polls
            valid_polls.append((question, answers, correct_indices))

        if progress % 10 == 0:
            await event.reply(f"Progress: {progress}/{total_messages} messages scanned...")

    await event.reply(f"Found {len(valid_polls)} polls, including {quiz_count} quiz polls.")
    
    # Generate the output
    await generate_txt(valid_polls, event)

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
    await event.reply(f"Successfully detected correct answers in {correct_count} polls and marked them with ✅")
    
    # If no correct answers detected, provide a fallback version
    if correct_count == 0 and polls:
        # Create a version with first answers marked as correct
        with open("quiz_results_first_marked.txt", "w", encoding="utf-8") as f:
            output = ""
            for question, answers, _ in polls:
                output += f"{question}\n"
                
                for i, ans in enumerate(answers):
                    if ans.strip().startswith('(') and len(ans) > 3 and ans[1].isalpha() and ans[2] == ')':
                        mark = " ✅" if i == 0 else ""
                        output += f"{ans}{mark}\n"
                    else:
                        letter = chr(97 + i)
                        mark = " ✅" if i == 0 else ""
                        output += f"({letter}) {ans}{mark}\n"
                
                output += "\n"
            
            f.write(output)
        
        await event.reply("Since no correct answers were detected, I've created a fallback version with first answers marked:", file="quiz_results_first_marked.txt")

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
