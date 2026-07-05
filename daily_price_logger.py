"""
Standalone script: fetches TODAY's price for every supported commodity
and upserts one row to the Supabase price_history table.

WHY SUPABASE INSTEAD OF CSV:
  CSV files live on the local machine — Render's free tier doesn't
  persist local files across restarts, so CSVs written on Render
  would disappear. Supabase is a cloud-hosted PostgreSQL database
  that both your laptop AND Render can read/write reliably.

UPSERT (not just insert):
  Uses Supabase's upsert with (date, commodity) as the unique key —
  so running this script twice on the same day safely updates the
  existing row instead of creating a duplicate.

RUN MANUALLY (for now):
  python daily_price_logger.py

LATER — automate via cron-job.org hitting your Render endpoint
  (see /log-prices route in main.py).
"""
from datetime import date
from supabase import create_client
from config import SUPABASE_URL, SUPABASE_KEY
from handlers.price import get_gold_price_per_gram, COMMODITY_FETCHERS

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def log_price(commodity: str, price: float, unit: str) -> None:
    """Upserts one price row into Supabase price_history table."""
    supabase.table("price_history").upsert({
        "date": date.today().isoformat(),
        "commodity": commodity,
        "price": price,
        "unit": unit,
    }, on_conflict="date,commodity").execute()


def log_all_commodities() -> None:
    results = []

    # Gold — special case (24K/22K)
    try:
        data = get_gold_price_per_gram()
        log_price("gold", data["24k_per_gram"], "INR per gram (24K)")
        results.append(("gold", "OK", data["24k_per_gram"]))
    except Exception as e:
        results.append(("gold", f"FAILED: {e}", None))

    # All other commodities
    for slug, fetch_fn in COMMODITY_FETCHERS.items():
        try:
            data = fetch_fn()
            price = data.get("price_per_gram") or data.get("price")
            unit = "INR per gram" if "price_per_gram" in data else f"INR {data['unit']}"
            log_price(slug, price, unit)
            results.append((slug, "OK", price))
        except Exception as e:
            results.append((slug, f"FAILED: {e}", None))

    print(f"\nDaily price log — {date.today().isoformat()}")
    print("-" * 50)
    for slug, status, price in results:
        if price is not None:
            print(f"  {slug:12} {status:6} {price}")
        else:
            print(f"  {slug:12} {status}")


if __name__ == "__main__":
    log_all_commodities()