"""WSGI application wrapper for the Telegram bot."""

import asyncio
import threading
from flask import Flask

from run_bot import run_scheduled

app = Flask(__name__)

def run_bot_thread():
    """Run the bot in a separate thread."""
    asyncio.run(run_scheduled())

# Start the bot in a separate thread
bot_thread = threading.Thread(target=run_bot_thread, daemon=True)
bot_thread.start()

@app.route('/')
def health_check():
    """Health check endpoint."""
    return 'Bot is running', 200

# WSGI application
application = app
