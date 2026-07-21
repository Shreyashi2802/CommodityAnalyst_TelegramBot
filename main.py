"""
Entry point for the bot. Routes incoming messages to the right handler:
  - /start              -> welcome message
  - PDF document upload -> extract + store for that user
  - text message        -> classified by intent.py into:
                            live_price       -> scrape goldpriceindia.com
                            historical_price -> Supabase date lookup
                            chart            -> trend chart PNG from Supabase
                            analysis         -> blended doc + web + OpenAI
"""
import logging
import os
import io

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
from handlers.charts import generate_trend_chart, parse_chart_request

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

UPLOAD_DIR = "data/uploads"
PORT = int(os.getenv("PORT", 8000))
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")

fastapi_app = FastAPI()
bot_app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Hi! I'm your commodity analysis bot.\n\n"
        "- 'gold price today' — live price\n"
        "- 'gold price yesterday' — historical lookup\n"
        "- 'show gold trend last 7 days' — trend chart\n"
        "- Upload a PDF — I'll remember it for analysis\n"
        "- Ask any analysis question — I'll blend your docs + news"
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
        num_chunks = store_document(
            file_path, user_id=user_id, filename=document.file_name
        )
        await update.message.reply_text(
            f"Done! Stored {num_chunks} sections from '{document.file_name}'. "
            "You can now ask me questions about it."
        )
    except ValueError as e:
        await update.message.reply_text(f"Couldn't process this PDF: {e}")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user_text = update.message.text

    intent = classify_intent(user_text)

    # ── CHART ──────────────────────────────────────────────────────
    if intent == "chart":
        commodity_slug, days = parse_chart_request(user_text)

        if commodity_slug is None:
            await update.message.reply_text(
                "I couldn't tell which commodity you want a chart for. "
                "Try 'show gold trend last 7 days' or 'silver chart 14 days'."
            )
            return

        display = commodity_slug.replace("_", " ").title()
        await update.message.reply_text(
            f"Generating {display} trend chart for the last {days} days..."
        )

        try:
            image_bytes, error = generate_trend_chart(commodity_slug, days)

            if error:
                await update.message.reply_text(error)
                return

            await update.message.reply_photo(
                photo=io.BytesIO(image_bytes),
                caption=f"{display} price trend — last {days} days (INR)"
            )
        except Exception as e:
            logger.error(f"Chart generation failed: {e}", exc_info=True)
            await update.message.reply_text(
                f"Sorry, chart generation failed: {e}"
            )
        return

    # ── HISTORICAL PRICE ───────────────────────────────────────────
    if intent == "historical_price":
        await update.message.reply_text("Looking up that price from my records...")
        reply = lookup_historical_price(user_text)
        await update.message.reply_text(reply)
        return

    # ── LIVE PRICE ─────────────────────────────────────────────────
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
                "Try 'silver price' or 'crude oil price today'."
            )
            return

        if commodity_slug == "gold":
            await update.message.reply_text("Checking today's gold price...")
            try:
                prices = get_gold_price_per_gram()
                reply = (
                    "Today's Gold Price (India, per gram):\n"
                    f"24K: Rs{prices['24k_per_gram']:,.2f}\n"
                    f"22K: Rs{prices['22k_per_gram']:,.2f}"
                )
                if not prices["changed"]:
                    reply += (
                        "\n\n(No change from previous close — "
                        "markets likely closed today.)"
                    )
            except RuntimeError as e:
                reply = f"Sorry, couldn't fetch the price right now.\n({e})"
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
                    f"Per gram: Rs{data['price_per_gram']:,.2f}"
                )
                if data.get("price_per_kg"):
                    reply += f"\nPer kg: Rs{data['price_per_kg']:,.2f}"
            else:
                reply = (
                    f"{commodity_slug.replace('_', ' ').title()} price (India): "
                    f"Rs{data['price']:,.2f} {data['unit']}"
                )
        except RuntimeError as e:
            reply = f"Sorry, couldn't fetch that price right now.\n({e})"
        await update.message.reply_text(reply)
        return

    # ── ANALYSIS ───────────────────────────────────────────────────
    await update.message.reply_text(
        "Thinking through that with your documents and the web..."
    )
    try:
        answer = answer_with_context(user_text, user_id=user_id)
    except Exception as e:
        answer = f"Sorry, something went wrong while answering: {e}"
    await update.message.reply_text(answer)


bot_app.add_handler(CommandHandler("start", start))
bot_app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))


@fastapi_app.post("/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, bot_app.bot)
    await bot_app.initialize()
    await bot_app.process_update(update)
    return {"ok": True}


@fastapi_app.get("/")
async def health_check():
    return {"status": "running"}


@fastapi_app.get("/log-prices")
async def log_prices():
    from daily_price_logger import log_all_commodities
    try:
        log_all_commodities()
        return {"status": "ok", "message": "Prices logged to Supabase"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@fastapi_app.on_event("startup")
async def on_startup():
    await bot_app.initialize()
    if WEBHOOK_URL:
        await bot_app.bot.set_webhook(url=f"{WEBHOOK_URL}/webhook")
        logger.info(f"Webhook set to {WEBHOOK_URL}/webhook")
    else:
        logger.warning("WEBHOOK_URL not set — webhook not registered with Telegram")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(fastapi_app, host="0.0.0.0", port=PORT)