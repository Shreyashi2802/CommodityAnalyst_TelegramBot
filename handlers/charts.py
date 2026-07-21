import sys
sys.setrecursionlimit(5000)  # makes it fail faster with clearer error
"""
Generates commodity price trend charts from Supabase historical data
and returns them as PNG image bytes for sending via Telegram.
"""
import io
import re
from datetime import date, timedelta, datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from handlers.price import resolve_commodity

COMMODITY_DISPLAY = {
    "gold": ("Gold (24K)", "#FFD700"),
    "silver": ("Silver", "#C0C0C0"),
    "platinum": ("Platinum", "#E5E4E2"),
    "copper": ("Copper", "#B87333"),
    "nickel": ("Nickel", "#7B8B6F"),
    "crude_oil": ("Crude Oil", "#888888"),
}


def fetch_price_history(commodity_slug: str, days: int) -> list[dict]:
    """Query Supabase inside the function to avoid circular import/init issues."""
    from supabase import create_client
    from config import SUPABASE_URL, SUPABASE_KEY

    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    from_date = (date.today() - timedelta(days=days)).isoformat()

    result = (
        supabase.table("price_history")
        .select("date, price")
        .eq("commodity", commodity_slug)
        .gte("date", from_date)
        .order("date")
        .execute()
    )
    return result.data


def generate_trend_chart(commodity_slug: str, days: int) -> tuple:
    rows = fetch_price_history(commodity_slug, days)

    if not rows:
        return None, (
            f"No price history found for "
            f"{commodity_slug.replace('_', ' ')} in the last {days} days. "
            f"Make sure the daily logger has been running."
        )

    if len(rows) < 2:
        return None, (
            f"Only {len(rows)} data point found — need at least 2 to draw a trend."
        )

    dates = [datetime.strptime(r["date"], "%Y-%m-%d") for r in rows]
    prices = [float(r["price"]) for r in rows]

    display_name, color = COMMODITY_DISPLAY.get(
        commodity_slug,
        (commodity_slug.replace("_", " ").title(), "#4A90D9")
    )

    fig, ax = plt.subplots(figsize=(10, 5))
    fig.patch.set_facecolor("#1a1a2e")
    ax.set_facecolor("#16213e")

    ax.plot(dates, prices, color=color, linewidth=2.5, marker="o",
            markersize=5, markerfacecolor=color,
            markeredgecolor="white", markeredgewidth=0.8)
    ax.fill_between(dates, prices, alpha=0.15, color=color)

    ax.set_title(f"{display_name} — Last {len(rows)} Days",
                 color="white", fontsize=14, fontweight="bold", pad=15)
    ax.set_xlabel("Date", color="#aaaaaa", fontsize=10)
    ax.set_ylabel("Price (INR)", color="#aaaaaa", fontsize=10)
    ax.tick_params(colors="#aaaaaa")

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax.xaxis.set_major_locator(
        mdates.DayLocator(interval=max(1, len(dates) // 7))
    )
    plt.xticks(rotation=45, ha="right")

    for spine in ax.spines.values():
        spine.set_edgecolor("#333355")

    ax.yaxis.set_major_formatter(
        plt.FuncFormatter(lambda x, _: f"Rs{x:,.0f}")
    )

    change = prices[-1] - prices[0]
    change_pct = (change / prices[0]) * 100
    change_color = "#00ff88" if change >= 0 else "#ff4444"
    symbol = "+" if change >= 0 else "-"
    ax.annotate(
        f"{symbol} Rs{abs(change):,.2f} ({change_pct:+.2f}%)",
        xy=(0.02, 0.95), xycoords="axes fraction",
        color=change_color, fontsize=10, fontweight="bold",
        bbox=dict(boxstyle="round,pad=0.3", facecolor="#1a1a2e", alpha=0.8)
    )

    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf.read(), ""


def parse_chart_request(user_text: str) -> tuple:
    commodity_slug = resolve_commodity(user_text)
    match = re.search(r"(\d+)\s*days?", user_text.lower())
    days = int(match.group(1)) if match else 7
    days = min(days, 90)
    return commodity_slug, days