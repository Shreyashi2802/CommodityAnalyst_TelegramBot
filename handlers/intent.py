"""
Classifies user messages into three categories:
  live_price       -> scrape goldpriceindia.com for today's price
  historical_price -> look up a past date from Supabase
  analysis         -> RAG pipeline (doc search + news + OpenAI)
"""
from openai import OpenAI
from config import OPENAI_API_KEY

client_openai = OpenAI(api_key=OPENAI_API_KEY)

CLASSIFIER_SYSTEM_PROMPT = """\
You classify a user's message into exactly one of three categories:

- "live_price": user wants TODAY's current live price of any commodity.

- "historical_price": user wants the price on a SPECIFIC PAST DATE —
  yesterday, last Monday, July 3rd, 3 days ago, etc.
  Single specific past date only, not a range or trend.

- "analysis": anything else — outlook, why, how, comparisons, document
  questions, trends, charts, multi-period analysis.

Examples:
"gold price today"                    -> live_price
"current silver rate"                 -> live_price
"gold price yesterday"                -> historical_price
"silver price last Monday"            -> historical_price
"what's the outlook for gold"         -> analysis
"why is copper expensive"             -> analysis
"what was gold price in 2024"         -> analysis
"show gold trend last 7 days"         -> historical_price
"compare today's gold price with yesterday's" -> historical_price
"average silver price this week"      -> historical_price
"highest gold price this week"        -> historical_price
"gold price history" -> historical_price
"gold prices this week" -> historical_price
"compare silver with yesterday"       -> historical_price
"silver price change"                 -> historical_price

Respond with ONLY one word: live_price, historical_price, or analysis.
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
        return "analysis"
    except Exception:
        return "analysis"


if __name__ == "__main__":
    tests = [
        "gold price today",
        "silver price yesterday",
        "what's the outlook for gold",
        "crude oil price right now",
        "gold price last Monday",
    ]
    for msg in tests:
        print(f"{msg!r:50} -> {classify_intent(msg)}")