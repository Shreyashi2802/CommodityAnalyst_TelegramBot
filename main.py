"""
Entry point for the bot. Routes incoming messages to the right handler:
  - /start              -> welcome message
  - PDF document upload -> extract + store for that user
  - text message         -> classified by intent.py into:
                              "live_price" -> resolve which commodity,
                                              fetch from goldpriceindia.com
                              "analysis"   -> blended document + web answer
"""
import logging
import os

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

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

UPLOAD_DIR = "data/uploads"


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
    """
    Handles plain text messages.
    Uses classify_intent() to decide:
      - "live_price" -> figure out WHICH commodity, then scrape its price
      - "analysis"   -> blended document + web answer via OpenAI
    """
    user_id = update.effective_user.id
    user_text = update.message.text

    intent = classify_intent(user_text)

    if intent == "live_price":
        unsupported = mentions_unsupported_commodity(user_text)
        if unsupported:
            await update.message.reply_text(
                f"Sorry, I don't currently have live price data for "
                f"{unsupported}. Supported commodities: gold, silver, "
                f"platinum, copper, nickel, and crude oil."
            )
            return

        commodity_slug = resolve_commodity(user_text)

        if commodity_slug is None:
            await update.message.reply_text(
                "I couldn't tell which commodity you're asking about. "
                "Try something like 'silver price' or 'crude oil price today'."
            )
            return

        # Gold gets its own detailed 24K/22K reply.
        if commodity_slug == "gold":
            await update.message.reply_text("Checking today's gold price...")
            try:
                prices = get_gold_price_per_gram()
                reply = (
                    "Today's Gold Price (India, per gram):\n"
                    f"24K: ₹{prices['24k_per_gram']:,.2f}\n"
                    f"22K: ₹{prices['22k_per_gram']:,.2f}"
                )
                if not prices["changed"]:
                    reply += (
                        "\n\n(No change from the previous close — markets "
                        "are likely closed today, e.g. a weekend.)"
                    )
            except RuntimeError as e:
                reply = f"Sorry, couldn't fetch the price right now.\n({e})"
            await update.message.reply_text(reply)
            return

        # Every other supported commodity uses its fetcher from price.py.
        fetch_fn = COMMODITY_FETCHERS.get(commodity_slug)
        await update.message.reply_text(f"Checking today's {commodity_slug.replace('_', ' ')} price...")
        try:
            data = fetch_fn()
            if "price_per_gram" in data:
                reply = f"{commodity_slug.title()} price (India):\nPer gram: ₹{data['price_per_gram']:,.2f}"
                if data.get("price_per_kg"):
                    reply += f"\nPer kg: ₹{data['price_per_kg']:,.2f}"
            else:
                reply = f"{commodity_slug.replace('_', ' ').title()} price (India): ₹{data['price']:,.2f} {data['unit']}"
        except RuntimeError as e:
            reply = f"Sorry, couldn't fetch that price right now.\n({e})"
        await update.message.reply_text(reply)
        return

    # "analysis" -> document + web blending
    await update.message.reply_text("Thinking through that with your documents and the web...")
    try:
        answer = answer_with_context(user_text, user_id=user_id)
    except Exception as e:
        answer = f"Sorry, something went wrong while answering: {e}"
    await update.message.reply_text(answer)


def main() -> None:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("Bot is starting (polling mode)...")
    app.run_polling()


if __name__ == "__main__":
    main()