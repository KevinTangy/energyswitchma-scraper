"""
Daily scraper for EnergySwitch MA supplier offers.

Usage:
    python scrape.py 02148 --city Malden                    # National Grid page (default)
    python scrape.py 02138 --city Cambridge --compare-id 2  # Eversource page
    python scrape.py 02138 --city Cambridge --compare-id auto
    python scrape.py 02148 --city Malden --from-raw data/raw/02148/2026-11-18.json.gz

Opens the compare page for the given ZIP in headless Chromium, captures the
offer list the site loads from /consumers/compare, and appends one row per
offer to data/rates.csv (shared across all ZIPs, with zip and city columns).
Re-running for a ZIP on the same date replaces that day's rows for the ZIP
instead of adding them again; earlier days are never touched.
The raw capture is kept gzip-compressed in data/raw/<zip>/<date>.json.gz so
history can be re-processed.
--from-raw skips the browser and re-reads a saved capture instead.

The site has one compare page per utility: /compare/1/1/<zip> for National
Grid and /compare/2/1/<zip> for Eversource. --compare-id picks one;
"auto" tries both and keeps the one that lists the utility's basic service
plus competing offers (see choose_compare_id). The daily workflow passes the
ID saved for each city in cities.csv, so it loads only one page per city.
"""
import argparse
import csv
import datetime as dt
import gzip
import json
import re
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

URL_TEMPLATE = "https://energyswitchma.gov/#/compare/{compare_id}/1/{zip}//"
# Compare-page ID -> the utility whose offers that page shows.
COMPARE_IDS = {"1": "National Grid", "2": "Eversource"}
API_MARKER = "/consumers/compare"
DATA = Path("data")
CSV_PATH = DATA / "rates.csv"
CSV_COLUMNS = ["date", "zip", "city", "supplier", "price_cents_per_kwh", "term", "fees"]
# Which suppliers are a town's own electricity program (municipal
# aggregation), per ZIP. Kept beside rates.csv so that file's columns don't
# change; make_charts.py uses it for "cheapest offer that isn't the town
# program".
PROGRAMS_PATH = DATA / "town_programs.csv"
PROGRAMS_COLUMNS = ["zip", "city", "supplier"]
# Dates are recorded in Massachusetts time. GitHub runners use UTC, so an
# evening run would otherwise be labeled with the next day's date.
LOCAL_TZ = ZoneInfo("America/New_York")


def parse_args():
    ap = argparse.ArgumentParser(description="Scrape EnergySwitch MA offers for a ZIP code.")
    ap.add_argument("zip", help="5-digit Massachusetts ZIP code, e.g. 02148")
    ap.add_argument("--city", default="", help="Optional city name to record in the CSV")
    ap.add_argument("--from-raw", type=Path, help="Re-process a saved raw capture (.json.gz or .json) instead of scraping")
    ap.add_argument("--date", help="Date to record (YYYY-MM-DD); defaults to today")
    ap.add_argument("--compare-id", default="1", choices=[*COMPARE_IDS, "auto"],
                    help="Which utility's compare page to load: 1 = National Grid (default), "
                         "2 = Eversource, auto = try both")
    args = ap.parse_args()
    if not re.fullmatch(r"\d{5}", args.zip):
        ap.error(f"ZIP code must be exactly 5 digits, got {args.zip!r}")
    return args


def fetch(zip_code, compare_id):
    """Load one compare page in headless Chromium. Returns (all JSON
    responses, the page's visible text)."""
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
        url = URL_TEMPLATE.format(compare_id=compare_id, zip=zip_code)
        page.goto(url, wait_until="networkidle", timeout=90_000)
        page.wait_for_timeout(8_000)  # let the offer list finish loading
        text = page.inner_text("body")
        browser.close()
    return captured, text


def capture(zip_code, raw_dir, today, compare_id="1"):
    """Fetch the page and save the raw capture for the day."""
    captured, text = fetch(zip_code, compare_id)
    save_capture(raw_dir, today, captured, text)
    return captured


def save_capture(raw_dir, today, captured, text):
    save_gz(raw_dir / f"{today}.txt.gz", text.encode())
    save_raw(raw_dir / f"{today}.json.gz", captured)
    for ext in ("json", "txt"):  # uncompressed files from older versions
        (raw_dir / f"{today}.{ext}").unlink(missing_ok=True)


def summarize(offers):
    """What a compare page returned: the utility named on its basic service
    record, how many competing (non-utility) offers it lists, and how many of
    those are regular supplier offers rather than the town's own electricity
    program (municipal aggregation).

    A town's program products show up on BOTH utilities' pages, so they say
    nothing about which utility serves the town. Only the program's default
    product carries municipalAggregationTown; its other products share the
    supplier name, so every offer under that name counts as the program."""
    utilities = sorted({(o.get("supplierName") or "").strip()
                        for o in offers if o.get("isDistributionCompany")})
    competing = [o for o in offers if not o.get("isDistributionCompany")]
    programs = program_suppliers(offers)
    regular = [o for o in competing if (o.get("supplierName") or "").strip() not in programs]
    return {"utility": " / ".join(utilities), "competing": len(competing),
            "regular": len(regular), "offers": len(offers)}


def program_suppliers(offers):
    """Supplier names that are the town's own electricity program. Only the
    program's default product carries municipalAggregationTown; its other
    products share the supplier name, so the name identifies them all."""
    return {(o.get("supplierName") or "").strip() for o in offers
            if o.get("municipalAggregationTown") and not o.get("isDistributionCompany")}


def update_programs(zip_code, city, names):
    """Add this ZIP's program supplier names to data/town_programs.csv.
    Names are only added, never removed, so older days keep their meaning."""
    rows = []
    if PROGRAMS_PATH.exists():
        with PROGRAMS_PATH.open(newline="") as f:
            rows = list(csv.DictReader(f))
    known = {(r["zip"], r["supplier"]) for r in rows}
    new = [{"zip": zip_code, "city": city, "supplier": n}
           for n in sorted(names) if (zip_code, n) not in known]
    if not new:
        return 0
    DATA.mkdir(parents=True, exist_ok=True)
    with PROGRAMS_PATH.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=PROGRAMS_COLUMNS)
        w.writeheader()
        w.writerows(sorted(rows + new, key=lambda r: (r["zip"], r["supplier"])))
    return len(new)


def choose_compare_id(summaries):
    """Pick the compare page for a ZIP from {compare_id: summarize(...)}.

    A page counts only if it names a utility's basic service AND lists
    regular supplier offers (not just the town's own electricity program,
    which appears on both pages). If exactly one page counts, use it. If both
    do, use the one whose utility matches what that ID stands for; if that
    doesn't settle it (a ZIP that straddles both utilities), return None.
    Returns (compare_id or None, reason)."""
    usable = {cid: s for cid, s in summaries.items()
              if s["utility"] and s.get("regular", s["competing"])}
    if not usable:
        return None, "no competing offers on either page (municipal light plant, or not served)"
    if len(usable) == 1:
        (cid, s), = usable.items()
        return cid, (f"only page {cid} has regular offers ({s['utility']}, "
                     f"{s.get('regular', s['competing'])} regular, {s['competing']} competing)")
    # Both pages have regular offers. The site names a utility on every page
    # ("National Grid" on page 1 even for Eversource towns), so a name match
    # only helps when the two pages name different utilities than expected.
    matching = [cid for cid, s in usable.items() if COMPARE_IDS[cid].lower() in s["utility"].lower()]
    if len(matching) == 1:
        cid = matching[0]
        return cid, f"both pages have offers; page {cid} names {usable[cid]['utility']}"
    return None, "both pages have regular offers (ZIP may straddle both utilities): " + "; ".join(
        f"page {cid} = {s['utility']} ({s.get('regular', s['competing'])} regular)"
        for cid, s in usable.items())


def save_gz(path, data):
    """gzip-compress bytes to path. mtime=0 keeps the bytes identical when the
    content hasn't changed, so git stores no new copy. (The filename is left
    out of the gzip header for the same reason.)"""
    with path.open("wb") as raw, gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0, compresslevel=9) as f:
        f.write(data)


def save_raw(path, captured):
    """Write a capture as compact, gzip-compressed JSON."""
    save_gz(path, json.dumps(captured, separators=(",", ":"), ensure_ascii=False).encode())


def load_raw(path):
    """Read a capture saved as .json.gz (current) or plain .json (older)."""
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as f:
        return json.load(f)


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
        captured = load_raw(args.from_raw)
    else:
        raw_dir = DATA / "raw" / args.zip
        raw_dir.mkdir(parents=True, exist_ok=True)
        if args.compare_id == "auto":
            results, summaries = {}, {}
            for cid in COMPARE_IDS:
                results[cid] = fetch(args.zip, cid)
                summaries[cid] = summarize(find_offers(results[cid][0]))
            cid, reason = choose_compare_id(summaries)
            print(f"[{label}] {reason}")
            if cid is None:
                sys.exit(1)
            save_capture(raw_dir, today, *results[cid])
            captured = results[cid][0]
        else:
            captured = capture(args.zip, raw_dir, today, args.compare_id)

    offers = find_offers(captured)
    if not offers:
        print(f"[{label}] No offer data found; check data/raw/{args.zip}/{today}.txt.gz")
        sys.exit(1)

    rows = []
    for offer in offers:
        for r in offer_rows(offer):
            rows.append({"date": today, "zip": args.zip, "city": args.city, **r})

    dropped = write_rows(sort_rows(rows))
    update_programs(args.zip, args.city, program_suppliers(offers))
    note = f" (replaced {dropped} rows already saved for {today})" if dropped else ""
    print(f"[{label}] Saved {len(rows)} rows from {len(offers)} offers{note}")


if __name__ == "__main__":
    main()

