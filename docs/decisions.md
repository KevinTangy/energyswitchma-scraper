# Decision log

In the order they were made (Nov 17–18, 2026).

1. **GitHub Actions for scheduling.** It's free, runs in the cloud, and
   doesn't need Kevin's computer to be on. The results are committed back to
   the repo, so the history lives in git.

2. **Playwright headless browser instead of plain HTTP.** The site is a
   single-page app, and fetching the URL returns no data.

3. **Capture the JSON instead of scraping the HTML.** Reading the app's own
   API response holds up better than CSS selectors. The first version guessed
   column meanings with regexes on field names. After Kevin shared a real
   capture, this was replaced with exact field names.

4. **Keep the raw captures every day** (`data/raw/<zip>/<date>.json.gz`). That
   way parsing changes can be re-run on past days with `--from-raw`.

5. **ZIP as a CLI argument** (5 digits, checked) with an optional `--city`
   label. The workflow loops through the six cities one after another in a
   single job, rather than using a matrix, so there are no parallel
   `git push` conflicts. One city failing doesn't stop the others.

6. **One shared CSV** with `zip` and `city` columns, rather than one file per
   city, so it's easy to filter and compare in Excel.

7. **Basic service split into two rows**, at Kevin's request. The source
   joins both price periods with `|`.

8. **Supplier name, not ID**, at Kevin's request. Fixes the early bug that
   used `supplierId`.

9. **Dropped the product, renewable and price_type columns**, at Kevin's
   request.

10. **Numeric price column `price_cents_per_kwh`**, so it can be sorted and
    charted.

11. **Sorting**, at Kevin's request: basic service rows first, then cheapest
    to most expensive, within each date+city batch. The CSV only ever gets
    rows added, so it isn't re-sorted as a whole.

12. **Automatic CSV migration.** If the header changes, the old file moves to
    `data/rates_old_format.csv` so columns never get misaligned.

13. **The README is generated** because GitHub markdown can't read a CSV.
    `make_charts.py` rebuilds the SVG charts and README after every scrape.

14. **Chart design**: one axis (both series are ¢/kWh), basic service as a
    step line, supplier labels only where the cheapest supplier changes, the
    latest values at the end of each line, light and dark variants, and a
    colorblind-safe pair of colors checked with a palette-checking tool.

15. **Municipal aggregation programs kept** in the "cheapest offer" series,
    because they're real options for residents. This hasn't been finally
    decided; see `status.md`.

16. **Cron at an off-the-hour minute** (now 6:11 AM America/New_York via
    the `timezone` key, Nov 19; was 11:11 UTC, and :17 before that), because GitHub delays scheduled jobs set for the
    top of the hour.

17. **Replace, don't append, a day's rows** (Nov 18). A re-run on the same
    date replaces that date+ZIP batch, keeping the latest capture, which
    matches the raw JSON file (also overwritten per day). Older days are
    never touched, so chart history is kept.

18. **Dates in Massachusetts time** (Nov 18). GitHub runners use UTC, which
    labeled evening runs with the next day.

19. **Compress raw captures** (Nov 18). Uncompressed captures were about
    120 KB per city per day, which would push the repo past GitHub's
    recommended 1 GB within a year or two if more cities were added. They're
    now compact gzip files (about 7 KB JSON + 2 KB text). The gzip header has
    no timestamp or filename, so an unchanged capture produces identical
    bytes and git stores no new copy.

20. **15-second pause between cities** (Nov 18). The load was already tiny
    (one page view per city, one at a time), but the pause keeps it gentle
    if more cities are added. It adds about 15 s per city to the run, which
    costs nothing because Actions minutes are free for public repos.

21. **Savings bar chart + grid of small charts instead of one chart per
    city** (Nov 18). One combined chart was ruled out: past about six cities
    the line colors become hard to tell apart (especially for colorblind
    readers), and cities with identical offers (Everett, Revere and Saugus
    today) draw exactly on top of each other. A grid keeps each panel to the
    familiar two lines, and adding a city just adds a panel. The bar chart
    answers "where's the best deal today?" at a glance. The README table now
    shows savings (positive = cheaper than basic) instead of a negative
    difference, to match the bar chart.

22. **One compare page per city, chosen by checking both** (Nov 18). The
    site has a page per utility (1 = National Grid, 2 = Eversource). Rather
    than guess each town's utility, `probe.py` loads both pages and keeps
    the one that names a basic service and lists competing offers; the
    result is saved as `compare_id` in `cities.csv`, so the daily job loads
    only one page per city. City list moved from the workflow heredoc to
    `cities.csv` so it's easy to edit as cities are added.

23. **Municipal light plant towns excluded** (Nov 18): Wakefield, Reading,
    Belmont, Peabody and Lynnfield. State law exempts them from competitive
    supply, so there are no offers to track.

24. **Ignore town electricity programs when picking the page** (Nov 18).
    The first full check flagged 50 of 68 ZIPs as ambiguous because a
    town's program products (e.g. Malden Community Electricity) appear on
    both utilities' pages. Only regular supplier offers now count.

25. **Added the 13 towns that run their own city electricity program**
    (Nov 18): Winthrop and Quincy (National Grid); Chelsea, Boston,
    Somerville, Cambridge, Arlington, Brookline, Stoneham, Winchester,
    Woburn, Burlington and Waltham (Eversource). Their offer lists differ
    from town to town; towns without a program would duplicate existing
    charts. Daily run grows from 6 to 19 cities (about 10 minutes with the
    15-second pause; free on a public repo).

26. **Timezone-aware schedule** (Nov 19). The workflow comments said GitHub
    cron is UTC only; that was outdated. GitHub's docs now support an IANA
    `timezone` next to `cron`, so the job runs at 6:11 AM Eastern all year
    instead of shifting to 7:11 AM during daylight saving time.

27. **Backup run at 12:41 PM Eastern** (Nov 19). GitHub dropped the Nov 19
    morning run, and delayed Nov 18's by 8 hours. A second daily schedule
    costs nothing (public repo) and can't duplicate data because a re-run
    replaces the day's rows. Trade-off: on days both run, the saved rates
    are from early afternoon rather than the morning.

28. **Third series: cheapest offer that isn't the town program** (Nov 19).
    Town programs are often the cheapest, so this shows the best deal from a
    regular supplier for comparison. Program suppliers are recorded in a
    separate `data/town_programs.csv` rather than a new `rates.csv` column,
    because changing that file's columns would trigger the old-format
    migration and move the history aside. Drawn dashed in aqua (third
    palette slot, validated together with blue and orange) and only when it
    differs from the cheapest offer.

29. **Charts start Nov 18** (Nov 20). Nov 17 only has data for the first 6
    cities (the other 13 were added Nov 18), so `CHART_START` in
    `make_charts.py` hides it. The rows stay in `data/rates.csv`.

30. **Runs at 2:05 AM and 11:11 AM Eastern** (Nov 20, Kevin's choice),
    replacing 6:11 AM + 12:41 PM. Both use the `timezone` key; both are off
    the top of the hour. When both run, the 11:11 AM data is what's kept
    for the day.

31. **Actions on Node 24** (Nov 20). GitHub warned that checkout@v4 and
    setup-python@v5 run on deprecated Node 20. Moved to checkout@v7,
    setup-python@v7 and upload-artifact@v7 (all `using: node24` in their
    action.yml). checkout v6+ stores the token in a separate file, but
    `git push` in the commit step still works without changes.

32. **Back to one run a day: 2:05 AM Eastern** (Nov 24, Kevin's choice).
    The 11:11 AM run was removed. Trade-off: no automatic backup if GitHub
    drops the 2:05 AM run; use the manual "Run workflow" button that day.
