"""
Central place to load configuration / secrets.
Keeps the rest of the codebase from touching os.environ directly.
"""
import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "paste_your_token_here":
    raise ValueError("TELEGRAM_BOT_TOKEN is not set in .env")

if not OPENAI_API_KEY or OPENAI_API_KEY == "paste_your_openai_key_here":
    raise ValueError("OPENAI_API_KEY is not set in .env")

if not PINECONE_API_KEY:
    raise ValueError("PINECONE_API_KEY is not set in .env")

if not PINECONE_INDEX_NAME:
    raise ValueError("PINECONE_INDEX_NAME is not set in .env")

if not SUPABASE_URL:
    raise ValueError("SUPABASE_URL is not set in .env")

if not SUPABASE_KEY:
    raise ValueError("SUPABASE_KEY is not set in .env")