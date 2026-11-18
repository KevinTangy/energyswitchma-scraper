"""
Daily scraper for EnergySwitch MA supplier offers.

Usage:
    python scrape.py 02148
    python scrape.py 02148 --city Malden

Opens the compare page for the given ZIP in headless Chromium, captures the
JSON the site loads behind the scenes, and appends one row per offer to
data/rates.csv (shared across all ZIPs, with zip and city columns).
Raw captures are kept in data/raw/<zip>/ so nothing is lost if the
field-matching below needs tuning after the first run.
"""
import argparse
import csv
import datetime as dt
import json
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

URL_TEMPLATE = "https://energyswitchma.gov/#/compare/1/1/{zip}//"
DATA = Path("data")
CSV_PATH = DATA / "rates.csv"

# Regexes used to pick useful columns out of whatever field names the API uses
FIELD_PATTERNS = {
    "supplier": r"supplier|company|vendor|provider",
    "product": r"product|plan|offer.*name",
    "price": r"price|rate|cents|kwh",
    "term": r"term|month|length|duration",
    "fees": r"fee|cancel|termination|enroll",
    "renewable": r"renew|green|clean",
    "price_type": r"fixed|variable|pricetype|ratetype",
}
CSV_COLUMNS = ["date", "zip", "city"] + list(FIELD_PATTERNS)


def parse_args():
    ap = argparse.ArgumentParser(description="Scrape EnergySwitch MA offers for a ZIP code.")
    ap.add_argument("zip", help="5-digit Massachusetts ZIP code, e.g. 02148")
    ap.add_argument("--city", default="", help="Optional city name to record in the CSV")
    args = ap.parse_args()
    if not re.fullmatch(r"\d{5}", args.zip):
        ap.error(f"ZIP code must be exactly 5 digits, got {args.zip!r}")
    return args


def walk(obj):
    """Yield every list of dicts anywhere in a JSON structure."""
    if isinstance(obj, list):
        if obj and all(isinstance(x, dict) for x in obj):
            yield obj
        for x in obj:
            yield from walk(x)
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from walk(v)


def flatten(d, prefix=""):
    out = {}
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(flatten(v, key + "."))
        elif not isinstance(v, list):
            out[key] = v
    return out


def pick_columns(row):
    picked = {}
    for col, pat in FIELD_PATTERNS.items():
        for k, v in row.items():
            if re.search(pat, k, re.I) and v not in (None, ""):
                picked[col] = v
                break
    return picked


def scrape(zip_code, city):
    today = dt.date.today().isoformat()
    raw_dir = DATA / "raw" / zip_code
    raw_dir.mkdir(parents=True, exist_ok=True)
    url = URL_TEMPLATE.format(zip=zip_code)
    captured = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()

        def on_response(resp):
            if "json" in (resp.headers.get("content-type") or ""):
                try:
                    captured.append({"url": resp.url, "body": resp.json()})
                except Exception:
                    pass

        page.on("response", on_response)
        page.goto(url, wait_until="networkidle", timeout=90_000)
        page.wait_for_timeout(8_000)  # let the offer list finish loading
        (raw_dir / f"{today}.txt").write_text(page.inner_text("body"))
        browser.close()

    (raw_dir / f"{today}.json").write_text(json.dumps(captured, indent=1))

    # Choose the biggest list of offer-like records across all responses
    best, best_url = [], ""
    for c in captured:
        for lst in walk(c["body"]):
            flat = [flatten(x) for x in lst]
            offers = [r for r in flat if pick_columns(r).get("price")]
            if len(offers) > len(best):
                best, best_url = offers, c["url"]

    label = f"{zip_code} {city}".strip()
    if not best:
        print(f"[{label}] No offer data found in JSON; see {raw_dir}/{today}.txt")
        return False

    print(f"[{label}] Found {len(best)} offers from {best_url}")
    new_file = not CSV_PATH.exists()
    with CSV_PATH.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        if new_file:
            w.writeheader()
        for r in best:
            w.writerow({"date": today, "zip": zip_code, "city": city, **pick_columns(r)})
    return True


def main():
    args = parse_args()
    ok = scrape(args.zip, args.city)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
