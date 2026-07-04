# CommodityAnalyst Bot 🤖📈

A production-deployed Telegram bot that delivers live commodity prices and AI-powered market analysis — combining real-time data scraping, document intelligence, and large language model synthesis into a single conversational interface.

**Live on Telegram:** [@CommodityAnalyst_TelegramBot](https://t.me/CommodityAnalyst_TelegramBot)  
**Deployed on:** Render | **Vector Store:** Pinecone | **LLM:** OpenAI GPT-4o-mini

---

## What It Does

### Live Price Queries
Ask for any supported commodity in natural language — the bot fetches the latest India-specific INR price directly from a live source, with no caching or stale data.

Supported: **Gold (24K/22K)**, **Silver**, **Platinum**, **Copper**, **Nickel**, **Crude Oil**

### AI-Powered Document Analysis (RAG Pipeline)
Users can upload their own PDF research reports. The bot:
1. Extracts and chunks the document text
2. Generates semantic embeddings via OpenAI
3. Stores them in Pinecone, isolated per user
4. On each query, retrieves the most semantically relevant chunks
5. Blends document context with live commodity news headlines
6. Synthesises a single, coherent answer via GPT-4o-mini

### Smart Intent Routing
Every message passes through an LLM-based classifier before any data is fetched — distinguishing "give me today's price" from "explain the outlook for gold" with high accuracy, even when phrasing is ambiguous.

### Historical Price Logging
A separate script appends daily prices for all commodities to per-commodity CSV files — building a time-series dataset for trend analysis.

---

## Architecture

```
Telegram message
       │
       ▼
  Intent Classifier (GPT-4o-mini)
       │
       ├── live_price ──▶ Scraper ──▶ goldpriceindia.com (INR, real-time)
       │
       └── analysis ────▶ Retrieval (Pinecone — user-scoped namespace)
                     │
                     ├──▶ News context (investing.com RSS feed)
                     │
                     └──▶ GPT-4o-mini synthesis
                               │
                               ▼
                         Telegram reply
```

**Deployment:** Webhook mode (FastAPI + Uvicorn) on Render free tier — the server only activates on incoming messages, no always-on polling required.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Bot interface | Telegram Bot API (`python-telegram-bot`) |
| Web framework | FastAPI + Uvicorn (webhook mode) |
| LLM | OpenAI GPT-4o-mini |
| Embeddings | OpenAI `text-embedding-3-small` (1536-dim) |
| Vector store | Pinecone (cloud-hosted, persistent, per-user namespaces) |
| PDF parsing | pypdf |
| Data scraping | requests + BeautifulSoup |
| News feed | investing.com RSS (`feedparser`) |
| Hosting | Render (free tier, webhook-based web service) |

---

## Key Engineering Decisions

**Why scraping over a paid API?** The primary data source (`goldpriceindia.com`) provides India-specific INR pricing that commodity APIs either don't offer or charge for. We initially integrated API Ninjas but dropped it after discovering free-tier rotation made silver/nickel unreliable — scraping a single trusted source proved more consistent.

**Why Pinecone over local ChromaDB?** ChromaDB writes to the local filesystem, which free hosting tiers don't persist across restarts. Pinecone's cloud-hosted index survives redeploys and scales naturally. ChromaDB integration is preserved (commented out) for local development.

**Why an LLM classifier instead of keyword matching?** A naive `if "gold" in text and "price" in text` check misrouted historical questions ("what was the gold price in 2024?") to the live scraper. An LLM classifier with contrastive examples handles semantic intent correctly regardless of surface phrasing — a meaningful improvement discovered through real failure cases during development.

**Why webhook over polling?** Polling requires a continuously-running background process — incompatible with free hosting tiers. Webhook mode turns the bot into a standard HTTP web service, activated only on incoming messages, with no idle resource consumption.

---

## Project Structure

```
CommodityAnalyst_bot/
├── main.py                    # FastAPI app + Telegram webhook handler
├── config.py                  # Environment variable loading
├── daily_price_logger.py      # Standalone script — appends daily prices to CSV
├── cleanup_documents.py       # Utility — list/delete user documents from Pinecone
├── render.yaml                # Render deployment config
├── requirements.txt
├── handlers/
│   ├── price.py               # Live price scrapers (3 parser patterns)
│   ├── intent.py              # LLM-based intent classifier
│   ├── documents.py           # PDF extraction, chunking, Pinecone storage
│   └── qa.py                  # RAG retrieval + OpenAI synthesis
└── data/
    ├── uploads/<user_id>/     # Raw uploaded PDFs (per user)
    └── price_history/         # Daily price CSVs (gold.csv, silver.csv, ...)
```

---

## Setup (New Contributor)

You need your own API keys — these are not shared.

**Prerequisites:**
- Python 3.10+
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- An OpenAI API key from [platform.openai.com](https://platform.openai.com)
- A free Pinecone index from [pinecone.io](https://pinecone.io) (dimensions: 1536, metric: cosine)

```bash
git clone <repo-url>
cd CommodityAnalyst_bot
python -m venv venv
venv\Scripts\activate        # Windows — or: source venv/bin/activate
pip install -r requirements.txt
```

Create `.env` in project root:
```
TELEGRAM_BOT_TOKEN=your_token
OPENAI_API_KEY=your_key
PINECONE_API_KEY=your_key
PINECONE_INDEX_NAME=your_index_name
WEBHOOK_URL=                  # leave blank for local dev (uses polling fallback)
```

Test each layer in isolation:
```bash
python -m handlers.price      # verify live scraping works
python -m handlers.intent     # verify intent classifier works
python main.py                # run the bot locally
```

---

## Known Limitations & Planned Improvements

- **Cold starts:** Free Render tier sleeps after 15 min inactivity — first message after idle takes ~30s. Solvable with a paid tier or a keep-alive ping.
- **Scraping fragility:** If `goldpriceindia.com` changes its page layout, parsers in `price.py` need updating. A `debug_dump_table_rows()` helper is included for fast diagnosis.
- **PDF only:** Document uploads support PDF only. Word/image support would require additional extraction libraries.
- **No financial advice:** Analysis answers are summaries of retrieved context, not investment recommendations.