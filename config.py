"""
Central place to load configuration / secrets.
Keeps the rest of the codebase from touching os.environ directly.
"""
import os
from dotenv import load_dotenv

load_dotenv()  # reads the .env file into environment variables

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "paste_your_token_here":
    raise ValueError(
        "TELEGRAM_BOT_TOKEN is not set. "
        "Open the .env file and paste your real token from @BotFather."
    )

if not OPENAI_API_KEY or OPENAI_API_KEY == "paste_your_openai_key_here":
    raise ValueError(
        "OPENAI_API_KEY is not set. "
        "Open the .env file and paste your real OpenAI API key."
    )