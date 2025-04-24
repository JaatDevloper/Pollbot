import os
import json
from flask import Flask, jsonify, request
from telethon import TelegramClient
from telethon.sessions import StringSession
import asyncio
from threading import Thread

# Flask App Setup
app = Flask(__name__)

# Telethon Client Setup with Active String Session
api_id = '27488818'  # Replace with your API ID
api_hash = '321fb972c3c3aee2dbdca1deeab39050'  # Replace with your API hash
session_string = '1BVtsOKEBu1n1e48GEEoqRlPzUUy1CloJ4rwmCDOAfcyXvjPKoxgDTLfoypsaQxMKqqcXRTZ7Z7gACuECJuX8GnpAtiVMNTRQKMphB7j-Un7nILgKZ_EfYd1uwBMXN3WU1rPHsenQRxuhWsXcIx9T7hU2hF_za2l2saJhsj5N5WuvfazFBdX01sXV3y6PbCCYW4eSxBFhrcqR7cHoAoJWNlphdk7jygTHlltDbAt2aJzBKn_JBJgStE08OG5sFjkYQvnrMEJV7dpFjwPzW3akWHWGdFqdwNqDEz4yn6gnWP3wDZRsWOMy8r9FCmFpcx5V28g3d8L07XdkWtSHgDYoN9aK9kU1a9A='  # Replace with your active string session

# Initialize the Telegram client with the existing string session
client = TelegramClient(StringSession(session_string), api_id, api_hash)

# Path to save the extracted polls with IDs
saved_polls_path = 'saved_polls.json'

# Helper function to load saved polls from file
def load_saved_polls():
    if os.path.exists(saved_polls_path):
        with open(saved_polls_path, 'r') as f:
            return json.load(f)
    return {}

# Helper function to save extracted polls to file
def save_poll_data(polls_data):
    with open(saved_polls_path, 'w') as f:
        json.dump(polls_data, f)

# Health check endpoint to ensure the bot is running
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify(status="OK", message="Userbot is healthy"), 200

# Command to extract polls between two links
@app.route('/extract_polls', methods=['GET'])
def extract_polls():
    first_poll_link = request.args.get('first_poll_link')
    last_poll_link = request.args.get('last_poll_link')

    # Ensure the user is logged in before proceeding
    if not client.is_user_authorized():
        return jsonify(status="Error", message="User not authorized")

    # Your logic to extract polls between first_poll_link and last_poll_link here
    polls_data = []  # Assuming you have a function that fetches polls based on the links

    # After extracting polls, save them with unique IDs
    saved_polls = load_saved_polls()
    new_poll_id = len(saved_polls) + 1
    saved_polls[new_poll_id] = polls_data  # Store the extracted polls with an ID

    # Save the polls to file
    save_poll_data(saved_polls)

    return jsonify(status="OK", message="Polls extracted and saved successfully")

# Command to play a quiz using saved polls by ID
@app.route('/play_quiz/<quiz_id>', methods=['GET'])
def play_quiz(quiz_id):
    saved_polls = load_saved_polls()

    # Retrieve the quiz by ID
    if quiz_id in saved_polls:
        quiz_data = saved_polls[quiz_id]
        # Logic to start the quiz (send questions one by one)
        return jsonify(status="OK", message="Quiz started", quiz_data=quiz_data)
    else:
        return jsonify(status="Error", message="Quiz ID not found")

# Main entry point
async def main():
    await client.start()
    print("Userbot is running...")

    # Run any additional logic after starting the client (like sending messages or handling updates)

# Start the Flask server and Telethon client together
def start_telethon_and_flask():
    # Start the Telethon client in the main event loop
    asyncio.run(main())

    # Start Flask in a separate thread
    app.run(host='0.0.0.0', port=5000)

# Start both Flask and Telethon in separate threads
if __name__ == '__main__':
    # Run Telethon and Flask together in a separate thread
    flask_thread = Thread(target=start_telethon_and_flask)
    flask_thread.start()
    
