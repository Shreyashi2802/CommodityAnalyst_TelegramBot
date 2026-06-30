# Commodity Analyst Bot

A Telegram bot that answers two kinds of questions about commodities (gold, silver, platinum, copper, nickel, crude oil):

1. **Live price questions** ("gold price today") → scrapes real-time prices directly from goldpriceindia.com
2. **Analysis questions** ("what's the outlook for gold?") → searches the user's uploaded PDF documents + recent commodity news, and uses OpenAI to write a blended answer

A separate script (`daily_price_logger.py`) builds a historical price archive (CSV files) over time, intended for trend analysis.

## Architecture

```
Telegram message
       │
       ▼
intent.py classifies: "live_price" or "analysis"
       │
       ├── live_price ──▶ price.py ──▶ scrapes goldpriceindia.com
       │
       └── analysis ────▶ qa.py ─────▶ documents.py (search user's uploaded PDFs)
                                  │
                                  └──▶ investing.com RSS (commodity news)
                                  │
                                  └──▶ OpenAI (blends both into one answer)
```

- `main.py` — entry point, routes incoming Telegram messages
- `handlers/price.py` — live price scraping (gold, silver, platinum, copper, nickel, crude oil)
- `handlers/intent.py` — classifies each message as a live-price question or an analysis question
- `handlers/documents.py` — PDF text extraction, chunking, and storage in a per-user vector database (ChromaDB)
- `handlers/qa.py` — blends document search + commodity news into one AI-written answer
- `daily_price_logger.py` — standalone script, appends today's price to per-commodity CSV files for trend history
- `cleanup_documents.py` — standalone script to list/delete a user's stored documents from the vector DB

## Setup (for a new contributor)

You'll need your **own** API keys — these are not shared between collaborators, each person needs their own.

1. **Get a Telegram bot token**: message [@BotFather](https://t.me/BotFather) on Telegram, send `/newbot`, follow the prompts, copy the token it gives you.

2. **Get an OpenAI API key**: sign up at [platform.openai.com](https://platform.openai.com), create an API key under your account. Note: this requires billing setup, though usage cost for testing is low.

3. **Clone the repo and set up a virtual environment:**
   ```bash
   git clone <repo-url>
   cd CommodityAnalyst_bot
   python -m venv venv
   venv\Scripts\activate        # Windows
   # source venv/bin/activate   # Mac/Linux
   pip install -r requirements.txt
   ```

4. **Create your own `.env` file** in the project root (this file is gitignored — never commit it):
   ```
   TELEGRAM_BOT_TOKEN=your_token_here
   OPENAI_API_KEY=your_key_here
   ```

5. **Test each piece in isolation** before running the full bot:
   ```bash
   python -m handlers.price      # confirms live scraping works
   python -m handlers.intent     # confirms the classifier works (uses OpenAI)
   ```

6. **Run the bot:**
   ```bash
   python main.py
   ```
   Open Telegram, find your bot, send `/start`.

7. **(Optional) Build price history for trend analysis:**
   ```bash
   python daily_price_logger.py
   ```
   Run this once a day to accumulate price history. Output lands in `data/price_history/*.csv` — one file per commodity, growing by one row per day. Currently run manually; can later be automated via Task Scheduler (Windows) or cron (Mac/Linux).

## Known limitations

- Only supports PDF uploads (no Word docs, images, etc.)
- Live prices cover gold, silver, platinum, copper, nickel, and crude oil only — not yet palladium, aluminium, lead, or zinc, though goldpriceindia.com has pages for these too if extended later
- Web/news context for the "analysis" path relies on a free RSS feed and a DuckDuckGo fallback scrape — not a paid news API, so coverage can be thin on less-covered topics
- All scraping depends on goldpriceindia.com's current page structure; if the site changes its layout, the relevant parser in `handlers/price.py` will need updating (see `debug_dump_table_rows()` in that file for a debugging helper)
- Price history (`daily_price_logger.py`) only starts accumulating from whenever it's first run — no historical backfill