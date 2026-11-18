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

## Open issue: scheduled run didn't fire

The first scheduled run, on Nov 18, 2026 at 6:17 AM ET, did not trigger. The
cause isn't known yet. Kevin hasn't reported back what the Actions tab shows.
Things to check, in order:

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

- **No de-duplication:** running the workflow twice in one day adds that
  day's rows twice. Possible fix: in `write_rows()`, drop existing rows with
  the same `date` and `zip` before adding.
- The same supplier can show up on several rows (different products). Could
  bring back `supplierProductId` or the renewable % to tell them apart.
- Try calling `/consumers/compare` directly to replace Playwright.
- Possible additions: price alerts (for example, when the cheapest offer
  drops X¢ below basic service), cancellation fee and term filters, a
  comparison chart across cities.
