"""
Classifies what kind of question the user is asking, so main.py can
route to the right handler.

WHY NOT JUST KEYWORDS:
  A simple "if 'gold' in text and 'price' in text" check has two
  failure modes:
    1. Misses naturally-phrased price questions that don't literally
       say "price" (e.g. "how much is gold worth today").
    2. Wrongly grabs historical/analytical questions that happen to
       contain both words (e.g. "what was the gold price in 2024"
       — this needs the user's DOCUMENT, not today's live price).

  A small LLM call handles this far more reliably than string
  matching, at the cost of one extra cheap API call per message.
"""
from openai import OpenAI
from config import OPENAI_API_KEY

client_openai = OpenAI(api_key=OPENAI_API_KEY)

CLASSIFIER_SYSTEM_PROMPT = """\
You classify a user's message into exactly one category:

- "live_price": the user wants TODAY's current/live price of ANY \
commodity (gold, silver, oil, copper, etc.) — right now, in real time. \
This is ONLY for questions about the present moment.

- "analysis": ANY question about a past date, a past year, a trend, an \
outlook, demand, comparisons, or a specific document — even if a \
commodity name and the word "price" appear together. The presence of \
those words does NOT make it a live_price question. What matters is \
WHEN: past/trend/analysis = analysis. Right-now/current moment = live_price.

Examples:
"gold price today" -> live_price
"what's the current silver price" -> live_price
"how much is crude oil worth right now" -> live_price
"copper price" -> live_price
"what was the gold price in 2024" -> analysis   (past year, not "right now")
"how has oil price changed this year" -> analysis  (trend)
"what's the outlook for silver" -> analysis
"why is copper expensive" -> analysis

If the message refers to any specific past date, past year, or time period \
that is not literally "now" or "today", it is ALWAYS "analysis" — never \
live_price, regardless of how the sentence is worded.

Respond with ONLY one word: live_price or analysis. No punctuation, \
no explanation.
"""


def classify_intent(user_text: str) -> str:
    """
    Returns "live_price" or "analysis".
    Defaults to "analysis" if anything goes wrong, since that path
    degrades more gracefully (it can still try to answer, or say it
    found no relevant info — rather than wrongly firing the scraper).
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
        return "analysis"
    except Exception:
        return "analysis"


if __name__ == "__main__":
    # Quick manual test: run `python handlers/intent.py` directly
    test_messages = [
        "gold price today",
        "what's the current gold price",
        "how much is gold worth right now",
        "what was the gold price in 2024",
        "what was the gold price last week",
        "how has gold price changed this year",
        "what's the outlook for gold",
        "why is gold expensive",
    ]
    for msg in test_messages:
        print(f"{msg!r:50} -> {classify_intent(msg)}")