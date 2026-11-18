"""
Builds README.md and one line chart per city from data/rates.csv.

For each city and each day it tracks:
  1. the utility's basic service rate (National Grid or Eversource) for the
     period that covers that day
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
# Same data -> byte-identical SVGs, so git only records charts that changed:
# no creation timestamp, and fixed (not random) element ids.
matplotlib.rcParams["svg.hashsalt"] = "rate-tracker"
SVG_META = {"Date": None}
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


# {city: utility name}, e.g. "National Grid", taken from the latest basic
# service rows ("National Grid (Basic Service)"). Filled in by load_series().
UTILITY = {}
BASIC_SUFFIX = " (Basic Service)"


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
                UTILITY[city] = basic[0]["supplier"].removesuffix(BASIC_SUFFIX)
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


def style_time_axes(ax, days, t, labelsize=9, show_year=True):
    """Shared x-axis (dates) and frame styling for the line charts."""
    span = (days[-1] - days[0]).days
    if span <= 14:
        # Daily data: one tick per day, never hour ticks like "12:00".
        ax.xaxis.set_major_locator(mdates.DayLocator(interval=1 if span <= 7 else 2))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %-d"))
    else:
        locator = mdates.AutoDateLocator(minticks=3, maxticks=6)
        locator.intervald[mdates.HOURLY] = [24]  # no sub-day ticks
        ax.xaxis.set_major_locator(locator)
        ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator, show_offset=show_year))
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
    ax.tick_params(colors=t["muted"], labelsize=labelsize, length=0)


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
            label=f"{UTILITY.get(city, 'Utility')} basic service", drawstyle="steps-post" if len(points) > 1 else "default")
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
    style_time_axes(ax, days, t)

    leg = ax.legend(loc="upper left", bbox_to_anchor=(0, 1.0), ncol=2, frameon=False,
                    fontsize=9, labelcolor=t["text"], handlelength=1.6)
    leg.set_zorder(5)

    fig.tight_layout()
    fig.savefig(path, format="svg", facecolor=t["surface"], metadata=SVG_META)
    plt.close(fig)


def latest_savings(series):
    """[(city, savings, cheapest_supplier), ...] for each city's latest day,
    biggest savings first. Savings = basic service minus cheapest offer, so a
    positive number means the cheapest offer beats basic service."""
    rows = []
    for city, points in series.items():
        if not points:
            continue
        _, basic, cheap, supplier = points[-1]
        if basic is not None and cheap is not None:
            rows.append((city, basic - cheap, supplier))
    return sorted(rows, key=lambda r: (-r[1], r[0]))


def city_order(series):
    """Cities with the biggest savings first (same order as the bar chart);
    cities missing a basic or cheapest rate go last."""
    ranked = [c for c, _, _ in latest_savings(series)]
    return ranked + sorted(c for c in series if c not in ranked and series[c])


def bar(ax, y, length, height, color, radius_pts=4):
    """Horizontal bar from 0 with a rounded data end and a square baseline."""
    from matplotlib.patches import FancyBboxPatch, Rectangle
    if length == 0:
        return
    fig = ax.figure
    # Convert the corner radius from points to data units along x.
    x_per_pt = (ax.get_xlim()[1] - ax.get_xlim()[0]) / (
        ax.get_window_extent().width * 72 / fig.dpi)
    y_per_pt = (ax.get_ylim()[0] - ax.get_ylim()[1]) / (
        ax.get_window_extent().height * 72 / fig.dpi)
    r = min(abs(length), radius_pts * x_per_pt)
    left = min(0, length)
    ax.add_patch(FancyBboxPatch(
        (left, y - height / 2), abs(length), height, color=color, lw=0,
        boxstyle="round,pad=0,rounding_size=%f" % r,
        mutation_aspect=abs(y_per_pt / x_per_pt) if x_per_pt else 1))
    # Square off the baseline end.
    base = 0 if length > 0 else -r
    ax.add_patch(Rectangle((base, y - height / 2), r, height, color=color, lw=0))


def draw_savings(series, theme_name, path):
    """Horizontal bars: how much cheaper each city's cheapest offer is than
    basic service today, biggest first."""
    t = THEMES[theme_name]
    rows = latest_savings(series)
    if not rows:
        return False
    n = len(rows)
    row_h = 0.42  # inches per city
    fig, ax = plt.subplots(figsize=(9, 1.25 + row_h * n), dpi=100)
    fig.patch.set_facecolor(t["surface"])
    ax.set_facecolor(t["surface"])

    rows = [(c, v, s if len(s or "") <= 50 else s[:48].rstrip() + "…") for c, v, s in rows]
    vals = [v for _, v, _ in rows]
    lo, hi = min(0, min(vals)), max(0, max(vals))
    ax.set_xlim(lo, hi or 1)  # provisional, for layout
    ax.set_ylim(n - 0.4, -0.6)
    ax.set_yticks(range(n))
    ax.set_yticklabels([c for c, _, _ in rows], fontsize=10, color=t["text"])
    ax.tick_params(length=0, pad=8)
    # Lay out before drawing bars: bar() converts its corner radius using the
    # final axes size.
    fig.tight_layout(rect=(0, 0, 1, 1 - 0.62 / fig.get_figheight()))
    # Leave room past the longest bar for its value + supplier label
    # (value ~44pt, then ~5.2pt per character of supplier name).
    axes_pts = ax.get_window_extent().width * 72 / fig.dpi
    label_pts = 56 + 5.2 * max(len(s or "") for _, _, s in rows)
    bar_frac = max(0.25, 1 - label_pts / axes_pts)  # share of width for bars
    span = (hi - lo) or 1
    ax.set_xlim(lo, lo + span / bar_frac)

    bar_h = min(0.6, (24 / 72) / row_h)  # <= 24px thick
    for i, (city, v, supplier) in enumerate(rows):
        bar(ax, i, v, bar_h, t["cheap"] if v >= 0 else t["muted"])
        x = max(v, 0)
        ax.annotate(f"{v:.2f}¢", (x, i), xytext=(6, 0), textcoords="offset points",
                    va="center", fontsize=10, color=t["text"], fontweight="bold")
        ax.annotate(supplier, (x, i), xytext=(50, 0), textcoords="offset points",
                    va="center", fontsize=9, color=t["muted"])

    ax.axvline(0, color=t["grid"], lw=1)
    ax.set_xticks([])
    for side in ("top", "right", "bottom", "left"):
        ax.spines[side].set_visible(False)
    fig.suptitle("How much less the cheapest offer costs than basic service",
                 x=0.012, ha="left", y=0.985, fontsize=13, fontweight="bold", color=t["text"])
    fig.text(0.012, 0.985 - 0.32 / fig.get_figheight(),
             "Cents per kWh, today. Gray bars would mean basic service is cheaper.",
             ha="left", va="top", fontsize=9, color=t["muted"])
    fig.savefig(path, format="svg", facecolor=t["surface"], metadata=SVG_META)
    plt.close(fig)
    return True


def draw_grid(series, theme_name, path):
    """Small multiples: one panel per city with the same two lines as the
    single-city charts, all on the same scale, biggest savings first."""
    t = THEMES[theme_name]
    cities = city_order(series)
    n = len(cities)
    ncols = 1 if n == 1 else 2 if n <= 4 else 3 if n <= 12 else 4
    nrows = -(-n // ncols)
    fig, axes = plt.subplots(nrows, ncols, figsize=(3.3 * ncols, 2.35 * nrows + 0.75),
                             dpi=100, sharex=True, sharey=True, squeeze=False)
    fig.patch.set_facecolor(t["surface"])

    all_days = [p[0] for c in cities for p in series[c]]
    all_vals = [v for c in cities for p in series[c] for v in (p[1], p[2]) if v is not None]
    days_range = sorted(set(all_days))
    lo, hi = min(all_vals), max(all_vals)
    pad = max((hi - lo) * 0.15, 0.5)

    for idx, ax in enumerate(axes.flat):
        ax.set_facecolor(t["surface"])
        if idx >= n:
            ax.set_visible(False)
            continue
        city = cities[idx]
        points = series[city]
        days = [p[0] for p in points]
        basic = [p[1] for p in points]
        cheap = [p[2] for p in points]
        marker = "o" if len(days_range) < 40 else None
        common = dict(lw=2, marker=marker, ms=4.5, markeredgecolor=t["surface"],
                      markeredgewidth=1.2, solid_capstyle="round", solid_joinstyle="round")
        ax.plot(days, basic, color=t["basic"], drawstyle="steps-post" if len(days) > 1 else "default",
                label="Utility basic service", **common)
        ax.plot(days, cheap, color=t["cheap"], label="Cheapest supplier offer", **common)
        # Latest values at the line ends, pushed apart when the lines are close.
        ends = [v[-1] for v in (basic, cheap)]
        nudge = [0, 0]
        if None not in ends:
            panel_pts = 1.55 * 72  # approximate plot height of one panel
            gap_pts = abs(ends[0] - ends[1]) / ((hi + pad) - (lo - pad)) * panel_pts
            if gap_pts < 10:
                push = (10 - gap_pts) / 2
                upper = 0 if ends[0] >= ends[1] else 1
                nudge[upper], nudge[1 - upper] = push, -push
        for v, dy in zip(ends, nudge):
            if v is not None:
                ax.annotate(f"{v:.2f}¢", (days[-1], v), xytext=(5, dy),
                            textcoords="offset points", va="center", fontsize=8,
                            color=t["text"], fontweight="bold")
        ax.set_title(city, loc="left", fontsize=11, fontweight="bold", color=t["text"], pad=16)
        supplier = points[-1][3] or ""
        limit = 38 - len(UTILITY.get(city, "")) - 3 if UTILITY.get(city) else 38
        if len(supplier) > limit:
            supplier = supplier[:limit - 2].rstrip() + "…"
        utility = UTILITY.get(city, "")
        ax.text(0, 1.02, f"{utility} · Cheapest: {supplier}" if utility else f"Cheapest: {supplier}",
                transform=ax.transAxes, fontsize=7.5,
                color=t["muted"], va="bottom")
        style_time_axes(ax, days_range, t, labelsize=8, show_year=False)

    ax0 = axes.flat[0]
    ax0.set_ylim(lo - pad, hi + pad)
    ax0.yaxis.set_major_locator(plt.MaxNLocator(nbins=4, steps=[1, 2, 2.5, 5, 10]))
    ax0.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:g}¢"))
    # With sharex, hidden empty panels would hide the date labels above them.
    for ax in axes.flat:
        if ax.get_visible():
            ax.xaxis.set_tick_params(labelbottom=True)

    handles, labels = ax0.get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper left", bbox_to_anchor=(0.008, 1.0), ncol=2,
               frameon=False, fontsize=9.5, labelcolor=t["text"], handlelength=1.6)
    fig.tight_layout(rect=(0, 0, 1, 1 - 0.5 / fig.get_figheight()), h_pad=1.6, w_pad=1.2)
    fig.savefig(path, format="svg", facecolor=t["surface"], metadata=SVG_META)
    plt.close(fig)


# ---------- README ----------

def fmt(v):
    return f"{v:.3f}¢" if v is not None else "n/a"


def picture(name, alt):
    """README <picture> that follows the reader's light/dark GitHub theme."""
    return "\n".join([
        "<picture>",
        f'  <source media="(prefers-color-scheme: dark)" srcset="charts/{name}-dark.svg">',
        f'  <img src="charts/{name}.svg" alt="{alt}">',
        "</picture>",
    ])


def write_readme(series):
    latest = max((p[-1][0] for p in series.values() if p), default=None)
    lines = [
        "# Electricity Rate Tracker",
        "",
        "Daily electricity supply rates from [EnergySwitch MA](https://energyswitchma.gov), "
        "comparing each city's utility basic service rate (National Grid or Eversource) "
        "with the cheapest supplier offer.",
        "",
        f"**Last updated:** {latest.strftime('%B %-d, %Y') if latest else 'n/a'}",
        "",
        "## Today's savings",
        "",
        picture("savings", "Bar chart: how many cents per kWh less the cheapest supplier offer "
                "costs than the utility's basic service in each city today"),
        "",
        "| City | Utility | Basic service | Cheapest offer | Cheapest supplier | Savings |",
        "|---|---|---:|---:|---|---:|",
    ]
    for city in city_order(series):
        _, basic, cheap, supplier = series[city][-1]
        saving = f"{basic - cheap:.3f}¢" if basic is not None and cheap is not None else "n/a"
        lines.append(f"| {city} | {UTILITY.get(city, 'n/a')} | {fmt(basic)} | {fmt(cheap)} | {supplier or 'n/a'} | {saving} |")

    lines += [
        "",
        "Rates are in cents per kWh. Savings is basic service minus the cheapest offer; "
        "a negative number would mean basic service is cheaper.",
        "",
        "## Rate history",
        "",
        picture("all-cities", "Small charts, one per city, of the utility basic service "
                "rate and the cheapest supplier rate over time"),
        "",
        "Larger chart for one city: " + " · ".join(
            f"[{c}](charts/{slug(c)}.svg)" for c in city_order(series)),
        "",
    ]
    lines += [
        "## How this works",
        "",
        "- `scrape.py` collects each city's offers every morning and adds them to `data/rates.csv`.",
        "- `make_charts.py` rebuilds this README and the charts from that file.",
        "- Basic service is the rate for the period that covers each day.",
        "- The cheapest offer leaves out basic service. Cities are ordered by today's savings.",
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
    for theme, suffix in (("light", ""), ("dark", "-dark")):
        draw_grid(series, theme, CHART_DIR / f"all-cities{suffix}.svg")
        draw_savings(series, theme, CHART_DIR / f"savings{suffix}.svg")
    write_readme(series)
    print(f"Wrote README.md and charts for {len(series)} cities")


if __name__ == "__main__":
    main()

