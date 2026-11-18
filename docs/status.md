# Status and next steps

_As of Nov 18, 2026._

## Done

- `scrape.py`: takes a ZIP, captures with Playwright, parses exact fields,
  splits basic service, sorts, migrates old CSVs, and supports `--from-raw`
  and `--date`.
- `make_charts.py`: per-city light and dark SVG charts and a generated
  README.
- `.github/workflows/scrape.yml`: daily cron plus manual dispatch, a 6-city
  loop, charts, a commit, and a failure report.
- Checked offline: parsing against the real Malden capture (42 offers to 43
  rows, sort order confirmed), charts against made-up data covering several
  months, the CSV migration, the missing-CSV case, and the YAML and city
  loop.

## Open issue: scheduled run fired late

The first scheduled run, set for Nov 18, 2026 at 6:17 AM EST (11:17 UTC),
didn't start until 2:24 PM EST (19:24 UTC), about 8 hours late. It succeeded.
The schedule was then moved to 6:11 AM EST (`11 11 * * *`). Watch whether
the next runs start near that time. GitHub only promises "best effort" for
scheduled runs, and new schedules are often delayed at first. If runs keep
coming in hours late, these are the things to check:

1. Whether a "Scheduled" run happened late. GitHub can delay scheduled runs,
   or occasionally drop them.
2. The workflow file is at exactly `.github/workflows/scrape.yml` (with the
   leading dot) on the **default branch**. Files uploaded through the web
   page often end up in the wrong place.
3. Settings → Actions → General allows actions.
4. In a private repo, there are reports of `schedule` not triggering even
   though `workflow_dispatch` works. If so, contact GitHub Support.
5. Brand-new schedules sometimes take a day before they start.

Fallback if scheduling stays unreliable: start the workflow from an outside
scheduler (cron-job.org, a local cron job, etc.) through the
`workflow_dispatch` API:
`POST /repos/{owner}/{repo}/actions/workflows/scrape.yml/dispatches` with
`{"ref":"main"}`.

## Not yet confirmed

- Whether a manual run worked from start to finish on GitHub, including
  Playwright on the runner, the commit and the push.
- Whether Medford, Melrose, Everett, Revere and Saugus return offers with the
  `/compare/1/1/` URL. Malden is the only city confirmed.

## Questions for Kevin

- Filter out offers with `isManualRemoval: true`? (One in Malden: Clearview,
  18.49¢.)
- Leave city-run programs (Malden Community Electricity, etc.) out of the
  "cheapest offer" series?
- Medford also has ZIP 02153 (PO boxes); only 02155 is tracked.

## Known limitations and ideas

- **Duplicates fixed (Nov 18):** running twice in one day used to add that
  day's rows again. `write_rows()` now replaces the rows for the same date
  and ZIP. The duplicate rows from Nov 18 were cleaned up.
- **Dates fixed (Nov 18):** dates were taken from the runner's UTC clock, so
  the manual runs on the evening of Nov 17 (EST) were saved as Nov 18. Dates
  are now in America/New_York. Nov 17 was rebuilt from that evening's raw
  capture (saved as `data/raw/<zip>/2026-11-17.json`), so the charts start
  on Nov 17.
- The same supplier can show up on several rows (different products). Could
  bring back `supplierProductId` or the renewable % to tell them apart.
- Try calling `/consumers/compare` directly to replace Playwright.
- Possible additions: price alerts (for example, when the cheapest offer
  drops X¢ below basic service), cancellation fee and term filters, a
  comparison chart across cities.
