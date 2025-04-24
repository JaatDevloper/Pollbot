from telethon import TelegramClient
from flask import Flask, jsonify, request
import json
import os

# Flask App Setup
app = Flask(__name__)

# Telethon Client Setup with Active String Session
api_id = 'your_api_id'  # Replace with your API ID
api_hash = 'your_api_hash'  # Replace with your API hash
session_string = 'your_active_string_session'  # Replace with your active string session

# Initialize the Telegram client with the existing string session
client = TelegramClient('userbot', api_id, api_hash)

# Set the string session for client
client.session.set_string(session_string)

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
    # Example: Extract poll data (pseudo code)
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
if __name__ == '__main__':
    # Start the Telethon client
    client.start()

    # Start the Flask server in the background
    app.run(host='0.0.0.0', port=5000)
    
