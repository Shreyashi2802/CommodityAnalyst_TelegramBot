"""
Looks up historical commodity prices from Supabase price_history table.

Two responsibilities:
  1. Parse the user's message to figure out WHICH DATE they mean
     (via a small OpenAI call that returns a clean ISO date string)
  2. Query Supabase for that commodity + date and return the price
"""
from datetime import date, timedelta
from supabase import create_client
from openai import OpenAI

from config import OPENAI_API_KEY, SUPABASE_URL, SUPABASE_KEY
from handlers.price import resolve_commodity

client_openai = OpenAI(api_key=OPENAI_API_KEY)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

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
"2 weeks ago"       -> 2026-06-20
"""


def parse_date_from_text(user_text: str) -> str | None:
    """Uses GPT-4o-mini to extract a specific past date from natural language.
    Returns ISO date string (YYYY-MM-DD) or None."""
    today = date.today().isoformat()
    try:
        response = client_openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{
                "role": "user",
                "content": DATE_PARSER_PROMPT.format(
                    today=today, user_text=user_text
                ),
            }],
            temperature=0,
            max_tokens=15,
        )
        raw = response.choices[0].message.content.strip()
        parsed = date.fromisoformat(raw)
        if parsed > date.today():
            return None
        if parsed < date.today() - timedelta(days=365 * 5):
            return None
        return raw
    except Exception:
        return None


def detect_history_query(user_text: str) -> str:
    """
    Returns:
        single_date
        comparison
        trend
    """

    text = user_text.lower()

    trend_keywords = [
        "trend",
        "last 7",
        "past 7",
        "last week",
        "weekly",
        "history",
        "last seven",
    ]

    comparison_keywords = [
        "compare",
        "comparison",
        "difference",
        "change",
        "changed",
        "increase",
        "decrease",
        "higher",
        "lower",
        "vs",
        "versus",
    ]

    if any(word in text for word in trend_keywords):
        return "trend"

    if any(word in text for word in comparison_keywords):
        return "comparison"

    return "single_date"


def compare_today_vs_yesterday(commodity_slug: str) -> str:
    """
    Compare today's logged price with yesterday's logged price.
    Uses only Supabase (no live scraping).
    """

    today_date = date.today().isoformat()
    yesterday_date = (date.today() - timedelta(days=1)).isoformat()

    try:
        result = (
            supabase.table("price_history")
            .select("date, price, unit")
            .eq("commodity", commodity_slug)
            .in_("date", [today_date, yesterday_date])
            .execute()
        )
    except Exception as e:
        return f"Couldn't access the historical database.\n({e})"

    if not result.data:
        return (
            f"No historical data available for "
            f"{commodity_slug.replace('_', ' ')}."
        )

    prices = {
        row["date"]: row
        for row in result.data
    }

    if today_date not in prices:
        return (
            "Today's price hasn't been logged yet.\n"
            "Please try again after the daily logger runs."
        )

    if yesterday_date not in prices:
        return (
            "I don't have yesterday's price yet."
        )

    today_price = float(prices[today_date]["price"])
    yesterday_price = float(prices[yesterday_date]["price"])

    difference = today_price - yesterday_price
    percent = (difference / yesterday_price) * 100

    if difference > 0:
        trend = "📈 Increased"
    elif difference < 0:
        trend = "📉 Decreased"
    else:
        trend = "➖ No change"

    commodity_label = commodity_slug.replace("_", " ").title()

    return (
        f"{commodity_label} Price Comparison\n\n"
        f"Today's Price : ₹{today_price:,.2f}\n"
        f"Yesterday's Price : ₹{yesterday_price:,.2f}\n\n"
        f"{trend}\n"
        f"Difference : ₹{abs(difference):,.2f}\n"
        f"Percentage Change : {percent:+.2f}%"
    )

def get_weekly_trend(commodity_slug: str) -> str:
    """
    Returns the last 7 logged prices for a commodity.
    """

    try:
        result = (
            supabase.table("price_history")
            .select("date, price, unit")
            .eq("commodity", commodity_slug)
            .order("date", desc=True)
            .limit(7)
            .execute()
        )
    except Exception as e:
        return f"Couldn't access the historical database.\n({e})"

    if not result.data:
        return "No historical data available."

    rows = result.data

    output = [
        f"{commodity_slug.replace('_',' ').title()} Prices (Last {len(rows)} Days)\n"
    ]

    for row in rows:
        formatted_date = date.fromisoformat(row["date"]).strftime("%d %b")
        output.append(
            f"{formatted_date} : ₹{float(row['price']):,.2f}"
        )

    oldest = float(rows[-1]["price"])
    newest = float(rows[0]["price"])

    difference = newest - oldest
    percent = (difference / oldest) * 100

    if difference > 0:
        trend = "📈 Upward"
    elif difference < 0:
        trend = "📉 Downward"
    else:
        trend = "➖ Flat"

    output.append("")
    output.append(
        f"Overall Trend: {trend} ({percent:+.2f}%)"
    )

    return "\n".join(output)


def lookup_historical_price(user_text: str) -> str:
    """
    Main entry point: figures out commodity + date from user message,
    queries Supabase, returns a formatted reply string.
    """
    commodity_slug = resolve_commodity(user_text)

    if commodity_slug is None:
        return (
            "I couldn't tell which commodity you're asking about. "
            "Try something like 'gold price yesterday' or "
            "'silver price last week'."
        )

    query_type = detect_history_query(user_text)

    if query_type == "comparison":
        return compare_today_vs_yesterday(commodity_slug)

    if query_type == "trend":
        return get_weekly_trend(commodity_slug)
    
    target_date = parse_date_from_text(user_text)
    
    if target_date is None:
        return (
            "I couldn't figure out which date you mean. "
            "Try phrasing like 'gold price yesterday', "
            "'silver price last Monday', or 'copper price on June 28'."
        )

    if target_date == date.today().isoformat():
        return (
            "That looks like today's date — ask me 'gold price today' "
            "for the live current price."
        )

    # Query Supabase
    try:
        result = (
            supabase.table("price_history")
            .select("price, unit")
            .eq("commodity", commodity_slug)
            .eq("date", target_date)
            .execute()
        )
    except Exception as e:
        return f"Sorry, couldn't reach the price history database.\n({e})"

    if not result.data:
        # Tell the user what range we actually have
        try:
            range_result = (
                supabase.table("price_history")
                .select("date")
                .eq("commodity", commodity_slug)
                .order("date")
                .execute()
            )
            dates = [r["date"] for r in range_result.data]
            if dates:
                return (
                    f"I don't have a price for "
                    f"{commodity_slug.replace('_', ' ')} on {target_date}. "
                    f"My records run from {dates[0]} to {dates[-1]} "
                    f"({len(dates)} days logged so far)."
                )
        except Exception:
            pass
        return (
            f"No price data found for "
            f"{commodity_slug.replace('_', ' ')} on {target_date}. "
            f"Price logging may not have started yet — run "
            f"daily_price_logger.py to begin building history."
        )

    row = result.data[0]
    commodity_label = commodity_slug.replace("_", " ").title()
    return (
        f"{commodity_label} price on {target_date}:\n"
        f"₹{float(row['price']):,.2f} ({row['unit']})"
    )

