"""
Builds README.md and one line chart per city from data/rates.csv.

For each city and each day it tracks:
  1. the National Grid basic service rate for the period that covers that day
  2. the cheapest supplier offer, labeled with the supplier's name

Charts are written to charts/<city>.svg (light) and charts/<city>-dark.svg
(dark). The README shows whichever matches the reader's GitHub theme.
GitHub Actions runs this after each daily scrape, so README.md is
regenerated every day. Don't edit README.md by hand.

Usage:
    python make_charts.py
"""
import csv
import datetime as dt
import re
from collections import OrderedDict, defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

CSV_PATH = Path("data/rates.csv")
CHART_DIR = Path("charts")
README = Path("README.md")

THEMES = {
    "light": {"surface": "#fcfcfb", "text": "#0b0b0b", "muted": "#52514e",
              "grid": "#e4e3df", "basic": "#2a78d6", "cheap": "#eb6834"},
    "dark": {"surface": "#1a1a19", "text": "#f0efec", "muted": "#c3c2b7",
             "grid": "#33332f", "basic": "#3987e5", "cheap": "#d95926"},
}

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


# ---------- reading the data ----------

def parse_period(term):
    """"Aug '26 through Jan '27" -> (date(2026,8,1), date(2027,1,31)); else None."""
    found = re.findall(r"([A-Za-z]{3})\w*\s*'(\d{2})", term or "")
    if len(found) != 2:
        return None
    (m1, y1), (m2, y2) = found
    if m1.lower() not in MONTHS or m2.lower() not in MONTHS:
        return None
    start = dt.date(2000 + int(y1), MONTHS[m1.lower()], 1)
    end_month, end_year = MONTHS[m2.lower()], 2000 + int(y2)
    nxt = dt.date(end_year + (end_month == 12), end_month % 12 + 1, 1)
    return start, nxt - dt.timedelta(days=1)


def price(row):
    try:
        return float(row["price_cents_per_kwh"])
    except (KeyError, ValueError):
        return None


def load_series():
    """Return {city: [(date, basic_rate, cheapest_rate, cheapest_supplier), ...]}."""
    by_city_day = OrderedDict()
    with CSV_PATH.open(newline="") as f:
        for row in csv.DictReader(f):
            city = row.get("city") or row.get("zip")
            by_city_day.setdefault(city, defaultdict(list))[row["date"]].append(row)

    series = OrderedDict()
    for city, days in by_city_day.items():
        points = []
        for day_str in sorted(days):
            day = dt.date.fromisoformat(day_str)
            rows = [r for r in days[day_str] if price(r) is not None]
            basic = [r for r in rows if r["supplier"].endswith("(Basic Service)")]
            offers = [r for r in rows if not r["supplier"].endswith("(Basic Service)")]

            basic_rate = None
            if basic:
                current = basic[0]
                for r in basic:
                    period = parse_period(r["term"])
                    if period and period[0] <= day <= period[1]:
                        current = r
                        break
                basic_rate = price(current)

            cheap_rate = cheap_supplier = None
            if offers:
                best = min(offers, key=lambda r: (price(r), r["supplier"]))
                cheap_rate, cheap_supplier = price(best), best["supplier"]

            points.append((day, basic_rate, cheap_rate, cheap_supplier))
        series[city] = points
    return series


# ---------- drawing ----------

def slug(city):
    return re.sub(r"[^a-z0-9]+", "-", city.lower()).strip("-")


def draw(city, points, theme_name, path):
    t = THEMES[theme_name]
    fig, ax = plt.subplots(figsize=(9, 4.2), dpi=100)
    fig.patch.set_facecolor(t["surface"])
    ax.set_facecolor(t["surface"])

    days = [p[0] for p in points]
    basic = [p[1] for p in points]
    cheap = [p[2] for p in points]
    suppliers = [p[3] for p in points]
    marker = "o" if len(points) < 40 else None

    ax.plot(days, basic, color=t["basic"], lw=2, marker=marker, ms=6,
            markeredgecolor=t["surface"], markeredgewidth=1.5,
            label="National Grid basic service", drawstyle="steps-post" if len(points) > 1 else "default")
    ax.plot(days, cheap, color=t["cheap"], lw=2, marker=marker, ms=6,
            markeredgecolor=t["surface"], markeredgewidth=1.5, label="Cheapest supplier offer")

    # Label the cheapest line where the cheapest supplier changes. Brief
    # one- or two-day flips and labels too close together are skipped so the
    # chart stays readable; the latest supplier is always labeled.
    runs = []  # (supplier, first index, last index)
    for i, s in enumerate(suppliers):
        if cheap[i] is None:
            continue
        if runs and runs[-1][0] == s:
            runs[-1] = (s, runs[-1][1], i)
        else:
            runs.append((s, i, i))
    min_run = 1 if len(points) < 10 else max(3, len(points) // 20)
    min_gap = max(1, len(points) // 8)
    labeled = []
    for n, (s, first, last) in enumerate(runs):
        is_last_run = n == len(runs) - 1
        long_enough = (last - first + 1) >= min_run
        if not (long_enough or is_last_run):
            continue
        if labeled and labeled[-1][0] == s and not is_last_run:
            continue
        if labeled and first - labeled[-1][1] < min_gap:
            if not is_last_run:
                continue
            labeled.pop()  # make room for the latest supplier
        labeled.append((s, first))
    for s, i in labeled:
        pos = i / max(1, len(points) - 1)
        align = "left" if pos < 0.15 else "right" if pos > 0.85 else "center"
        ax.annotate(s, (days[i], cheap[i]), xytext=(0, -12), textcoords="offset points",
                    ha=align, va="top", fontsize=8.5, color=t["muted"])

    # Latest values at the right end of each line
    for values, color in ((basic, t["basic"]), (cheap, t["cheap"])):
        if values and values[-1] is not None:
            ax.annotate(f"{values[-1]:.2f}¢", (days[-1], values[-1]), xytext=(8, 0),
                        textcoords="offset points", va="center", fontsize=9.5,
                        color=t["text"], fontweight="bold")

    all_vals = [v for v in basic + cheap if v is not None]
    if all_vals:
        lo, hi = min(all_vals), max(all_vals)
        pad = max((hi - lo) * 0.2, 0.75)
        ax.set_ylim(lo - pad * 1.4, hi + pad)  # extra room below for supplier labels

    ax.set_title(city, loc="left", fontsize=14, fontweight="bold", color=t["text"], pad=12)
    ax.set_ylabel("¢ per kWh", color=t["muted"], fontsize=9.5)
    ax.yaxis.set_major_locator(plt.MaxNLocator(nbins=6, steps=[1, 2, 2.5, 5, 10]))
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:g}¢"))
    span = (days[-1] - days[0]).days
    if span <= 14:
        # Daily data: one tick per day, never hour ticks like "12:00".
        ax.xaxis.set_major_locator(mdates.DayLocator(interval=1 if span <= 7 else 2))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %-d"))
    else:
        locator = mdates.AutoDateLocator(minticks=3, maxticks=8)
        locator.intervald[mdates.HOURLY] = [24]  # no sub-day ticks
        ax.xaxis.set_major_locator(locator)
        ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
    if len(days) == 1:
        ax.set_xlim(days[0] - dt.timedelta(days=3), days[0] + dt.timedelta(days=3))
    else:
        # Small margin on the left so the first point isn't clipped; more on
        # the right for the latest-value labels.
        # (Plain date objects drop fractions of a day, so use day numbers.)
        first, last = mdates.date2num(days[0]), mdates.date2num(days[-1])
        ax.set_xlim(first - max(0.15, span * 0.02), last + max(0.35, span * 0.08))

    ax.grid(axis="y", color=t["grid"], lw=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(t["grid"])
    ax.tick_params(colors=t["muted"], labelsize=9, length=0)

    leg = ax.legend(loc="upper left", bbox_to_anchor=(0, 1.0), ncol=2, frameon=False,
                    fontsize=9, labelcolor=t["text"], handlelength=1.6)
    leg.set_zorder(5)

    fig.tight_layout()
    fig.savefig(path, format="svg", facecolor=t["surface"])
    plt.close(fig)


# ---------- README ----------

def fmt(v):
    return f"{v:.3f}¢" if v is not None else "n/a"


def write_readme(series):
    latest = max((p[-1][0] for p in series.values() if p), default=None)
    lines = [
        "# Electricity Rate Tracker",
        "",
        "Daily electricity supply rates from [EnergySwitch MA](https://energyswitchma.gov), "
        "comparing National Grid's basic service rate with the cheapest supplier offer in each city.",
        "",
        f"**Last updated:** {latest.strftime('%B %-d, %Y') if latest else 'n/a'}",
        "",
        "## Today's rates",
        "",
        "| City | Basic service | Cheapest offer | Cheapest supplier | Difference |",
        "|---|---:|---:|---|---:|",
    ]
    for city, points in series.items():
        if not points:
            continue
        _, basic, cheap, supplier = points[-1]
        diff = f"{cheap - basic:+.3f}¢" if basic is not None and cheap is not None else "n/a"
        lines.append(f"| {city} | {fmt(basic)} | {fmt(cheap)} | {supplier or 'n/a'} | {diff} |")

    lines += ["", "Rates are in cents per kWh. A negative difference means the cheapest offer "
              "beats basic service.", "", "## Rate history by city", ""]
    for city in series:
        s = slug(city)
        lines += [
            f"### {city}",
            "",
            "<picture>",
            f'  <source media="(prefers-color-scheme: dark)" srcset="charts/{s}-dark.svg">',
            f'  <img src="charts/{s}.svg" alt="{city}: National Grid basic service rate and '
            f'cheapest supplier rate over time">',
            "</picture>",
            "",
        ]
    lines += [
        "## How this works",
        "",
        "- `scrape.py` collects each city's offers every morning and adds them to `data/rates.csv`.",
        "- `make_charts.py` rebuilds this README and the charts from that file.",
        "- Basic service is the rate for the period that covers each day.",
        "- The cheapest offer leaves out basic service and is labeled whenever the cheapest supplier changes.",
        "",
        "_This file is generated automatically. Edits made by hand will be overwritten._",
        "",
    ]
    README.write_text("\n".join(lines))


def main():
    if not CSV_PATH.exists():
        print(f"{CSV_PATH} not found yet; skipping charts")
        return
    series = load_series()
    CHART_DIR.mkdir(exist_ok=True)
    for city, points in series.items():
        if not points:
            continue
        draw(city, points, "light", CHART_DIR / f"{slug(city)}.svg")
        draw(city, points, "dark", CHART_DIR / f"{slug(city)}-dark.svg")
    write_readme(series)
    print(f"Wrote README.md and charts for {len(series)} cities")


if __name__ == "__main__":
    main()

