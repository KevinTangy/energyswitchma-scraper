"""
Daily scraper for EnergySwitch MA supplier offers.

Usage:
    python scrape.py 02148 --city Malden
    python scrape.py 02148 --city Malden --from-raw data/raw/02148/2026-11-18.json

Opens the compare page for the given ZIP in headless Chromium, captures the
offer list the site loads from /consumers/compare, and appends one row per
offer to data/rates.csv (shared across all ZIPs, with zip and city columns).
Re-running for a ZIP on the same date replaces that day's rows for the ZIP
instead of adding them again; earlier days are never touched.
The raw capture is kept in data/raw/<zip>/ so history can be re-processed.
--from-raw skips the browser and re-reads a saved capture instead.
"""
import argparse
import csv
import datetime as dt
import json
import re
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

URL_TEMPLATE = "https://energyswitchma.gov/#/compare/1/1/{zip}//"
API_MARKER = "/consumers/compare"
DATA = Path("data")
CSV_PATH = DATA / "rates.csv"
CSV_COLUMNS = ["date", "zip", "city", "supplier", "price_cents_per_kwh", "term", "fees"]
# Dates are recorded in Massachusetts time. GitHub runners use UTC, so an
# evening run would otherwise be labeled with the next day's date.
LOCAL_TZ = ZoneInfo("America/New_York")


def parse_args():
    ap = argparse.ArgumentParser(description="Scrape EnergySwitch MA offers for a ZIP code.")
    ap.add_argument("zip", help="5-digit Massachusetts ZIP code, e.g. 02148")
    ap.add_argument("--city", default="", help="Optional city name to record in the CSV")
    ap.add_argument("--from-raw", type=Path, help="Re-process a saved raw JSON capture instead of scraping")
    ap.add_argument("--date", help="Date to record (YYYY-MM-DD); defaults to today")
    args = ap.parse_args()
    if not re.fullmatch(r"\d{5}", args.zip):
        ap.error(f"ZIP code must be exactly 5 digits, got {args.zip!r}")
    return args


def capture(zip_code, raw_dir, today):
    """Load the page in headless Chromium and return all JSON responses."""
    from playwright.sync_api import sync_playwright

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
        page.goto(URL_TEMPLATE.format(zip=zip_code), wait_until="networkidle", timeout=90_000)
        page.wait_for_timeout(8_000)  # let the offer list finish loading
        (raw_dir / f"{today}.txt").write_text(page.inner_text("body"))
        browser.close()

    (raw_dir / f"{today}.json").write_text(json.dumps(captured, indent=1))
    return captured


def find_offers(captured):
    """Return the offer list from the /consumers/compare response."""
    for c in captured:
        body = c.get("body")
        if API_MARKER in c.get("url", "") and isinstance(body, list):
            return body
    # Fallback: any list of records that carry supplierName
    for c in captured:
        body = c.get("body")
        if isinstance(body, list) and body and isinstance(body[0], dict) and "supplierName" in body[0]:
            return body
    return []


def split_pipe(value):
    """'a|b' -> ['a', 'b']; None -> ['']."""
    return [part.strip() for part in (value or "").split("|")]


def cents(price_text):
    """'17.185 ¢/kWh' -> '17.185'."""
    m = re.search(r"\d+(?:\.\d+)?", price_text or "")
    return m.group(0) if m else ""


def fees_text(offer):
    parts = []
    if offer.get("enrollmentFee"):
        parts.append(f"Enrollment fee: {offer['enrollmentFee']}")
    if offer.get("pricePerMonth"):
        parts.append(f"Monthly charge: {offer['pricePerMonth']}")
    parts.append(offer.get("earlyTerminationDetail") or "No cancellation fee")
    return "; ".join(parts)


def offer_rows(offer):
    """One row per price period. Basic service lists two periods joined by '|'."""
    prices = split_pipe(offer.get("pricePerUnit") or offer.get("fixedPrice"))
    terms = split_pipe(offer.get("contractTerm"))
    if len(terms) < len(prices):
        terms += [terms[-1]] * (len(prices) - len(terms))
    supplier = (offer.get("supplierName") or "").strip()
    if offer.get("isDistributionCompany"):
        supplier += " (Basic Service)"
    fees = fees_text(offer)
    return [
        {"supplier": supplier, "price_cents_per_kwh": cents(p), "term": t, "fees": fees}
        for p, t in zip(prices, terms)
    ]


def sort_rows(rows):
    """Basic service rows first (in their original period order), then
    everything else from cheapest to most expensive."""
    basic = [r for r in rows if r["supplier"].endswith("(Basic Service)")]
    others = [r for r in rows if not r["supplier"].endswith("(Basic Service)")]

    def price_key(r):
        try:
            return (float(r["price_cents_per_kwh"]), r["supplier"])
        except ValueError:
            return (float("inf"), r["supplier"])  # missing price goes last

    return basic + sorted(others, key=price_key)


def write_rows(rows):
    DATA.mkdir(parents=True, exist_ok=True)
    if CSV_PATH.exists():
        with CSV_PATH.open(newline="") as f:
            header = next(csv.reader(f), [])
        if header != CSV_COLUMNS:
            legacy = DATA / "rates_old_format.csv"
            CSV_PATH.rename(legacy)
            print(f"Column layout changed; moved old file to {legacy}")
    # Keep every existing row except this ZIP's rows for the same date, so a
    # second run on one day replaces that day's data rather than duplicating it.
    replaced = {(r["date"], r["zip"]) for r in rows}
    kept, dropped = [], 0
    if CSV_PATH.exists():
        with CSV_PATH.open(newline="") as f:
            for r in csv.DictReader(f):
                if (r["date"], r["zip"]) in replaced:
                    dropped += 1
                else:
                    kept.append(r)
    tmp = CSV_PATH.with_suffix(".csv.tmp")
    with tmp.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        w.writeheader()
        # Stable sort by date: keeps each batch's row order and the file in
        # date order even when an earlier day is re-run.
        w.writerows(sorted(kept + rows, key=lambda r: r["date"]))
    tmp.replace(CSV_PATH)  # atomic: a crash never leaves a half-written CSV
    return dropped


def main():
    args = parse_args()
    today = args.date or dt.datetime.now(LOCAL_TZ).date().isoformat()
    label = f"{args.zip} {args.city}".strip()

    if args.from_raw:
        captured = json.loads(args.from_raw.read_text())
    else:
        raw_dir = DATA / "raw" / args.zip
        raw_dir.mkdir(parents=True, exist_ok=True)
        captured = capture(args.zip, raw_dir, today)

    offers = find_offers(captured)
    if not offers:
        print(f"[{label}] No offer data found; check data/raw/{args.zip}/{today}.txt")
        sys.exit(1)

    rows = []
    for offer in offers:
        for r in offer_rows(offer):
            rows.append({"date": today, "zip": args.zip, "city": args.city, **r})

    dropped = write_rows(sort_rows(rows))
    note = f" (replaced {dropped} rows already saved for {today})" if dropped else ""
    print(f"[{label}] Saved {len(rows)} rows from {len(offers)} offers{note}")


if __name__ == "__main__":
    main()

