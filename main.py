from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import InputPollAnswerVote
from telethon.tl.functions.messages import SendVoteRequest, GetPollResultsRequest
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
    
    # Load known correct answers from file if it exists
    correct_answers_data = {}
    if os.path.exists("correct_answers.txt"):
        try:
            with open("correct_answers.txt", "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip() and ":" in line:
                        parts = line.strip().split(":", 1)
                        if len(parts) == 2:
                            question = parts[0].strip()
                            answers = parts[1].strip().split(",")
                            correct_answers_data[question] = [int(a) for a in answers if a.isdigit()]
        except Exception as e:
            await event.reply(f"Warning: Failed to load correct answers data: {e}")
    
    # First pass - collect all messages
    all_messages = []
    async for msg in client.iter_messages(entity, min_id=first_id, max_id=last_id):
        all_messages.append(msg)
        progress += 1
        if progress % 20 == 0:
            await event.reply(f"Collecting messages: {progress}/{total_messages}...")
    
    # Sort by ID
    all_messages.sort(key=lambda msg: msg.id)
    
    # Process polls
    await event.reply("Processing polls...")
    for i, msg in enumerate(all_messages):
        if msg.media and hasattr(msg.media, 'poll'):
            poll = msg.media.poll
            question = poll.question
            answers = [ans.text for ans in poll.answers]
            correct_indices = []
            
            # Critical difference: Try to vote in the poll to get results
            # This is likely what your friend's bot is doing
            try:
                # The trick is to vote in the poll first
                # This gives your session access to the correct answer data
                if len(answers) > 0 and hasattr(poll, 'poll'):
                    poll_id = poll.poll.id
                    
                    # Try to vote for the first option - this is how we get access to results
                    vote_result = await client(SendVoteRequest(
                        peer=entity,
                        msg_id=msg.id,
                        options=[b'0']  # Vote for first option
                    ))
                    
                    # Now get poll results which will include the correct answer
                    results = await client(GetPollResultsRequest(
                        peer=entity,
                        msg_id=msg.id
                    ))
                    
                    # Process results to find correct answer
                    if hasattr(results, 'poll') and hasattr(results.poll, 'answers'):
                        for i, ans_result in enumerate(results.poll.answers):
                            if hasattr(ans_result, 'correct') and ans_result.correct:
                                correct_indices.append(i)
            except Exception as e:
                # Voting might fail if you already voted or don't have permission
                # Continue to other methods
                pass
            
            # If voting didn't work, try direct attribute access
            if not correct_indices and hasattr(poll, 'quiz') and poll.quiz:
                # Try directly accessing correct answer via various attributes
                if hasattr(poll.quiz, 'correct_answer_id'):
                    idx = poll.quiz.correct_answer_id
                    if 0 <= idx < len(answers):
                        correct_indices.append(idx)
                
                elif hasattr(poll.quiz, 'correct_answers'):
                    for idx in poll.quiz.correct_answers:
                        if 0 <= idx < len(answers) and idx not in correct_indices:
                            correct_indices.append(idx)
            
            # If still no correct answers, check for special markers in answer text
            if not correct_indices:
                for i, ans in enumerate(answers):
                    if any(marker in ans for marker in ["✓", "✅", "*", "(*)"]):
                        correct_indices.append(i)
            
            # If still no correct answers, check stored answers
            if not correct_indices and question in correct_answers_data:
                correct_indices = [idx for idx in correct_answers_data[question] if 0 <= idx < len(answers)]
            
            # If still nothing, try a neighboring message for answer
            if not correct_indices and i+1 < len(all_messages):
                next_msg = all_messages[i+1]
                if hasattr(next_msg, 'message') and next_msg.message:
                    msg_text = next_msg.message.lower()
                    if "correct" in msg_text or "answer" in msg_text:
                        # Try to extract answer from text
                        for letter in "abcd":
                            if f"answer {letter}" in msg_text or f"correct {letter}" in msg_text:
                                idx = ord(letter) - ord('a')
                                if 0 <= idx < len(answers):
                                    correct_indices.append(idx)
            
            valid_polls.append((question, answers, correct_indices))
            
            # Store this correct answer for future use
            if correct_indices:
                with open("correct_answers.txt", "a", encoding="utf-8") as f:
                    indices_str = ",".join(str(idx) for idx in correct_indices)
                    f.write(f"{question}: {indices_str}\n")

    # Generate output
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
    
    if correct_count > 0:
        await event.reply(f"Successfully detected correct answers in {correct_count} polls and marked them with ✅")
    else:
        # If no correct answers found at all, create a version with first answers marked
        output = ""
        for question, answers, _ in polls:
            output += f"{question}\n"
            
            for i, ans in enumerate(answers):
                # Format answer with the first one marked as correct
                if ans.strip().startswith('(') and len(ans) > 3 and ans[1].isalpha() and ans[2] == ')':
                    mark = " ✅" if i == 0 else ""
                    output += f"{ans}{mark}\n"
                else:
                    letter = chr(97 + i)
                    mark = " ✅" if i == 0 else ""
                    output += f"({letter}) {ans}{mark}\n"
            
            output += "\n"
        
        with open("quiz_results_first_marked.txt", "w", encoding="utf-8") as f:
            f.write(output)
        
        await event.reply("No correct answers detected. Here's a version with the first answer in each poll marked:", file="quiz_results_first_marked.txt")

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
