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

16. **Cron at an off-the-hour minute** (now 11:11 UTC = 6:11 AM EST, moved
    from :17 on Nov 18), because GitHub delays scheduled jobs set for the
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
