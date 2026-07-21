"""
QA module

Blends:
1. User uploaded documents (Pinecone)
2. Live commodity news (Investing.com RSS)
3. DuckDuckGo fallback

Uses GPT-4o-mini to generate one final response.
"""

from openai import OpenAI
import requests
import feedparser

from config import OPENAI_API_KEY
from handlers.documents import search_user_documents

client_openai = OpenAI(api_key=OPENAI_API_KEY)

RSS_FEED_URL = "https://www.investing.com/rss/news_11.rss"


# ----------------------------
# RSS NEWS
# ----------------------------
def get_commodity_news(question: str, max_results: int = 5) -> list[str]:
    """
    Returns relevant commodity news headlines.

    If the question is generic like:
    - latest commodity news
    - latest news
    - market news

    then simply return the latest headlines.

    Otherwise rank by keyword overlap.
    """

    try:
        feed = feedparser.parse(RSS_FEED_URL)
    except Exception:
        return []

    if not feed.entries:
        return []

    q = question.lower()

    generic_news_words = [
        "latest",
        "recent",
        "news",
        "market",
        "commodity",
        "headlines",
        "update",
    ]

    # Generic news request -> latest headlines
    if any(word in q for word in generic_news_words):
        headlines = []

        for entry in feed.entries[:max_results]:
            headlines.append(entry.get("title", ""))

        return headlines

    query_words = set(q.split())

    scored = []

    for entry in feed.entries:
        title = entry.get("title", "")
        title_words = set(title.lower().split())

        overlap = len(query_words & title_words)

        scored.append((overlap, title))

    scored.sort(reverse=True)

    matched = [title for score, title in scored if score > 0]

    if matched:
        return matched[:max_results]

    return [entry.get("title", "") for entry in feed.entries[:max_results]]


# ----------------------------
# DUCKDUCKGO FALLBACK
# ----------------------------
def simple_web_search(query: str, max_results: int = 3) -> list[str]:

    try:
        response = requests.get(
            "https://duckduckgo.com/html/",
            params={"q": query},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )

        response.raise_for_status()

    except requests.RequestException:
        return []

    from bs4 import BeautifulSoup

    soup = BeautifulSoup(response.text, "html.parser")

    snippets = []

    for result in soup.select(".result__snippet")[:max_results]:
        text = result.get_text(strip=True)

        if text:
            snippets.append(text)

    return snippets


# ----------------------------
# MAIN QA
# ----------------------------
def answer_with_context(question: str, user_id: int) -> str:

    print("\n========== QA DEBUG ==========")
    print("User :", user_id)
    print("Question :", question)

    # Search user documents
    doc_chunks = search_user_documents(
        question,
        user_id=user_id,
        top_k=3,
    )

    print("Documents :", len(doc_chunks))

    # RSS news
    web_snippets = get_commodity_news(question)

    web_source = "Latest Commodity News"

    # Fallback
    if not web_snippets:
        web_snippets = simple_web_search(question)
        web_source = "Web Search Results"

    print("Web Snippets:")
    for item in web_snippets:
        print("-", item)

    print("==============================\n")

    document_context = (
        "\n\n".join(doc_chunks)
        if doc_chunks
        else "No relevant user documents."
    )

    news_context = (
        "\n".join(f"• {item}" for item in web_snippets)
        if web_snippets
        else "No recent web news."
    )

    system_prompt = """
You are an expert Commodity Market Analysis Assistant.

You are provided with:

1. User uploaded documents.
2. Latest commodity news headlines.

Rules:

- Always use the provided news headlines when answering questions about:
    • latest commodity news
    • market updates
    • today's news
    • current events
    • recent developments
    • price movements

- Headlines about:
    • wars
    • geopolitical tensions
    • sanctions
    • trade
    • tariffs
    • inflation
    • central banks
    • interest rates
    • recession
    • currency movements

  are ALL relevant because they influence commodity markets.

- Summarize the headlines naturally.

- Do NOT say:
  "The context does not contain commodity news"
  if headlines have been provided.

- If both documents and news are relevant,
  combine both.

- Only state that context is insufficient when BOTH
  document context AND web context are empty.

- Never invent facts.

- Keep answers concise but informative.
"""

    user_prompt = f"""
User Question:
{question}

==========================
USER DOCUMENTS
==========================

{document_context}

==========================
{web_source}
==========================

{news_context}

Instructions:

If the question asks for:

- latest news
- recent developments
- today's market
- market updates

Prioritize the news section.

If it asks about uploaded documents,
prioritize the documents.

If both are useful,
combine both naturally.
"""

    response = client_openai.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.3,
        messages=[
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": user_prompt,
            },
        ],
    )

    return response.choices[0].message.content