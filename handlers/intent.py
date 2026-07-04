"""
Classifies what kind of question the user is asking, so main.py can
route to the right handler. Three categories:

  live_price       -> scrape goldpriceindia.com for today's price
  historical_price -> look up a past date from our local CSV logs
  analysis         -> RAG pipeline (doc search + news + OpenAI)
"""
from openai import OpenAI
from config import OPENAI_API_KEY

client_openai = OpenAI(api_key=OPENAI_API_KEY)

CLASSIFIER_SYSTEM_PROMPT = """\
You classify a user's message into exactly one of three categories:

- "live_price": the user wants TODAY's current/live price of any
  commodity — right now, in real time. Only for the present moment.

- "historical_price": the user wants the price of a commodity on a
  SPECIFIC PAST DATE or relative past period — yesterday, last week,
  last Monday, 3 days ago, a specific date like "June 28", etc.
  The key signal is: they want ONE specific past price point, not
  a trend/analysis/outlook.

- "analysis": anything else — trends, outlooks, comparisons, "why",
  "how has it changed", document questions, multi-period analysis.
  Also use this for vague past references that aren't a specific
  single date (e.g. "how was gold last year" = analysis, not historical).

Examples:
"gold price today"               -> live_price
"current silver rate"            -> live_price
"crude oil price right now"      -> live_price
"gold price yesterday"           -> historical_price
"what was silver price last week"-> historical_price
"copper price on June 28"        -> historical_price
"nickel price 3 days ago"        -> historical_price
"gold price last Monday"         -> historical_price
"how has gold changed this year" -> analysis
"what's the outlook for silver"  -> analysis
"why is copper expensive"        -> analysis
"what was gold price in 2024"    -> analysis  (full year, not a specific date)

Respond with ONLY one word: live_price, historical_price, or analysis.
No punctuation, no explanation.
"""


def classify_intent(user_text: str) -> str:
    """
    Returns "live_price", "historical_price", or "analysis".
    Defaults to "analysis" on any error.
    """
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
    test_messages = [
        "gold price today",
        "what's the current gold price",
        "gold price yesterday",
        "what was silver price last week",
        "copper price on June 28",
        "nickel price 3 days ago",
        "what was gold price in 2024",
        "how has gold changed this year",
        "what's the outlook for silver",
    ]
    for msg in test_messages:
        print(f"{msg!r:55} -> {classify_intent(msg)}")