"""
Entry point for the bot.

POLLING vs WEBHOOK:
  - Polling (old): bot continuously asks Telegram "any new messages?"
    Works on localhost, doesn't need a public URL. Bad for hosting
    since it needs an always-on background process.
  - Webhook (current): Telegram pushes messages directly to our
    server the moment they arrive. Needs a public HTTPS URL (Render
    provides this automatically). Better for free hosting since the
    server only wakes up when a message arrives.

Routes incoming messages to:
  - /start              -> welcome message
  - PDF document upload -> extract + store for that user
  - text message        -> classified by intent.py into:
                            "live_price" -> scrape goldpriceindia.com
                            "analysis"   -> blended doc + web answer
"""
import logging
import os
from datetime import datetime

from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

from config import TELEGRAM_BOT_TOKEN
from handlers.price import (
    get_gold_price_per_gram,
    resolve_commodity,
    mentions_unsupported_commodity,
    COMMODITY_FETCHERS,
)
from handlers.documents import store_document
from handlers.qa import answer_with_context
from handlers.intent import classify_intent
from handlers.history import lookup_historical_price

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

UPLOAD_DIR = "data/uploads"

# Render injects a PORT env var — we must bind to it, not a hardcoded port
PORT = int(os.getenv("PORT", 8000))

# Your Render service URL — set this as an env var on Render dashboard
# e.g. https://your-bot-name.onrender.com
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")

# ── FastAPI app (receives Telegram webhook POST requests) ──────────
fastapi_app = FastAPI()

# ── Telegram bot application ───────────────────────────────────────
bot_app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Hi! I'm your commodity analysis bot.\n\n"
        "- Ask me things like 'gold price today', 'silver price', "
        "'copper price', 'nickel price', or 'crude oil price'\n"
        "- Upload a PDF report and I'll remember it for your questions\n"
        "- Ask analysis questions and I'll blend your documents with "
        "current web info"
    )


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    document = update.message.document

    if not document.file_name.lower().endswith(".pdf"):
        await update.message.reply_text("Right now I only support PDF files.")
        return

    await update.message.reply_text("Got it, processing your PDF...")

    user_folder = os.path.join(UPLOAD_DIR, str(user_id))
    os.makedirs(user_folder, exist_ok=True)
    file_path = os.path.join(user_folder, document.file_name)

    telegram_file = await document.get_file()
    await telegram_file.download_to_drive(file_path)

    try:
        num_chunks = store_document(file_path, user_id=user_id, filename=document.file_name)
        await update.message.reply_text(
            f"Done! Stored {num_chunks} sections from '{document.file_name}'. "
            "You can now ask me questions about it."
        )
    except ValueError as e:
        await update.message.reply_text(f"Couldn't process this PDF: {e}")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user_text = update.message.text.strip()

    # Handle greetings separately
    GREETINGS = {
        "hi",
        "hello",
        "hey",
        "good morning",
        "good afternoon",
        "good evening",
        "hola",
    }

    if user_text.lower() in GREETINGS:
        await update.message.reply_text(
            "Hi! 👋\n\n"
            "I'm your Commodity Analysis Bot.\n\n"
            "You can ask me things like:\n"
            "• Gold price today\n"
            "• Silver price yesterday\n"
            "• Latest commodity news\n"
            "• Why is copper getting expensive?\n"
            "• Upload a PDF and ask questions about it."
        )
        return

    intent = classify_intent(user_text)

    logger.info(
        f"""
=========================
User ID : {user_id}
Chat ID : {update.effective_chat.id}
Message : {user_text}
Intent  : {intent}
=========================
"""
    )

    if intent == "historical_price":
        await update.message.reply_text("Looking up that price from my records...")
        reply = lookup_historical_price(user_text)
        await update.message.reply_text(reply)
        return


    if intent == "live_price":
        unsupported = mentions_unsupported_commodity(user_text)
        if unsupported:
            await update.message.reply_text(
                f"Sorry, I don't currently have live price data for "
                f"{unsupported}. Supported: gold, silver, platinum, "
                f"copper, nickel, crude oil."
            )
            return

        commodity_slug = resolve_commodity(user_text)

        if commodity_slug is None:
            await update.message.reply_text(
                "I couldn't tell which commodity you're asking about. "
                "Try something like 'silver price' or 'crude oil price today'."
            )
            return

        if commodity_slug == "gold":
            await update.message.reply_text("Checking today's gold price...")

            try:
                prices = get_gold_price_per_gram()

                reply = (
                     "📈 Today's Gold Price (India, per gram)\n\n"
                    f"🥇 24K: ₹{prices['24k_per_gram']:,.2f}\n"
                    f"🥈 22K: ₹{prices['22k_per_gram']:,.2f}"
                )

        # If today is Saturday (5) or Sunday (6), mention that these
        # are the latest available prices.
                if datetime.now().weekday() >= 5:
                    reply += (
                        "\n\nℹ️ Markets are generally closed on weekends. "
                        "These are the latest available gold prices."
                    )

            except RuntimeError as e:
                reply = (
                    "Sorry, I couldn't fetch the gold price right now.\n"
                    f"({e})"
                )

            await update.message.reply_text(reply)
            return

        fetch_fn = COMMODITY_FETCHERS.get(commodity_slug)
        await update.message.reply_text(
            f"Checking today's {commodity_slug.replace('_', ' ')} price..."
        )
        try:
            data = fetch_fn()
            if "price_per_gram" in data:
                reply = (
                    f"{commodity_slug.title()} price (India):\n"
                    f"Per gram: ₹{data['price_per_gram']:,.2f}"
                )
                if data.get("price_per_kg"):
                    reply += f"\nPer kg: ₹{data['price_per_kg']:,.2f}"
            else:
                reply = (
                    f"{commodity_slug.replace('_', ' ').title()} price (India): "
                    f"₹{data['price']:,.2f} {data['unit']}"
                )
        except RuntimeError as e:
            reply = f"Sorry, couldn't fetch that price right now.\n({e})"
        await update.message.reply_text(reply)
        return

    await update.message.reply_text(
        "Thinking through that with your documents and the web..."
    )
    try:
        answer = answer_with_context(user_text, user_id=user_id)
    except Exception as e:
        answer = f"Sorry, something went wrong while answering: {e}"
    await update.message.reply_text(answer)


# ── Register handlers ──────────────────────────────────────────────
bot_app.add_handler(CommandHandler("start", start))
bot_app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))


# ── FastAPI routes ─────────────────────────────────────────────────
@fastapi_app.post("/webhook")
async def telegram_webhook(request: Request):
    """Telegram calls this endpoint every time a message is sent."""
    data = await request.json()
    update = Update.de_json(data, bot_app.bot)
    await bot_app.initialize()
    await bot_app.process_update(update)
    return {"ok": True}


@fastapi_app.get("/")
async def health_check():
    """
    Render uses this to confirm the service is alive.
    Must return HTTP 200 or Render marks the deploy as failed.
    """
    return {"status": "running"}


@fastapi_app.get("/log-prices")
async def log_prices():
    """
    Called daily by cron-job.org to trigger the price logger on Render.
    Fetches today's prices for all commodities and saves to Supabase.
    """
    from daily_price_logger import log_all_commodities
    try:
        log_all_commodities()
        return {"status": "ok", "message": "Prices logged to Supabase"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ── Startup: register webhook with Telegram on boot ───────────────
@fastapi_app.on_event("startup")
async def on_startup():
    await bot_app.initialize()
    if WEBHOOK_URL:
        await bot_app.bot.set_webhook(url=f"{WEBHOOK_URL}/webhook")
        logger.info(f"Webhook set to {WEBHOOK_URL}/webhook")
    else:
        logger.warning("WEBHOOK_URL not set — webhook not registered with Telegram")


# ── Entry point ────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(fastapi_app, host="0.0.0.0", port=PORT)