"""
Looks up historical commodity prices from the locally-logged CSV files
in data/price_history/<commodity>.csv.

Two responsibilities:
  1. Parse the user's message to figure out WHICH DATE they mean
     ("yesterday", "last week", "June 28", "3 days ago", etc.)
     — done via a small OpenAI call that returns a clean ISO date string

  2. Look up that date in the right commodity's CSV and return the price

IMPORTANT: data only exists from the day daily_price_logger.py was
first run. If the user asks for a date before that, we tell them
clearly instead of silently returning nothing.
"""
import csv
import os
from datetime import date, timedelta

from openai import OpenAI
from config import OPENAI_API_KEY
from handlers.price import resolve_commodity

client_openai = OpenAI(api_key=OPENAI_API_KEY)

HISTORY_DIR = "data/price_history"

DATE_PARSER_PROMPT = """\
Today's date is {today}.
The user said: "{user_text}"

Extract the date they are referring to and return it in YYYY-MM-DD format.
Return ONLY the date string, nothing else. No explanation, no punctuation.

Examples (assuming today is 2026-07-04):
"yesterday"         -> 2026-07-03
"last week"         -> 2026-06-27
"3 days ago"        -> 2026-07-01
"last Monday"       -> 2026-06-29
"June 28"           -> 2026-06-28
"on June 15"        -> 2026-06-15
"2 weeks ago"       -> 2026-06-20
"""


def parse_date_from_text(user_text: str) -> str | None:
    """
    Uses GPT-4o-mini to extract a specific past date from the user's
    natural language message. Returns an ISO date string (YYYY-MM-DD)
    or None if no clear date could be extracted.
    """
    today = date.today().isoformat()
    try:
        response = client_openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": DATE_PARSER_PROMPT.format(
                        today=today, user_text=user_text
                    ),
                }
            ],
            temperature=0,
            max_tokens=15,
        )
        raw = response.choices[0].message.content.strip()
        # Validate it looks like a real date before trusting it
        parsed = date.fromisoformat(raw)
        # Sanity check: don't accept future dates or dates more than
        # 5 years back (likely a parsing error)
        if parsed > date.today():
            return None
        if parsed < date.today() - timedelta(days=365 * 5):
            return None
        return raw
    except Exception:
        return None


def lookup_historical_price(user_text: str) -> str:
    """
    Main entry point: given a user message asking for a past price,
    figures out which commodity and which date, looks it up in the
    CSV, and returns a formatted reply string.

    Returns a plain string — either the price info or a clear
    explanation of why it couldn't find the data.
    """
    # Figure out which commodity
    commodity_slug = resolve_commodity(user_text)
    if commodity_slug is None:
        return (
            "I couldn't tell which commodity you're asking about. "
            "Try something like 'gold price yesterday' or "
            "'silver price last week'."
        )

    # Figure out which date
    target_date = parse_date_from_text(user_text)
    if target_date is None:
        return (
            "I couldn't figure out which date you mean. "
            "Try phrasing like 'gold price yesterday', "
            "'silver price last Monday', or 'copper price on June 28'."
        )

    # Don't allow today — that should go through the live scraper
    if target_date == date.today().isoformat():
        return (
            "That looks like today's date — ask me 'gold price today' "
            "for the live current price."
        )

    # Look up the CSV
    csv_path = os.path.join(HISTORY_DIR, f"{commodity_slug}.csv")
    if not os.path.exists(csv_path):
        return (
            f"I don't have any historical data for "
            f"{commodity_slug.replace('_', ' ')} yet — "
            f"price logging hasn't started for this commodity."
        )

    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = {row["date"]: row for row in csv.DictReader(f)}

    if target_date not in rows:
        # Tell the user what range we actually have, so they know
        # whether to ask differently or whether data just doesn't exist
        available_dates = sorted(rows.keys())
        if not available_dates:
            return (
                f"No price history found for "
                f"{commodity_slug.replace('_', ' ')} yet."
            )
        earliest = available_dates[0]
        latest = available_dates[-1]
        return (
            f"I don't have a price for {commodity_slug.replace('_', ' ')} "
            f"on {target_date}. "
            f"My records run from {earliest} to {latest} "
            f"({len(available_dates)} days logged so far)."
        )

    row = rows[target_date]
    commodity_label = commodity_slug.replace("_", " ").title()
    return (
        f"{commodity_label} price on {target_date}:\n"
        f"₹{float(row['price']):,.2f} ({row['unit']})"
    )