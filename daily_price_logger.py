"""
Standalone script: fetches TODAY's price for every supported commodity
and appends one row to that commodity's CSV file under
data/price_history/. This is how price HISTORY accumulates over time,
separate from the bot itself (the bot only ever shows "today's price"
live — it doesn't remember past days. This script is what builds the
archive your friend can analyze trends from).

THIS IS MANUAL FOR NOW — run it yourself once a day:
    python daily_price_logger.py

(Later, this exact same script can be wired into Windows Task
Scheduler to run automatically — no code changes needed for that,
just a scheduling setup outside of Python.)

SAFE TO RE-RUN: if you accidentally run this twice on the same day,
it won't create a duplicate row — it overwrites today's entry instead
of appending a second one.

OUTPUT FORMAT (one CSV per commodity, e.g. data/price_history/gold.csv):
    date,price,unit,note
    2026-06-28,14241.80,INR per gram (24K),
    2026-06-29,14300.10,INR per gram (24K),
"""
import csv
import os
from datetime import date

from handlers.price import get_gold_price_per_gram, COMMODITY_FETCHERS

HISTORY_DIR = "data/price_history"


def _csv_path(commodity_slug: str) -> str:
    return os.path.join(HISTORY_DIR, f"{commodity_slug}.csv")


def _read_existing_rows(csv_path: str) -> list[dict]:
    """Reads existing rows if the file exists, else returns []."""
    if not os.path.exists(csv_path):
        return []
    with open(csv_path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _write_rows(csv_path: str, rows: list[dict], fieldnames: list[str]) -> None:
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def append_price_row(commodity_slug: str, price: float, unit: str, note: str = "") -> None:
    """
    Adds today's price for one commodity to its CSV.
    If a row for today's date already exists, replaces it instead of
    duplicating (makes the script safe to re-run on the same day).
    """
    os.makedirs(HISTORY_DIR, exist_ok=True)
    csv_path = _csv_path(commodity_slug)
    today_str = date.today().isoformat()

    rows = _read_existing_rows(csv_path)
    rows = [r for r in rows if r.get("date") != today_str]  # drop any existing entry for today
    rows.append({"date": today_str, "price": price, "unit": unit, "note": note})

    # keep rows sorted by date so the CSV reads cleanly top-to-bottom
    rows.sort(key=lambda r: r["date"])

    _write_rows(csv_path, rows, fieldnames=["date", "price", "unit", "note"])


def log_all_commodities() -> None:
    """Fetches and logs today's price for every supported commodity.
    Prints a summary of what succeeded/failed — a single commodity's
    site hiccup shouldn't stop the others from being logged."""
    results = []

    # Gold gets special handling since it returns 24K/22K, not one price.
    try:
        gold_data = get_gold_price_per_gram()
        append_price_row("gold", gold_data["24k_per_gram"], unit="INR per gram (24K)")
        results.append(("gold", "OK", gold_data["24k_per_gram"]))
    except RuntimeError as e:
        results.append(("gold", f"FAILED: {e}", None))

    for slug, fetch_fn in COMMODITY_FETCHERS.items():
        try:
            data = fetch_fn()
            if "price_per_gram" in data:
                price = data["price_per_gram"]
                unit = "INR per gram"
            else:
                price = data["price"]
                unit = f"INR {data['unit']}"
            append_price_row(slug, price, unit=unit)
            results.append((slug, "OK", price))
        except RuntimeError as e:
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