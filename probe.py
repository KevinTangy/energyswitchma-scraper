"""
Checks which EnergySwitch compare page (utility) each ZIP should use.

Usage:
    python probe.py                      # every ZIP in candidates.csv
    python probe.py 02148 02138          # just these ZIPs
    python probe.py --pause 10           # seconds between page loads

For each ZIP it loads both compare pages (1 = National Grid, 2 = Eversource),
records what each returns, and picks one with scrape.choose_compare_id(): the
page that names a utility's basic service AND lists competing offers. ZIPs
where neither page has competing offers are reported as such (towns served
by a municipal light plant can't buy from competing suppliers).

Nothing in data/ is changed. Results are printed, written to
probe_results.csv, and (on GitHub Actions) added to the run summary. The
"same_as" column flags ZIPs whose offer list is identical to an earlier
ZIP's, so a town with several ZIPs can be tracked with just one.
"""
import argparse
import csv
import hashlib
import os
import sys
import time
from pathlib import Path

import scrape

COLUMNS = ["zip", "city", "choice", "utility", "competing", "cheapest", "same_as",
           "page1", "page2", "reason"]


def load_candidates(path, only=None):
    with open(path, newline="") as f:
        rows = [(r["zip"].strip(), r["city"].strip()) for r in csv.DictReader(f)]
    if only:
        known = dict(rows)
        rows = [(z, known.get(z, "")) for z in only]
    return rows


def fingerprint(offers):
    """Short hash of the offer list (supplier, price, term), ignoring order."""
    rows = sorted((r["supplier"], r["price_cents_per_kwh"], r["term"])
                  for o in offers for r in scrape.offer_rows(o))
    return hashlib.sha1(repr(rows).encode()).hexdigest()[:10]


def cheapest(offers):
    prices = []
    for o in offers:
        if o.get("isDistributionCompany"):
            continue
        for r in scrape.offer_rows(o):
            try:
                prices.append((float(r["price_cents_per_kwh"]), r["supplier"]))
            except ValueError:
                pass
    return f"{min(prices)[0]:.3f} {min(prices)[1]}" if prices else ""


def describe(s):
    if not s["offers"]:
        return "no offers"
    return f"{s['utility'] or 'no utility'}, {s['regular']} regular + {s['competing'] - s['regular']} town program"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("zips", nargs="*", help="ZIPs to check (default: all in candidates.csv)")
    ap.add_argument("--candidates", default="candidates.csv")
    ap.add_argument("--pause", type=float, default=10, help="seconds between page loads")
    ap.add_argument("--out", default="probe_results.csv")
    args = ap.parse_args()

    results, seen, first = [], {}, True
    for zip_code, city in load_candidates(args.candidates, args.zips):
        summaries, offers_by_id = {}, {}
        for cid in scrape.COMPARE_IDS:
            if not first:
                time.sleep(args.pause)
            first = False
            try:
                captured, _ = scrape.fetch(zip_code, cid)
                offers = scrape.find_offers(captured)
            except Exception as e:  # keep going; one bad page shouldn't stop the run
                print(f"  {zip_code} page {cid}: error {e}", file=sys.stderr)
                offers = []
            offers_by_id[cid] = offers
            summaries[cid] = scrape.summarize(offers)
        choice, reason = scrape.choose_compare_id(summaries)
        row = {"zip": zip_code, "city": city, "choice": choice or "none",
               "page1": describe(summaries["1"]), "page2": describe(summaries["2"]),
               "reason": reason, "utility": "", "competing": "", "cheapest": "", "same_as": ""}
        if choice:
            offers = offers_by_id[choice]
            fp = fingerprint(offers)
            row.update(utility=summaries[choice]["utility"],
                       competing=summaries[choice]["competing"],
                       cheapest=cheapest(offers), same_as=seen.get(fp, ""))
            seen.setdefault(fp, f"{zip_code} {city}")
        results.append(row)
        print(" | ".join(str(row[c]) for c in COLUMNS), flush=True)

    # A ZIP that straddles both utilities gets the page the rest of its town
    # uses, when the town's other ZIPs agree.
    town = lambda c: c.split(" - ")[0]
    for r in results:
        if r["choice"] != "none" or "straddle" not in r["reason"]:
            continue
        others = {o["choice"] for o in results
                  if o is not r and town(o["city"]) == town(r["city"]) and o["choice"] != "none"}
        if len(others) == 1:
            r["choice"] = others.pop()
            r["reason"] += f"; rest of {town(r['city'])} uses page {r['choice']}"

    with open(args.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(results)

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as f:
            f.write("## Utility check\n\n| " + " | ".join(COLUMNS) + " |\n|"
                    + "---|" * len(COLUMNS) + "\n")
            for r in results:
                f.write("| " + " | ".join(str(r[c]) for c in COLUMNS) + " |\n")
    print(f"\nChecked {len(results)} ZIPs; results in {args.out}")


if __name__ == "__main__":
    main()
