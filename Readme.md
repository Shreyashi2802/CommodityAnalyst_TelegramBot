# CommodityAnalyst Bot 

A production-deployed Telegram bot that delivers live commodity prices and AI-powered market analysis — combining real-time data scraping, document intelligence, and large language model synthesis into a single conversational interface.

**Live on Telegram:** [@CommodityAnalyst_TelegramBot](https://t.me/CommodityAnalyst_TelegramBot)  
**Deployed on:** Render | **Vector Store:** Pinecone | **LLM:** OpenAI GPT-4o-mini | **Database:** Supabase

---

## What It Does

### 1. Live Price Queries
Ask for any supported commodity in natural language — the bot fetches the latest India-specific INR price directly from a live source, with no caching or stale data.

Supported: **Gold (24K/22K)**, **Silver**, **Platinum**, **Copper**, **Nickel**, **Crude Oil**

### 2. Historical Price Lookup
Ask for a commodity price on any past date using natural language — "gold price yesterday", "silver price last Monday", "copper price on July 3". The bot uses an LLM to parse the date and queries a Supabase PostgreSQL database for the stored value.

### 3. AI-Powered Document Analysis (RAG Pipeline)
Users upload their own PDF research reports. The bot:
1. Extracts and chunks the document text (~500 words per chunk)
2. Generates semantic embeddings via OpenAI `text-embedding-3-small`
3. Stores them in Pinecone, isolated per user via namespaces
4. On each query, retrieves the most semantically relevant chunks
5. Blends document context with live commodity news headlines (investing.com RSS)
6. Synthesises a single, coherent answer via GPT-4o-mini

### 4. Smart Intent Routing
Every message passes through an LLM-based classifier before any data is fetched — routing to `live_price`, `historical_price`, or `analysis` with high accuracy, even for ambiguous phrasing.

### 5. Automated Daily Price Logging
A cron job (cron-job.org) hits a `/log-prices` endpoint on Render every day at 4:30 PM, which scrapes all 6 commodity prices and writes them to Supabase — fully automated, zero manual intervention.

---

## Architecture

```
Telegram message
       │
       ▼
  Intent Classifier (GPT-4o-mini)
       │
       ├── live_price ──────▶ Scraper ──▶ goldpriceindia.com (INR, real-time)
       │
       ├── historical_price ─▶ Date parser (GPT-4o-mini) ──▶ Supabase query
       │
       └── analysis ─────────▶ Pinecone (user-scoped semantic search)
                          │
                          ├──▶ investing.com RSS (live news headlines)
                          │
                          └──▶ GPT-4o-mini synthesis
                                    │
                                    ▼
                              Telegram reply

Daily automation:
  cron-job.org ──▶ /log-prices (Render) ──▶ scrape prices ──▶ Supabase
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Bot interface | Telegram Bot API (`python-telegram-bot`) |
| Web framework | FastAPI + Uvicorn (webhook mode) |
| LLM | OpenAI GPT-4o-mini |
| Embeddings | OpenAI `text-embedding-3-small` (1536-dim) |
| Vector store | Pinecone (cloud-hosted, per-user namespaces) |
| Relational DB | Supabase (PostgreSQL, price history) |
| PDF parsing | pypdf |
| Data scraping | requests + BeautifulSoup |
| News feed | investing.com RSS (`feedparser`) |
| Hosting | Render (free tier, webhook-based web service) |
| Automation | cron-job.org (daily price logging) |

---

## Key Engineering Decisions

**Why scraping over a paid API for prices?**
India-specific INR pricing isn't reliably available on free commodity APIs. We initially integrated API Ninjas but dropped it after discovering free-tier weekly rotation made silver/nickel unreliable. Scraping `goldpriceindia.com` proved more consistent — one trusted source covering all required commodities including nickel, which the API didn't support at all.

**Why Pinecone over local ChromaDB?**
ChromaDB writes to the local filesystem, which Render's free tier doesn't persist across restarts. Pinecone's cloud-hosted index survives redeploys permanently. ChromaDB integration is preserved (commented out) for local development.

**Why Supabase for price history?**
Structured time-series data (date, commodity, price) is a poor fit for a vector database — semantic similarity search is meaningless for exact date lookups. Supabase provides free cloud PostgreSQL that both local dev and Render can access, with a simple upsert on (date, commodity) preventing duplicates.

**Why an LLM classifier instead of keyword matching?**
A naive keyword check misrouted historical questions ("what was the gold price in 2024?") to the live scraper. An LLM classifier with contrastive examples handles semantic intent correctly regardless of surface phrasing — a real improvement discovered through failure cases during development.

**Why webhook over polling?**
Polling requires a continuously-running background process — incompatible with free hosting tiers. Webhook mode turns the bot into a standard HTTP web service activated only on incoming messages, with no idle resource consumption.

---

## Project Structure

```
CommodityAnalyst_bot/
├── main.py                    # FastAPI app + Telegram webhook + /log-prices endpoint
├── config.py                  # Environment variable loading
├── daily_price_logger.py      # Scrapes + writes daily prices to Supabase
├── cleanup_documents.py       # Utility — list/delete user documents from Pinecone
├── render.yaml                # Render deployment config
├── requirements.txt
├── handlers/
│   ├── price.py               # Live price scrapers (3 parser patterns)
│   ├── intent.py              # LLM-based 3-way intent classifier
│   ├── documents.py           # PDF extraction, chunking, Pinecone storage
│   ├── qa.py                  # RAG retrieval + OpenAI synthesis
│   └── history.py             # Historical price lookup from Supabase
└── data/
    └── uploads/<user_id>/     # Raw uploaded PDFs (per user, gitignored)
```

---

## Setup (New Contributor)

**You need your own API keys — these are not shared.**

Prerequisites: Python 3.10+, accounts at Telegram, OpenAI, Pinecone, Supabase.

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
PINECONE_INDEX_NAME=your_index_name   # dimensions: 1536, metric: cosine
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_KEY=your_anon_key
WEBHOOK_URL=                          # leave blank for local dev
```

Create Supabase table (run in SQL Editor):
```sql
CREATE TABLE price_history (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    commodity VARCHAR(50) NOT NULL,
    price DECIMAL(12, 2) NOT NULL,
    unit VARCHAR(50) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(date, commodity)
);
```

Test each layer:
```bash
python -m handlers.price      # verify live scraping
python -m handlers.intent     # verify intent classifier
python daily_price_logger.py  # verify Supabase writes
python main.py                # run locally
```

---

## Known Limitations & Planned Improvements

- **Cold starts:** Free Render tier sleeps after 15 min inactivity — first message after idle takes ~30s
- **Scraping fragility:** If `goldpriceindia.com` changes layout, parsers in `price.py` need updating. Use `debug_dump_table_rows()` for fast diagnosis
- **PDF only:** Document uploads support PDF only — Word/image support needs additional libraries
- **Historical data starts from day 1:** No backfill — only dates after first logger run are available
- **No financial advice:** Answers are summaries of retrieved context, not investment recommendations