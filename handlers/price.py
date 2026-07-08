"""
Live commodity prices — scraped entirely from goldpriceindia.com.

WHY ONE SITE FOR EVERYTHING:
  We initially used a separate API (API Ninjas) for non-gold
  commodities, but its free tier only grants access to a rotating
  subset of 7 commodities per week, which made it unreliable for
  always-available silver/nickel/etc. goldpriceindia.com has a
  dedicated page per commodity, all in INR (more useful for Indian
  users than the API's USD/troy-ounce pricing), with no quota or
  rotation — so we switched fully to scraping this one trusted site.

THREE PAGE PATTERNS, one parser function per pattern:
  1. "Karat-style"   (gold)                    -> parse_karat_table()
  2. "Spot table"    (silver, platinum)         -> parse_spot_table()
  3. "Simple value"  (crude oil, copper, nickel)-> parse_simple_value()

Each commodity's public function (get_gold_price, get_silver_price,
etc.) just calls the right parser against its own URL.
"""
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

BASE_URL = "https://goldpriceindia.com"

URLS = {
    "gold": f"{BASE_URL}/",
    "silver": f"{BASE_URL}/silver-price-india.php",
    "platinum": f"{BASE_URL}/platinum-price-india.php",
    "copper": f"{BASE_URL}/copper-price-india.php",
    "nickel": f"{BASE_URL}/nickel-price-india.php",
    "crude_oil": f"{BASE_URL}/crude-oil-price-india.php",
}

# Maps natural-language commodity names/aliases the user might type
# to our internal slug (matches the keys in URLS above).
COMMODITY_ALIASES = {
    "gold": "gold",
    "silver": "silver",
    "platinum": "platinum",
    "copper": "copper",
    "nickel": "nickel",
    "crude oil": "crude_oil",
    "crude": "crude_oil",
    "oil": "crude_oil",
    "wti": "crude_oil",
}

# Commodities the site has pages for, but we haven't built support
# for yet. Listed honestly so we can tell the user clearly, rather
# than silently failing.
KNOWN_BUT_UNSUPPORTED = {"palladium", "aluminium", "aluminum", "lead", "zinc"}


def _fetch_soup(url: str) -> BeautifulSoup:
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        raise RuntimeError(f"Could not reach the price source: {e}")
    return BeautifulSoup(response.text, "html.parser")


def _clean_price(text: str) -> float:
    """Turns '₹14,419.90' into 14419.90"""
    digits = text.replace("₹", "").replace(",", "").strip()
    return float(digits)


def parse_karat_table(soup: BeautifulSoup) -> dict:
    """Pattern 1: gold's page — 24K/22K columns, multiple weight rows.
    We only need the '1 gram' row."""
    target_row = None
    for row in soup.find_all("tr"):
        cells = row.find_all("td")
        if cells and "1 gram" in cells[0].get_text(strip=True).lower():
            target_row = cells
            break

    if not target_row or len(target_row) < 3:
        raise RuntimeError("Could not find the gold price row — page layout may have changed.")

    price_24k = _clean_price(target_row[1].get_text())
    price_22k = _clean_price(target_row[2].get_text())

    #page_text = soup.get_text()
    #changed = not ("+0 (0%)" in page_text or "+0(0%)" in page_text)

    return {
        "24k_per_gram": price_24k,
        "22k_per_gram": price_22k,
    }


def parse_spot_table(soup: BeautifulSoup) -> dict:
    """Pattern 2: silver/platinum pages.

    IMPORTANT (discovered via debugging on real site HTML): these
    pages do NOT have a clean <td>label</td><td>price</td> row
    structure. Instead, all the weight/price pairs ("1 gram", then
    its price, "2 grams", then its price, etc.) are packed together
    as plain text inside ONE table cell, like:
        "1 gram\\n\\n₹223.85\\n\\n2 grams\\n\\n₹447.70\\n..."

    So instead of matching table rows/cells, we find the cell whose
    text contains "Spot Price in India" (this uniquely identifies
    the right cell), then use a regex to pull out "<label> ... ₹<price>"
    pairs directly from its raw text. This is more robust than
    depending on exact DOM/cell structure, which doesn't match what
    we assumed.
    """
    import re

    target_text = None
    for cell in soup.find_all("td"):
        text = cell.get_text()
        if "Spot Price in India" in text:
            target_text = text
            break

    if not target_text:
        raise RuntimeError(
            "Could not find the spot price section — page layout may have changed."
        )

    # Matches e.g. "1 gram" followed (after any whitespace/newlines)
    # by "₹223.85" or "₹223,852.00"
    pairs = re.findall(r"(\d+\s*(?:gram|grams|kilogram|ounce))\s*₹([\d,]+\.?\d*)", target_text, re.IGNORECASE)

    price_per_gram = None
    price_per_kg = None

    for label, price_str in pairs:
        label_norm = re.sub(r"\s+", " ", label).strip().lower()
        price_val = float(price_str.replace(",", ""))
        if label_norm == "1 gram":
            price_per_gram = price_val
        elif label_norm == "1 kilogram":
            price_per_kg = price_val

    if price_per_gram is None:
        raise RuntimeError("Could not find the price row — page layout may have changed.")

    return {"price_per_gram": price_per_gram, "price_per_kg": price_per_kg}


def parse_simple_value(soup: BeautifulSoup, unit_label: str) -> dict:
    """Pattern 3: crude oil/copper/nickel pages — one headline price,
    no breakdown table. The price appears as the first '₹...' text
    right after the date header."""
    page_text = soup.get_text()

    # Find the first ₹ amount on the page — this is the headline price
    # for these simple single-value pages.
    import re
    match = re.search(r"₹[\d,]+(?:\.\d+)?", page_text)
    if not match:
        raise RuntimeError("Could not find the price on the page — layout may have changed.")

    price = _clean_price(match.group())
    return {"price": price, "unit": unit_label}


def get_gold_price_per_gram() -> dict:
    """India gold price, 24K/22K, per gram (INR)."""
    soup = _fetch_soup(URLS["gold"])
    return parse_karat_table(soup)


def get_silver_price() -> dict:
    """India silver price, per gram and per kg (INR)."""
    soup = _fetch_soup(URLS["silver"])
    return parse_spot_table(soup)


def get_platinum_price() -> dict:
    """India platinum price, per gram and per kg (INR)."""
    soup = _fetch_soup(URLS["platinum"])
    return parse_spot_table(soup)


def get_copper_price() -> dict:
    """India copper price, per KG (INR)."""
    soup = _fetch_soup(URLS["copper"])
    return parse_simple_value(soup, unit_label="per KG")


def get_nickel_price() -> dict:
    """India nickel price, per KG (INR)."""
    soup = _fetch_soup(URLS["nickel"])
    return parse_simple_value(soup, unit_label="per KG")


def get_crude_oil_price() -> dict:
    """India crude oil price, per barrel (INR)."""
    soup = _fetch_soup(URLS["crude_oil"])
    return parse_simple_value(soup, unit_label="per barrel")


# Maps each commodity slug to its fetch function, so main.py can do
# a simple lookup instead of a long if/elif chain.
COMMODITY_FETCHERS = {
    "silver": get_silver_price,
    "platinum": get_platinum_price,
    "copper": get_copper_price,
    "nickel": get_nickel_price,
    "crude_oil": get_crude_oil_price,
}


def resolve_commodity(user_text: str) -> str | None:
    """Looks for any known commodity name/alias in the user's text.
    Returns our internal slug if found, else None. Checks longer
    phrases first so multi-word aliases aren't shadowed."""
    lowered = user_text.lower()
    for alias in sorted(COMMODITY_ALIASES, key=len, reverse=True):
        if alias in lowered:
            return COMMODITY_ALIASES[alias]
    return None


def mentions_unsupported_commodity(user_text: str) -> str | None:
    """Returns the unsupported commodity name if the user mentioned
    one we know about but haven't built a fetcher for yet."""
    lowered = user_text.lower()
    for name in KNOWN_BUT_UNSUPPORTED:
        if name in lowered:
            return name
    return None


def debug_dump_table_rows(commodity_slug: str) -> None:
    """
    Debug helper: prints every table row's raw cell text for a given
    commodity's page. Use this if a parser keeps failing and you need
    to see exactly what the site's HTML actually contains, rather
    than guessing.
    Usage: python -c "from handlers.price import debug_dump_table_rows; debug_dump_table_rows('silver')"
    """
    soup = _fetch_soup(URLS[commodity_slug])
    for i, row in enumerate(soup.find_all("tr")):
        cells = row.find_all("td")
        cell_texts = [repr(c.get_text()) for c in cells]
        if cell_texts:
            print(f"row {i}: {cell_texts}")


if __name__ == "__main__":
    # Quick manual test: run `python -m handlers.price` from project root
    print("Gold (24K/22K, per gram):")
    try:
        data = get_gold_price_per_gram()
        print(f"  24K: ₹{data['24k_per_gram']:,.2f}  22K: ₹{data['22k_per_gram']:,.2f}")
    except RuntimeError as e:
        print(f"  Error: {e}")

    for label, fetch_fn in COMMODITY_FETCHERS.items():
        print(f"\n{label.replace('_', ' ').title()}:")
        try:
            data = fetch_fn()
            print(f"  {data}")
        except RuntimeError as e:
            print(f"  Error: {e}")