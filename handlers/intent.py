"""
Classifies user messages into four categories:
  live_price       -> scrape goldpriceindia.com for today's price
  historical_price -> look up a past date from Supabase
  chart            -> generate a trend chart from Supabase history
  analysis         -> RAG pipeline (doc search + news + OpenAI)
"""
from openai import OpenAI
from config import OPENAI_API_KEY

client_openai = OpenAI(api_key=OPENAI_API_KEY)

CLASSIFIER_SYSTEM_PROMPT = """\
You classify a user's message into exactly one of four categories:

- "live_price": user wants TODAY's current live price of any commodity.

- "historical_price": user wants the price on a SPECIFIC PAST DATE —
  yesterday, last Monday, July 3rd, 3 days ago, etc.
  Single specific past date only, not a range or trend.

- "chart": user wants a TREND CHART or GRAPH showing price movement
  over a period — last 7 days, last week, past month, show trend, etc.
  Key signals: "chart", "graph", "trend", "show", "plot", "visualize",
  "last N days", "past N days", "over the last".

- "analysis": anything else — outlook, why, how, comparisons, document
  questions, multi-period analysis without asking for a chart.

Examples:
"gold price today"                    -> live_price
"current silver rate"                 -> live_price
"gold price yesterday"                -> historical_price
"silver price last Monday"            -> historical_price
"show gold trend last 7 days"         -> chart
"gold chart for past week"            -> chart
"plot copper prices last 14 days"     -> chart
"silver trend"                        -> chart
"what's the outlook for gold"         -> analysis
"why is copper expensive"             -> analysis
"what was gold price in 2024"         -> analysis

Respond with ONLY one word: live_price, historical_price, chart, or analysis.
"""


def classify_intent(user_text: str) -> str:
    try:
        response = client_openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": CLASSIFIER_SYSTEM_PROMPT},
                {"role": "user", "content": user_text},
            ],
            temperature=0,
            max_tokens=10,
        )
        label = response.choices[0].message.content.strip().lower()
        if "live_price" in label:
            return "live_price"
        if "historical_price" in label:
            return "historical_price"
        if "chart" in label:
            return "chart"
        return "analysis"
    except Exception:
        return "analysis"


if __name__ == "__main__":
    tests = [
        "gold price today",
        "silver price yesterday",
        "show gold trend last 7 days",
        "copper chart past 14 days",
        "silver trend",
        "what's the outlook for gold",
        "crude oil price right now",
        "gold price last Monday",
    ]
    for msg in tests:
        print(f"{msg!r:50} -> {classify_intent(msg)}")