"""
The "blending" step: takes a user's question, gathers context from
  (a) their uploaded documents (via search_user_documents)
  (b) the web (via an RSS commodity news feed, with DuckDuckGo as fallback)
and asks OpenAI to write one synthesized answer using both.

NOTE ON WEB SEARCH:
  OpenAI's chat models don't browse the web by themselves unless
  you use a specific "web search" enabled model/tool. Two sources
  are used here for "the web" half of the context:

  1. RSS_FEED_URL (investing.com's commodity news feed) — a real,
     legitimate, key-free RSS feed of live commodity market news.
     This is the PRIMARY source: structured XML, meant for
     programmatic consumption, much more reliable than scraping
     a search engine's HTML.

  2. DuckDuckGo HTML scrape — kept as a FALLBACK for questions the
     RSS feed's recent headlines don't cover (e.g. "what is XYZ"
     type background questions, rather than "what's happening now").
"""
from openai import OpenAI
import requests
import feedparser

from config import OPENAI_API_KEY
from handlers.documents import search_user_documents

client_openai = OpenAI(api_key=OPENAI_API_KEY)

RSS_FEED_URL = "https://www.investing.com/rss/news_11.rss"


def get_commodity_news(query: str, max_results: int = 3) -> list[str]:
    """
    Pulls the latest commodity news headlines from investing.com's
    RSS feed, and does a simple keyword-overlap filter to surface
    the ones most relevant to the user's question.

    Returns a list of headline strings (most relevant first).
    Returns [] if the feed can't be reached or nothing matches.
    """
    try:
        feed = feedparser.parse(RSS_FEED_URL)
    except Exception:
        return []

    if not feed.entries:
        return []

    query_words = set(query.lower().split())

    scored = []

    for entry in feed.entries:
        title = entry.get("title", "")
        title_words = set(title.lower().split())
        overlap = len(query_words & title_words)
        scored.append((overlap, title))

    scored.sort(key=lambda x: x[0], reverse=True)

    matched = [
        title
        for score, title in scored
        if score > 0
    ]

    if matched:
        return matched[:max_results]

    # Nothing matched the user's query
    return []

def simple_web_search(query: str, max_results: int = 3) -> list[str]:
    """
    Fallback, key-free web search using DuckDuckGo's HTML endpoint.
    Only used when the RSS feed doesn't return anything useful.
    """
    try:
        resp = requests.get(
            "https://duckduckgo.com/html/",
            params={"q": query},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        resp.raise_for_status()
    except requests.RequestException:
        return []  # fail quietly — the bot will just rely on documents only

    from bs4 import BeautifulSoup

    soup = BeautifulSoup(resp.text, "html.parser")
    snippets = []
    for result in soup.select(".result__snippet")[:max_results]:
        text = result.get_text(strip=True)
        if text:
            snippets.append(text)
    return snippets


def answer_with_context(question: str, user_id: int) -> str:
    """
    Main entry point: given a user's question, pulls relevant
    document chunks (scoped to this user) and web context — RSS
    commodity news first, DuckDuckGo as fallback — then asks
    OpenAI to write one blended answer citing both where useful.
    """
    print("\n========== QA DEBUG ==========")
    print("User ID :", user_id)
    print("Question :", question)

    doc_chunks = search_user_documents(question, user_id=user_id, top_k=3)
    print("Document Chunks Found :", len(doc_chunks))
    web_snippets = get_commodity_news(question)
    print("Web Snippets :", web_snippets)
    print("==============================\n")
    web_source_label = "From recent commodity news headlines:"
    if not web_snippets:
        web_snippets = simple_web_search(question)
        web_source_label = "From recent web search results:"

    context_parts = []
    if doc_chunks:
        context_parts.append(
            "From the user's uploaded document(s):\n"
            + "\n---\n".join(doc_chunks)
        )
    if web_snippets:
        context_parts.append(
            f"{web_source_label}\n" + "\n---\n".join(web_snippets)
        )

    if not context_parts:
        context_block = "(No document or web context was found.)"
    else:
        context_block = "\n\n".join(context_parts)

    system_prompt = (
        "You are a commodity market analysis assistant. "
        "Answer the user's question using the provided context. "
        "If the document and web context disagree, point that out. "
        "If context is missing or insufficient, say so clearly rather "
        "than guessing. Keep the answer concise and practical."
    )

    user_prompt = f"Question: {question}\n\nContext:\n{context_block}"

    response = client_openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )

    return response.choices[0].message.content